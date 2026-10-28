import sys
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
