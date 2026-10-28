#!/usr/bin/env python3
"""Conservative static control-flow index for a little-endian MIPS/R5900 ELF.

This parser recognizes only control-transfer encodings with stable MIPS opcode
fields. It deliberately does not decode R5900 multimedia instructions or infer
function boundaries from prologues. The output is an index of observed encoded
transfers, not a complete disassembly or proof of runtime behavior.
"""
from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import elf_recon  # noqa: E402

SHT_NOBITS = 8
SHF_EXECINSTR = 0x4


def _sign_extend_16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def decode_control_transfer(word: int, pc: int) -> dict[str, Any] | None:
    """Decode only MIPS control transfers identifiable from the instruction word.

    `pc` is the virtual address of the instruction. Delay-slot semantics are not
    emulated; each result reports `delay_slot_address` where relevant.
    """
    word &= 0xFFFFFFFF
    opcode = (word >> 26) & 0x3F
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    funct = word & 0x3F
    imm = word & 0xFFFF

    def branch(kind: str) -> dict[str, Any]:
        return {
            "kind": kind,
            "target": (pc + 4 + (_sign_extend_16(imm) << 2)) & 0xFFFFFFFF,
            "delay_slot_address": (pc + 4) & 0xFFFFFFFF,
            "opcode": opcode,
            "rs": rs,
            "rt": rt,
        }

    if opcode in (0x02, 0x03):  # J / JAL
        target = (((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)) & 0xFFFFFFFF
        return {
            "kind": "direct_jump" if opcode == 0x02 else "direct_call",
            "target": target,
            "delay_slot_address": (pc + 4) & 0xFFFFFFFF,
            "opcode": opcode,
            "rs": rs,
            "rt": rt,
        }

    if opcode == 0x00:
        if funct == 0x08:  # JR
            return {
                "kind": "return" if rs == 31 else "indirect_jump",
                "target": None,
                "delay_slot_address": (pc + 4) & 0xFFFFFFFF,
                "opcode": opcode,
                "rs": rs,
                "rt": rt,
            }
        if funct == 0x09:  # JALR
            rd = (word >> 11) & 0x1F
            return {
                "kind": "indirect_call",
                "target": None,
                "delay_slot_address": (pc + 4) & 0xFFFFFFFF,
                "opcode": opcode,
                "rs": rs,
                "rt": rt,
                "rd": rd,
            }

    if opcode == 0x01 and rt in (0x10, 0x11, 0x12, 0x13):  # BLTZAL/BGEZAL variants
        return branch("conditional_call")

    branch_opcodes = {
        0x04: "conditional_branch",  # BEQ
        0x05: "conditional_branch",  # BNE
        0x06: "conditional_branch",  # BLEZ
        0x07: "conditional_branch",  # BGTZ
        0x14: "conditional_branch",  # BEQL
        0x15: "conditional_branch",  # BNEL
        0x16: "conditional_branch",  # BLEZL
        0x17: "conditional_branch",  # BGTZL
    }
    if opcode in branch_opcodes:
        return branch(branch_opcodes[opcode])

    # COP1/COP2 branch encodings use rs=8. The condition-code details are not
    # needed to recover their statically encoded relative target.
    if opcode in (0x11, 0x12) and rs == 0x08:
        return branch("coprocessor_branch")

    return None


def executable_regions(elf: dict[str, Any]) -> list[dict[str, Any]]:
    """Return bounded, file-backed executable section ranges."""
    regions = []
    for section in elf["sections"]:
        if not (section["flags"] & SHF_EXECINSTR):
            continue
        if section["type"] == SHT_NOBITS or section["size"] == 0:
            regions.append({**section, "scan_status": "skipped_empty_or_nobits"})
            continue
        # Custom DVP overlay sections share VMA 0 and may hold code/data for a
        # different execution domain. Do not interpret them as ordinary EE code.
        if section["name"].startswith(".DVP.overlay."):
            regions.append({**section, "scan_status": "excluded_unmapped_overlay"})
            continue
        if section["address"] == 0:
            regions.append({**section, "scan_status": "excluded_zero_virtual_address"})
            continue
        if section["type"] >= 0x70000000 and section["type"] != SHT_NOBITS:
            regions.append({**section, "scan_status": "excluded_processor_specific_section_type"})
            continue
        if section["address"] & 0x3:
            # Do not silently assume that a misaligned section uses normal words.
            regions.append({**section, "scan_status": "skipped_misaligned_virtual_address"})
            continue
        regions.append({**section, "scan_status": "scanned"})
    return regions


def _find_section(address: int, regions: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [r for r in regions if r["scan_status"] == "scanned"
                  and r["address"] <= address < r["address"] + r["size"]]
    if not candidates:
        return None
    # Prefer the most specific section over the large monolithic .text section.
    return min(candidates, key=lambda r: (r["size"], r["index"]))


def analyze_control_flow(elf: dict[str, Any], payload: bytes) -> dict[str, Any]:
    regions = executable_regions(elf)
    transfers: list[dict[str, Any]] = []
    region_findings: list[str] = []
    scanned_words = 0
    scanned_bytes = 0

    scanned_regions = [r for r in regions if r["scan_status"] == "scanned"]
    excluded_region_overlaps: list[dict[str, Any]] = []
    for i, left in enumerate(regions):
        if left["size"] == 0:
            continue
        l0, l1 = left["address"], left["address"] + left["size"]
        for right in regions[i + 1:]:
            if right["size"] == 0:
                continue
            r0, r1 = right["address"], right["address"] + right["size"]
            overlap_start, overlap_end = max(l0, r0), min(l1, r1)
            if overlap_start < overlap_end:
                finding = {
                    "section_a": left["name"],
                    "section_a_scan_status": left["scan_status"],
                    "section_b": right["name"],
                    "section_b_scan_status": right["scan_status"],
                    "overlap_start": f"0x{overlap_start:08x}",
                    "overlap_end_exclusive": f"0x{overlap_end:08x}",
                }
                if left["scan_status"] == "scanned" and right["scan_status"] == "scanned":
                    region_findings.append(
                        f"executable-section virtual overlap: {left['name']} and {right['name']}"
                    )
                else:
                    excluded_region_overlaps.append(finding)

    for region in regions:
        if region["scan_status"] != "scanned":
            continue
        file_off = region["file_offset"]
        size = region["size"]
        # parse_elf32_le validates section ranges; retain a local defensive check.
        if file_off < 0 or size < 0 or file_off > len(payload) or size > len(payload) - file_off:
            raise elf_recon.ELFFormatError(f"executable section {region['name']} outside ELF file")
        aligned_size = size - (size % 4)
        scanned_bytes += aligned_size
        scanned_words += aligned_size // 4
        for byte_delta in range(0, aligned_size, 4):
            word = struct.unpack_from("<I", payload, file_off + byte_delta)[0]
            pc = region["address"] + byte_delta
            decoded = decode_control_transfer(word, pc)
            if not decoded:
                continue
            target = decoded["target"]
            target_section = _find_section(target, regions) if target is not None else None
            transfers.append({
                "source_address": pc,
                "source_section_index": region["index"],
                "source_section": region["name"] or f"section_{region['index']}",
                "source_section_offset": byte_delta,
                "instruction_word": f"0x{word:08x}",
                "kind": decoded["kind"],
                "target_address": target,
                "target_section_index": target_section["index"] if target_section else None,
                "target_section": target_section["name"] if target_section else None,
                "delay_slot_address": decoded["delay_slot_address"],
                "rs": decoded.get("rs"),
                "rt": decoded.get("rt"),
                "rd": decoded.get("rd"),
            })

    counts = Counter(item["kind"] for item in transfers)
    incoming_calls: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in transfers:
        if item["kind"] in ("direct_call", "conditional_call") and item["target_address"] is not None:
            incoming_calls[item["target_address"]].append(item)

    function_candidates: list[dict[str, Any]] = []
    seeds: dict[int, str] = {elf["entry_point"]: "ELF entry point"}
    for transfer in transfers:
        if transfer["kind"] in ("direct_call", "conditional_call") and transfer["target_address"] is not None:
            seeds.setdefault(transfer["target_address"], "direct call target")
    for address, evidence in sorted(seeds.items()):
        section = _find_section(address, regions)
        if section and section["name"].startswith(".gnu.linkonce.t.") and section["address"] == address:
            label = section["name"][len(".gnu.linkonce.t."):]
            label_kind = "retained_linkonce_section_label"
        else:
            label = f"sub_{address:08x}"
            label_kind = "generated_candidate_label"
        calls = incoming_calls.get(address, [])
        sources = sorted({f"{call['source_section']}@0x{call['source_address']:08x}" for call in calls})
        function_candidates.append({
            "address": f"0x{address:08x}",
            "candidate_label": label,
            "label_kind": label_kind,
            "evidence": evidence,
            "containing_section": section["name"] if section else None,
            "incoming_direct_call_count": len(calls),
            "incoming_direct_call_sites": ";".join(sources),
            "semantic_identity": "unresolved; control-transfer evidence only",
        })

    return {
        "method": "conservative fixed-width MIPS control-transfer opcode scan",
        "source_binary_sha256": __import__("hashlib").sha256(payload).hexdigest(),
        "processor_model": "not a full R5900 decoder; no execution or delay-slot emulation",
        "executable_section_count": len(regions),
        "scanned_executable_section_count": sum(r["scan_status"] == "scanned" for r in regions),
        "skipped_sections": [
            {"index": r["index"], "name": r["name"], "status": r["scan_status"],
             "virtual_address": f"0x{r['address']:08x}",
             "file_offset": f"0x{r['file_offset']:08x}", "size": r["size"],
             "section_type": r["type"], "flags_hex": f"0x{r['flags']:x}"}
            for r in regions if r["scan_status"] != "scanned"
        ],
        "scanned_instruction_words": scanned_words,
        "scanned_instruction_bytes": scanned_bytes,
        "control_transfer_count": len(transfers),
        "transfer_counts_by_kind": dict(sorted(counts.items())),
        "unique_direct_call_targets": len(incoming_calls),
        "function_entry_candidates": len(function_candidates),
        "executable_section_overlap_findings": region_findings,
        "excluded_region_overlap_findings": excluded_region_overlaps,
        "coverage_notes": [
            "The scan recognizes direct J/JAL, JR/JALR, common integer branches, branch-and-link variants, and COP1/COP2 branch fields.",
            "The scan includes the main .text section and retained .gnu.linkonce.t.* sections; custom .DVP.overlay.* sections at VMA 0 are excluded from EE instruction scanning.",
            "It does not decode other instructions, emulate delay slots, recover indirect-call targets, or establish function boundaries.",
            "Many calls originate from the monolithic .text section, so source function identities for those sites remain unresolved.",
            "Direct-call targets are function-entry candidates, not verified function boundaries or semantic names.",
        ],
        "transfers": transfers,
        "function_candidates": function_candidates,
    }


def write_outputs(result: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "static_control_flow.json"
    json_path.write_text(json.dumps({k: v for k, v in result.items()
                                    if k not in ("transfers", "function_candidates")}, indent=2) + "\n",
                          encoding="utf-8")
    transfer_fields = [
        "source_address", "source_section", "source_section_offset", "instruction_word",
        "kind", "target_address", "target_section", "delay_slot_address", "rs", "rt", "rd",
    ]
    with (out_dir / "control_transfers.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=transfer_fields, lineterminator="\n")
        writer.writeheader()
        for item in result["transfers"]:
            row = dict(item)
            for key in ("source_address", "delay_slot_address"):
                row[key] = f"0x{row[key]:08x}" if row[key] is not None else ""
            if row["target_address"] is not None:
                row["target_address"] = f"0x{row['target_address']:08x}"
            writer.writerow({key: row.get(key) for key in transfer_fields})
    candidate_fields = [
        "address", "candidate_label", "label_kind", "evidence", "containing_section",
        "incoming_direct_call_count", "incoming_direct_call_sites", "semantic_identity",
    ]
    with (out_dir / "function_entry_candidates.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=candidate_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(result["function_candidates"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="raw 2352-byte-sector BIN image")
    parser.add_argument("--boot-path", default="SLES_517.41;1")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        _, payload = elf_recon.inspect_boot_elf(args.image, args.boot_path)
        elf = elf_recon.parse_elf32_le(payload)
        result = analyze_control_flow(elf, payload)
        write_outputs(result, args.out_dir)
        print(json.dumps({k: result[k] for k in (
            "source_binary_sha256", "scanned_executable_section_count", "scanned_instruction_words",
            "control_transfer_count", "transfer_counts_by_kind", "unique_direct_call_targets",
            "function_entry_candidates", "executable_section_overlap_findings",
        )}, indent=2))
        return 0
    except (OSError, ValueError, elf_recon.ELFFormatError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
