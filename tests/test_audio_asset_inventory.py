from __future__ import annotations

import importlib.util
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("audio_asset_inventory_under_test", ROOT / "tools/audio_asset_inventory.py")
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
AudioFormatError = _MODULE.AudioFormatError
parse_chunk_chain = _MODULE.parse_chunk_chain
parse_sq = _MODULE.parse_sq
scan_disc_root = _MODULE.scan_disc_root


def chunk(name: str, size: int, value: int = 0, body: bytes = b"") -> bytes:
    assert len(body) == size - 16
    return struct.pack("<4s4sII", b"IECS", name.encode("ascii")[::-1], size, value) + body


def sample_sq(*, song: bool) -> bytes:
    midi_body = b"\x14\x00\x00\x00" + b"\x00" * 12
    midi_size = 16 + len(midi_body)
    midi = chunk("Midi", midi_size, 0, midi_body)
    chunks = (
        chunk("Vers", 16, 0x20000)
        + chunk("Sequ", 32, 48 + midi_size + (32 if song else 0), b"\x00" * 16)
        + midi
    )
    if song:
        chunks += chunk("Song", 32, 0, b"\x00" * 16)
    return chunks


def test_sq_accepts_observed_snd1_three_chunk_variant() -> None:
    parsed = parse_sq(sample_sq(song=False))
    assert parsed["chunk_names"] == ["Vers", "Sequ", "Midi"]
    assert parsed["trailing_song_chunk"] is False


def test_sq_accepts_observed_snd2_terminal_song_chunk() -> None:
    parsed = parse_sq(sample_sq(song=True))
    assert parsed["chunk_names"] == ["Vers", "Sequ", "Midi", "Song"]
    assert parsed["trailing_song_chunk"] is True


def test_sq_rejects_out_of_bounds_midi_chunk() -> None:
    good = bytearray(sample_sq(song=False))
    struct.pack_into("<I", good, 0x38, len(good) + 8)
    with pytest.raises(AudioFormatError, match="outside file"):
        parse_sq(bytes(good))


def test_chunk_chain_requires_exact_contiguous_chunks() -> None:
    good = chunk("Vers", 16, 0x20000) + chunk("Test", 16)
    assert [x["name"] for x in parse_chunk_chain(good)] == ["Vers", "Test"]
    with pytest.raises(AudioFormatError, match="outside file"):
        parse_chunk_chain(struct.pack("<4s4sII", b"IECS", b"sreV", 32, 0))


def test_full_disc_audio_inventory(tmp_path: Path) -> None:
    sq_dir = tmp_path / "SND2"
    sq_dir.mkdir()
    (sq_dir / "A.SQ;1").write_bytes(sample_sq(song=True))
    (sq_dir / "B.SQ;1").write_bytes(sample_sq(song=False))
    report = scan_disc_root(tmp_path)
    assert report["file_count"] == 2
    assert report["counts_by_kind"] == {"SQ": 2}
    assert report["sq_terminal_song_chunk_count"] == 1
    assert report["source_audio_bytes_exported"] is False


def test_hd_chunk_chain_rejects_unexpected_order() -> None:
    data = chunk("Vers", 16, 0x20000) + chunk("Bogus", 16)
    with pytest.raises(AudioFormatError, match="unexpected chunk chain"):
        parse_chunk_chain(data, expected=("Vers", "Head"))
