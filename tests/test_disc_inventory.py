import sys
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import disc_inventory as inv


def test_bcd_round_trip_for_msf_component_range():
    for value in range(60):
        assert inv.bcd_to_int(inv.int_to_bcd(value)) == value


def test_bcd_rejects_invalid_digit():
    with pytest.raises(ValueError):
        inv.bcd_to_int(0x6A)


def test_expected_msf_starts_at_two_seconds():
    assert inv.expected_msf(0) == bytes.fromhex("000200")
    assert inv.expected_msf(75) == bytes.fromhex("000300")
    assert inv.expected_msf(16) == bytes.fromhex("000216")


def test_both_endian_accepts_consistent_field():
    value = 0x12345678
    raw = value.to_bytes(4, "little") + value.to_bytes(4, "big")
    assert inv.both_endian(raw, 4, "test") == value


def test_both_endian_rejects_disagreement():
    raw = (22).to_bytes(4, "little") + (23).to_bytes(4, "big")
    with pytest.raises(ValueError, match="mismatch"):
        inv.both_endian(raw, 4, "test")


def test_directory_record_parses_root_record():
    # Minimal ISO9660 root record: extent 22, size 2048, directory flag, id 0.
    extent = 22
    size = 2048
    rec = bytearray(34)
    rec[0] = 34
    rec[1] = 0
    rec[2:6] = extent.to_bytes(4, "little")
    rec[6:10] = extent.to_bytes(4, "big")
    rec[10:14] = size.to_bytes(4, "little")
    rec[14:18] = size.to_bytes(4, "big")
    rec[25] = 0x02
    rec[28:30] = (1).to_bytes(2, "little")
    rec[30:32] = (1).to_bytes(2, "big")
    rec[32] = 1
    rec[33] = 0
    parsed = inv.parse_directory_record(bytes(rec))
    assert parsed["extent_lba"] == 22
    assert parsed["data_length"] == 2048
    assert parsed["flags"] == 0x02
    assert parsed["name_bytes"] == b"\x00"


def test_directory_record_rejects_too_short_record():
    with pytest.raises(ValueError, match="shorter than minimum"):
        inv.parse_directory_record(b"\x00" * 20)


def make_mode2_sector(lba=0, submode=0x08):
    raw = bytearray(inv.SECTOR_SIZE)
    raw[:12] = inv.SYNC
    raw[12:15] = inv.expected_msf(lba)
    raw[15] = 2
    raw[16:20] = bytes((0, 0, submode, 0))
    raw[20:24] = raw[16:20]
    raw[24:24 + inv.BLOCK_SIZE] = b"A" * inv.BLOCK_SIZE
    return bytes(raw)


def test_read_block_accepts_valid_mode2_form1(tmp_path):
    path = tmp_path / "sector.bin"
    path.write_bytes(make_mode2_sector())
    with path.open("rb") as f:
        assert inv.read_block(f, 0, 1) == b"A" * inv.BLOCK_SIZE


def test_read_block_rejects_different_subheader_copies(tmp_path):
    raw = bytearray(make_mode2_sector())
    raw[20] ^= 1
    path = tmp_path / "bad_subheader.bin"
    path.write_bytes(raw)
    with path.open("rb") as f, pytest.raises(ValueError, match="subheaders differ"):
        inv.read_block(f, 0, 1)


def test_read_block_rejects_form2_sector(tmp_path):
    path = tmp_path / "form2.bin"
    path.write_bytes(make_mode2_sector(submode=0x28))
    with path.open("rb") as f, pytest.raises(ValueError, match="Form 2"):
        inv.read_block(f, 0, 1)


def test_sector_scan_detects_bad_msf(tmp_path):
    raw = bytearray(make_mode2_sector())
    raw[12:15] = bytes.fromhex("000201")
    path = tmp_path / "bad_msf.bin"
    path.write_bytes(raw)
    with path.open("rb") as f:
        report = inv.check_sector_headers(f, 1)
    assert report["header_counts"]["msf_mismatch"] == 1
    assert report["finding_count"] == 1


def make_valid_mode2_form1_sector(lba=0):
    raw = bytearray(make_mode2_sector(lba=lba))
    # Use a nontrivial subheader and payload so parity tests exercise real data.
    raw[16:20] = bytes((1, 2, 0x08, 0))
    raw[20:24] = raw[16:20]
    for index in range(2048):
        raw[24 + index] = (index * 37 + 11) & 0xFF
    raw[2072:2076] = inv.cdrom_edc(bytes(raw[16:2072])).to_bytes(4, "little")
    p_source = bytearray(raw[12:2076])
    p_source[:4] = b"\x00" * 4
    raw[2076:2248] = inv.cdrom_ecc(bytes(p_source), 86, 24, 2, 86)
    q_source = bytearray(raw[12:2248])
    q_source[:4] = b"\x00" * 4
    raw[2248:2352] = inv.cdrom_ecc(bytes(q_source), 52, 43, 86, 88)
    return bytes(raw)


def test_mode2_form1_edc_and_ecc_accept_valid_sector():
    assert inv.verify_mode2_form1_sector(make_valid_mode2_form1_sector()) == {
        "edc_ok": True,
        "ecc_p_ok": True,
        "ecc_q_ok": True,
    }


def test_mode2_form1_edc_and_ecc_detect_payload_corruption():
    raw = bytearray(make_valid_mode2_form1_sector())
    raw[900] ^= 0x40
    assert inv.verify_mode2_form1_sector(bytes(raw)) == {
        "edc_ok": False,
        "ecc_p_ok": False,
        "ecc_q_ok": False,
    }


