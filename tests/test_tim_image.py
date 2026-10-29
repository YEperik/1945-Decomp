from __future__ import annotations

import ctypes
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO_ROOT / "tools"))
from tim_assets import TimFormatError, decode_tim  # noqa: E402


class NativeTimImage(ctypes.Structure):
    _fields_ = [
        ("image_x", ctypes.c_uint32),
        ("image_y", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("pixel_mode", ctypes.c_uint32),
        ("has_clut", ctypes.c_uint8),
        ("clut_x", ctypes.c_uint32),
        ("clut_y", ctypes.c_uint32),
        ("clut_width", ctypes.c_uint32),
        ("clut_height", ctypes.c_uint32),
        ("clut_entries", ctypes.c_size_t),
        ("clut_words", ctypes.POINTER(ctypes.c_uint16)),
        ("rgba", ctypes.POINTER(ctypes.c_uint8)),
        ("rgba_size", ctypes.c_size_t),
    ]


@pytest.fixture(scope="session")
def native_tim():
    with tempfile.TemporaryDirectory(prefix="1945-tim-tests-") as temp_dir:
        output = Path(temp_dir) / "libtim_image.so"
        source = REPO_ROOT / "app/src/main/cpp/game/tim_image.c"
        proc = subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wsign-conversion",
             "-fPIC", "-shared", "-I", str(source.parent), str(source), "-o", str(output)],
            capture_output=True, text=True, check=False,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        lib = ctypes.CDLL(str(output))
        lib.tim_image_decode_rgba.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.POINTER(NativeTimImage),
            ctypes.POINTER(ctypes.c_char), ctypes.c_size_t,
        ]
        lib.tim_image_decode_rgba.restype = ctypes.c_int
        lib.tim_image_free.argtypes = [ctypes.POINTER(NativeTimImage)]
        lib.tim_image_free.restype = None
        yield lib


def _block(payload: bytes, *, payload_only_length: bool = False, x: int = 0, y: int = 0, width_words: int, height: int) -> bytes:
    declared = len(payload) if payload_only_length else 12 + len(payload)
    return struct.pack("<IHHHH", declared, x, y, width_words, height) + payload


def _make_tim(mode: int, width_words: int, height: int, payload: bytes, clut: tuple[int, int, list[int]] | None = None, *, payload_only_image_length: bool = False) -> bytes:
    flags = mode | (0x08 if clut is not None else 0)
    out = bytearray(struct.pack("<II", 0x10, flags))
    if clut is not None:
        clut_width, clut_height, words = clut
        pal_payload = struct.pack(f"<{len(words)}H", *words)
        out.extend(_block(pal_payload, width_words=clut_width, height=clut_height))
    out.extend(_block(payload, payload_only_length=payload_only_image_length, width_words=width_words, height=height))
    return bytes(out)


def _native_decode(lib, data: bytes):
    input_buffer = ctypes.create_string_buffer(data)
    result = NativeTimImage()
    error = ctypes.create_string_buffer(256)
    status = lib.tim_image_decode_rgba(
        ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_uint8)), len(data),
        ctypes.byref(result), error, len(error),
    )
    if status != 0:
        raise TimFormatError(error.value.decode("utf-8", errors="replace"))
    try:
        return {
            "width": int(result.width),
            "height": int(result.height),
            "pixel_mode": int(result.pixel_mode),
            "has_clut": bool(result.has_clut),
            "clut_width": int(result.clut_width),
            "clut_height": int(result.clut_height),
            "rgba": ctypes.string_at(result.rgba, result.rgba_size),
        }
    finally:
        lib.tim_image_free(ctypes.byref(result))


def _triple(rgba: bytes, index: int) -> tuple[int, int, int, int]:
    return tuple(rgba[index * 4:index * 4 + 4])


def test_4bpp_low_nibble_first_and_transparency(native_tim):
    palette = [0] * 16
    palette[1] = 0x001F  # red
    palette[2] = 0x03E0  # green
    palette[3] = 0x7C00  # blue
    palette[4] = 0x801F  # semitransparent red (STP)
    tim = _make_tim(0, 1, 1, bytes([0x21, 0x43]), (16, 1, palette))
    py = decode_tim(tim)
    native = _native_decode(native_tim, tim)
    assert py.rgba == native["rgba"]
    assert (py.width, py.height) == (4, 1)
    assert [_triple(py.rgba, i) for i in range(4)] == [
        (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 0, 0, 128)
    ]


