from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("ee_named_section_index_under_test", ROOT / "tools/ee_named_section_index.py")
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
IndexError = _MODULE.IndexError
build_index = _MODULE.build_index


def report() -> dict:
    return {
        "boot_sha256": "a" * 64,
        "elf": {
            "entry_point": 0x100008,
            "named_code_sections": [
                {"name": ".gnu.linkonce.t.Example", "address": 0x1000, "file_offset": 0x200, "size": 0x20},
                {"name": ".gnu.linkonce.t.Another", "address": 0x2000, "file_offset": 0x300, "size": 0x10},
            ],
        },
    }


def test_matches_exact_and_interior_direct_edges_without_claiming_runtime_execution() -> None:
    transfers = [
        {"kind": "direct_call", "source_address": "0x3000", "target_address": "0x1000", "source_section": ".text"},
        {"kind": "direct_call", "source_address": "0x3004", "target_address": "0x1004", "source_section": ".text"},
        {"kind": "direct_jump", "source_address": "0x3008", "target_address": "0x2004", "source_section": ".text"},
        {"kind": "indirect_call", "source_address": "0x3010", "target_address": "0x1000", "source_section": ".text"},
    ]
    result = build_index(report(), transfers)
    assert result["named_linkonce_text_section_count"] == 2
    assert result["direct_calls_targeting_named_sections"] == 2
    assert result["named_sections_with_direct_call_incoming"] == 1
    first = next(s for s in result["sections"] if s["name"].endswith("Example"))
    assert [x["exact_section_entry"] for x in first["incoming_direct_calls"]] == [True, False]
    assert first["incoming_direct_jumps"] == []
    another = next(s for s in result["sections"] if s["name"].endswith("Another"))
    assert another["incoming_direct_jumps"][0]["target_offset"] == 4
    assert "does not prove" in result["limitations"][2]


def test_rejects_duplicate_names_and_invalid_addresses() -> None:
    bad = report()
    bad["elf"]["named_code_sections"].append(bad["elf"]["named_code_sections"][0])
    with pytest.raises(IndexError, match="duplicate link-once"):
        build_index(bad, [])
    bad = report()
    bad["elf"]["named_code_sections"][0]["size"] = 0
    with pytest.raises(IndexError, match="invalid range"):
        build_index(bad, [])


def test_rejects_malformed_transfer_addresses() -> None:
    with pytest.raises(IndexError, match="invalid source/target"):
        build_index(report(), [{"kind": "direct_call", "source_address": "abc", "target_address": "0x1000"}])
