#!/usr/bin/env python3
"""Probe candidate internal sound-container markers without extracting payloads.

The tool reports observations only. In particular, it does not assert that every
pQES occurrence begins an independent record or that the pBAV +0x0C word is a
formal size field; it labels the latter as a size candidate and checks bounds.
Original media should remain outside the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

DEFAULT_MAX_BYTES = 128 * 1024 * 1024
SIGNATURES = (b"pQES", b"pBAV", b"BGMAP", b"SCEI")
CONTEXT_STRINGS = (b"RECTDT  SEQUENCE", b"PALETTE BGMAPTBL", b"CHECKSUMSEQUENCE", b"BGMAP   OBJDT")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class ProbeError(ValueError):
    """Raised when inputs are invalid or larger than the configured bound."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _find_all(data: bytes, needle: bytes, cap: int = 10000) -> tuple[list[int], bool]:
    hits: list[int] = []
    cursor = 0
    while True:
        offset = data.find(needle, cursor)
        if offset < 0:
            return hits, False
        if len(hits) >= cap:
            return hits, True
        hits.append(offset)
        cursor = offset + 1


def probe_bytes(name: str, data: bytes, expected_sha256: str | None = None) -> dict[str, Any]:
    digest = _sha256(data)
    if expected_sha256 is not None and not SHA256_RE.fullmatch(expected_sha256):
        raise ProbeError(f"invalid expected SHA-256 for {name}")

    marker_data: dict[str, dict[str, Any]] = {}
    all_offsets: list[tuple[int, str]] = []
    for signature in SIGNATURES:
        hits, truncated = _find_all(data, signature)
        marker_data[signature.decode("ascii")] = {
            "count_observed": len(hits),
            "offsets_hex": [f"0x{x:X}" for x in hits],
            "offset_list_truncated": truncated,
        }
        all_offsets.extend((offset, signature.decode("ascii")) for offset in hits)
    all_offsets.sort()

    # A few stable printable labels help distinguish background-map/graphics
    # content from sound-like headers. These hits are context clues, not a
    # formal classification or resource-boundary declaration.
    context_strings: dict[str, dict[str, Any]] = {}
    for token in CONTEXT_STRINGS:
        hits, truncated = _find_all(data, token)
        context_strings[token.decode("ascii")] = {
            "count_observed": len(hits),
            "offsets_hex": [f"0x{x:X}" for x in hits],
            "offset_list_truncated": truncated,
        }

    # SNDCOM.BIN has a reproducible compact-table candidate: a LE32 count,
    # followed by (offset, tag) LE32 pairs, with the first offset exactly at
    # the end of this directory. Treat this only as a candidate layout; target
    # offsets may point inside an enclosing payload, so never infer spans from
    # adjacent directory entries.
    directory_candidate: dict[str, Any] = {
        "detected": False,
        "layout_hypothesis": "LE32 entry_count followed by entry_count (LE32 target_offset, LE32 tag) pairs",
        "detection_rule": "count in 1..64; first target equals 4 + count*8; all targets in bounds and nondecreasing",
        "entry_count_candidate": None,
        "directory_size_candidate_bytes": None,
        "entries": [],
    }
    if len(data) >= 4:
        count = int.from_bytes(data[0:4], "little")
        directory_size = 4 + count * 8
        if 1 <= count <= 64 and directory_size <= len(data):
            candidate_entries: list[dict[str, Any]] = []
            last_target = -1
            valid = True
            for index in range(count):
                base = 4 + index * 8
                target_offset = int.from_bytes(data[base:base + 4], "little")
                tag = int.from_bytes(data[base + 4:base + 8], "little")
                if target_offset < last_target or target_offset >= len(data):
                    valid = False
                last_target = target_offset
                matching_signatures = [sig.decode("ascii") for sig in SIGNATURES
                                        if data.startswith(sig, target_offset)] if target_offset < len(data) else []
                candidate_entries.append({
                    "index": index,
                    "target_offset_hex": f"0x{target_offset:X}",
                    "tag_u32_hex": f"0x{tag:08X}",
                    "tag_ascii_if_byte": chr(tag) if 32 <= tag <= 126 else None,
                    "recognized_marker_at_target": matching_signatures[0] if matching_signatures else None,
                })
            valid = valid and bool(candidate_entries) and int(candidate_entries[0]["target_offset_hex"], 16) == directory_size
            directory_candidate.update({
                "detected": valid,
                "entry_count_candidate": count,
                "directory_size_candidate_bytes": directory_size,
                "entries": candidate_entries if valid else [],
            })

    p_bav_records: list[dict[str, Any]] = []
    p_bav_hits, _ = _find_all(data, b"pBAV")
    for offset in p_bav_hits:
        if offset + 16 > len(data):
            p_bav_records.append({
                "offset_hex": f"0x{offset:X}",
                "header_complete": False,
                "candidate_size_field_offset_hex": f"0x{offset + 12:X}",
                "candidate_size_u32": None,
                "candidate_end_offset_hex": None,
                "candidate_size_in_bounds": False,
                "next_recognized_marker_at_candidate_end": None,
            })
            continue
        version = int.from_bytes(data[offset + 4:offset + 8], "little")
        flags = int.from_bytes(data[offset + 8:offset + 12], "little")
        candidate_size = int.from_bytes(data[offset + 12:offset + 16], "little")
        candidate_end = offset + candidate_size if candidate_size else None
        in_bounds = candidate_end is not None and offset < candidate_end <= len(data)
        next_marker = None
        gap = None
        if in_bounds:
            later = [(pos, sig) for pos, sig in all_offsets if pos >= candidate_end]
            if later:
                next_marker = {"offset_hex": f"0x{later[0][0]:X}", "signature": later[0][1]}
                gap = later[0][0] - candidate_end
        p_bav_records.append({
            "offset_hex": f"0x{offset:X}",
            "header_complete": True,
            "version_candidate_u32": version,
            "flags_candidate_u32": flags,
            "candidate_size_field_offset_hex": f"0x{offset + 12:X}",
            "candidate_size_u32": candidate_size,
            "candidate_end_offset_hex": f"0x{candidate_end:X}" if candidate_end is not None else None,
            "candidate_size_in_bounds": in_bounds,
            "next_recognized_marker_at_or_after_candidate_end": next_marker,
            "gap_to_next_recognized_marker_bytes": gap,
            "interpretation": "candidate size only; format field semantics require loader or format confirmation",
        })

    result: dict[str, Any] = {
        "schema_version": 1,
        "input_name": name,
        "size_bytes": len(data),
        "sha256": digest,
        "expected_sha256": expected_sha256,
        "expected_sha256_matches": (digest.lower() == expected_sha256.lower()) if expected_sha256 else None,
        "marker_counts_and_offsets": marker_data,
        "context_string_hits": context_strings,
        "compact_directory_table_candidate": directory_candidate,
        "pBAV_candidate_headers": p_bav_records,
        "interpretation_limits": [
            "pQES and BGMAP are signature hits, not proof of independent object boundaries",
            "pBAV +0x0C is reported as a candidate length field based on observed boundaries, not a finalized format specification",
            "no resource names are inferred from marker hits alone",
            "input bytes are read only and are never copied to the output report",
        ],
    }
    return result


