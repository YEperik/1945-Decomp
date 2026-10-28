"""Regression tests for the two additional user-supplied listing files."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/controller_input_disassembly_audit.py"
SPEC = importlib.util.spec_from_file_location("controller_input_disassembly_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def test_new_listing_hashes_and_anchors_match() -> None:
    assert AUDIT.audit_manifest() == []
    candidate = AUDIT.CANDIDATE.read_text(encoding="utf-8", errors="replace")
    input_listing = AUDIT.INPUT.read_text(encoding="utf-8", errors="replace")
    assert AUDIT.audit_candidate_listing(candidate) == []
    assert AUDIT.audit_input_listing(input_listing) == []


def test_missing_reset_instruction_is_detected() -> None:
    tiny = ".text:00187860  140080a4        sh zero,0x14(a0)\n"
    issues = AUDIT.audit_input_listing(tiny)
    assert any("missing word at 0x00187864" in issue for issue in issues)
