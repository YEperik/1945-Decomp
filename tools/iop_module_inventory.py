#!/usr/bin/env python3
"""Inventory symbols and ELF metadata for PS2 IOP IRX modules.

This tool reports function names, addresses, sizes, section layout and hashes;
it does not emit disassembly or recover copyrighted source code. The input disc
extraction must remain outside the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any

ELF_HEADER = struct.Struct("<16sHHIIIIIHHHHHH")
SECTION_HEADER = struct.Struct("<IIIIIIIIII")
SYMBOL = struct.Struct("<IIIBBH")
ET_PS2_IRX = 0xFF80
EM_MIPS = 8
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
STT_FUNC = 2
SHN_UNDEF = 0


class IopElfError(ValueError):
    """Malformed or unsupported ELF input."""


def _slice(data: bytes, offset: int, size: int, label: str) -> bytes:
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise IopElfError(f"{label} lies outside the file")
    return data[offset:offset + size]


def _cstring(table: bytes, offset: int, label: str) -> str:
    if offset < 0 or offset >= len(table):
        if offset == 0 and table:
            return ""
        raise IopElfError(f"{label} string offset is invalid")
    end = table.find(b"\0", offset)
    if end < 0:
        raise IopElfError(f"{label} string is not NUL-terminated")
    return table[offset:end].decode("utf-8", errors="replace")


def parse_irx(data: bytes, path: str = "<memory>") -> dict[str, Any]:
    if len(data) < ELF_HEADER.size:
        raise IopElfError("file is shorter than an ELF32 header")
    header = ELF_HEADER.unpack_from(data, 0)
    ident, e_type, e_machine, e_version, e_entry, e_phoff, e_shoff, e_flags, e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx = header
    if ident[:4] != b"\x7fELF" or ident[4] != 1 or ident[5] != 1:
        raise IopElfError("expected ELF32 little-endian input")
    if e_type != ET_PS2_IRX or e_machine != EM_MIPS:
        raise IopElfError(f"expected PS2 IRX/MIPS (type=0xFF80, machine=8), got type=0x{e_type:04X}, machine={e_machine}")
    if e_version != 1 or e_ehsize < ELF_HEADER.size:
        raise IopElfError("unsupported ELF version/header size")
    if e_shentsize < SECTION_HEADER.size or e_shnum == 0:
        raise IopElfError("section table is absent or uses an undersized entry")
    if e_shstrndx >= e_shnum:
        raise IopElfError("section-name string table index is out of range")
    section_bytes = _slice(data, e_shoff, e_shentsize * e_shnum, "section table")
    sections: list[dict[str, int]] = []
    for i in range(e_shnum):
        fields = SECTION_HEADER.unpack_from(section_bytes, i * e_shentsize)
        sections.append(dict(zip(("name_off", "type", "flags", "addr", "offset", "size", "link", "info", "align", "entsize"), fields)))
    name_section = sections[e_shstrndx]
    names_data = _slice(data, name_section["offset"], name_section["size"], "section-name string table")
    for section in sections:
        section["name"] = _cstring(names_data, section["name_off"], "section name") if section["name_off"] else ""
        if section["type"] != 8:  # SHT_NOBITS consumes no bytes in the file.
            _slice(data, section["offset"], section["size"], f"section {section['name'] or '<unnamed>'}")

    text_section = next((s for s in sections if s["name"] == ".text"), None)
    if text_section is None:
        raise IopElfError(".text section is missing")
    symbol_records: list[dict[str, Any]] = []
    for section in sections:
        if section["type"] != SHT_SYMTAB:
            continue
        if section["entsize"] < SYMBOL.size or section["size"] % section["entsize"] != 0:
            raise IopElfError("symbol table has invalid entry sizing")
        if section["link"] >= len(sections) or sections[section["link"]]["type"] != SHT_STRTAB:
            raise IopElfError("symbol table does not link to a valid string table")
        string_section = sections[section["link"]]
        strings = _slice(data, string_section["offset"], string_section["size"], "symbol string table")
        raw_symbols = _slice(data, section["offset"], section["size"], "symbol table")
        for offset in range(0, len(raw_symbols), section["entsize"]):
            st_name, st_value, st_size, st_info, st_other, st_shndx = SYMBOL.unpack_from(raw_symbols, offset)
            st_type = st_info & 0x0F
            st_bind = st_info >> 4
            if st_type != STT_FUNC or st_shndx in (SHN_UNDEF,) or st_size <= 0:
                continue
            # This report only retains regular function symbols that begin in .text.
            if st_shndx >= len(sections) or sections[st_shndx]["name"] != ".text":
                continue
            if st_value < text_section["addr"] or st_value - text_section["addr"] > text_section["size"]:
                continue
            if st_size > text_section["size"] - (st_value - text_section["addr"]):
                continue
            symbol_records.append({
                "name": _cstring(strings, st_name, "symbol name") if st_name else "",
                "address": st_value,
                "size_bytes": st_size,
                "binding": {0: "LOCAL", 1: "GLOBAL", 2: "WEAK"}.get(st_bind, f"BIND_{st_bind}"),
                "section": ".text",
            })

    symbol_records.sort(key=lambda s: (s["address"], s["name"]))
    deduplicated: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for symbol in symbol_records:
        key = (symbol["address"], symbol["name"])
        if key not in seen:
            seen.add(key)
            deduplicated.append(symbol)

    return {
        "path": path,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "elf_class": "ELF32",
        "endianness": "little",
        "elf_type": f"0x{e_type:04X}",
        "machine_id": e_machine,
        "machine": "MIPS R3000/IOP class",
        "elf_flags": f"0x{e_flags:08X}",
        "entry_point": e_entry,
        "sections": [
            {"name": s["name"], "type": s["type"], "address": s["addr"], "size_bytes": s["size"], "file_offset": s["offset"]}
            for s in sections if s["name"]
        ],
        "function_symbols": deduplicated,
        "function_symbol_count": len(deduplicated),
        "contains_mdebug": any(s["name"] == ".mdebug" and s["size"] > 0 for s in sections),
        "contains_symbol_table": any(s["type"] == SHT_SYMTAB for s in sections),
    }


def scan_disc_root(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"disc root is not a directory: {root}")
    modules = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name.upper().endswith(".IRX;1")):
        try:
            item = parse_irx(path.read_bytes(), path.relative_to(root).as_posix())
        except IopElfError as exc:
            modules.append({"path": path.relative_to(root).as_posix(), "status": "unsupported_or_invalid", "error": str(exc)})
        else:
            item["status"] = "parsed"
            modules.append(item)
    return {
        "schema_version": 1,
        "disc_root": "external extraction directory (not included in repository)",
        "module_count": len(modules),
        "parsed_module_count": sum(item.get("status") == "parsed" for item in modules),
        "modules": modules,
        "source_code_exported": False,
        "original_payload_bytes_embedded": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disc_root", type=Path, help="path to an external extracted disc directory")
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    args = parser.parse_args(argv)
    try:
        report = scan_disc_root(args.disc_root)
    except (OSError, ValueError, IopElfError) as exc:
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
