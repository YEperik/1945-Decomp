#!/usr/bin/env python3
"""Read-only ELF32 little-endian reconnaissance for the disc boot executable.

This tool extracts the executable named by SYSTEM.CNF into a temporary file,
validates ELF table bounds, summarizes load segments and sections, captures
selected strings as leads (not proof of behavior), and optionally runs LLVM's
MIPS disassembler on the entry range. It never executes the ELF.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any

sys_path = Path(__file__).resolve().parent
import sys
if str(sys_path) not in sys.path:
    sys.path.insert(0, str(sys_path))
import disc_inventory as inv  # noqa: E402

ELF_HEADER_SIZE = 52
PROGRAM_HEADER_SIZE = 32
SECTION_HEADER_SIZE = 40
PT_LOAD = 1
SHT_NOBITS = 8
SHT_SYMTAB = 2
SHT_DYNSYM = 11


class ELFFormatError(ValueError):
    """Raised for malformed or unsupported ELF metadata."""


def _bounded_range(offset: int, size: int, limit: int, label: str) -> None:
    if offset < 0 or size < 0 or offset > limit or size > limit - offset:
        raise ELFFormatError(f"{label} lies outside file bounds")


def parse_elf32_le(data: bytes) -> dict[str, Any]:
    """Parse core ELF32-LE metadata without executing or loading the ELF."""
    if len(data) < ELF_HEADER_SIZE:
        raise ELFFormatError("ELF file shorter than 52-byte ELF32 header")
    ident = data[:16]
    if ident[:4] != b"\x7fELF":
        raise ELFFormatError("missing ELF magic")
    if ident[4] != 1 or ident[5] != 1:
        raise ELFFormatError("only ELF32 little-endian inputs are supported")
    if ident[6] != 1:
        raise ELFFormatError(f"unsupported ELF ident version {ident[6]}")

    (e_type, e_machine, e_version, e_entry, e_phoff, e_shoff, e_flags,
     e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx) = struct.unpack_from(
        "<HHIIIIIHHHHHH", data, 16
    )
    if e_ehsize < ELF_HEADER_SIZE:
        raise ELFFormatError(f"ELF header size is too small: {e_ehsize}")
    if e_version != 1:
        raise ELFFormatError(f"unsupported ELF header version {e_version}")
    if e_phnum:
        if e_phentsize < PROGRAM_HEADER_SIZE:
            raise ELFFormatError("program header entry size is too small")
        _bounded_range(e_phoff, e_phentsize * e_phnum, len(data), "program header table")
    if e_shnum:
        if e_shentsize < SECTION_HEADER_SIZE:
            raise ELFFormatError("section header entry size is too small")
        _bounded_range(e_shoff, e_shentsize * e_shnum, len(data), "section header table")
        if e_shstrndx >= e_shnum:
            raise ELFFormatError("section-name string-table index is out of range")
    elif e_shoff or e_shstrndx not in (0, 0xFFFF):
        raise ELFFormatError("extended or inconsistent section-table metadata is unsupported")

    segments: list[dict[str, Any]] = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        (p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align) = struct.unpack_from(
            "<IIIIIIII", data, off
        )
        if p_type == PT_LOAD:
            _bounded_range(p_offset, p_filesz, len(data), f"load segment {i}")
            if p_memsz < p_filesz:
                raise ELFFormatError(f"load segment {i} has memory size smaller than file size")
        segments.append({
            "index": i, "type": p_type, "type_name": "LOAD" if p_type == PT_LOAD else f"PT_{p_type}",
            "file_offset": p_offset, "virtual_address": p_vaddr, "physical_address": p_paddr,
            "file_size": p_filesz, "memory_size": p_memsz, "flags_hex": f"0x{p_flags:x}",
            "alignment": p_align,
        })

    sections_raw = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        (sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size,
         sh_link, sh_info, sh_addralign, sh_entsize) = struct.unpack_from("<IIIIIIIIII", data, off)
        if sh_type != SHT_NOBITS and sh_size:
            _bounded_range(sh_offset, sh_size, len(data), f"section {i}")
        sections_raw.append({
            "index": i, "name_offset": sh_name, "type": sh_type,
            "flags": sh_flags, "address": sh_addr, "file_offset": sh_offset,
            "size": sh_size, "link": sh_link, "info": sh_info,
            "alignment": sh_addralign, "entry_size": sh_entsize,
        })

    names: bytes = b""
    if e_shnum:
        name_section = sections_raw[e_shstrndx]
        if name_section["type"] != 3:
            raise ELFFormatError("section-name table is not a string table")
        names = data[name_section["file_offset"]:name_section["file_offset"] + name_section["size"]]

    sections = []
    for section in sections_raw:
        name_offset = section.pop("name_offset")
        if not names:
            name = ""
        elif name_offset >= len(names):
            raise ELFFormatError(f"section {section['index']} name offset is out of range")
        else:
            end = names.find(b"\x00", name_offset)
            if end < 0:
                raise ELFFormatError(f"section {section['index']} name is unterminated")
            name = names[name_offset:end].decode("ascii", "replace")
        section["name"] = name
        sections.append(section)

    return {
        "elf_class": "ELF32", "endianness": "little", "type": e_type,
        "machine": e_machine, "version": e_version, "entry_point": e_entry,
        "program_header_offset": e_phoff, "program_header_count": e_phnum,
        "section_header_offset": e_shoff, "section_header_count": e_shnum,
        "section_name_table_index": e_shstrndx, "flags_hex": f"0x{e_flags:08x}",
        "program_headers": segments, "sections": sections,
        "symbol_table_sections": [s["name"] for s in sections if s["type"] in (SHT_SYMTAB, SHT_DYNSYM)],
    }


def find_interesting_strings(data: bytes, max_results: int = 120) -> list[dict[str, Any]]:
    priority_groups = (
        ("jumpforstage", "setbosstbl", "playerset", "player[].shotnum", "dataload error",
         "datatransfer", "bgm_stage", "bgm_boss", "sound_start", "sound_pause",
         "open tim", "quick_loadimage", "padinit", "mpeg error", "texture page",
         "texture window", "scepad", "scempeg", "errorstop"),
        ("boss", "bullet", "enemy", "shot", "weapon", "game over", "continue",
         "snd1\\", "snd2\\", ".pss", ".tim", ".sq", "host0:", "cdrom0:",
         "camera", "stage", "player", "sound", "bgm", "music", "texture",
         "sprite", "loadimage", "vram", "option"),
    )
    found: list[tuple[int, int, dict[str, Any]]] = []
    seen_text: set[str] = set()
    for match in re.finditer(rb"[\x20-\x7e]{4,}", data):
        raw = match.group(0)
        text = raw.decode("ascii", "replace")
        lower = text.lower()
        if text in seen_text:
            continue
        score = next((group_idx for group_idx, patterns in enumerate(priority_groups)
                      if any(pattern in lower for pattern in patterns)), None)
        if score is not None:
            seen_text.add(text)
            found.append((score, match.start(), {"file_offset": match.start(), "text": text[:300]}))
    found.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in found[:max_results]]


def _va_for_file_offset(segments: list[dict[str, Any]], file_offset: int) -> int | None:
    for segment in segments:
        if segment["type"] == PT_LOAD and segment["file_offset"] <= file_offset < segment["file_offset"] + segment["file_size"]:
            return segment["virtual_address"] + file_offset - segment["file_offset"]
    return None


def inspect_boot_elf(image_path: Path, boot_path: str, max_file_size: int = 16 * 1024 * 1024) -> tuple[dict[str, Any], bytes]:
    image_size = image_path.stat().st_size
    if image_size <= 0 or image_size % inv.SECTOR_SIZE:
        raise ValueError("raw BIN image is not a positive multiple of 2352 bytes")
    total_sectors = image_size // inv.SECTOR_SIZE
    with image_path.open("rb") as image:
        filesystem = inv.parse_iso(image, total_sectors, 100000, 32, max_file_size)
        entry = next((item for item in filesystem["entries"] if item["path"].upper() == boot_path.upper()), None)
        if entry is None:
            raise ValueError(f"boot ELF path not found in ISO inventory: {boot_path}")
        if entry["type"] != "file":
            raise ValueError(f"boot path is not a file: {boot_path}")
        record = {
            "extent_lba": entry["extent_lba"],
            "extended_attribute_length": entry["extended_attribute_length"],
            "data_length": entry["size_bytes"],
            "file_unit_size": entry["file_unit_size"],
            "interleave_gap_size": entry["interleave_gap_size"],
        }
        payload = inv.extract_record_data(image, record, total_sectors, max_file_size)
    if not payload.startswith(b"\x7fELF"):
        raise ValueError(f"entry does not start with ELF magic: {boot_path}")
    elf = parse_elf32_le(payload)
    if elf["machine"] != 8:
        raise ValueError(f"expected EM_MIPS (8), found {elf['machine']}")
    for segment in elf["program_headers"]:
        if segment["type"] == PT_LOAD and segment["file_offset"] + segment["file_size"] > len(payload):
            raise ELFFormatError("load segment content is truncated")
    sections_of_interest = {
        ".text", ".data", ".rodata", ".sdata", ".sbss", ".bss", ".reginfo",
        ".vutext", ".vudata", ".eh_frame", ".ctors", ".dtors", ".lit4", ".lit8",
    }
    summary_sections = [
        {"name": s["name"], "address": s["address"], "file_offset": s["file_offset"],
         "size": s["size"], "type": s["type"], "flags_hex": f"0x{s['flags']:x}"}
        for s in elf["sections"]
        if s["name"] in sections_of_interest or s["name"].startswith(".gnu.linkonce.t.__tf")
    ]
    all_names = [s["name"] for s in elf["sections"]]
    elf["named_code_sections"] = [
        {"name": s["name"], "address": s["address"], "file_offset": s["file_offset"],
         "size": s["size"], "type": s["type"], "flags_hex": f"0x{s['flags']:x}"}
        for s in elf["sections"] if s["name"].startswith(".gnu.linkonce.t.")
    ]
    elf["section_summary"] = summary_sections
    elf["section_name_counts"] = {
        "total_sections": len(all_names),
        "gnu_linkonce_text_sections": sum(name.startswith(".gnu.linkonce.t.") for name in all_names),
        "gnu_linkonce_data_sections": sum(name.startswith(".gnu.linkonce.d.") for name in all_names),
        "mangled_named_camera_or_renderer_sections": [
            name for name in all_names
            if name.startswith(".gnu.linkonce.t.") and any(word in name.lower() for word in ("camera", "cttm", "cframe"))
        ],
    }
    interesting = find_interesting_strings(payload)
    for item in interesting:
        item["virtual_address"] = _va_for_file_offset(elf["program_headers"], item["file_offset"])
    report = {
        "boot_path": boot_path,
        "boot_file_size": len(payload),
        "boot_sha256": hashlib.sha256(payload).hexdigest(),
        "filesystem_identity": {
            "system_identifier": filesystem["system_identifier"],
            "volume_blocks": filesystem["volume_space_size_blocks"],
            "path_table_error_count": filesystem["path_table_integrity"]["error_count"],
            "extent_error_count": filesystem["extent_integrity"]["error_count"],
        },
        "elf": {k: v for k, v in elf.items() if k not in ("sections",)},
        "selected_strings": interesting,
        "analysis_limitations": [
            "This is static metadata and disassembly reconnaissance, not an execution trace.",
            "The ELF is stripped of conventional symbol tables; section names and printable strings are leads, not proof of function behavior.",
            "LLVM's MIPS disassembler does not fully decode the R5900/Emotion Engine instruction set; unknown instructions are retained as unresolved evidence.",
            "The native Android runtime has not been implemented or tested.",
        ],
    }
    return report, payload


def make_entry_disassembly(payload: bytes, start: int, end: int, llvm_objdump: str) -> str:
    with tempfile.TemporaryDirectory(prefix="1945-elf-recon-") as tmp:
        elf_path = Path(tmp) / "boot.elf"
        elf_path.write_bytes(payload)
        proc = subprocess.run(
            [llvm_objdump, "-d", "--triple=mipsel-unknown-elf", "--mcpu=mips3",
             f"--start-address=0x{start:x}", f"--stop-address=0x{end:x}", str(elf_path)],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"llvm-objdump failed: {proc.stderr.strip()}")
        return (
            "# Static entry-range disassembly\n\n"
            "Tool: LLVM llvm-objdump, MIPS little-endian triple, generic MIPS III CPU\n"
            "Caution: this is not a complete R5900 decoder. Unknown instruction decodes are preserved.\n\n"
            + proc.stdout
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="raw 2352-byte-sector BIN image")
    parser.add_argument("--boot-path", default="SLES_517.41;1")
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--disassembly", type=Path)
    parser.add_argument("--start-address", type=lambda x: int(x, 0), default=0x00100000)
    parser.add_argument("--stop-address", type=lambda x: int(x, 0), default=0x00100200)
    parser.add_argument("--no-disassembly", action="store_true")
    args = parser.parse_args()
    try:
        report, payload = inspect_boot_elf(args.image, args.boot_path)
        if not args.no_disassembly and args.disassembly:
            objdump = shutil.which("llvm-objdump")
            if objdump:
                disassembly = make_entry_disassembly(payload, args.start_address, args.stop_address, objdump)
                args.disassembly.parent.mkdir(parents=True, exist_ok=True)
                args.disassembly.write_text(disassembly, encoding="utf-8")
                report["disassembly"] = {
                    "tool": objdump,
                    "start_address": f"0x{args.start_address:08x}",
                    "stop_address": f"0x{args.stop_address:08x}",
                    "unknown_instruction_markers": disassembly.count("<unknown>"),
                    "output_path": str(args.disassembly),
                }
            else:
                report["disassembly"] = {"status": "not run; llvm-objdump unavailable"}
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "boot_sha256": report["boot_sha256"],
            "entry_point": f"0x{report['elf']['entry_point']:08x}",
            "program_header_count": report["elf"]["program_header_count"],
            "section_header_count": report["elf"]["section_header_count"],
            "symbol_table_sections": report["elf"]["symbol_table_sections"],
            "load_segment_count": sum(1 for p in report["elf"]["program_headers"] if p["type"] == PT_LOAD),
            "interesting_strings": len(report["selected_strings"]),
            "disassembly": report.get("disassembly", {}).get("unknown_instruction_markers"),
        }, indent=2))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
