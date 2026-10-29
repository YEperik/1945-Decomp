#!/usr/bin/env python3
"""Audit the SND2 sequence pointer table in the extracted PS2 boot ELF.

This reads ELF metadata and a metadata-only ISO manifest. It never executes the
ELF or copies proprietary payload bytes into the repository.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))
import elf_recon  # noqa: E402

POINTER_TABLE_VA = 0x0027A9A8
POINTER_COUNT = 18
OPTIONAL_PATH_CAPACITY = 32
EXPECTED_ELF_MANIFEST_PATH = "SLES_517.41;1"
SEQUENCE_NAME_RE = re.compile(r"^sq_(\d{3})\.sq$", re.IGNORECASE)
SND2_SHARED_PATHS = (
    ("se_hd", 0x0032A768),
    ("se_bd", 0x0032A778),
    ("inst_hd", 0x0032A7A8),
    ("inst_bd", 0x0032A7B8),
)
PATH_FORMAT_VA = 0x00335EA8
PATH_PREFIX_VA = 0x00335EB0


class Snd2AuditError(ValueError):
    """Raised when ELF pointers or manifest correlations are inconsistent."""


def _section_for_va(elf: dict[str, Any], va: int, length: int) -> dict[str, Any]:
    if length < 0:
        raise Snd2AuditError("negative read length")
    for section in elf["sections"]:
        start = int(section["address"])
        size = int(section["size"])
        if start <= va and va - start <= size and length <= size - (va - start):
            if int(section["type"]) == elf_recon.SHT_NOBITS:
                raise Snd2AuditError(f"virtual address 0x{va:08X} points into NOBITS section")
            return section
    raise Snd2AuditError(f"virtual address range 0x{va:08X}+0x{length:X} is not file-backed")


def _read_va(data: bytes, elf: dict[str, Any], va: int, length: int) -> bytes:
    section = _section_for_va(elf, va, length)
    file_offset = int(section["file_offset"]) + va - int(section["address"])
    if file_offset < 0 or file_offset + length > len(data):
        raise Snd2AuditError(f"mapped file range for 0x{va:08X} exceeds ELF size")
    return data[file_offset:file_offset + length]


def _read_c_string(data: bytes, elf: dict[str, Any], va: int, max_length: int = 256) -> str:
    section = _section_for_va(elf, va, 1)
    remaining = int(section["size"]) - (va - int(section["address"]))
    length = min(max_length, remaining)
    raw = _read_va(data, elf, va, length)
    end = raw.find(b"\0")
    if end < 0:
        raise Snd2AuditError(f"unterminated string at virtual address 0x{va:08X}")
    try:
        value = raw[:end].decode("ascii", "strict")
    except UnicodeDecodeError as exc:
        raise Snd2AuditError(f"non-ASCII sequence name at 0x{va:08X}") from exc
    if not value:
        raise Snd2AuditError(f"empty sequence name at 0x{va:08X}")
    return value


def _load_manifest(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"path", "type", "size_bytes", "sha256"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise Snd2AuditError(f"manifest missing required columns: {', '.join(sorted(missing))}")
        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            key = (row.get("path") or "").replace("/", "/").upper()
            if not key:
                continue
            if key in rows:
                raise Snd2AuditError(f"duplicate manifest path: {key}")
            rows[key] = row
    return rows


def audit_snd2_elf(elf_data: bytes, manifest_rows: dict[str, dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    elf = elf_recon.parse_elf32_le(elf_data)
    if elf["machine"] != 8:
        raise Snd2AuditError(f"expected MIPS ELF machine 8, got {elf['machine']}")

    executable_hash = hashlib.sha256(elf_data).hexdigest()
    executable_record = manifest_rows.get(EXPECTED_ELF_MANIFEST_PATH.upper())
    if executable_record is None:
        raise Snd2AuditError(f"manifest lacks {EXPECTED_ELF_MANIFEST_PATH}")
    if executable_record.get("type") != "file":
        raise Snd2AuditError(f"{EXPECTED_ELF_MANIFEST_PATH} is not a file manifest entry")
    if executable_record.get("sha256", "").lower() != executable_hash:
        raise Snd2AuditError("ELF SHA-256 does not match the boot executable entry in the disc manifest")

    raw_table = _read_va(elf_data, elf, POINTER_TABLE_VA, POINTER_COUNT * 4)
    pointers = [int.from_bytes(raw_table[i * 4:i * 4 + 4], "little") for i in range(POINTER_COUNT)]
    rows: list[dict[str, Any]] = []
    first_slot_by_pointer: dict[int, int] = {}
    first_slot_by_name: dict[str, int] = {}

    for slot_index, string_va in enumerate(pointers):
        if string_va == 0:
            raise Snd2AuditError(f"null pointer at slot {slot_index}")
        logical_filename = _read_c_string(elf_data, elf, string_va).lower()
        match = SEQUENCE_NAME_RE.fullmatch(logical_filename)
        if match is None:
            raise Snd2AuditError(f"unexpected SND2 sequence name in slot {slot_index}: {logical_filename!r}")

        sequence_number = int(match.group(1))
        logical_path = f"snd2/{logical_filename}"
        iso_path = f"SND2/{logical_filename.upper()};1"
        manifest_record = manifest_rows.get(iso_path.upper())
        if manifest_record is None or manifest_record.get("type") != "file":
            raise Snd2AuditError(f"logical sequence does not resolve to an ISO file record: {iso_path}")

        duplicate_of: int | None = first_slot_by_pointer.get(string_va)
        duplicate_kind = "same_string_pointer" if duplicate_of is not None else ""
        if duplicate_of is None:
            duplicate_of = first_slot_by_name.get(logical_filename)
            if duplicate_of is not None:
                duplicate_kind = "same_filename_different_pointer"
        first_slot_by_pointer.setdefault(string_va, slot_index)
        first_slot_by_name.setdefault(logical_filename, slot_index)

        rows.append({
            "loader_slot_index": slot_index,
            "pointer_entry_va": f"0x{POINTER_TABLE_VA + slot_index * 4:08X}",
            "string_va": f"0x{string_va:08X}",
            "sequence_number": sequence_number,
            "logical_filename": logical_filename,
            "logical_path": logical_path,
            "resolved_iso_path": iso_path,
            "manifest_status": "present",
            "size_bytes": int(manifest_record["size_bytes"]),
            "sha256": manifest_record["sha256"].lower(),
            "duplicate_of_slot": "" if duplicate_of is None else duplicate_of,
            "duplicate_kind": duplicate_kind,
        })

    unique_names = {row["logical_filename"] for row in rows}
    duplicate_slots = [row for row in rows if row["duplicate_of_slot"] != ""]
    blank_slots = list(range(POINTER_COUNT, OPTIONAL_PATH_CAPACITY))
    shared_paths: list[dict[str, Any]] = []
    for role, string_va in SND2_SHARED_PATHS:
        logical_path = _read_c_string(elf_data, elf, string_va).lower()
        if not logical_path.startswith("snd2/"):
            raise Snd2AuditError(f"unexpected shared resource path for {role}: {logical_path!r}")
        iso_path = f"SND2/{logical_path.split('/', 1)[1].upper()};1"
        record = manifest_rows.get(iso_path.upper())
        if record is None or record.get("type") != "file":
            raise Snd2AuditError(f"shared path does not resolve to an ISO file record: {iso_path}")
        shared_paths.append({
            "role": role,
            "string_va": f"0x{string_va:08X}",
            "logical_path": logical_path,
            "resolved_iso_path": iso_path,
            "manifest_status": "present",
            "size_bytes": int(record["size_bytes"]),
            "sha256": record["sha256"].lower(),
        })

    path_format = _read_c_string(elf_data, elf, PATH_FORMAT_VA)
    path_prefix = _read_c_string(elf_data, elf, PATH_PREFIX_VA)
    if path_format != "%s%s" or path_prefix != "snd2/":
        raise Snd2AuditError(
            f"SND2 initializer constants changed: format={path_format!r}, prefix={path_prefix!r}"
        )

    current_sequence_path = "SND2/SQ_001.SQ;1"
    current_in_optional_list = any(row["resolved_iso_path"] == current_sequence_path for row in rows)
    if not current_in_optional_list:
        raise Snd2AuditError("the observed active SQ_001 path is absent from the optional sequence table")
    summary = {
        "status": "passed",
        "input_elf_sha256": executable_hash,
        "input_elf_manifest_path": EXPECTED_ELF_MANIFEST_PATH,
        "pointer_table_va": f"0x{POINTER_TABLE_VA:08X}",
        "pointer_count": POINTER_COUNT,
        "unique_sequence_names": len(unique_names),
        "duplicate_slots": duplicate_slots,
        "optional_path_capacity": OPTIONAL_PATH_CAPACITY,
        "populated_optional_slots_from_initializer": POINTER_COUNT,
        "empty_optional_slots_from_initializer": blank_slots,
        "path_format": {"string_va": f"0x{PATH_FORMAT_VA:08X}", "value": path_format},
        "path_prefix": {"string_va": f"0x{PATH_PREFIX_VA:08X}", "value": path_prefix},
        "shared_resource_paths": shared_paths,
        "current_sequence_path": current_sequence_path,
        "current_sequence_also_appears_in_optional_list": current_in_optional_list,
        "interpretation_limits": [
            "Metadata correlation only; no SIF/RPC or audio playback is performed.",
            "The 18-entry optional list contains 17 unique names because slots 9 and 10 share one string pointer.",
            "The active SQ_001 path is supplied separately and is also present in optional-list slot 0.",
            "Slots 18..31 are not written by the observed SND2 initializer; this is not a claim about other initializers or other runtime paths.",
        ],
    }
    return rows, summary


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "loader_slot_index", "pointer_entry_va", "string_va", "sequence_number",
        "logical_filename", "logical_path", "resolved_iso_path", "manifest_status",
        "size_bytes", "sha256", "duplicate_of_slot", "duplicate_kind",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", required=True, type=Path, help="extracted SLES_517.41 ELF; never executed")
    parser.add_argument("--manifest", required=True, type=Path, help="metadata-only evidence/disc_file_manifest.csv")
    parser.add_argument("--out-csv", required=True, type=Path, help="output path catalog CSV")
    parser.add_argument("--out-json", required=True, type=Path, help="output summary JSON")
    args = parser.parse_args()

    try:
        elf_data = args.elf.read_bytes()
        manifest_rows = _load_manifest(args.manifest)
        rows, summary = audit_snd2_elf(elf_data, manifest_rows)
        write_csv(args.out_csv, rows)
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({"status": summary["status"], "slots": len(rows),
                      "unique_names": summary["unique_sequence_names"],
                      "duplicates": len(summary["duplicate_slots"]),
                      "empty_optional_slots": len(summary["empty_optional_slots_from_initializer"]),
                      "csv": str(args.out_csv), "json": str(args.out_json)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