def test_mode2_form1_rejects_bad_subheader():
    raw = bytearray(make_valid_mode2_form1_sector())
    raw[20] ^= 1
    with pytest.raises(ValueError, match="subheader copies differ"):
        inv.verify_mode2_form1_sector(bytes(raw))


def _path_entry(name, extent, parent, endian):
    name = bytes(name)
    record = bytearray((len(name), 0))
    record += extent.to_bytes(4, endian)
    record += parent.to_bytes(2, endian)
    record += name
    if len(name) & 1:
        record += b"\x00"
    return bytes(record)


def test_path_table_parses_root_and_child_in_both_endiannesses():
    for endian in ("little", "big"):
        raw = _path_entry(b"\x00", 22, 1, endian) + _path_entry(b"DATA", 27, 1, endian)
        parsed = inv.parse_path_table(raw, endian)
        assert [entry["extent_lba"] for entry in parsed] == [22, 27]
        assert [entry["parent_index"] for entry in parsed] == [1, 1]
        assert [entry["identifier"] for entry in parsed] == ["", "DATA"]


def test_path_table_rejects_forward_parent_reference():
    raw = _path_entry(b"\x00", 22, 1, "little") + _path_entry(b"DATA", 27, 3, "little")
    with pytest.raises(ValueError, match="invalid parent index"):
        inv.parse_path_table(raw, "little")


def test_extent_checker_finds_overlap_and_out_of_volume_extent():
    entries = [
        {"path": "A.BIN;1", "type": "file", "extent_lba": 10, "size_bytes": 4096,
         "extended_attribute_length": 0, "file_unit_size": 0, "interleave_gap_size": 0},
        {"path": "B.BIN;1", "type": "file", "extent_lba": 11, "size_bytes": 2048,
         "extended_attribute_length": 0, "file_unit_size": 0, "interleave_gap_size": 0},
        {"path": "C.BIN;1", "type": "file", "extent_lba": 99, "size_bytes": 4096,
         "extended_attribute_length": 0, "file_unit_size": 0, "interleave_gap_size": 0},
    ]
    report = inv.check_extent_overlaps(entries, {"extent_lba": 1, "size_bytes": 2048}, 100)
    assert report["overlap_count"] == 1
    assert report["out_of_volume_count"] == 1
    assert report["overlaps"][0]["first"] == "A.BIN;1"
    assert report["overlaps"][0]["second"] == "B.BIN;1"


@pytest.mark.skipif(not (shutil.which("cc") or shutil.which("clang")),
                    reason="native C compiler is unavailable")
def test_native_edc_ecc_scanner_accepts_valid_sector(tmp_path):
    path = tmp_path / "valid_form1.bin"
    path.write_bytes(make_valid_mode2_form1_sector())
    report = inv.check_sector_edc_ecc_native(path)
    assert report["eligible_data_sector_count"] == 1
    assert report["failure_count"] == 0
    assert report["all_eligible_sectors_verified"] is True


@pytest.mark.skipif(not (shutil.which("cc") or shutil.which("clang")),
                    reason="native C compiler is unavailable")
def test_native_edc_ecc_scanner_flags_corrupted_sector(tmp_path):
    raw = bytearray(make_valid_mode2_form1_sector())
    raw[900] ^= 0x80
    path = tmp_path / "corrupt_form1.bin"
    path.write_bytes(raw)
    report = inv.check_sector_edc_ecc_native(path)
    assert report["eligible_data_sector_count"] == 1
    assert report["failure_count"] == 3
    assert report["all_eligible_sectors_verified"] is False


@pytest.mark.skipif(not (shutil.which("cc") or shutil.which("clang")),
                    reason="native C compiler is unavailable")
def test_native_edc_ecc_scanner_rejects_unsupported_form2_sector(tmp_path):
    path = tmp_path / "unsupported_form2.bin"
    path.write_bytes(make_mode2_sector(submode=0x28))
    report = inv.check_sector_edc_ecc_native(path)
    assert report["eligible_data_sector_count"] == 0
    assert report["unsupported_sector_types_present"] is True
    assert report["all_eligible_sectors_verified"] is False


def test_inventory_cli_fails_if_edc_checker_reports_unsupported_sector(monkeypatch, tmp_path):
    image = tmp_path / "synthetic.bin"
    image.write_bytes(b"\x00" * inv.SECTOR_SIZE)
    monkeypatch.setattr(inv, "check_sector_headers", lambda _f, total: {
        "sector_count": total, "finding_count": 0, "header_counts": {},
        "findings_truncated_to": 40, "findings": [],
        "edc_ecc_checked_by_header_scanner": False,
    })
    monkeypatch.setattr(inv, "check_sector_edc_ecc_native", lambda _path: {
        "sector_count": 1, "eligible_data_sector_count": 0,
        "counts": {"skipped_form2_unsupported": 1}, "failure_count": 0,
        "finding_count": 0, "findings_truncated_to": 100, "findings": [],
        "unsupported_sector_types_present": True,
        "all_eligible_sectors_verified": False,
    })
    monkeypatch.setattr(inv, "parse_iso", lambda *_args: {
        "system_identifier": "TEST", "volume_space_size_blocks": 1,
        "file_count": 0, "directory_count": 0, "entries": [],
        "inventory_errors": [], "elf_candidates": [],
        "path_table_integrity": {"error_count": 0},
        "extent_integrity": {"overlap_count": 0, "error_count": 0},
    })
    status = inv.main([
        str(image), "--json", str(tmp_path / "report.json"),
        "--csv", str(tmp_path / "manifest.csv"),
    ])
    assert status == 3