def test_8bpp_uses_first_clut_row(native_tim):
    palette = [0] * 256
    palette[1] = 0x03E0
    palette[2] = 0x801F
    palette[255] = 0x7C00
    tim = _make_tim(1, 2, 1, bytes([1, 255, 2, 0]), (256, 1, palette))
    py = decode_tim(tim)
    native = _native_decode(native_tim, tim)
    assert py.rgba == native["rgba"]
    assert (py.width, py.height) == (4, 1)
    assert [_triple(py.rgba, i) for i in range(4)] == [
        (0, 255, 0, 255), (0, 0, 255, 255), (255, 0, 0, 128), (0, 0, 0, 0)
    ]


def test_16bpp_direct_color(native_tim):
    pixels = struct.pack("<HHH", 0x001F, 0x03E0, 0x0000)
    tim = _make_tim(2, 3, 1, pixels)
    py = decode_tim(tim)
    native = _native_decode(native_tim, tim)
    assert py.rgba == native["rgba"]
    assert [_triple(py.rgba, i) for i in range(3)] == [
        (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 0, 0)
    ]


def test_24bpp_direct_rgb(native_tim):
    tim = _make_tim(3, 3, 1, bytes([255, 0, 0, 0, 255, 0]))
    py = decode_tim(tim)
    native = _native_decode(native_tim, tim)
    assert py.rgba == native["rgba"]
    assert (py.width, py.height) == (2, 1)
    assert [_triple(py.rgba, i) for i in range(2)] == [(255, 0, 0, 255), (0, 255, 0, 255)]


def test_observed_payload_only_image_length_is_accepted(native_tim):
    palette = [0] * 16
    palette[1] = 0x001F
    tim = _make_tim(0, 1, 1, bytes([0x01, 0x00]), (16, 1, palette), payload_only_image_length=True)
    parsed = decode_tim(tim)
    native = _native_decode(native_tim, tim)
    assert parsed.image_block_length_style == "payload-only"
    assert parsed.rgba == native["rgba"]
    assert _triple(parsed.rgba, 0) == (255, 0, 0, 255)


@pytest.mark.parametrize("malformed", [
    b"", b"\x00\x00\x00\x00\x00\x00\x00\x00", struct.pack("<II", 0x10, 7),
    struct.pack("<II", 0x10, 0x10),
])
def test_rejects_invalid_or_unsupported_header(native_tim, malformed):
    with pytest.raises(TimFormatError):
        decode_tim(malformed)
    with pytest.raises(TimFormatError):
        _native_decode(native_tim, malformed)


def test_rejects_truncated_payload(native_tim):
    tim = _make_tim(2, 2, 1, b"\x1f\x00")
    with pytest.raises(TimFormatError):
        decode_tim(tim)
    with pytest.raises(TimFormatError):
        _native_decode(native_tim, tim)


def test_rejects_indexed_image_without_full_palette(native_tim):
    tim = _make_tim(1, 1, 1, b"\x00\x00", (16, 1, [0] * 16))
    with pytest.raises(TimFormatError):
        decode_tim(tim)
    with pytest.raises(TimFormatError):
        _native_decode(native_tim, tim)


def test_malformed_input_sweep_under_address_and_undefined_sanitizers(tmp_path: Path):
    compiler = shutil.which("clang")
    if compiler is None:
        pytest.skip("Clang is required for the native TIM sanitizer sweep")
    source = REPO_ROOT / "app/src/main/cpp/game/tim_image.c"
    harness = REPO_ROOT / "tests/native_tim_fuzz.c"
    executable = tmp_path / "native_tim_fuzz"
    compile_result = subprocess.run(
        [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
         "-Wsign-conversion", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
         "-g", "-I", str(source.parent), str(harness), str(source), "-o", str(executable)],
        capture_output=True, text=True, check=False,
    )
    assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr
    run_result = subprocess.run([str(executable)], capture_output=True, text=True, check=False)
    assert run_result.returncode == 0, run_result.stdout + run_result.stderr
