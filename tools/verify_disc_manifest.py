#!/usr/bin/env python3
"""Validate the checked-in ISO file manifest and, optionally, an extracted disc tree.

The repository intentionally excludes original game payloads. Without --disc-root,
this tool validates manifest structure/counts only. With --disc-root, it verifies
all 659 file payloads by relative path, byte size, and SHA-256 and rejects extras.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "evidence" / "disc_file_manifest.csv"
EXPECTED_FILE_RECORDS = 659
EXPECTED_DIRECTORY_RECORDS = 37
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
REQUIRED_COLUMNS = {
    "path", "name", "type", "size_bytes", "sha256"
}


def load_manifest(path: Path, *, enforce_project_counts: bool = True) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or [])
            missing_columns = REQUIRED_COLUMNS - fields
            if missing_columns:
                return [], [f"manifest is missing columns: {', '.join(sorted(missing_columns))}"]
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        return [], [f"cannot read manifest {path}: {exc}"]

    seen: set[str] = set()
    seen_casefold: set[str] = set()
    for index, row in enumerate(rows, start=2):
        rel = row.get("path", "")
        record_type = row.get("type", "")
        if not rel:
            errors.append(f"line {index}: empty path")
            continue
        posix = PurePosixPath(rel)
        if posix.is_absolute() or ".." in posix.parts or "\\" in rel or rel.startswith("/"):
            errors.append(f"line {index}: unsafe/non-POSIX path: {rel!r}")
        if rel in seen:
            errors.append(f"line {index}: duplicate path: {rel}")
        if rel.casefold() in seen_casefold:
            errors.append(f"line {index}: case-insensitive path collision: {rel}")
        seen.add(rel)
        seen_casefold.add(rel.casefold())
        if record_type not in {"file", "directory"}:
            errors.append(f"line {index}: unsupported record type {record_type!r}")
            continue
        if record_type == "file":
            raw_size = row.get("size_bytes", "")
            try:
                size = int(raw_size)
                if size < 0:
                    raise ValueError("negative")
            except (TypeError, ValueError):
                errors.append(f"line {index}: invalid size_bytes for {rel}: {raw_size!r}")
            digest = row.get("sha256", "")
            if not SHA256_RE.fullmatch(digest):
                errors.append(f"line {index}: invalid SHA-256 for {rel}")
        elif row.get("sha256", ""):
            errors.append(f"line {index}: directory unexpectedly has a SHA-256: {rel}")

    file_count = sum(row.get("type") == "file" for row in rows)
    directory_count = sum(row.get("type") == "directory" for row in rows)
    if enforce_project_counts and file_count != EXPECTED_FILE_RECORDS:
        errors.append(f"expected {EXPECTED_FILE_RECORDS} file records; found {file_count}")
    if enforce_project_counts and directory_count != EXPECTED_DIRECTORY_RECORDS:
        errors.append(f"expected {EXPECTED_DIRECTORY_RECORDS} directory records; found {directory_count}")
    return rows, errors


def verify_extracted_tree(rows: list[dict[str, str]], disc_root: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    try:
        root = disc_root.resolve(strict=True)
    except OSError as exc:
        return {"disc_root": str(disc_root), "payload_verification": "failed"}, [f"cannot access disc root: {exc}"]
    if not root.is_dir():
        return {"disc_root": str(root), "payload_verification": "failed"}, [f"disc root is not a directory: {root}"]

    expected: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.get("type") != "file":
            continue
        rel = PurePosixPath(row["path"])
        if rel.is_absolute() or ".." in rel.parts:
            errors.append(f"unsafe path skipped during payload check: {row['path']}")
            continue
        expected[rel.as_posix()] = row

    actual_paths: set[str] = set()
    try:
        for path in root.rglob("*"):
            if path.is_file():
                actual_paths.add(path.relative_to(root).as_posix())
    except OSError as exc:
        errors.append(f"cannot enumerate extracted tree: {exc}")

    for extra in sorted(actual_paths - set(expected)):
        errors.append(f"unexpected extracted file: {extra}")
    for missing in sorted(set(expected) - actual_paths):
        errors.append(f"missing extracted file: {missing}")

    checked = 0
    hash_mismatches = 0
    size_mismatches = 0
    for rel, row in expected.items():
        path = root.joinpath(*PurePosixPath(rel).parts)
        try:
            resolved_path = path.resolve(strict=True)
        except OSError:
            continue
        if not resolved_path.is_relative_to(root):
            errors.append(f"extracted path resolves outside disc root: {rel}")
            continue
        if not resolved_path.is_file():
            continue
        path = resolved_path
        checked += 1
        expected_size = int(row["size_bytes"])
        if path.stat().st_size != expected_size:
            size_mismatches += 1
            errors.append(f"size mismatch for {rel}: expected {expected_size}, got {path.stat().st_size}")
            continue
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
        except OSError as exc:
            errors.append(f"cannot hash {rel}: {exc}")
            continue
        if digest.hexdigest().lower() != row["sha256"].lower():
            hash_mismatches += 1
            errors.append(f"SHA-256 mismatch for {rel}")

    summary = {
        "disc_root": str(root),
        "payload_verification": "passed" if not errors else "failed",
        "expected_file_records": len(expected),
        "actual_extracted_files": len(actual_paths),
        "payloads_checked": checked,
        "size_mismatches": size_mismatches,
        "sha256_mismatches": hash_mismatches,
        "missing_files": len(set(expected) - actual_paths),
        "unexpected_files": len(actual_paths - set(expected)),
    }
    return summary, errors


def verify_manifest(path: Path, disc_root: Path | None = None) -> tuple[dict[str, Any], list[str]]:
    rows, errors = load_manifest(path, enforce_project_counts=True)
    summary: dict[str, Any] = {
        "manifest": str(path),
        "manifest_validation": "passed" if not errors else "failed",
        "manifest_rows": len(rows),
        "file_records": sum(row.get("type") == "file" for row in rows),
        "directory_records": sum(row.get("type") == "directory" for row in rows),
        "payload_hashes_checked": False,
    }
    if disc_root is not None and not errors:
        payload_summary, payload_errors = verify_extracted_tree(rows, disc_root)
        summary.update(payload_summary)
        summary["payload_hashes_checked"] = True
        errors.extend(payload_errors)
    elif disc_root is None:
        summary["note"] = "manifest metadata only; original disc payload files were intentionally excluded from Git"
    if errors:
        summary["manifest_validation"] = "failed"
        summary["errors"] = errors
    return summary, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--disc-root", type=Path, help="external directory containing extracted disc files")
    args = parser.parse_args(argv)
    summary, errors = verify_manifest(args.manifest, args.disc_root)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
