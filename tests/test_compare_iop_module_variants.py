from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
_SPEC = importlib.util.spec_from_file_location(
    "compare_iop_module_variants_under_test", ROOT / "tools/compare_iop_module_variants.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
compare_variant_records = _MODULE.compare_variant_records
VariantComparisonError = _MODULE.VariantComparisonError


def _record(*symbols: tuple[str, int, int]) -> dict:
    return {
        "path": "MODULES/EZMIDI.IRX;1",
        "size_bytes": 1000,
        "sha256": "a" * 64,
        "function_symbol_count": len(symbols),
        "sections": [
            {"name": ".text", "size_bytes": 400},
            {"name": ".mdebug", "size_bytes": 200},
        ],
        "function_symbols": [
            {"name": name, "address": address, "size_bytes": size, "binding": "GLOBAL"}
            for name, address, size in symbols
        ],
    }


def test_compares_shared_symbol_metadata_and_keeps_variant_labels_explicit() -> None:
    result = compare_variant_records({
        "OLD": _record(("MidiStart", 0x100, 32), ("MidiStop", 0x200, 40)),
        "NEW": _record(("MidiStart", 0x100, 48), ("MidiSeek", 0x220, 24)),
        "IRX": _record(("MidiStart", 0x100, 48), ("MidiStop", 0x210, 40)),
    })
    assert result["variant_count"] == 3
    assert result["symbols_present_in_all_variants"] == 1
    assert result["shared_symbols_with_different_metadata"] == 2
    assert result["shared_symbols_with_different_size"] == 1
    assert result["shared_symbols_with_different_address"] == 1
    rows = {row["name"]: row for row in result["symbols"]}
    assert rows["MidiStart"]["metadata_differs"] is True
    assert rows["MidiSeek"]["present_in"] == ["NEW"]
    assert any("chronology" in limit for limit in result["limitations"])


def test_requires_at_least_two_variants() -> None:
    with pytest.raises(VariantComparisonError, match="at least two"):
        compare_variant_records({"IRX": _record(("MidiStart", 0x100, 32))})


def test_rejects_conflicting_duplicate_symbol_metadata_in_one_variant() -> None:
    bad = _record(("MidiStart", 0x100, 32), ("MidiStart", 0x100, 48))
    with pytest.raises(VariantComparisonError, match="conflicting records"):
        compare_variant_records({"OLD": bad, "NEW": _record(("MidiStart", 0x100, 32))})
