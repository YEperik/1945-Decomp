#!/usr/bin/env python3
"""Read-only integrity inventory of a 2352-byte-sector PlayStation disc image.

The tool validates raw-sector headers and XA Form 1 EDC/ECC, parses the
ISO9660-style volume descriptors and path tables, checks extent bounds and
overlaps, and hashes file payloads without extracting original file contents.
These checks do not prove PlayStation-specific full conformance or authenticity.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, BinaryIO

SECTOR_SIZE = 2352
USER_DATA_OFFSET = 24
BLOCK_SIZE = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
MAX_PATH_CHARS = 4096
EDC_POLY = 0xD8018001


def _make_edc_lut() -> tuple[int, ...]:
    table = []
    for value in range(256):
        remainder = value
        for _ in range(8):
            remainder = (remainder >> 1) ^ (EDC_POLY if remainder & 1 else 0)
        table.append(remainder)
    return tuple(table)


EDC_LUT = _make_edc_lut()


def _make_ecc_luts() -> tuple[tuple[int, ...], tuple[int, ...]]:
    forward = [0] * 256
    backward = [0] * 256
    for value in range(256):
        doubled = value << 1
        if doubled & 0x100:
            doubled ^= 0x11D
        forward[value] = doubled
        backward[value ^ doubled] = value
    return tuple(forward), tuple(backward)


ECC_FORWARD, ECC_BACKWARD = _make_ecc_luts()


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
        "edc_ecc_checked_by_header_scanner": False,
    }


def cdrom_edc(data: bytes) -> int:
    """Compute the CD-ROM EDC CRC (reflected polynomial 0xD8018001)."""
    value = 0
    for byte in data:
        value = (value >> 8) ^ EDC_LUT[(value ^ byte) & 0xFF]
    return value


def cdrom_ecc(data: bytes, major_count: int, minor_count: int,
              major_mult: int, minor_inc: int) -> bytes:
    """Calculate one CD-ROM Reed-Solomon ECC parity block."""
    expected_len = major_count * minor_count
    if len(data) != expected_len:
        raise ValueError(f"ECC source length {len(data)} != expected {expected_len}")
    if major_mult <= 0 or minor_inc <= 0:
        raise ValueError("ECC strides must be positive")
    parity = bytearray(major_count * 2)
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        ecc_a = 0
        ecc_b = 0
        for _ in range(minor_count):
            symbol = data[index]
            index += minor_inc
            if index >= expected_len:
                index -= expected_len
            ecc_a ^= symbol
            ecc_b ^= symbol
            ecc_a = ECC_FORWARD[ecc_a]
        ecc_a = ECC_BACKWARD[ECC_FORWARD[ecc_a] ^ ecc_b]
        parity[major] = ecc_a
        parity[major + major_count] = ecc_a ^ ecc_b
    return bytes(parity)


def verify_mode2_form1_sector(raw: bytes) -> dict[str, bool]:
    """Check EDC, P parity and Q parity in a raw Mode 2 Form 1 sector.

    XA Form 1 layout: duplicated subheader at 16..23, 2048 user bytes at
    24..2071, EDC at 2072..2075, P parity at 2076..2247 and Q parity at
    2248..2351. Mode 2 ECC is computed with the four address bytes zeroed.
    """
    if len(raw) != SECTOR_SIZE:
        raise ValueError("raw sector must be exactly 2352 bytes")
    if raw[15] != 2:
        raise ValueError("sector is not Mode 2")
    if raw[18] & 0x20:
        raise ValueError("Mode 2 Form 2 sector is unsupported by this verifier")
    if raw[16:20] != raw[20:24]:
        raise ValueError("XA subheader copies differ")

    expected_edc = cdrom_edc(raw[16:2072]).to_bytes(4, "little")
    edc_ok = raw[2072:2076] == expected_edc

    p_source = bytearray(raw[12:2076])
    p_source[:4] = b"\x00" * 4
    expected_p = cdrom_ecc(bytes(p_source), 86, 24, 2, 86)
    p_ok = raw[2076:2248] == expected_p

    q_source = bytearray(raw[12:2248])
    q_source[:4] = b"\x00" * 4
    expected_q = cdrom_ecc(bytes(q_source), 52, 43, 86, 88)
    q_ok = raw[2248:2352] == expected_q
    return {"edc_ok": edc_ok, "ecc_p_ok": p_ok, "ecc_q_ok": q_ok}


def check_sector_edc_ecc(f: BinaryIO, total_sectors: int,
                         max_findings: int = 100) -> dict[str, Any]:
    """Verify stored EDC/P/Q checks on Mode 2 Form 1 data sectors.

    Sectors whose XA submode does not mark them as data are explicitly
    counted as skipped; Form 2 sectors are reported as unsupported, not
    silently treated as verified.
    """
    counts: Counter[str] = Counter()
    findings: list[dict[str, Any]] = []
    for lba in range(total_sectors):
        raw = read_raw_sector(f, lba, total_sectors)
        if raw[15] != 2:
            counts["skipped_non_mode2"] += 1
            continue
        submode = raw[18]
        if not (submode & 0x08):
            counts["skipped_non_data"] += 1
            continue
        if submode & 0x20:
            counts["skipped_form2_unsupported"] += 1
            continue
        counts["form1_data_sectors_checked"] += 1
        try:
            result = verify_mode2_form1_sector(raw)
        except ValueError as exc:
            counts["sector_verification_errors"] += 1
            if len(findings) < max_findings:
                findings.append({"lba": lba, "error": str(exc)})
            continue
        for key, ok in result.items():
            label = key.removesuffix("_ok")
            counts[f"{label}_{'passed' if ok else 'failed'}"] += 1
            if not ok and len(findings) < max_findings:
                findings.append({"lba": lba, "failed_check": label})
    failures = sum(v for k, v in counts.items() if k.endswith("_failed")) + counts["sector_verification_errors"]
    unsupported = counts["skipped_form2_unsupported"] > 0 or counts["skipped_non_mode2"] > 0
    return {
        "sector_count": total_sectors,
        "eligible_data_sector_count": counts["form1_data_sectors_checked"],
        "counts": dict(sorted(counts.items())),
        "failure_count": failures,
        "finding_count": failures,
        "findings_truncated_to": max_findings,
        "findings": findings,
        "unsupported_sector_types_present": unsupported,
        "all_eligible_sectors_verified": failures == 0 and not unsupported,
    }


def check_sector_edc_ecc_native(image_path: Path) -> dict[str, Any]:
    """Run the C accelerator for full-disc EDC/ECC verification.

    The pure-Python reference implementation remains available for tests and
    small samples. Full disc images use the compiled implementation because
    evaluating every parity symbol in Python is impractically slow.
    The helper binary is cached under the system temp directory, never in the
    project repository.
    """
    compiler = os.environ.get("CC") or shutil.which("cc") or shutil.which("clang")
    if not compiler:
        raise RuntimeError(
            "full-disc EDC/ECC verification requires a C compiler (cc or clang); "
            "no checks were skipped or represented as passed"
        )
    source = Path(__file__).with_name("cdrom_integrity.c")
    if not source.is_file():
        raise RuntimeError(f"native EDC/ECC source is missing: {source}")
    source_id = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    cache_dir = Path(tempfile.gettempdir()) / "1945-native-port-tools"
    cache_dir.mkdir(parents=True, exist_ok=True)
    executable = cache_dir / f"cdrom_integrity_{source_id}"
    if not executable.is_file():
        built = subprocess.run(
            [compiler, "-O3", "-std=c11", "-Wall", "-Wextra", "-Werror",
             str(source), "-o", str(executable)],
            text=True, capture_output=True, check=False,
        )
        if built.returncode != 0:
            raise RuntimeError(
                f"failed to build native EDC/ECC verifier with {compiler}:\n"
                f"{built.stdout}{built.stderr}"
            )
    result = subprocess.run(
        [str(executable), str(image_path)], text=True,
        capture_output=True, check=False,
    )
    if result.returncode not in (0, 3):
        raise RuntimeError(
            f"native EDC/ECC verifier failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"native EDC/ECC verifier returned invalid JSON: {exc}") from exc
    report["implementation"] = "C accelerator (source tools/cdrom_integrity.c)"
    return report


def read_volume_bytes(f: BinaryIO, start_lba: int, byte_count: int,
                      volume_blocks: int) -> bytes:
    if start_lba < 0 or byte_count < 0:
        raise ValueError("negative path-table location or size")
    if byte_count > volume_blocks * BLOCK_SIZE:
        raise ValueError("path table size exceeds declared volume capacity")
    block_count = (byte_count + BLOCK_SIZE - 1) // BLOCK_SIZE
    if start_lba + block_count > volume_blocks:
        raise ValueError("path table extends beyond declared volume")
    out = bytearray()
    for lba in range(start_lba, start_lba + block_count):
        out.extend(read_block(f, lba, volume_blocks))
    return bytes(out[:byte_count])


def parse_path_table(raw: bytes, endian: str) -> list[dict[str, Any]]:
    """Parse an ISO9660 path table, validating bounds and parent indices."""
    if endian not in ("little", "big"):
        raise ValueError("path table endian must be 'little' or 'big'")
    entries: list[dict[str, Any]] = []
    pos = 0
    while pos < len(raw):
        if len(raw) - pos < 8:
            raise ValueError(f"truncated path table header at byte {pos}")
        name_len = raw[pos]
        ext_attr_len = raw[pos + 1]
        if name_len == 0:
            raise ValueError(f"zero-length path table identifier at byte {pos}")
        total_len = 8 + name_len + (name_len & 1)
        if pos + total_len > len(raw):
            raise ValueError(f"path table identifier overruns table at byte {pos}")
        extent_lba = int.from_bytes(raw[pos + 2:pos + 6], endian)
        parent_index = int.from_bytes(raw[pos + 6:pos + 8], endian)
        name = raw[pos + 8:pos + 8 + name_len]
        idx = len(entries) + 1
        if idx == 1:
            if name != b"\x00" or parent_index != 1:
                raise ValueError("first path table entry is not a valid root entry")
        elif parent_index < 1 or parent_index >= idx:
            raise ValueError(f"invalid parent index {parent_index} for path entry {idx}")
        entries.append({
            "index": idx,
            "identifier_hex": name.hex(),
            "identifier": "" if name == b"\x00" else name.decode("ascii", "replace"),
            "extent_lba": extent_lba,
            "extended_attribute_length": ext_attr_len,
            "parent_index": parent_index,
        })
        pos += total_len
    return entries


def check_path_tables(f: BinaryIO, volume_blocks: int, path_table_size: int,
                      path_locations: dict[str, int], root_extent_lba: int,
                      directory_entries: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    tables: dict[str, list[dict[str, Any]]] = {}
    variants = (
        ("type_l", "little", "type_l_lba", False),
        ("optional_type_l", "little", "optional_type_l_lba", True),
        ("type_m", "big", "type_m_lba", False),
        ("optional_type_m", "big", "optional_type_m_lba", True),
    )
    if path_table_size <= 0:
        errors.append("primary volume descriptor declares an empty path table")
    for name, endian, field, optional in variants:
        lba = path_locations[field]
        if not lba and optional:
            continue
        if not lba:
            errors.append(f"required {name} path table location is zero")
            continue
        try:
            raw = read_volume_bytes(f, lba, path_table_size, volume_blocks)
            tables[name] = parse_path_table(raw, endian)
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
    primary = tables.get("type_l")
    if primary:
        if primary[0]["extent_lba"] != root_extent_lba:
            errors.append("Type L path-table root extent disagrees with PVD root directory extent")
        if primary[0]["extended_attribute_length"] != 0:
            errors.append("Type L path-table root has unexpected extended-attribute length")
        for name in ("optional_type_l", "type_m", "optional_type_m"):
            other = tables.get(name)
            if other is not None and other != primary:
                errors.append(f"{name} path table disagrees with Type L path table")
        resolved: list[dict[str, Any]] = []
        for entry in primary:
            if entry["index"] == 1:
                path = ""
            else:
                parent = resolved[entry["parent_index"] - 1]
                component = entry["identifier"]
                path = f"{parent['path']}/{component}" if parent["path"] else component
            resolved.append({**entry, "path": path})
        actual_dirs = {"": root_extent_lba}
        for entry in directory_entries:
            if entry["type"] == "directory":
                actual_dirs[entry["path"]] = entry["extent_lba"]
        path_dirs = {entry["path"]: entry["extent_lba"] for entry in resolved}
        missing_from_table = sorted(set(actual_dirs) - set(path_dirs))
        extra_in_table = sorted(set(path_dirs) - set(actual_dirs))
        extent_mismatches = sorted(
            path for path in set(actual_dirs) & set(path_dirs)
            if actual_dirs[path] != path_dirs[path]
        )
        if missing_from_table:
            errors.append(f"directories missing from path table: {missing_from_table[:20]}")
        if extra_in_table:
            errors.append(f"path-table directories absent from walked tree: {extra_in_table[:20]}")
        if extent_mismatches:
            errors.append(f"directory extent mismatches: {extent_mismatches[:20]}")
    expected_tables = {"type_l", "type_m"}
    if path_locations["optional_type_l_lba"]:
        expected_tables.add("optional_type_l")
    if path_locations["optional_type_m_lba"]:
        expected_tables.add("optional_type_m")
    table_copies = [tables.get(name) for name in sorted(expected_tables)]
    tables_match = (
        expected_tables.issubset(tables)
        and bool(table_copies)
        and all(table == tables.get("type_l") for table in table_copies)
    )
    return {
        "path_table_size_bytes": path_table_size,
        "locations": path_locations,
        "table_entry_counts": {k: len(v) for k, v in tables.items()},
        "tables_parsed": sorted(tables),
        "tables_match": tables_match,
        "directory_tree_crosscheck": "passed" if primary and not any(
            e.startswith(("directories missing", "path-table directories absent", "directory extent mismatches"))
            for e in errors
        ) else "failed_or_unavailable",
        "error_count": len(errors),
        "errors": errors,
        "entries": resolved if primary else [],
    }


def check_extent_overlaps(entries: list[dict[str, Any]], root_directory: dict[str, Any],
                          volume_blocks: int, max_findings: int = 100) -> dict[str, Any]:
    """Detect out-of-volume extents and overlaps between directory/file records."""
    ranges: list[dict[str, Any]] = [{
        "path": "<ROOT>", "type": "directory", "start_lba": root_directory["extent_lba"],
        "end_lba_exclusive": root_directory["extent_lba"] +
            (root_directory["size_bytes"] + BLOCK_SIZE - 1) // BLOCK_SIZE,
    }]
    errors: list[str] = []
    skipped_interleaved = 0
    for entry in entries:
        if entry.get("file_unit_size", 0) or entry.get("interleave_gap_size", 0):
            skipped_interleaved += 1
            continue
        start = int(entry["extent_lba"])
        ext_attr = int(entry.get("extended_attribute_length", 0))
        size = int(entry["size_bytes"])
        data_blocks = (size + BLOCK_SIZE - 1) // BLOCK_SIZE
        end = start + ext_attr + data_blocks
        if start < 0 or end > volume_blocks:
            errors.append(f"{entry['path']}: extent [{start}, {end}) is outside volume [0, {volume_blocks})")
        if end > start:
            ranges.append({"path": entry["path"], "type": entry["type"], "start_lba": start,
                           "end_lba_exclusive": end})
    ranges.sort(key=lambda r: (r["start_lba"], r["end_lba_exclusive"], r["path"]))
    overlaps: list[dict[str, Any]] = []
    active: list[dict[str, Any]] = []
    for current in ranges:
        active = [old for old in active if old["end_lba_exclusive"] > current["start_lba"]]
        for old in active:
            overlap_start = max(old["start_lba"], current["start_lba"])
            overlap_end = min(old["end_lba_exclusive"], current["end_lba_exclusive"])
            if overlap_start < overlap_end:
                if len(overlaps) < max_findings:
                    overlaps.append({
                        "first": old["path"], "second": current["path"],
                        "start_lba": overlap_start, "end_lba_exclusive": overlap_end,
                        "overlap_blocks": overlap_end - overlap_start,
                    })
                errors.append(f"extent overlap: {old['path']} and {current['path']} at [{overlap_start}, {overlap_end})")
        active.append(current)
    return {
        "volume_blocks": volume_blocks,
        "record_extent_count": len(ranges),
        "out_of_volume_count": sum(1 for e in errors if "outside volume" in e),
        "overlap_count": sum(1 for e in errors if "extent overlap:" in e),
        "overlaps_truncated_to": max_findings,
        "overlaps": overlaps,
        "interleaved_records_skipped": skipped_interleaved,
        "error_count": len(errors),
        "errors": errors[:max_findings],
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
    path_table_locations = {
        "type_l_lba": int.from_bytes(pvd[140:144], "little"),
        "optional_type_l_lba": int.from_bytes(pvd[144:148], "little"),
        "type_m_lba": int.from_bytes(pvd[148:152], "big"),
        "optional_type_m_lba": int.from_bytes(pvd[152:156], "big"),
    }
    path_table_report = check_path_tables(
        f, volume_blocks, path_table_size, path_table_locations,
        root_rec["extent_lba"], entries,
    )
    extent_report = check_extent_overlaps(
        entries,
        {"extent_lba": root_rec["extent_lba"], "size_bytes": root_rec["data_length"]},
        volume_blocks,
    )
    return {
        "volume_descriptor_lbas": descriptors,
        "volume_descriptor_terminator_lba": descriptor_end,
        "system_identifier": pvd[8:40].decode("ascii", "replace").rstrip(" \x00"),
        "volume_identifier": pvd[40:72].decode("ascii", "replace").rstrip(" \x00"),
        "volume_space_size_blocks": volume_blocks,
        "logical_block_size_bytes": logical_block_size,
        "path_table_size_bytes": path_table_size,
        "path_table_locations": path_table_locations,
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
        "path_table_integrity": path_table_report,
        "extent_integrity": extent_report,
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
            print("Verifying EDC/ECC on Mode 2 Form 1 data sectors...", file=sys.stderr)
            edc_ecc_report = check_sector_edc_ecc_native(args.image)
            print("Reading ISO9660-style descriptors, path tables, extents and file records...", file=sys.stderr)
            iso_report = parse_iso(f, total_sectors, args.max_entries, args.max_depth, args.max_file_size)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    report = {
        "image_name": args.image.name,
        "image_size_bytes": image_size,
        "image_sha256": sha256_path(args.image),
        "sector_scan": sector_report,
        "sector_edc_ecc": edc_ecc_report,
        "iso9660_style_inventory": iso_report,
        "limitations": [
            "Mode 2 Form 1 data-sector EDC/P/Q checks are verified; non-data sectors are skipped and Mode 2 Form 2 sectors are reported as unsupported.",
            "A filesystem inventory does not establish media authenticity or regional identity.",
            "Multi-extent ISO files are flagged but not aggregated into one logical file.",
            "Extent overlap checks cover the contiguous extents represented by directory records; interleaved records are skipped and reported.",
            "This tool inventories bytes and metadata; it does not execute disc code or decode game assets.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with args.csv.open("w", newline="", encoding="utf-8") as out:
        fields = ["path", "name", "type", "extent_lba", "data_lba", "size_bytes", "flags_hex", "extended_attribute_length", "file_unit_size", "interleave_gap_size", "sha256", "hash_status", "notes"]
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(iso_report["entries"])
    print(json.dumps({
        "image_sha256": report["image_sha256"],
        "sector_count": sector_report["sector_count"],
        "sector_header_findings": sector_report["finding_count"],
        "edc_ecc_eligible_sectors": edc_ecc_report["eligible_data_sector_count"],
        "edc_ecc_failures": edc_ecc_report["failure_count"],
        "edc_ecc_unsupported_sector_types_present": edc_ecc_report["unsupported_sector_types_present"],
        "edc_ecc_all_eligible_sectors_verified": edc_ecc_report["all_eligible_sectors_verified"],
        "system_identifier": iso_report["system_identifier"],
        "volume_blocks": iso_report["volume_space_size_blocks"],
        "file_count": iso_report["file_count"],
        "directory_count": iso_report["directory_count"],
        "path_table_error_count": iso_report["path_table_integrity"]["error_count"],
        "extent_overlap_count": iso_report["extent_integrity"]["overlap_count"],
        "extent_error_count": iso_report["extent_integrity"]["error_count"],
        "elf_candidates": iso_report["elf_candidates"],
        "inventory_errors": len(iso_report["inventory_errors"]),
    }, indent=2))
    # All enabled integrity gates contribute to the command's result code.
    integrity_errors = (
        sector_report["finding_count"]
        + edc_ecc_report["failure_count"]
        + int(edc_ecc_report["unsupported_sector_types_present"])
        + len(iso_report["inventory_errors"])
        + iso_report["path_table_integrity"]["error_count"]
        + iso_report["extent_integrity"]["error_count"]
    )
    return 0 if integrity_errors == 0 else 3

if __name__ == "__main__":
    raise SystemExit(main())
