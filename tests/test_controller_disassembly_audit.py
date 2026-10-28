"""Integrity checks for the supplied R5900 controller disassembly evidence."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/controller_disassembly_audit.py"
SPEC = importlib.util.spec_from_file_location("controller_disassembly_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def test_preserved_listing_hash_and_key_instruction_words() -> None:
    assert AUDIT.audit_manifest(
        ROOT / "evidence/controller_api_disassembly_bui.txt",
        ROOT / "evidence/controller_api_disassembly_bui.sha256",
    ) == []


def test_audit_detects_missing_instruction_word() -> None:
    sample = ".text:001b43b0  1c000224        li v0,0x1c\n"
    issues = AUDIT.audit_text(sample)
    assert any("missing instruction word at 0x001B43B8" in issue for issue in issues)
