#!/usr/bin/env python3
"""Parse user-exported Ghidra listings into a metadata-only PS2 audio catalog.

The parser records logical names and table addresses; it does not copy source
media or claim that logical keys correspond to standalone ISO9660 files.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

RESOURCE_TABLE_START = 0x0030C0B0
RESOURCE_TABLE_STOP = 0x0030C38C  # exclusive; first non-pointer slot follows
SEQUENCE_TABLE_STARTS = (
    (0x001DFCC8, 0x001DFD20, "sequence"),
    (0x001DFD20, 0x001DFD78, "bank"),
)
ADDR_LINE = re.compile(
    r"\.(?:data|rodata|sdata):([0-9a-fA-F]{8})\s+"
    r"([0-9a-fA-F]{8})\s+addr\s+([^;]+?)(?:\s*;\s*=\s*(.*))?$"
)
DATA_LINE = re.compile(r"\.(?:data|rodata|sdata):([0-9a-fA-F]{8})\s+(.*)$")
QUOTED = re.compile(r'^"(.*)"$')
CHAR_HINT = re.compile(r"(?:^|\s)([0-9a-fA-F]{2})h\s+(.)(?:\s|$)")
HEX_HINT = re.compile(r"^([0-9a-fA-F]{8})h?$")


class ListingError(ValueError):
    """Raised when a listing is truncated or does not match expected layout."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unescape_listing_string(value: str) -> str:
    # Ghidra's HTML-style Listing export escapes each literal backslash as \\\\.
    return value.replace("\\\\", "\\")


def _comment_value(comment: str | None) -> tuple[str | None, str | None]:
    if not comment:
        return None, None
    quoted = QUOTED.match(comment.strip())
    if quoted:
        return _unescape_listing_string(quoted.group(1)), None
    char_match = CHAR_HINT.search(comment)
    if char_match:
        char = char_match.group(2)
        if char.isprintable():
            return None, char
    hex_match = HEX_HINT.match(comment.strip())
    if hex_match:
        try:
            raw = int(hex_match.group(1), 16).to_bytes(4, "little")
            decoded = raw.split(b"\0", 1)[0].decode("ascii")
            if decoded and all(32 <= ord(c) < 127 for c in decoded):
                return decoded, None
        except (OverflowError, UnicodeDecodeError):
            pass
    return None, None


def parse_address_rows(text: str) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for line in text.splitlines():
        match = ADDR_LINE.search(line.strip())
        if not match:
            continue
        address = int(match.group(1), 16)
        word = bytes.fromhex(match.group(2))
        target_address = int.from_bytes(word, "little")
        target_symbol = match.group(3).strip()
        comment = match.group(4).strip() if match.group(4) else None
        literal, char_hint = _comment_value(comment)
        rows[address] = {
            "address": address,
            "word_hex": match.group(2).lower(),
            "target_address": target_address,
            "target_symbol": target_symbol,
            "comment": comment,
            "literal": literal,
            "char_hint": char_hint,
        }
    return rows


def parse_byte_hints(text: str) -> dict[int, str]:
    """Read isolated-byte output at table slots where the pointer is null."""
    hints: dict[int, str] = {}
    for line in text.splitlines():
        match = DATA_LINE.search(line.strip())
        if not match:
            continue
        address = int(match.group(1), 16)
        tail = match.group(2)
        if "addr" in tail:
            continue
        # Ghidra's byte line usually looks like `00 ?? 00h` or `01 ?? 01h`.
        byte_match = re.match(r"([0-9a-fA-F]{2})\s+\?\?\s+([0-9a-fA-F]{2})h", tail)
        if byte_match:
            hints[address] = byte_match.group(1).lower()
    return hints


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or not {"path", "type", "data_lba", "sha256"}.issubset(rows[0]):
        raise ListingError("disc manifest must contain path, type, data_lba, sha256 columns")
    return rows


