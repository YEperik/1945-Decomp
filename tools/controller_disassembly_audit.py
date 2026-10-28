#!/usr/bin/env python3
"""Audit key instruction words in the user-supplied controller disassembly listing.

This audit checks that the reviewed evidence file has not silently changed and
that the instruction words used for ABI/delay-slot conclusions are present at
expected addresses. It does not decode instructions or prove game behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LISTING = ROOT / "evidence/controller_api_disassembly_bui.txt"
DEFAULT_MANIFEST = ROOT / "evidence/controller_api_disassembly_bui.sha256"

# Exact machine words as printed by the supplied listing. The display follows
# Ghidra's word formatting; this tool intentionally does not reinterpret them.
EXPECTED_WORDS: dict[int, str] = {
    0x001B43B0: "1c000224",  # li v0,0x1c
    0x001B43B8: "1828a200",  # mult a1,a1,v0 (R5900 three-operand form)
    0x001B43BC: "18208370",  # mult1 a0,a0,v1
    0x001B43DC: "0000b08c",  # load selected buffer pointer
    0x001B43E4: "f6d8060c",  # jal FUN_001b63d8
    0x001B43E8: "00010526",  # delay slot: set a1 = buffer + 0x100
    0x001B43FC: "c0110200",  # shift bool result by 7 to form +0x80
    0x001B4400: "21100202",  # add selected offset to buffer pointer
    0x001B4408: "0800e003",  # jr ra
    0x001B4494: "1000438c",  # registration field load
    0x001B44A8: "ecd0060c",  # jal FUN_001b43b0
    0x001B44AC: "2d20e000",  # delay slot: restore a0 = port
    0x001B44B8: "6000068e",  # packet length from +0x60
    0x001B44BC: "e953070c",  # jal FUN_001d4fa4
    0x001B44C0: "2d280002",  # delay slot: a1 = source buffer
    0x001B44C4: "6000028e",  # return packet length
    0x001B4518: "ecd0060c",  # jal FUN_001b43b0
    0x001B451C: "2d20c000",  # delay slot: restore a0 = port
    0x001B4528: "70008290",  # status byte at +0x70
    0x001B4534: "71008390",  # subtype byte at +0x71
    0x001B45D4: "ecd0060c",  # jal FUN_001b43b0
    0x001B45D8: "2d20e000",  # delay slot: restore a0 = port
    0x001B45DC: "710050a0",  # store subtype byte at +0x71
    0x001B45F8: "2d308000",  # getter begins
    0x001B4630: "ecd0060c",  # jal FUN_001b43b0
    0x001B4634: "2d20c000",  # delay slot: restore a0 = port
    0x001B4638: "71004290",  # load subtype byte at +0x71
}

LINE_RE = re.compile(r"\.text:([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})\s+")


def parse_listing(text: str) -> dict[int, str]:
    """Return address -> printed instruction word for disassembled lines."""
    words: dict[int, str] = {}
    for line in text.splitlines():
        match = LINE_RE.search(line)
        if match:
            words[int(match.group(1), 16)] = match.group(2).lower()
    return words


def audit_text(text: str) -> list[str]:
    words = parse_listing(text)
    issues: list[str] = []
    for address, expected in EXPECTED_WORDS.items():
        actual = words.get(address)
        if actual is None:
            issues.append(f"missing instruction word at 0x{address:08X}")
        elif actual != expected:
            issues.append(
                f"0x{address:08X}: expected {expected}, found {actual}"
            )
    return issues


def audit_manifest(listing_path: Path, manifest_path: Path) -> list[str]:
    issues: list[str] = []
    raw = listing_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    manifest = manifest_path.read_text(encoding="utf-8")
    match = re.search(r"^SHA-256:\s*([0-9a-f]{64})\s*$", manifest, re.MULTILINE)
    if not match:
        issues.append("SHA-256 entry missing from listing manifest")
    elif match.group(1) != sha:
        issues.append(f"listing SHA-256 mismatch: computed {sha}")
    issues.extend(audit_text(raw.decode("utf-8", errors="replace")))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listing", type=Path, default=DEFAULT_LISTING)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    issues = audit_manifest(args.listing, args.manifest)
    if issues:
        for issue in issues:
            print(f"FAIL: {issue}", file=sys.stderr)
        return 1
    print(f"PASS: listing hash matches manifest; {len(EXPECTED_WORDS)} key instruction words verified")
    print("Scope: evidence integrity only; not an instruction decoder or runtime validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
