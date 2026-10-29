#!/usr/bin/env python3
"""Validate per-function Ghidra pseudocode exports without claiming source recovery.

A partial export is a valid diagnostic artifact but is reported as ``partial``.
The command fails if no functions were listed, the manifest is malformed, a
status is unknown, or any row marked SUCCESS points to a missing/empty output.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

EXPECTED_COLUMNS = {
    "entry", "name", "prototype", "status", "elapsed_ms", "output_file", "error"
}
VALID_STATUSES = {"SUCCESS", "INCOMPLETE", "FAILED"}


def validate(manifest: Path, output_dir: Path) -> dict[str, Any]:
    if not manifest.is_file() or manifest.stat().st_size == 0:
        raise ValueError(f"missing or empty decompilation manifest: {manifest}")
    with manifest.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not EXPECTED_COLUMNS.issubset(reader.fieldnames):
            raise ValueError("manifest is missing required columns")
        rows = list(reader)

    if not rows:
        raise ValueError("manifest contains no discovered functions")

    counts = {status: 0 for status in sorted(VALID_STATUSES)}
    invalid_rows: list[str] = []
    missing_outputs: list[str] = []
    seen_entries: set[str] = set()
    root = output_dir.resolve()

    for line_number, row in enumerate(rows, start=2):
        entry = (row.get("entry") or "").strip()
        status = (row.get("status") or "").strip()
        relative_output = (row.get("output_file") or "").strip()
        if not entry or entry in seen_entries:
            invalid_rows.append(f"line {line_number}: blank or duplicate function entry {entry!r}")
        seen_entries.add(entry)
        if status not in VALID_STATUSES:
            invalid_rows.append(f"line {line_number}: unknown status {status!r}")
            continue
        counts[status] += 1
        if status == "SUCCESS":
            candidate = (root / relative_output).resolve()
            if not relative_output or (candidate != root and root not in candidate.parents):
                invalid_rows.append(f"line {line_number}: output path escapes decompilation directory")
                continue
            if not candidate.is_file() or candidate.stat().st_size == 0:
                missing_outputs.append(f"line {line_number}: {relative_output}")

    if invalid_rows:
        raise ValueError("; ".join(invalid_rows[:12]))
    if missing_outputs:
        raise ValueError("successful function outputs missing/empty: " + "; ".join(missing_outputs[:12]))
    if counts["SUCCESS"] == 0:
        raise ValueError("no function produced pseudocode; export is not usable")

    total = len(rows)
    return {
        "status": "complete" if counts["SUCCESS"] == total else "partial",
        "total_functions": total,
        "success": counts["SUCCESS"],
        "incomplete": counts["INCOMPLETE"],
        "failed": counts["FAILED"],
        "coverage_ratio": round(counts["SUCCESS"] / total, 6),
        "pseudocode_is_original_source": False,
        "manifest": str(manifest.resolve()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--summary", type=Path, help="optional JSON summary path")
    args = parser.parse_args(argv)
    try:
        result = validate(args.manifest, args.output_dir)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