def _file_index(manifest: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["path"].upper().replace("\\", "/"): row for row in manifest if row.get("type") == "file"}


def _squash_iso_name(base: str | None, extension: str) -> str | None:
    if not base:
        return None
    return f"SND1/{base}.{extension};1".upper()


def _resolve_sequence_stem(
    table_row: dict[str, Any] | None,
    index: int,
    seq_candidates_by_lba: list[str],
    manifest_file_keys: set[str],
) -> tuple[str | None, str]:
    if table_row is None:
        return None, "null_pointer_or_no_listing_row"
    literal = table_row.get("literal")
    target = table_row.get("target_address")
    if literal:
        return literal.lower(), "literal_in_listing"
    # The 8 sequential 8-byte slots at 0x00335300..0x00335338 each show a
    # leading 'b'. Cross-correlate that order with the eight BGM*.SQ ISO records.
    if target is not None and 0x00335300 <= target <= 0x00335338 and (target - 0x00335300) % 8 == 0:
        position = (target - 0x00335300) // 8
        if position < len(seq_candidates_by_lba):
            return seq_candidates_by_lba[position].lower(), "cross_correlated_bgm_sq_slot_order"
    if target == 0x00335380:
        return "0", "placeholder_value_in_listing_no_matching_sq_file"
    char_hint = table_row.get("char_hint")
    if char_hint:
        candidates = []
        for key in manifest_file_keys:
            m = re.fullmatch(r"SND1/([^/]+)\.SQ;1", key)
            if m and m.group(1).startswith(char_hint.upper()):
                candidates.append(m.group(1).lower())
        candidates = sorted(set(candidates))
        if len(candidates) == 1:
            return candidates[0], "unique_initial_character_cross_reference"
        return None, f"ambiguous_initial_character:{char_hint}:{'|'.join(candidates)}"
    return None, "unresolved_target"


def _resolve_bank_stem(table_row: dict[str, Any] | None) -> tuple[str | None, str]:
    if table_row is None:
        return None, "null_pointer_or_no_listing_row"
    literal = table_row.get("literal")
    if literal:
        return literal.lower(), "literal_in_listing"
    target = table_row.get("target_address")
    # Both are 4-byte NUL-terminated strings shown as little-endian numeric data.
    if target == 0x00335388:
        return "end", "decoded_little_endian_string_word"
    if target == 0x00335390:
        return "bgm", "decoded_little_endian_string_word"
    char_hint = table_row.get("char_hint")
    if char_hint:
        candidates = {
            "m": "menu",
            "n": "name",
            "0": "0",
        }
        if char_hint.lower() in candidates:
            return candidates[char_hint.lower()], "unique_initial_character_cross_reference"
    return None, "unresolved_target"


