import struct
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import elf_recon  # noqa: E402


def make_elf32_le_header(*, phoff=0, phentsize=0, phnum=0, shoff=0,
                         shentsize=0, shnum=0, shstrndx=0, ident_data=1):
    ident = bytearray(16)
    ident[:4] = b"\x7fELF"
    ident[4] = 1
    ident[5] = ident_data
    ident[6] = 1
    header = struct.pack(
        "<HHIIIIIHHHHHH",
        2, 8, 1, 0x00100008, phoff, shoff, 0x20924001,
        52, phentsize, phnum, shentsize, shnum, shstrndx,
    )
    return bytes(ident) + header


def test_parse_minimal_elf32_le_header():
    parsed = elf_recon.parse_elf32_le(make_elf32_le_header())
    assert parsed["elf_class"] == "ELF32"
    assert parsed["endianness"] == "little"
    assert parsed["type"] == 2
    assert parsed["machine"] == 8
    assert parsed["entry_point"] == 0x00100008
    assert parsed["program_headers"] == []
    assert parsed["sections"] == []


def test_parse_elf_rejects_bad_magic():
    data = bytearray(make_elf32_le_header())
    data[0] = 0
    with pytest.raises(elf_recon.ELFFormatError, match="missing ELF magic"):
        elf_recon.parse_elf32_le(bytes(data))


def test_parse_elf_rejects_big_endian_header():
    with pytest.raises(elf_recon.ELFFormatError, match="little-endian"):
        elf_recon.parse_elf32_le(make_elf32_le_header(ident_data=2))


def test_parse_elf_rejects_truncated_program_header_table():
    data = make_elf32_le_header(phoff=52, phentsize=32, phnum=1)
    with pytest.raises(elf_recon.ELFFormatError, match="program header table"):
        elf_recon.parse_elf32_le(data)


def test_parse_elf_rejects_small_header():
    with pytest.raises(elf_recon.ELFFormatError, match="shorter than 52-byte"):
        elf_recon.parse_elf32_le(b"\x7fELF")


def test_string_leads_prioritize_functional_debug_labels():
    data = b"PLAYER\x00STAGE\x00SetBossTbl\x00JumpForStage\x00"
    found = elf_recon.find_interesting_strings(data, max_results=3)
    assert [item["text"] for item in found] == ["SetBossTbl", "JumpForStage", "PLAYER"]
