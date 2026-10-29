from __future__ import annotations

import csv
import hashlib
import importlib.util
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/audit_snd2_sequence_loader.py"
SPEC = importlib.util.spec_from_file_location("audit_snd2_sequence_loader", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def _section(name_offset: int, section_type: int, flags: int, address: int,
             file_offset: int, size: int, alignment: int = 1) -> bytes:
    return struct.pack("<IIIIIIIIII", name_offset, section_type, flags, address,
                       file_offset, size, 0, 0, alignment, 0)


def _synthetic_elf_and_manifest(tmp_path: Path) -> tuple[bytes, dict[str, dict[str, str]]]:
    file_size = 0x680
    data = bytearray(file_size)
    data[:16] = b"\x7fELF" + bytes([1, 1, 1]) + bytes(9)
    # ELF32 little-endian, ET_EXEC, EM_MIPS, no program header table.
    struct.pack_into("<HHIIIIIHHHHHH", data, 16, 2, 8, 1, 0x100000, 0,
                     0x40, 0, 52, 32, 0, 40, 5, 4)

    shstr = b"\0.data\0.rodata\0.sdata\0.shstrtab\0"
    data[0x580:0x580 + len(shstr)] = shstr
    section_table = b"".join([
        bytes(40),
        _section(1, 1, 3, module.POINTER_TABLE_VA, 0x200, 18 * 4, 4),
        _section(7, 1, 2, 0x0032A650, 0x300, 0x180, 1),
        _section(15, 1, 3, 0x00335E90, 0x500, 0x40, 4),
        _section(22, 3, 0, 0, 0x580, len(shstr), 1),
    ])
    data[0x40:0x40 + len(section_table)] = section_table

    names = [f"sq_{i:03d}.sq" for i in range(1, 18)]
    string_addresses: dict[str, int] = {}
    cursor = 8
    for name in names:
        string_addresses[name] = 0x0032A650 + cursor
        raw = name.encode("ascii") + b"\0"
        data[0x300 + cursor:0x300 + cursor + len(raw)] = raw
        cursor += 0x10
    pointers = []
    for index in range(18):
        name = "sq_010.sq" if index == 10 else names[index if index < 10 else index - 1]
        pointers.append(string_addresses[name])
    for index, pointer in enumerate(pointers):
        struct.pack_into("<I", data, 0x200 + index * 4, pointer)

    shared_strings = {
        0x0032A768: "snd2/se.hd",
        0x0032A778: "snd2/se.bd",
        0x0032A7A8: "snd2/inst.hd",
        0x0032A7B8: "snd2/inst.bd",
    }
    for virtual_address, value in shared_strings.items():
        offset = 0x300 + virtual_address - 0x0032A650
        raw = value.encode("ascii") + b"\0"
        data[offset:offset + len(raw)] = raw
    data[0x500 + module.PATH_FORMAT_VA - 0x00335E90:
         0x500 + module.PATH_FORMAT_VA - 0x00335E90 + len(b"%s%s\0")] = b"%s%s\0"
    data[0x500 + module.PATH_PREFIX_VA - 0x00335E90:
         0x500 + module.PATH_PREFIX_VA - 0x00335E90 + len(b"snd2/\0")] = b"snd2/\0"

    elf_bytes = bytes(data)
    digest = hashlib.sha256(elf_bytes).hexdigest()
    records: dict[str, dict[str, str]] = {
        module.EXPECTED_ELF_MANIFEST_PATH.upper(): {
            "path": module.EXPECTED_ELF_MANIFEST_PATH, "type": "file",
            "size_bytes": str(len(elf_bytes)), "sha256": digest,
        }
    }
    for name in set(names):
        path = f"SND2/{name.upper()};1"
        records[path] = {"path": path, "type": "file", "size_bytes": "1234",
                         "sha256": hashlib.sha256(name.encode()).hexdigest()}
    for name in ("SE.HD", "SE.BD", "INST.HD", "INST.BD"):
        path = f"SND2/{name};1"
        records[path] = {"path": path, "type": "file", "size_bytes": "2345",
                         "sha256": hashlib.sha256(name.encode()).hexdigest()}
    return elf_bytes, records


def test_audit_snd2_table_finds_18_slots_17_names_and_one_duplicate(tmp_path: Path) -> None:
    elf_bytes, manifest = _synthetic_elf_and_manifest(tmp_path)
    rows, summary = module.audit_snd2_elf(elf_bytes, manifest)
    assert len(rows) == 18
    assert summary["unique_sequence_names"] == 17
    assert rows[0]["logical_path"] == "snd2/sq_001.sq"
    assert rows[0]["resolved_iso_path"] == "SND2/SQ_001.SQ;1"
    assert rows[9]["logical_filename"] == rows[10]["logical_filename"] == "sq_010.sq"
    assert rows[9]["string_va"] == rows[10]["string_va"] == "0x0032A6E8"
    assert rows[10]["duplicate_of_slot"] == 9
    assert summary["empty_optional_slots_from_initializer"] == list(range(18, 32))
    assert summary["current_sequence_path"] == "SND2/SQ_001.SQ;1"
    assert summary["current_sequence_also_appears_in_optional_list"] is True
    assert summary["path_format"]["value"] == "%s%s"
    assert summary["path_prefix"]["value"] == "snd2/"
    assert [entry["role"] for entry in summary["shared_resource_paths"]] == [
        "se_hd", "se_bd", "inst_hd", "inst_bd",
    ]
    assert all(entry["manifest_status"] == "present" for entry in summary["shared_resource_paths"])


def test_audit_snd2_rejects_elf_hash_not_matching_manifest(tmp_path: Path) -> None:
    elf_bytes, manifest = _synthetic_elf_and_manifest(tmp_path)
    manifest[module.EXPECTED_ELF_MANIFEST_PATH.upper()]["sha256"] = "0" * 64
    try:
        module.audit_snd2_elf(elf_bytes, manifest)
    except module.Snd2AuditError as exc:
        assert "SHA-256" in str(exc)
    else:
        raise AssertionError("mismatched executable hash must be rejected")
