#!/usr/bin/env python3
"""Inventory PS2 title audio containers without extracting or decoding audio.

The report intentionally contains only hashes, chunk metadata and bounded
structure observations. Original samples and sequence bytes remain external.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any

CHUNK_HEADER = struct.Struct("<4s4sII")
CONTAINER_MAGIC = b"IECS"  # little-endian bytes for the SCEI word


class AudioFormatError(ValueError):
    """Raised when a recognized audio container has unsafe/inconsistent bounds."""


def _header(data: bytes, offset: int) -> tuple[str, int, int]:
    if offset < 0 or offset > len(data) - CHUNK_HEADER.size:
        raise AudioFormatError(f"chunk header outside file at 0x{offset:X}")
    magic, raw_name, size, value = CHUNK_HEADER.unpack_from(data, offset)
    if magic != CONTAINER_MAGIC:
        raise AudioFormatError(f"bad SCEI chunk signature at 0x{offset:X}")
    try:
        name = raw_name[::-1].decode("ascii")
    except UnicodeDecodeError as exc:
        raise AudioFormatError(f"non-ASCII chunk tag at 0x{offset + 4:X}") from exc
    if size < CHUNK_HEADER.size:
        raise AudioFormatError(f"chunk {name!r} size {size} is smaller than its header")
    end = offset + size
    if end > len(data):
        raise AudioFormatError(f"chunk {name!r} ends outside file: 0x{end:X} > 0x{len(data):X}")
    return name, size, value


def parse_chunk_chain(data: bytes, *, expected: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """Parse a contiguous SCEI chunk chain until EOF; chunk sizes include headers."""
    chunks: list[dict[str, Any]] = []
    offset = 0
    while offset < len(data):
        # Opaque data is not silently accepted as a chunk in a recognized container.
        name, size, value = _header(data, offset)
        chunks.append({"offset": offset, "name": name, "size_bytes": size, "value": value})
        offset += size
    if offset != len(data):
        raise AudioFormatError("chunk chain does not terminate at EOF")
    if expected is not None:
        got = tuple(chunk["name"] for chunk in chunks)
        if got != expected:
            raise AudioFormatError(f"unexpected chunk chain: {got!r}; expected {expected!r}")
    return chunks


def parse_sq(data: bytes) -> dict[str, Any]:
    """Validate observed SQ layout, including optional terminal Song chunk."""
    if len(data) < 48:
        raise AudioFormatError("SQ is shorter than the observed 48-byte three-header prefix")
    # The first two chunks are fixed by the observed title variant.
    first = _header(data, 0)
    second = _header(data, 16)
    third = _header(data, 48)
    if first[0] != "Vers" or first[1] != 16:
        raise AudioFormatError("SQ does not begin with a 16-byte Vers chunk")
    if second[0] != "Sequ" or second[1] != 32:
        raise AudioFormatError("SQ does not contain the observed 32-byte Sequ chunk")
    if second[2] != len(data):
        raise AudioFormatError("Sequ size field does not match physical file length")
    if third[0] != "Midi":
        raise AudioFormatError("SQ is missing the Midi chunk at offset 0x30")

    chunks = []
    offset = 0
    while offset < len(data):
        name, size, value = _header(data, offset)
        chunks.append({"offset": offset, "name": name, "size_bytes": size, "value": value})
        offset += size
    if offset != len(data):
        raise AudioFormatError("SQ chunks do not consume the entire file")
    names = [chunk["name"] for chunk in chunks]
    if names not in (["Vers", "Sequ", "Midi"], ["Vers", "Sequ", "Midi", "Song"]):
        raise AudioFormatError(f"unrecognized SQ chunk order: {names!r}")
    if len(chunks) == 4 and chunks[-1]["size_bytes"] != 32:
        raise AudioFormatError("observed terminal Song chunk must be 32 bytes")

    return {
        "format": "SCEI-SQ-observed-title-variant",
        "version_value": first[2],
        "declared_file_size": second[2],
        "chunk_names": names,
        "chunks": chunks,
        "midi_chunk_size_bytes": chunks[2]["size_bytes"],
        "trailing_song_chunk": len(chunks) == 4,
    }


def inspect_file(path: Path, root: Path) -> dict[str, Any]:
    data = path.read_bytes()
    rel = path.relative_to(root).as_posix()
    result: dict[str, Any] = {
        "path": rel,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "kind": "unknown",
    }
    name = path.name.upper()
    if name.endswith(".SQ;1"):
        result["kind"] = "SQ"
        result["structure"] = parse_sq(data)
    elif name.endswith(".HD;1"):
        result["kind"] = "HD"
        chunks = parse_chunk_chain(data, expected=("Vers", "Head", "Vagi", "Smpl", "Sset", "Prog"))
        result["structure"] = {"format": "SCEI-HD-chunk-chain", "chunk_names": [c["name"] for c in chunks], "chunks": chunks}
    elif name.endswith(".BD;1"):
        result["kind"] = "BD"
        result["structure"] = {
            "format": "opaque-binary-sample-bank",
            "leading_zero_bytes": next((i for i, b in enumerate(data) if b != 0), len(data)),
            "parse_status": "opaque; sample-bank encoding not decoded",
        }
    return result


def scan_disc_root(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"disc root is not a directory: {root}")
    media = [p for p in root.rglob("*") if p.is_file() and p.name.upper().endswith((".SQ;1", ".HD;1", ".BD;1"))]
    items = [inspect_file(p, root) for p in sorted(media)]
    by_kind: dict[str, int] = {}
    for item in items:
        by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1
    sq_songs = sum(1 for item in items if item["kind"] == "SQ" and item["structure"]["trailing_song_chunk"])
    return {
        "schema_version": 1,
        "disc_root": "external extraction directory (not included in repository)",
        "file_count": len(items),
        "counts_by_kind": dict(sorted(by_kind.items())),
        "sq_terminal_song_chunk_count": sq_songs,
        "files": items,
        "source_audio_bytes_exported": False,
        "decoded_audio_exported": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disc_root", type=Path, help="path to external extracted-disc directory")
    parser.add_argument("--output", type=Path, help="write metadata-only JSON report")
    args = parser.parse_args(argv)
    try:
        report = scan_disc_root(args.disc_root)
    except (OSError, ValueError, AudioFormatError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
