#!/usr/bin/env python3
"""Compare symbol/section metadata across PS2 IOP module variants.

The report is metadata-only: it does not dump module contents, disassembly,
source code, or executable byte ranges. Variant filenames such as OLD/NEW/IRX
are treated as labels, not assumed chronological versions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

from iop_module_inventory import IopElfError, parse_irx

_VARIANT_RE = re.compile(r"^(?P<module>.+)\.(?P<variant>IRX|NEW|OLD);1$", re.IGNORECASE)


class VariantComparisonError(ValueError):
    """Invalid or insufficient variant metadata."""


def compare_variant_records(variants: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if len(variants) < 2:
        raise VariantComparisonError("at least two parsed module variants are required")
    if len({key.upper() for key in variants}) != len(variants):
        raise VariantComparisonError("variant labels must be unique ignoring case")

    symbol_maps: dict[str, dict[str, dict[str, Any]]] = {}
    for variant, record in variants.items():
        raw_symbols = record.get("function_symbols")
        if not isinstance(raw_symbols, list):
            raise VariantComparisonError(f"variant {variant!r} lacks function_symbols")
        mapping: dict[str, dict[str, Any]] = {}
        for symbol in raw_symbols:
            if not isinstance(symbol, dict) or not isinstance(symbol.get("name"), str) or not symbol["name"]:
                continue
            name = symbol["name"]
            # Multiple ELF entries can alias an address/name; retain one deterministic tuple.
            item = {
                "address": symbol.get("address"),
                "size_bytes": symbol.get("size_bytes"),
                "binding": symbol.get("binding"),
            }
            old = mapping.get(name)
            if old is not None and old != item:
                raise VariantComparisonError(f"variant {variant!r} has conflicting records for symbol {name!r}")
            mapping[name] = item
        symbol_maps[variant] = mapping

    all_names = sorted({name for symbols in symbol_maps.values() for name in symbols})
    rows: list[dict[str, Any]] = []
    common_across_all = 0
    changed_shared = 0
    changed_size_shared = 0
    changed_binding_shared = 0
    changed_address_shared = 0
    stable_shared = 0
    for name in all_names:
        present = {variant: mapping[name] for variant, mapping in symbol_maps.items() if name in mapping}
        tuples = {(item["address"], item["size_bytes"], item["binding"]) for item in present.values()}
        if len(present) == len(symbol_maps):
            common_across_all += 1
        if len(present) >= 2:
            if len(tuples) == 1:
                stable_shared += 1
            else:
                changed_shared += 1
        size_differs = len({item["size_bytes"] for item in present.values()}) > 1
        address_differs = len({item["address"] for item in present.values()}) > 1
        binding_differs = len({item["binding"] for item in present.values()}) > 1
        if len(present) >= 2:
            changed_size_shared += int(size_differs)
            changed_address_shared += int(address_differs)
            changed_binding_shared += int(binding_differs)
        rows.append({
            "name": name,
            "present_in": list(present),
            "variants": present,
            "metadata_differs": len(tuples) > 1,
            "address_differs": address_differs,
            "size_differs": size_differs,
            "binding_differs": binding_differs,
        })

    shared_names = [row for row in rows if len(row["present_in"]) >= 2]
    return {
        "schema_version": 1,
        "module_family": next(iter(variants.values())).get("module_family", "unspecified"),
        "variant_count": len(variants),
        "variants": {
            key: {
                "path": value.get("path"),
                "size_bytes": value.get("size_bytes"),
                "sha256": value.get("sha256"),
                "text_size_bytes": next((s["size_bytes"] for s in value.get("sections", []) if s.get("name") == ".text"), None),
                "mdebug_size_bytes": next((s["size_bytes"] for s in value.get("sections", []) if s.get("name") == ".mdebug"), 0),
                "function_symbol_count": value.get("function_symbol_count", len(symbol_maps[key])),
            }
            for key, value in variants.items()
        },
        "union_symbol_count": len(all_names),
        "symbols_present_in_all_variants": common_across_all,
        "shared_symbol_count_two_or_more_variants": len(shared_names),
        "shared_symbols_with_identical_address_size_binding": stable_shared,
        "shared_symbols_with_different_metadata": changed_shared,
        "shared_symbols_with_different_address": changed_address_shared,
        "shared_symbols_with_different_size": changed_size_shared,
        "shared_symbols_with_different_binding": changed_binding_shared,
        "symbols": rows,
        "limitations": [
            "OLD, NEW, and IRX labels are filenames only; chronology or runtime selection is not inferred.",
            "Symbol address/size changes identify metadata differences, not semantic behavior changes by themselves.",
            "No machine code, disassembly, original payload bytes, or source code is emitted.",
        ],
    }


def scan_module_family(root: Path, family: str) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise VariantComparisonError(f"disc root is not a directory: {root}")
    candidates: dict[str, Path] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        match = _VARIANT_RE.match(path.name)
        if match and match.group("module").casefold() == family.casefold():
            label = match.group("variant").upper()
            if label in candidates:
                raise VariantComparisonError(f"duplicate {label} variant for {family}")
            candidates[label] = path
    if len(candidates) < 2:
        raise VariantComparisonError(f"found only {len(candidates)} variant(s) for {family}; need at least two")
    records: dict[str, dict[str, Any]] = {}
    for label, path in sorted(candidates.items()):
        try:
            item = parse_irx(path.read_bytes(), path.relative_to(root).as_posix())
        except (OSError, IopElfError) as exc:
            raise VariantComparisonError(f"cannot parse {path.name}: {exc}") from exc
        item["module_family"] = family
        records[label] = item
    return compare_variant_records(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disc_root", type=Path, help="path to an external extracted disc directory")
    parser.add_argument("module_family", help="module filename stem, e.g. EZMIDI")
    parser.add_argument("--output", type=Path, help="optional metadata-only JSON output")
    args = parser.parse_args(argv)
    try:
        result = scan_module_family(args.disc_root, args.module_family)
    except (OSError, VariantComparisonError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "symbols"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
