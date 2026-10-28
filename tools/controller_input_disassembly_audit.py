#!/usr/bin/env python3
"""Integrity and anchor-instruction checks for the user's two new R5900 listings.

This does not decode instructions. It verifies supplied listing bytes/words and
checks selected address anchors used by the input-state reconstruction.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "evidence/controller_candidate_1b4410_listing.txt"
INPUT = ROOT / "evidence/controller_input_reset_listing.txt"
MANIFEST = ROOT / "evidence/controller_input_disassembly.sha256"

WORD_RE = re.compile(r"\.text:([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})\s+", re.MULTILINE)
BYTE_RE = re.compile(r"\.text:([0-9a-fA-F]{8})\s+([0-9a-fA-F]{2})\s+", re.MULTILINE)

# These values use the same memory-order formatting as the supplied Ghidra listing.
INPUT_WORDS = {
    0x00187860: "140080a4",  # clear current-button field
    0x00187864: "180080a4",  # clear button-edge field
    0x00187868: "0800e003",  # return
    0x0018786C: "160080a4",  # delay slot: clear previous-button field
    0x0018789C: "181e060c",  # reset helper 1
    0x001878A0: "2d808000",  # delay slot: preserve record pointer
    0x001878A4: "1c1e060c",  # reset helper 2
    0x001878A8: "2d200002",  # delay slot: restore a0=record
    0x00187A60: "18d1060c",  # read packet into output buffer
    0x00187A64: "0400058e",  # delay slot: pass slot
    0x00187AD4: "27100800",  # NOR old current mask
    0x00187AE4: "2410c200",  # new button bits & inverse previous
    0x00187AF4: "180002a6",  # store newly pressed edge mask
    0x00187AF8: "1c0007a6",  # preserve old axis-direction mask
    0x00187B04: "160008a6",  # preserve old button mask
    0x00187B0C: "140006a6",  # store new current button mask in delay slot
    0x00187B28: "00f04230",  # test button mask & 0xf000
    0x00187B40: "c1ff6228",  # signed axis threshold < -63
    0x00187B54: "40006228",  # axis positive threshold >= 64 (via SLTI)
    0x00187C18: "24186200",  # direction mask & inverse previous direction
    0x00187C1C: "1e0003a6",  # store direction edges
    0x00187F60: "101f060c",  # per-record state update
    0x00187F64: "40011026",  # delay slot: record += 0x140
}

# The candidate listing prints each byte separately as unknown/data. Check key
# four-byte runs in memory order and full address coverage, but do not infer xrefs.
CANDIDATE_RUNS = {
    0x001B4410: "2d308000",  # move a2,a0 candidate
    0x001B4414: "70000324",  # li v1,0x70
    0x001B4418: "1c000424",  # li a0,0x1c
    0x001B441C: "1818c370",  # port stride multiply
    0x001B4420: "1820a400",  # slot stride multiply
    0x001B443C: "1000438c",  # registration field load
    0x001B4440: "04006010",  # return zero if unregistered
    0x001B4448: "ecd0060c",  # call selected-buffer helper
    0x001B444C: "2d20c000",  # delay slot: a0=port
    0x001B4450: "5800428c",  # load selected-buffer +0x58
    0x001B4458: "0800e003",  # return
    0x001B445C: "1000bd27",  # stack restore in delay slot
}


def word_map(text: str) -> dict[int, str]:
    return {int(a, 16): w.lower() for a, w in WORD_RE.findall(text)}


def byte_map(text: str) -> dict[int, int]:
    return {int(a, 16): int(b, 16) for a, b in BYTE_RE.findall(text)}


def audit_manifest() -> list[str]:
    issues: list[str] = []
    if not MANIFEST.exists():
        return ["manifest missing"]
    entries: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([0-9a-f]{64})\s+\*?(.+)$", line.strip())
        if match:
            entries[match.group(2)] = match.group(1)
    for path in (CANDIDATE, INPUT):
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            issues.append(f"cannot read {path.name}: {exc}")
            continue
        expected = entries.get(path.name)
        if expected is None:
            issues.append(f"manifest entry missing for {path.name}")
        elif expected != actual:
            issues.append(f"SHA-256 mismatch for {path.name}: {actual}")
    return issues


def audit_input_listing(text: str) -> list[str]:
    words = word_map(text)
    issues = []
    for addr, expected in INPUT_WORDS.items():
        actual = words.get(addr)
        if actual is None:
            issues.append(f"missing word at 0x{addr:08X}")
        elif actual != expected:
            issues.append(f"0x{addr:08X}: expected {expected}, found {actual}")
    return issues


def audit_candidate_listing(text: str) -> list[str]:
    data = byte_map(text)
    issues = []
    for addr, expected in CANDIDATE_RUNS.items():
        actual = "".join(f"{data.get(addr + i, -1):02x}" for i in range(4))
        if any((addr + i) not in data for i in range(4)):
            issues.append(f"missing candidate byte run at 0x{addr:08X}")
        elif actual != expected:
            issues.append(f"0x{addr:08X}: expected bytes {expected}, found {actual}")
    missing = [addr for addr in range(0x001B4410, 0x001B4460) if addr not in data]
    if missing:
        issues.append(f"candidate byte interval missing {len(missing)} byte address(es)")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    issues = audit_manifest()
    try:
        candidate_text = CANDIDATE.read_text(encoding="utf-8", errors="replace")
        input_text = INPUT.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        issues.append(f"cannot read listing: {exc}")
    else:
        issues.extend(audit_candidate_listing(candidate_text))
        issues.extend(audit_input_listing(input_text))
    if issues:
        for item in issues:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"PASS: hashes match; {len(CANDIDATE_RUNS)} candidate byte runs and {len(INPUT_WORDS)} instruction words verified")
        print("Scope: listing integrity/anchor checks only; no execution or full instruction decoding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