def probe_file(name: str, path: Path, expected_sha256: str | None, max_bytes: int) -> dict[str, Any]:
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise ProbeError(f"input is not a regular file: {path}")
        size = resolved.stat().st_size
        if size > max_bytes:
            raise ProbeError(f"input {name} is {size} bytes, greater than max_bytes {max_bytes}")
        data = resolved.read_bytes()
    except OSError as exc:
        raise ProbeError(f"cannot read input {name}: {exc}") from exc
    return probe_bytes(name, data, expected_sha256)


def _parse_named_value(raw: str, kind: str) -> tuple[str, str]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError(f"{kind} must use NAME=VALUE")
    name, value = raw.split("=", 1)
    if not name.strip() or not value.strip():
        raise argparse.ArgumentTypeError(f"{kind} must use non-empty NAME=VALUE")
    return name.strip(), value.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, metavar="NAME=PATH",
                        help="input binary path; may be specified more than once")
    parser.add_argument("--expected-sha256", action="append", default=[], metavar="NAME=HEX",
                        help="optional expected digest, keyed by input name")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--output", type=Path, required=True,
                        help="JSON metadata output path; never an extracted binary")
    args = parser.parse_args(argv)

    try:
        if args.max_bytes < 1:
            raise ProbeError("--max-bytes must be positive")
        input_pairs = [_parse_named_value(raw, "--input") for raw in args.input]
        expected_pairs = [_parse_named_value(raw, "--expected-sha256") for raw in args.expected_sha256]
        input_names = [name for name, _ in input_pairs]
        if len(set(input_names)) != len(input_names):
            raise ProbeError("input names must be unique")
        expected_map = dict(expected_pairs)
        if len(expected_map) != len(expected_pairs):
            raise ProbeError("expected SHA-256 names must be unique")
        unknown_expected = set(expected_map) - set(input_names)
        if unknown_expected:
            raise ProbeError(f"expected digest supplied for unknown input name(s): {', '.join(sorted(unknown_expected))}")
        reports = [probe_file(name, Path(path), expected_map.get(name), args.max_bytes)
                   for name, path in input_pairs]
        result = {"schema_version": 1, "input_count": len(reports), "reports": reports}
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if all(r["expected_sha256_matches"] is not False for r in reports) else 1
    except (OSError, ProbeError, argparse.ArgumentTypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
