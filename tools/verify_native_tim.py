#!/usr/bin/env python3
"""Cross-check the native C TIM decoder against tools/tim_assets.py.

The input directory is expected to contain TIM files extracted from an
authorized source image. Only names, hashes, metadata and validation counts are
written to the report; source media and decoded pixels are never serialized.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from tim_assets import TimFormatError, decode_tim


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


def _tim_paths(root: Path) -> list[Path]:
    return sorted(
        (p for p in root.rglob("*") if p.is_file() and p.name.upper().split(";", 1)[0].endswith(".TIM")),
        key=lambda p: p.as_posix().upper(),
    )


def _load_native_library(repo_root: Path, temp_dir: Path) -> ctypes.CDLL:
    source = repo_root / "app/src/main/cpp/game/tim_image.c"
    include_dir = source.parent
    output = Path(temp_dir) / "libtim_image_verify.so"
    compiler = subprocess.run(
        [
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
            "-Wsign-conversion", "-fPIC", "-shared", "-I", str(include_dir),
            str(source), "-o", str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if compiler.returncode != 0:
        raise RuntimeError(f"native TIM decoder compilation failed:\n{compiler.stdout}{compiler.stderr}")
    library = ctypes.CDLL(str(output))
    library.tim_image_decode_rgba.argtypes = [
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.POINTER(NativeTimImage),
        ctypes.POINTER(ctypes.c_char), ctypes.c_size_t,
    ]
    library.tim_image_decode_rgba.restype = ctypes.c_int
    library.tim_image_free.argtypes = [ctypes.POINTER(NativeTimImage)]
    library.tim_image_free.restype = None
    return library


def _native_decode(library: ctypes.CDLL, data: bytes) -> dict[str, Any]:
    input_buffer = ctypes.create_string_buffer(data)
    out = NativeTimImage()
    error = ctypes.create_string_buffer(256)
    result = library.tim_image_decode_rgba(
        ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_uint8)),
        len(data), ctypes.byref(out), error, len(error),
    )
    if result != 0:
        raise TimFormatError(error.value.decode("utf-8", errors="replace") or "native decoder failed")
    try:
        return {
            "image_x": int(out.image_x),
            "image_y": int(out.image_y),
            "width": int(out.width),
            "height": int(out.height),
            "pixel_mode": int(out.pixel_mode),
            "has_clut": bool(out.has_clut),
            "clut_x": int(out.clut_x),
            "clut_y": int(out.clut_y),
            "clut_width": int(out.clut_width),
            "clut_height": int(out.clut_height),
            "clut_entries": int(out.clut_entries),
            "rgba": ctypes.string_at(out.rgba, out.rgba_size),
        }
    finally:
        library.tim_image_free(ctypes.byref(out))


def verify_assets(asset_root: Path, repo_root: Path) -> dict[str, Any]:
    paths = _tim_paths(asset_root)
    if not paths:
        raise ValueError(f"no TIM files found below {asset_root}")

    rows: list[dict[str, Any]] = []
    mode_counts: dict[str, int] = {}
    length_style_counts: dict[str, int] = {}
    total_pixels = 0
    total_rgba_bytes = 0
    mismatches = 0
    with tempfile.TemporaryDirectory(prefix="1945-tim-verify-") as temp_dir:
        library = _load_native_library(repo_root, temp_dir)
        for path in paths:
            raw = path.read_bytes()
            py = decode_tim(raw)
            native = _native_decode(library, raw)
            metadata_fields = (
                "image_x", "image_y", "width", "height", "pixel_mode", "has_clut",
                "clut_x", "clut_y", "clut_width", "clut_height",
            )
            metadata_match = all(getattr(py, k) == native[k] for k in metadata_fields)
            rgba_match = py.rgba == native["rgba"]
            matched = metadata_match and rgba_match
            mismatches += 0 if matched else 1
            pixels = py.width * py.height
            total_pixels += pixels
            total_rgba_bytes += len(py.rgba)
            mode_key = str(py.pixel_mode)
            mode_counts[mode_key] = mode_counts.get(mode_key, 0) + 1
            style_key = py.image_block_length_style
            length_style_counts[style_key] = length_style_counts.get(style_key, 0) + 1
            try:
                relative_path = path.relative_to(asset_root).as_posix()
            except ValueError:
                relative_path = path.name
            rows.append({
                "path": relative_path,
                "source_size_bytes": len(raw),
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "pixel_mode": py.pixel_mode,
                "width": py.width,
                "height": py.height,
                "pixel_count": pixels,
                "clut_width": py.clut_width,
                "clut_height": py.clut_height,
                "image_block_length_style": style_key,
                "rgba_sha256": hashlib.sha256(py.rgba).hexdigest(),
                "native_metadata_match": metadata_match,
                "native_rgba_match": rgba_match,
            })

    return {
        "schema_version": 1,
        "validator": "tools/verify_native_tim.py",
        "source_media_bytes_included": False,
        "asset_root": "external extraction directory (not included in repository)",
        "files_found": len(paths),
        "files_decoded": len(rows),
        "metadata_or_rgba_mismatches": mismatches,
        "pixel_count_total": total_pixels,
        "rgba_bytes_total": total_rgba_bytes,
        "mode_counts": mode_counts,
        "image_block_length_style_counts": length_style_counts,
        "files": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_root", type=Path, help="directory containing extracted TIM files")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="optional JSON evidence output path")
    args = parser.parse_args()
    report = verify_assets(args.asset_root.resolve(), args.repo_root.resolve())
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, indent=2, sort_keys=True))
    if report["metadata_or_rgba_mismatches"] != 0:
        print("TIM decoder cross-validation failed")
        return 1
    print("TIM decoder cross-validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
