from __future__ import annotations

import importlib.util
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("iop_module_inventory_under_test", ROOT / "tools/iop_module_inventory.py")
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
IopElfError = _MODULE.IopElfError
parse_irx = _MODULE.parse_irx

ELF_HEADER = struct.Struct("<16sHHIIIIIHHHHHH")
SECTION_HEADER = struct.Struct("<IIIIIIIIII")
SYMBOL = struct.Struct("<IIIBBH")


def make_test_irx() -> bytes:
    """Build a minimal ELF32-LE PS2 IRX with one exported text function."""
    text_offset = 0x80
    text = b"\x00\x00\x00\x00\x08\x00\xe0\x03"
    shstr = b"\0.text\0.shstrtab\0.strtab\0.symtab\0"
    shnames = {
        ".text": shstr.index(b".text"),
        ".shstrtab": shstr.index(b".shstrtab"),
        ".strtab": shstr.index(b".strtab"),
        ".symtab": shstr.index(b".symtab"),
    }
    strtab = b"\0start\0AdpcmPlay\0"
    adpcm_name_offset = strtab.index(b"AdpcmPlay")
    symbols = b"\0" * SYMBOL.size + SYMBOL.pack(1, 0x1000, 4, 0x12, 0, 1)
    symbols += SYMBOL.pack(adpcm_name_offset, 0x1004, 4, 0x12, 0, 1)
    strtab_offset = text_offset + len(text)
    shstr_offset = strtab_offset + len(strtab)
    symtab_offset = (shstr_offset + len(shstr) + 3) & ~3
    shoff = (symtab_offset + len(symbols) + 3) & ~3
    sections = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (shnames[".text"], 1, 6, 0x1000, text_offset, len(text), 0, 0, 4, 0),
        (shnames[".shstrtab"], 3, 0, 0, shstr_offset, len(shstr), 0, 0, 1, 0),
        (shnames[".strtab"], 3, 0, 0, strtab_offset, len(strtab), 0, 0, 1, 0),
        (shnames[".symtab"], 2, 0, 0, symtab_offset, len(symbols), 3, 1, 4, SYMBOL.size),
    ]
    data = bytearray(shoff + len(sections) * SECTION_HEADER.size)
    ident = b"\x7fELF" + bytes((1, 1, 1, 0, 0)) + bytes(7)
    data[:ELF_HEADER.size] = ELF_HEADER.pack(
        ident, 0xFF80, 8, 1, 0, 0, shoff, 1, ELF_HEADER.size, 0, 0,
        SECTION_HEADER.size, len(sections), 2,
    )
    data[text_offset:text_offset + len(text)] = text
    data[strtab_offset:strtab_offset + len(strtab)] = strtab
    data[shstr_offset:shstr_offset + len(shstr)] = shstr
    data[symtab_offset:symtab_offset + len(symbols)] = symbols
    for i, section in enumerate(sections):
        begin = shoff + i * SECTION_HEADER.size
        data[begin:begin + SECTION_HEADER.size] = SECTION_HEADER.pack(*section)
    return bytes(data)


def test_irx_parser_recovers_text_function_symbols_and_hash() -> None:
    result = parse_irx(make_test_irx(), "MODULES/TEST.IRX;1")
    assert result["path"] == "MODULES/TEST.IRX;1"
    assert result["elf_type"] == "0xFF80"
    assert result["function_symbol_count"] == 2
    assert [item["name"] for item in result["function_symbols"]] == ["start", "AdpcmPlay"]
    assert result["contains_mdebug"] is False
    assert result["contains_symbol_table"] is True
    assert len(result["sha256"]) == 64


def test_irx_parser_rejects_non_elf() -> None:
    with pytest.raises(IopElfError, match="shorter than an ELF32 header"):
        parse_irx(b"not an elf")


def test_irx_parser_rejects_wrong_machine_or_type() -> None:
    data = bytearray(make_test_irx())
    # e_type and e_machine are immediately after e_ident.
    struct.pack_into("<H", data, 16, 2)
    with pytest.raises(IopElfError, match="expected PS2 IRX/MIPS"):
        parse_irx(bytes(data))


def test_irx_parser_rejects_out_of_bounds_section_table() -> None:
    data = bytearray(make_test_irx())
    # e_shoff is offset 32 in the ELF32 header.
    struct.pack_into("<I", data, 32, len(data) + 64)
    with pytest.raises(IopElfError, match="section table lies outside"):
        parse_irx(bytes(data))


def test_irx_parser_rejects_invalid_symbol_string_table_link() -> None:
    data = bytearray(make_test_irx())
    shoff = struct.unpack_from("<I", data, 32)[0]
    symtab_header = shoff + 4 * SECTION_HEADER.size
    # sh_link is the 7th uint32 field in the section header.
    struct.pack_into("<I", data, symtab_header + 24, 99)
    with pytest.raises(IopElfError, match="does not link to a valid string table"):
        parse_irx(bytes(data))
