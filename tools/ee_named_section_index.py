#!/usr/bin/env python3
"""Cross-reference retained EE link-once code-section labels with static edges.

This is a metadata index only: a section label is not proof of complete function
boundaries, and an encoded direct edge is not proof that the path executes.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any, Iterable


class IndexError(ValueError):
    """Input reports are inconsistent or not from the expected main ELF."""


def build_index(report: dict[str, Any], transfers: Iterable[dict[str, str]]) -> dict[str, Any]:
    boot_sha256 = report.get("boot_sha256")
    elf = report.get("elf")
    if not isinstance(boot_sha256, str) or len(boot_sha256) != 64 or not isinstance(elf, dict):
        raise IndexError("primary ELF report is missing its identity/hash or ELF metadata")
    raw_sections = elf.get("named_code_sections")
    if not isinstance(raw_sections, list):
        raise IndexError("primary ELF report lacks named_code_sections")

    sections: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}
    for raw in raw_sections:
        try:
            name = raw["name"]
            address = int(raw["address"])
            size = int(raw["size"])
            file_offset = int(raw["file_offset"])
        except (KeyError, TypeError, ValueError) as exc:
            raise IndexError("named section has missing/invalid fields") from exc
        if not isinstance(name, str) or not name.startswith(".gnu.linkonce.t."):
            raise IndexError(f"not a retained link-once text section: {name!r}")
        if address < 0 or size <= 0 or address + size > 0x1_0000_0000 or file_offset < 0:
            raise IndexError(f"invalid range for section {name!r}")
        if name in by_name:
            raise IndexError(f"duplicate link-once section name: {name}")
        entry = {
            "name": name,
            "address": address,
            "file_offset": file_offset,
            "size_bytes": size,
            "incoming_direct_calls": [],
            "incoming_direct_jumps": [],
        }
        sections.append(entry)
        by_name[name] = entry

    # A target match is only recorded when the encoded address is inside a
    # section's range. Exact-entry hits are labelled separately from interiors.
    ranges = sorted(sections, key=lambda s: s["address"])
    transfer_count = 0
    all_call_refs = 0
    targets_matched = set()
    for transfer in transfers:
        transfer_count += 1
        kind = transfer.get("kind", "")
        if kind not in ("direct_call", "direct_jump"):
            continue
        try:
            target = int(transfer["target_address"], 0)
            source = int(transfer["source_address"], 0)
        except (KeyError, TypeError, ValueError) as exc:
            raise IndexError("control transfer has invalid source/target address") from exc
        target_section = next((s for s in ranges if s["address"] <= target < s["address"] + s["size_bytes"]), None)
        if target_section is None:
            continue
        key = "incoming_direct_calls" if kind == "direct_call" else "incoming_direct_jumps"
        target_section[key].append({
            "source_address": source,
            "source_section": transfer.get("source_section", ""),
            "target_offset": target - target_section["address"],
            "exact_section_entry": target == target_section["address"],
        })
        if kind == "direct_call":
            all_call_refs += 1
            targets_matched.add(target_section["name"])

    sections.sort(key=lambda s: (s["address"], s["name"]))
    for section in sections:
        section["incoming_direct_calls"].sort(key=lambda x: x["source_address"])
        section["incoming_direct_jumps"].sort(key=lambda x: x["source_address"])

    direct_call_target_count = sum(len(s["incoming_direct_calls"]) for s in sections)
    direct_jump_target_count = sum(len(s["incoming_direct_jumps"]) for s in sections)
    return {
        "schema_version": 1,
        "boot_sha256": boot_sha256,
        "elf_entry_point": elf.get("entry_point"),
        "source": "evidence/primary_elf_static_analysis.json + evidence/control_transfers.csv",
        "named_linkonce_text_section_count": len(sections),
        "control_transfer_record_count": transfer_count,
        "direct_calls_targeting_named_sections": direct_call_target_count,
        "named_sections_with_direct_call_incoming": len(targets_matched),
        "direct_jumps_targeting_named_sections": direct_jump_target_count,
        "sections": sections,
        "limitations": [
            "Link-once section labels provide candidate code-region names, not guaranteed complete source-level function boundaries.",
            "Only statically encoded direct call/jump targets are matched; indirect calls, data references, and code paths are not resolved.",
            "A direct edge does not prove that the instruction or destination executes at runtime.",
            "The index does not recover original source code and is not a substitute for R5900-aware disassembly/decompilation.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf_report", type=Path, help="primary_elf_static_analysis.json")
    parser.add_argument("transfers_csv", type=Path, help="control_transfers.csv")
    parser.add_argument("--output", type=Path, required=True, help="output metadata-only JSON")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.elf_report.read_text(encoding="utf-8"))
        with args.transfers_csv.open(newline="", encoding="utf-8") as stream:
            transfers = list(csv.DictReader(stream))
        result = build_index(report, transfers)
    except (OSError, json.JSONDecodeError, csv.Error, IndexError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "sections"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
