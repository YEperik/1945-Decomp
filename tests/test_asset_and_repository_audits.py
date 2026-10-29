from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_manifest(path: Path, root: Path, include_extra_manifest: bool = False) -> None:
    payloads = {"A.BIN;1": b"authorized fixture bytes", "DATA/B.TIM;1": b"tim fixture"}
    for rel, data in payloads.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    rows = []
    for rel, data in payloads.items():
        rows.append({"path": rel, "name": Path(rel).name, "type": "file",
                     "size_bytes": str(len(data)), "sha256": hashlib.sha256(data).hexdigest()})
    rows.append({"path": "DATA", "name": "DATA", "type": "directory",
                 "size_bytes": "2048", "sha256": ""})
    if include_extra_manifest:
        rows.append({"path": "MISSING.SQ;1", "name": "MISSING.SQ;1", "type": "file",
                     "size_bytes": "1", "sha256": hashlib.sha256(b"x").hexdigest()})
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "name", "type", "size_bytes", "sha256"])
        writer.writeheader()
        writer.writerows(rows)


def test_project_disc_manifest_metadata_is_valid() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/verify_disc_manifest.py")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["file_records"] == 659
    assert data["directory_records"] == 37
    assert data["payload_hashes_checked"] is False


def test_full_disc_manifest_verification_accepts_exact_payload_tree(tmp_path: Path) -> None:
    verifier = _load_module("disc_manifest_verifier", "tools/verify_disc_manifest.py")
    root = tmp_path / "disc"
    root.mkdir()
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, root)
    rows, load_errors = verifier.load_manifest(manifest, enforce_project_counts=False)
    assert not load_errors
    summary, errors = verifier.verify_extracted_tree(rows, root)
    assert not errors
    assert summary["payloads_checked"] == 2
    assert summary["sha256_mismatches"] == 0
    assert summary["unexpected_files"] == 0


def test_full_disc_manifest_verification_rejects_hash_mismatch_and_unexpected_file(tmp_path: Path) -> None:
    verifier = _load_module("disc_manifest_verifier_bad", "tools/verify_disc_manifest.py")
    root = tmp_path / "disc"
    root.mkdir()
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, root)
    (root / "A.BIN;1").write_bytes(b"x" * len(b"authorized fixture bytes"))
    (root / "extra.dat").write_bytes(b"extra")
    rows, load_errors = verifier.load_manifest(manifest, enforce_project_counts=False)
    assert not load_errors
    summary, errors = verifier.verify_extracted_tree(rows, root)
    assert summary["sha256_mismatches"] == 1
    assert summary["unexpected_files"] == 1
    assert any("SHA-256 mismatch" in error for error in errors)
    assert any("unexpected extracted file" in error for error in errors)


def test_disc_manifest_rejects_unsafe_paths_and_bad_hashes(tmp_path: Path) -> None:
    verifier = _load_module("disc_manifest_verifier_unsafe", "tools/verify_disc_manifest.py")
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "path,name,type,size_bytes,sha256\n../escape.bin,escape.bin,file,1,not-a-hash\n",
        encoding="utf-8",
    )
    rows, errors = verifier.load_manifest(manifest)
    assert rows
    assert any("unsafe/non-POSIX path" in error for error in errors)
    assert any("invalid SHA-256" in error for error in errors)
    assert any("expected 659 file records" in error for error in errors)


def test_repository_hygiene_catches_iso_versioned_and_large_media_paths() -> None:
    hygiene = _load_module("repository_hygiene", "tools/check_repository_hygiene.py")
    violations = hygiene.violations_for_paths(
        ["source/foo.TIM;1", "disc.bin", "evidence/report.csv", "app/src/main/cpp/game.c"],
        {"source/foo.TIM;1": 1024, "disc.bin": 2000, "evidence/report.csv": 40},
    )
    assert len(violations) == 2
    assert any("source/foo.TIM;1" in item for item in violations)
    assert any("disc.bin" in item for item in violations)


def test_repository_hygiene_passes_for_current_tracked_tree() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/check_repository_hygiene.py"), "--repo", str(ROOT)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_full_disc_manifest_verification_rejects_symlink_escape(tmp_path: Path) -> None:
    verifier = _load_module("disc_manifest_verifier_symlink", "tools/verify_disc_manifest.py")
    root = tmp_path / "disc"
    root.mkdir()
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, root)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"authorized fixture bytes")
    (root / "A.BIN;1").unlink()
    (root / "A.BIN;1").symlink_to(outside)
    rows, load_errors = verifier.load_manifest(manifest, enforce_project_counts=False)
    assert not load_errors
    summary, errors = verifier.verify_extracted_tree(rows, root)
    assert any("resolves outside disc root" in error for error in errors)
    assert summary["payload_verification"] == "failed"
