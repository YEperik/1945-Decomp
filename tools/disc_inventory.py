#!/usr/bin/env python3
"""Read-only inventory of a 2352-byte-sector Mode 2 PlayStation disc image.

The tool validates basic raw-sector sync/mode/MSF/subheader structure, reads an
ISO9660-style volume descriptor, walks directory records with bounds checks,
and hashes file payloads without extracting original file contents. It does not
verify CD-ROM EDC/ECC, PlayStation-specific metadata, or game authenticity.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, BinaryIO

SECTOR_SIZE = 2352
USER_DATA_OFFSET = 24
BLOCK_SIZE = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
MAX_PATH_CHARS = 4096


def bcd_to_int(value: int) -> int:
    high, low = (value >> 4) & 0xF, value & 0xF
    if high > 9 or low > 9:
        raise ValueError(f"invalid BCD byte: 0x{value:02x}")
    return high * 10 + low


def int_to_bcd(value: int) -> int:
    if not 0 <= value <= 99:
        raise ValueError(f"not representable as BCD: {value}")
    return ((value // 10) << 4) | (value % 10)


def expected_msf(lba: int) -> bytes:
    """CD sector header MSF, where image LBA 0 is 00:02:00."""
    frames = lba + 150
    minute, remainder = divmod(frames, 60 * 75)
    second, frame = divmod(remainder, 75)
    if minute > 99:
        raise ValueError("MSF beyond 99 minutes")
    return bytes((int_to_bcd(minute), int_to_bcd(second), int_to_bcd(frame)))


def read_raw_sector(f: BinaryIO, lba: int, total_sectors: int) -> bytes:
    if lba < 0 or lba >= total_sectors:
        raise ValueError(f"LBA out of image bounds: {lba} (sectors={total_sectors})")
    f.seek(lba * SECTOR_SIZE)
    raw = f.read(SECTOR_SIZE)
    if len(raw) != SECTOR_SIZE:
        raise ValueError(f"short raw sector at LBA {lba}")
    return raw


def read_block(f: BinaryIO, lba: int, total_sectors: int) -> bytes:
    raw = read_raw_sector(f, lba, total_sectors)
    if raw[:12] != SYNC or raw[15] != 2:
        raise ValueError(f"not a valid Mode 2 sector header at LBA {lba}")
    if raw[16:20] != raw[20:24]:
        raise ValueError(f"duplicated XA subheaders differ at LBA {lba}")
    submode = raw[18]
    if submode & 0x20:
        raise ValueError(f"Mode 2 Form 2 sector cannot be read as 2048-byte block at LBA {lba}")
    if not (submode & 0x08):
        raise ValueError(f"Mode 2 sector is not marked as data at LBA {lba}")
    payload = raw[USER_DATA_OFFSET:USER_DATA_OFFSET + BLOCK_SIZE]
    if len(payload) != BLOCK_SIZE:
        raise ValueError(f"short payload at LBA {lba}")
    return payload


def both_endian(raw: bytes, width: int, label: str) -> int:
    if len(raw) != width * 2:
        raise ValueError(f"invalid {label} field width")
    little = int.from_bytes(raw[:width], "little")
    big = int.from_bytes(raw[width:], "big")
    if little != big:
        raise ValueError(f"both-endian {label} mismatch: little={little}, big={big}")
    return little


def parse_directory_record(record: bytes) -> dict[str, Any]:
    if len(record) < 34:
        raise ValueError("directory record shorter than minimum length")
    record_len = record[0]
    if record_len != len(record):
        raise ValueError("directory record length does not match supplied bytes")
    name_len = record[32]
    if 33 + name_len > record_len:
        raise ValueError("directory identifier runs past record boundary")
    return {
        "record_length": record_len,
        "extended_attribute_length": record[1],
        "extent_lba": both_endian(record[2:10], 4, "extent LBA"),
        "data_length": both_endian(record[10:18], 4, "data length"),
        "recording_date_raw": record[18:25].hex(),
        "flags": record[25],
        "file_unit_size": record[26],
        "interleave_gap_size": record[27],
        "volume_sequence_number": both_endian(record[28:32], 2, "volume sequence"),
        "name_bytes": record[33:33 + name_len],
    }


def check_sector_headers(f: BinaryIO, total_sectors: int, max_findings: int = 40) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    findings: list[str] = []
    for lba in range(total_sectors):
        raw = read_raw_sector(f, lba, total_sectors)
        if raw[:12] != SYNC:
            counts["sync_mismatch"] += 1
            if len(findings) < max_findings:
                findings.append(f"LBA {lba}: invalid sync pattern")
        if raw[15] != 2:
            counts["non_mode2"] += 1
            if len(findings) < max_findings:
                findings.append(f"LBA {lba}: mode byte is {raw[15]}, expected 2")
        try:
            expected = expected_msf(lba)
            actual = bytes(bcd_to_int(x) for x in raw[12:15])
            expected_dec = bytes(bcd_to_int(x) for x in expected)
            if actual != expected_dec:
                counts["msf_mismatch"] += 1
                if len(findings) < max_findings:
                    findings.append(f"LBA {lba}: MSF header mismatch {raw[12:15].hex()} vs {expected.hex()}")
        except ValueError as exc:
            counts["invalid_msf"] += 1
            if len(findings) < max_findings:
                findings.append(f"LBA {lba}: {exc}")
        if raw[16:20] != raw[20:24]:
            counts["subheader_mismatch"] += 1
            if len(findings) < max_findings:
                findings.append(f"LBA {lba}: XA subheader copies differ")
        mode = raw[15]
        counts[f"mode_{mode}"] += 1
        if mode == 2:
            submode = raw[18]
            counts[f"submode_0x{submode:02x}"] += 1
            counts["form2_sectors"] += int(bool(submode & 0x20))
    return {
        "sector_count": total_sectors,
        "sector_size_bytes": SECTOR_SIZE,
        "header_counts": dict(sorted(counts.items())),
        "finding_count": sum(counts[k] for k in ("sync_mismatch", "non_mode2", "msf_mismatch", "invalid_msf", "subheader_mismatch")),
        "findings_truncated_to": max_findings,
        "findings": findings,
        "edc_ecc_verified": False,
    }


def extract_record_data(f: BinaryIO, rec: dict[str, Any], total_sectors: int, hard_limit: int) -> bytes:
    size = rec["data_length"]
    start_lba = rec["extent_lba"] + rec["extended_attribute_length"]
    if size > hard_limit:
        raise ValueError(f"entry size {size} exceeds configured limit {hard_limit}")
    if rec["file_unit_size"] or rec["interleave_gap_size"]:
        raise ValueError("interleaved file record is unsupported for content hashing")
    blocks = (size + BLOCK_SIZE - 1) // BLOCK_SIZE
    if start_lba < 0 or start_lba + blocks > total_sectors:
        raise ValueError(f"extent outside image: start={start_lba}, blocks={blocks}")
    chunks = []
    remaining = size
    for lba in range(start_lba, start_lba + blocks):
        block = read_block(f, lba, total_sectors)
        take = min(remaining, BLOCK_SIZE)
        chunks.append(block[:take])
        remaining -= take
    data = b"".join(chunks)
    if len(data) != size:
        raise ValueError("internal data-length mismatch")
    return data


def hash_record_data(f: BinaryIO, rec: dict[str, Any], total_sectors: int, hard_limit: int) -> str:
    size = rec["data_length"]
    start_lba = rec["extent_lba"] + rec["extended_attribute_length"]
    if size > hard_limit:
        raise ValueError(f"entry size {size} exceeds configured limit {hard_limit}")
    if rec["file_unit_size"] or rec["interleave_gap_size"]:
        raise ValueError("interleaved file record is unsupported for content hashing")
    blocks = (size + BLOCK_SIZE - 1) // BLOCK_SIZE
    if start_lba < 0 or start_lba + blocks > total_sectors:
        raise ValueError(f"extent outside image: start={start_lba}, blocks={blocks}")
    hasher = hashlib.sha256()
    remaining = size
    for lba in range(start_lba, start_lba + blocks):
        block = read_block(f, lba, total_sectors)
        take = min(remaining, BLOCK_SIZE)
        hasher.update(block[:take])
        remaining -= take
    if remaining:
        raise ValueError("short file content while hashing")
    return hasher.hexdigest()


def parse_iso(f: BinaryIO, total_sectors: int, max_entries: int, max_depth: int, max_file_size: int) -> dict[str, Any]:
    descriptors: list[dict[str, Any]] = []
    pvd: bytes | None = None
    descriptor_end: int | None = None
    for lba in range(16, min(total_sectors, 16 + 256)):
        block = read_block(f, lba, total_sectors)
        if block[1:6] != b"CD001" or block[6] != 1:
            raise ValueError(f"invalid volume descriptor signature/version at LBA {lba}")
        dtype = block[0]
        descriptors.append({"lba": lba, "type": dtype, "identifier": "CD001", "version": block[6]})
        if dtype == 1 and pvd is None:
            pvd = block
        if dtype == 255:
            descriptor_end = lba
            break
    if pvd is None or descriptor_end is None:
        raise ValueError("primary volume descriptor or volume descriptor terminator missing")
    volume_blocks = both_endian(pvd[80:88], 4, "volume space size")
    logical_block_size = both_endian(pvd[128:132], 2, "logical block size")
    path_table_size = both_endian(pvd[132:140], 4, "path table size")
    if logical_block_size != BLOCK_SIZE:
        raise ValueError(f"unsupported logical block size {logical_block_size}")
    if volume_blocks > total_sectors:
        raise ValueError(f"volume reports {volume_blocks} blocks but image has {total_sectors} sectors")
    root_len = pvd[156]
    if root_len < 34 or 156 + root_len > BLOCK_SIZE:
        raise ValueError("invalid root directory record in primary volume descriptor")
    root_rec = parse_directory_record(pvd[156:156 + root_len])
    if not root_rec["flags"] & 0x02:
        raise ValueError("PVD root record is not marked as a directory")

    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_dirs: set[tuple[int, int]] = set()
    stack: list[tuple[str, dict[str, Any], int]] = [("", root_rec, 0)]
    boot_config: list[dict[str, str]] = []
    elf_candidates: list[dict[str, Any]] = []
    while stack:
        parent_path, directory_rec, depth = stack.pop()
        if depth > max_depth:
            errors.append(f"depth limit reached at {parent_path or '/'}")
            continue
        dir_start = directory_rec["extent_lba"] + directory_rec["extended_attribute_length"]
        dir_key = (dir_start, directory_rec["data_length"])
        if dir_key in seen_dirs:
            errors.append(f"directory cycle/duplicate extent: {parent_path or '/'} @ {dir_key}")
            continue
        seen_dirs.add(dir_key)
        try:
            raw_dir = extract_record_data(f, directory_rec, total_sectors, max_file_size)
        except ValueError as exc:
            errors.append(f"cannot read directory {parent_path or '/'}: {exc}")
            continue
        pos = 0
        children: list[tuple[str, dict[str, Any], int]] = []
        while pos < len(raw_dir):
            rec_len = raw_dir[pos]
            if rec_len == 0:
                pos = ((pos // BLOCK_SIZE) + 1) * BLOCK_SIZE
                continue
            if rec_len < 34 or pos + rec_len > len(raw_dir) or (pos % BLOCK_SIZE) + rec_len > BLOCK_SIZE:
                errors.append(f"invalid directory record length at {parent_path or '/'} offset {pos}: {rec_len}")
                # Move to next block boundary to avoid infinite loops on corrupt data.
                pos = ((pos // BLOCK_SIZE) + 1) * BLOCK_SIZE
                continue
            try:
                rec = parse_directory_record(raw_dir[pos:pos + rec_len])
            except ValueError as exc:
                errors.append(f"invalid directory record at {parent_path or '/'} offset {pos}: {exc}")
                pos += rec_len
                continue
            pos += rec_len
            name_b = rec.pop("name_bytes")
            if name_b in (b"\x00", b"\x01"):
                continue
            name = name_b.decode("ascii", "replace")
            if not name or "/" in name or "\\" in name or len(name) > MAX_PATH_CHARS:
                errors.append(f"invalid path component at {parent_path or '/'}: {name!r}")
                continue
            path = f"{parent_path}/{name}" if parent_path else name
            is_dir = bool(rec["flags"] & 0x02)
            row: dict[str, Any] = {
                "path": path,
                "name": name,
                "type": "directory" if is_dir else "file",
                "extent_lba": rec["extent_lba"],
                "data_lba": rec["extent_lba"] + rec["extended_attribute_length"],
                "size_bytes": rec["data_length"],
                "flags_hex": f"0x{rec['flags']:02x}",
                "extended_attribute_length": rec["extended_attribute_length"],
                "file_unit_size": rec["file_unit_size"],
                "interleave_gap_size": rec["interleave_gap_size"],
                "sha256": "",
                "hash_status": "not_applicable",
                "notes": "",
            }
            if rec["flags"] & 0x80:
                row["notes"] = "multi-extent flag set; extent-chain aggregation not implemented"
                row["hash_status"] = "skipped_multi_extent"
            elif rec["file_unit_size"] or rec["interleave_gap_size"]:
                row["notes"] = "interleaved extent; payload hash not computed"
                row["hash_status"] = "skipped_interleaved"
            elif not is_dir:
                try:
                    row["sha256"] = hash_record_data(f, rec, volume_blocks, max_file_size)
                    row["hash_status"] = "passed"
                    if name.upper().startswith("SYSTEM.CNF"):
                        data = extract_record_data(f, rec, volume_blocks, min(max_file_size, 1024 * 1024))
                        boot_config.append({"path": path, "text": data.decode("ascii", "replace").strip()})
                    if rec["data_length"] >= 4:
                        first = extract_record_data(f, {**rec, "data_length": min(rec["data_length"], 64)}, volume_blocks, max_file_size)
                        if first.startswith(b"\x7fELF"):
                            elf_candidates.append({
                                "path": path,
                                "extent_lba": row["data_lba"],
                                "size_bytes": rec["data_length"],
                                "sha256": row["sha256"],
                                "elf_ident_hex": first[:16].hex(),
                            })
                except ValueError as exc:
                    row["notes"] = str(exc)
                    row["hash_status"] = "error"
                    errors.append(f"{path}: {exc}")
            entries.append(row)
            if len(entries) > max_entries:
                raise ValueError(f"entry count exceeds configured limit {max_entries}")
            if is_dir:
                children.append((path, rec, depth + 1))
        stack.extend(reversed(children))
    return {
        "volume_descriptor_lbas": descriptors,
        "volume_descriptor_terminator_lba": descriptor_end,
        "system_identifier": pvd[8:40].decode("ascii", "replace").rstrip(" \x00"),
        "volume_identifier": pvd[40:72].decode("ascii", "replace").rstrip(" \x00"),
        "volume_space_size_blocks": volume_blocks,
        "logical_block_size_bytes": logical_block_size,
        "path_table_size_bytes": path_table_size,
        "path_table_locations": {
            "type_l_lba": int.from_bytes(pvd[140:144], "little"),
            "optional_type_l_lba": int.from_bytes(pvd[144:148], "little"),
            "type_m_lba": int.from_bytes(pvd[148:152], "big"),
            "optional_type_m_lba": int.from_bytes(pvd[152:156], "big"),
        },
        "root_directory": {
            "extent_lba": root_rec["extent_lba"],
            "size_bytes": root_rec["data_length"],
        },
        "entries": entries,
        "entry_count": len(entries),
        "file_count": sum(1 for e in entries if e["type"] == "file"),
        "directory_count": sum(1 for e in entries if e["type"] == "directory"),
        "content_hash_errors": sum(1 for e in entries if e["hash_status"] == "error"),
        "boot_config": boot_config,
        "elf_candidates": elf_candidates,
        "inventory_errors": errors,
    }


def sha256_path(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="read-only raw BIN image with 2352-byte Mode 2 sectors")
    parser.add_argument("--json", type=Path, required=True, help="write JSON report")
    parser.add_argument("--csv", type=Path, required=True, help="write CSV file manifest")
    parser.add_argument("--max-entries", type=int, default=100000)
    parser.add_argument("--max-depth", type=int, default=32)
    parser.add_argument("--max-file-size", type=int, default=2 * 1024 * 1024 * 1024)
    args = parser.parse_args(argv)
    if args.max_entries < 1 or args.max_depth < 0 or args.max_file_size < 0:
        parser.error("limits must be positive (depth may be zero)")
    image_size = args.image.stat().st_size
    if image_size == 0 or image_size % SECTOR_SIZE:
        print(f"ERROR: image size {image_size} is not a positive multiple of {SECTOR_SIZE}", file=sys.stderr)
        return 2
    total_sectors = image_size // SECTOR_SIZE
    try:
        with args.image.open("rb") as f:
            print(f"Scanning {total_sectors} raw sectors for header consistency...", file=sys.stderr)
            sector_report = check_sector_headers(f, total_sectors)
            print("Reading ISO9660-style descriptors and inventorying file records...", file=sys.stderr)
            iso_report = parse_iso(f, total_sectors, args.max_entries, args.max_depth, args.max_file_size)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    report = {
        "image_name": args.image.name,
        "image_size_bytes": image_size,
        "image_sha256": sha256_path(args.image),
        "sector_scan": sector_report,
        "iso9660_style_inventory": iso_report,
        "limitations": [
            "CD-ROM EDC/ECC checksums were not validated.",
            "A filesystem inventory does not establish media authenticity or regional identity.",
            "Multi-extent ISO files are flagged but not aggregated into one logical file.",
            "This tool inventories bytes and metadata; it does not execute disc code or decode game assets.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with args.csv.open("w", newline="", encoding="utf-8") as out:
        fields = ["path", "name", "type", "extent_lba", "data_lba", "size_bytes", "flags_hex", "extended_attribute_length", "file_unit_size", "interleave_gap_size", "sha256", "hash_status", "notes"]
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(iso_report["entries"])
    print(json.dumps({
        "image_sha256": report["image_sha256"],
        "sector_count": sector_report["sector_count"],
        "sector_header_findings": sector_report["finding_count"],
        "system_identifier": iso_report["system_identifier"],
        "volume_blocks": iso_report["volume_space_size_blocks"],
        "file_count": iso_report["file_count"],
        "directory_count": iso_report["directory_count"],
        "elf_candidates": iso_report["elf_candidates"],
        "inventory_errors": len(iso_report["inventory_errors"]),
    }, indent=2))
    # Sector-header anomalies and directory/hash errors are reported in the JSON.
    return 0 if not sector_report["finding_count"] and not iso_report["inventory_errors"] else 3

if __name__ == "__main__":
    raise SystemExit(main())