def parse_sequence_catalog(text: str, manifest: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows_by_addr = parse_address_rows(text)
    file_keys = set(_file_index(manifest))
    sq_rows = []
    for row in manifest:
        key = row.get("path", "").upper().replace("\\", "/")
        match = re.fullmatch(r"SND1/(BGM[5-8A-D])\.SQ;1", key)
        if match and row.get("type") == "file":
            try:
                lba = int(row.get("data_lba", ""))
            except ValueError:
                continue
            sq_rows.append((lba, match.group(1).lower()))
    seq_bgm_candidates = [name for _, name in sorted(sq_rows)]
    if len(seq_bgm_candidates) != 8:
        raise ListingError(f"expected 8 SND1 BGM5..BGM8/BGMA..BGMD SQ records, found {len(seq_bgm_candidates)}")

    result: list[dict[str, Any]] = []
    for start, stop, table_kind in SEQUENCE_TABLE_STARTS:
        for address in range(start, stop, 4):
            entry = rows_by_addr.get(address)
            index = (address - start) // 4
            if table_kind == "sequence":
                stem, resolution = _resolve_sequence_stem(entry, index, seq_bgm_candidates, file_keys)
                if entry is None:
                    # A null pointer inside this array is explicitly retained.
                    resolution = "null_pointer"
                bank_stem = None
            else:
                bank_stem, resolution = _resolve_bank_stem(entry)
                stem = None
            result.append({
                "table_kind": table_kind,
                "index": index,
                "table_address": f"0x{address:08X}",
                "target_address": f"0x{entry['target_address']:08X}" if entry else "",
                "target_symbol": entry["target_symbol"] if entry else "",
                "raw_literal": entry["literal"] if entry and entry.get("literal") else "",
                "first_character_hint": entry["char_hint"] if entry and entry.get("char_hint") else "",
                "sequence_stem": stem or "",
                "bank_stem": bank_stem or "",
                "resolution_method": resolution,
                "pointer_present": bool(entry),
            })
    if len(result) != 44:
        raise ListingError(f"expected 44 sequence/bank table slots, found {len(result)}")
    return result


def parse_resource_groups(text: str) -> list[dict[str, Any]]:
    rows = parse_address_rows(text)
    pointers = []
    for address in range(RESOURCE_TABLE_START, RESOURCE_TABLE_STOP, 4):
        row = rows.get(address)
        if row is None:
            break
        literal = row.get("literal")
        if not literal or not re.fullmatch(r"[A-Za-z0-9_]+\\[A-Za-z0-9_]+\.(SQ|HD|BD)", literal, re.IGNORECASE):
            break
        pointers.append((address, literal))
    if not pointers:
        raise ListingError(f"no logical resource pointers found at 0x{RESOURCE_TABLE_START:08X}")
    if len(pointers) % 3:
        raise ListingError(f"logical resource table has {len(pointers)} pointers, not divisible by 3")
    for i in range(1, len(pointers)):
        if pointers[i][0] != pointers[i - 1][0] + 4:
            raise ListingError("logical resource table has a gap in pointer addresses")

    groups: list[dict[str, Any]] = []
    seen: dict[tuple[str, str, str], int] = {}
    for offset in range(0, len(pointers), 3):
        triplet = pointers[offset:offset + 3]
        paths = [path for _, path in triplet]
        exts = [path.rsplit(".", 1)[-1].upper() for path in paths]
        stems = [path.rsplit(".", 1)[0].upper() for path in paths]
        if exts != ["SQ", "HD", "BD"]:
            raise ListingError(f"bad resource triplet at 0x{triplet[0][0]:08X}: {paths}")
        if len(set(stems)) != 1:
            raise ListingError(f"resource stems do not match at 0x{triplet[0][0]:08X}: {paths}")
        key = tuple(stems)
        resource_index = offset // 3
        first_seen = seen.setdefault(key, resource_index)
        group_path = paths[0].rsplit("\\", 1)[0]
        group_base = paths[0].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
        groups.append({
            "resource_index": resource_index,
            "table_address": f"0x{triplet[0][0]:08X}",
            "sq_address": f"0x{triplet[0][0]:08X}",
            "hd_address": f"0x{triplet[1][0]:08X}",
            "bd_address": f"0x{triplet[2][0]:08X}",
            "resource_directory": group_path,
            "resource_stem": group_base,
            "sq_path_key": paths[0],
            "hd_path_key": paths[1],
            "bd_path_key": paths[2],
            "duplicate_of_index": "" if first_seen == resource_index else first_seen,
            "physical_iso_file_matches": 0,
            "physical_container_candidate": "DATA/SND/SNDCOM.BIN;1",
            "interpretation": "logical_resource_key_no_standalone_iso_record_in_manifest",
        })
    return groups


def annotate_resource_groups(resource_rows: list[dict[str, Any]], manifest: list[dict[str, str]]) -> list[dict[str, Any]]:
    file_keys = set(_file_index(manifest))
    for row in resource_rows:
        matched = set()
        for field in ("sq_path_key", "hd_path_key", "bd_path_key"):
            logical = row[field].replace("\\", "/").upper()
            base_candidates = (logical, f"SND/{logical}", f"SND1/{logical}", f"DATA/SND/{logical}")
            for candidate in base_candidates:
                if not candidate.endswith(";1"):
                    candidate += ";1"
                if candidate in file_keys:
                    matched.add(candidate)
        row["physical_iso_file_matches"] = len(matched)
        row["physical_container_candidate"] = "DATA/SND/SNDCOM.BIN;1"
        row["physical_container_candidate_present"] = "true" if "DATA/SND/SNDCOM.BIN;1" in file_keys else "false"
        row["interpretation"] = (
            "logical_key_matches_standalone_iso_record" if matched else
            "logical_key_has_no_standalone_iso_record; container relationship unconfirmed"
        )
    return resource_rows


def parse_root_path_table(text: str, manifest: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows_by_addr = parse_address_rows(text)
    file_keys = set(_file_index(manifest))
    result: list[dict[str, Any]] = []
    start, stop = 0x001DFDE0, 0x001DFE58
    for address in range(start, stop, 4):
        entry = rows_by_addr.get(address)
        if entry and entry.get("literal"):
            logical_path = entry["literal"].replace("\\", "/").lower()
            resolution = "literal_in_listing"
        elif entry and entry.get("target_address") == 0x00335380:
            logical_path = "0"
            resolution = "placeholder_value_in_listing"
        else:
            logical_path = ""
            resolution = "unresolved_or_null_pointer"
        expected_iso_path = ""
        status = "no_path"
        if logical_path and logical_path != "0":
            expected_iso_path = logical_path.upper()
            if not expected_iso_path.endswith(";1"):
                expected_iso_path += ";1"
            status = "present" if expected_iso_path in file_keys else "missing_from_iso_manifest"
        result.append({
            "table_index": (address - start) // 4,
            "table_address": f"0x{address:08X}",
            "target_address": f"0x{entry['target_address']:08X}" if entry else "",
            "target_symbol": entry["target_symbol"] if entry else "",
            "logical_path": logical_path,
            "expected_iso_path": expected_iso_path,
            "manifest_status": status,
            "resolution_method": resolution,
        })
    if len(result) != 30:
        raise ListingError(f"expected 30 root audio path table slots, found {len(result)}")
    return result


def parse_bgm_boss_callbacks(text: str) -> list[dict[str, Any]]:
    """Recover the 4-entry function-pointer table at 0x001DFDD0..0x001DFDDC.

    Ghidra explicitly resolves only the first word as an address. The next three
    entries are four byte rows in this Listing export, so reconstruct them from
    the byte dump and keep the target identification clearly labelled.
    """
    byte_values: dict[int, int] = {}
    row_entries = parse_address_rows(text)
    # Build target addresses from the first word and byte rows in the Listing.
    for line in text.splitlines():
        match = DATA_LINE.search(line.strip())
        if not match:
            continue
        address = int(match.group(1), 16)
        tail = match.group(2)
        byte_match = re.match(r"([0-9a-fA-F]{2})\s+\?\?", tail)
        if byte_match:
            byte_values[address] = int(byte_match.group(1), 16)
    expected_targets: dict[int, int] = {}
    for address in (0x001DFDD0, 0x001DFDD4, 0x001DFDD8, 0x001DFDDC):
        if address in row_entries:
            expected_targets[address] = int(row_entries[address]["target_address"])
        else:
            raw = bytes(byte_values.get(address + offset, 0) for offset in range(4))
            expected_targets[address] = int.from_bytes(raw, "little")
    return [
        {
            "table_index": index,
            "table_address": f"0x{address:08X}",
            "target_address": f"0x{expected_targets[address]:08X}",
            "target_symbol": row_entries.get(address, {}).get("target_symbol", ""),
            "source_interpretation": "function pointer used by BGM_BOSS command path; target 3 also used directly by stop_bgm path",
        }
        for index, address in enumerate((0x001DFDD0, 0x001DFDD4, 0x001DFDD8, 0x001DFDDC))
    ]


def annotate_sequence_catalog(sequence_rows: list[dict[str, Any]], resource_rows: list[dict[str, Any]], manifest: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_key = _file_index(manifest)
    sequence_table = {int(r["index"]): r for r in sequence_rows if r["table_kind"] == "sequence"}
    bank_table = {int(r["index"]): r for r in sequence_rows if r["table_kind"] == "bank"}
    output: list[dict[str, Any]] = []
    for index in range(22):
        sequence = sequence_table.get(index, {})
        bank = bank_table.get(index, {})
        sequence_stem = sequence.get("sequence_stem") or ""
        bank_stem = bank.get("bank_stem") or ""
        sq_key = _squash_iso_name(sequence_stem, "SQ")
        hd_key = _squash_iso_name(bank_stem, "HD")
        bd_key = _squash_iso_name(bank_stem, "BD")
        result = {
            "sequence_id": index,
            "sequence_table_address": sequence.get("table_address", ""),
            "sequence_target_address": sequence.get("target_address", ""),
            "sequence_target_symbol": sequence.get("target_symbol", ""),
            "sequence_stem": sequence_stem,
            "sequence_resolution": sequence.get("resolution_method", "missing_table_slot"),
            "bank_table_address": bank.get("table_address", ""),
            "bank_target_address": bank.get("target_address", ""),
            "bank_target_symbol": bank.get("target_symbol", ""),
            "bank_stem": bank_stem,
            "bank_resolution": bank.get("resolution_method", "missing_table_slot"),
            "sq_iso_path": sq_key or "",
            "sq_manifest_status": "present" if sq_key and sq_key in by_key else ("no_sequence_pointer" if not sequence.get("pointer_present") else "missing_from_iso_manifest"),
            "hd_iso_path": hd_key or "",
            "hd_manifest_status": "present" if hd_key and hd_key in by_key else ("no_bank_pointer" if not bank.get("pointer_present") else "missing_from_iso_manifest"),
            "bd_iso_path": bd_key or "",
            "bd_manifest_status": "present" if bd_key and bd_key in by_key else ("no_bank_pointer" if not bank.get("pointer_present") else "missing_from_iso_manifest"),
            "sequence_and_bank_paths_physically_present": bool(sq_key and hd_key and bd_key and sq_key in by_key and hd_key in by_key and bd_key in by_key),
        }
        output.append(result)
    return output


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ListingError(f"refusing to write empty catalog: {path}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_catalog(sequence_listing: Path, resource_listing: Path, suffix_listing: Path, manifest_path: Path) -> dict[str, Any]:
    sequence_text = sequence_listing.read_text(encoding="utf-8", errors="replace")
    resource_text = resource_listing.read_text(encoding="utf-8", errors="replace")
    suffix_text = suffix_listing.read_text(encoding="utf-8", errors="replace")
    manifest = read_manifest(manifest_path)
    file_index = _file_index(manifest)

    sequence_rows = parse_sequence_catalog(sequence_text, manifest)
    resource_rows = annotate_resource_groups(parse_resource_groups(resource_text), manifest)
    root_path_rows = parse_root_path_table(sequence_text, manifest)
    boss_callback_rows = parse_bgm_boss_callbacks(sequence_text)
    sequence_catalog = annotate_sequence_catalog(sequence_rows, resource_rows, manifest)

    # The third listing proves that 0x003366D8 is the literal version suffix ;1;
    # neighboring values are zero-filled or unrelated runtime state, not paths.
    suffix_line_map: dict[int, str] = {}
    for line in suffix_text.splitlines():
        match = DATA_LINE.search(line.strip())
        if not match:
            continue
        address = int(match.group(1), 16)
        tail = match.group(2)
        byte_match = re.match(r"([0-9a-fA-F]{2})\s+\?\?\s+([0-9a-fA-F]{2})h", tail)
        if byte_match:
            suffix_line_map[address] = chr(int(byte_match.group(1), 16)) if int(byte_match.group(1), 16) >= 32 else "\\0"
    suffix_chars = "".join(suffix_line_map.get(addr, "") for addr in range(0x003366D8, 0x003366DB))
    suffix_confirmed = suffix_chars == ";1\\0"
    container_key = "DATA/SND/SNDCOM.BIN;1"
    container_found = container_key.upper() in file_index

    return {
        "schema_version": 1,
        "input_sources": {
            "sequence_listing": {"file_name": sequence_listing.name, "sha256": sha256_file(sequence_listing)},
            "resource_listing": {"file_name": resource_listing.name, "sha256": sha256_file(resource_listing)},
            "suffix_listing": {"file_name": suffix_listing.name, "sha256": sha256_file(suffix_listing)},
            "disc_manifest": {"file_name": manifest_path.name, "sha256": sha256_file(manifest_path)},
        },
        "sequence_selector_table_slots": len(sequence_rows) // 2,
        "sequence_ids": sequence_catalog,
        "logical_resource_group_count": len(resource_rows),
        "logical_resource_pointer_count": len(resource_rows) * 3,
        "logical_resource_groups": resource_rows,
        "iso_manifest_file_count": len(file_index),
        "root_audio_path_table_slots": len(root_path_rows),
        "root_audio_paths_present_in_iso_manifest": sum(1 for row in root_path_rows if row["manifest_status"] == "present"),
        "bgm_boss_callback_table": boss_callback_rows,
        "root_audio_paths": root_path_rows,
        "candidate_container_path": container_key,
        "candidate_container_present_in_iso_manifest": container_found,
        "iso_version_suffix_at_0x003366d8": ";1" if suffix_confirmed else "unconfirmed",
        "physical_path_interpretation": "logical keys do not match standalone ISO records; DATA/SND/SNDCOM.BIN is a candidate container, but the exact internal-container relationship still requires loader-path confirmation",
        "summary": {
            "sequence_sq_paths_present": sum(1 for x in sequence_catalog if x["sq_manifest_status"] == "present"),
            "sequence_sq_paths_missing_or_placeholder": sum(1 for x in sequence_catalog if x["sq_manifest_status"] != "present"),
            "full_sq_hd_bd_triplets_present": sum(1 for x in sequence_catalog if x["sequence_and_bank_paths_physically_present"]),
            "full_triplets_with_missing_hd_or_bd": [x["sequence_id"] for x in sequence_catalog if x["sq_manifest_status"] == "present" and not x["sequence_and_bank_paths_physically_present"]],
            "resource_groups_with_physical_standalone_iso_match": 0,
            "duplicate_logical_resource_groups": [x["resource_index"] for x in resource_rows if x["duplicate_of_index"] != ""],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequence-listing", required=True, type=Path)
    parser.add_argument("--resource-listing", required=True, type=Path)
    parser.add_argument("--suffix-listing", required=True, type=Path)
    parser.add_argument("--disc-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_catalog(args.sequence_listing, args.resource_listing, args.suffix_listing, args.disc_manifest)
        out_dir = args.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        sequence_rows = report.pop("sequence_ids")
        resource_rows = report.pop("logical_resource_groups")
        root_path_rows = report.pop("root_audio_paths")
        _write_csv(out_dir / "ghidra_audio_sequence_catalog.csv", sequence_rows)
        _write_csv(out_dir / "ghidra_audio_logical_resource_catalog.csv", resource_rows)
        _write_csv(out_dir / "ghidra_audio_root_path_catalog.csv", root_path_rows)
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        (out_dir / "ghidra_audio_catalog_validation.json").write_text(rendered, encoding="utf-8")
        print(rendered, end="")
    except (OSError, ValueError, ListingError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
