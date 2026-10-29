"""Preflight tests for the optional external R5900-aware Ghidra pipeline."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
RUNNER = ROOT / "tools" / "run_ghidra_headless.sh"
EXPORTER = ROOT / "ghidra_scripts" / "Export1945Evidence.java"
DECOMPILER = ROOT / "ghidra_scripts" / "Export1945Decompilation.java"


def make_fake_ghidra(root: Path, include_r5900_language: bool = True) -> Path:
    """Create a harmless fake installation to exercise runner preflight only."""
    home = root / "fake-ghidra"
    support = home / "support"
    support.mkdir(parents=True)
    launcher = support / "analyzeHeadless"
    launcher.write_text("#!/bin/sh\necho 'fake launcher must not be called in preflight tests' >&2\nexit 99\n", encoding="utf-8")
    launcher.chmod(0o755)
    languages = home / "Ghidra" / "Processors" / "MIPS" / "data" / "languages"
    languages.mkdir(parents=True)
    lang_id = ' id="r5900:LE:32:default"' if include_r5900_language else ' id="MIPS:LE:32:default"'
    (languages / "test.ldefs").write_text(f"<language{lang_id}/>\n", encoding="utf-8")
    return home


def test_runner_has_valid_bash_syntax() -> None:
    result = subprocess.run(["bash", "-n", str(RUNNER)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_runner_refuses_to_fallback_without_ghidra_home(tmp_path: Path) -> None:
    image = tmp_path / "synthetic.bin"
    image.write_bytes(b"not parsed by this preflight path")
    env = os.environ.copy()
    env.pop("GHIDRA_HOME", None)
    output = subprocess.run(
        ["bash", str(RUNNER), str(image), str(tmp_path / "out")],
        env=env, text=True, capture_output=True, check=False,
    )
    assert output.returncode == 3
    assert "GHIDRA_HOME is not set" in output.stderr
    assert not (tmp_path / "out").exists()


def test_runner_rejects_missing_r5900_language_without_import(tmp_path: Path) -> None:
    home = make_fake_ghidra(tmp_path, include_r5900_language=False)
    image = tmp_path / "synthetic.bin"
    image.write_bytes(b"not parsed by this preflight path")
    env = os.environ.copy()
    env["GHIDRA_HOME"] = str(home)
    output = subprocess.run(
        ["bash", str(RUNNER), str(image), str(tmp_path / "out")],
        env=env, text=True, capture_output=True, check=False,
    )
    assert output.returncode == 4
    assert "r5900:LE:32:default was not found" in output.stderr
    assert not (tmp_path / "out").exists()


def test_runner_rejects_repository_output_before_creating_it(tmp_path: Path) -> None:
    home = make_fake_ghidra(tmp_path, include_r5900_language=True)
    image = tmp_path / "synthetic.bin"
    image.write_bytes(b"not parsed by this preflight path")
    output_path = ROOT / f".ghidra-output-guard-test-{tmp_path.name}"
    assert not output_path.exists()
    env = os.environ.copy()
    env["GHIDRA_HOME"] = str(home)
    output = subprocess.run(
        ["bash", str(RUNNER), str(image), str(output_path)],
        env=env, text=True, capture_output=True, check=False,
    )
    assert output.returncode == 2
    assert "Ghidra project/output must be outside the repository" in output.stderr
    assert not output_path.exists()


def test_export_script_is_r5900_guarded_and_exports_expected_evidence() -> None:
    source = EXPORTER.read_text(encoding="utf-8")
    assert 'contains("r5900")' in source
    assert 'ghidra_functions.csv' in source
    assert 'ghidra_call_references.csv' in source
    assert 'ghidra_selected_disassembly.csv' in source
    assert '0x00100008' in source
    assert 'Refusing to export' in source


def test_runner_default_output_is_outside_repository() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert '1945-ghidra-r5900-output' in source
    assert 'Ghidra project/output must be outside the repository' in source
    assert 'RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"' in source
    assert 'mkdir -- "$RUN_DIR"' in source
    assert 'unique Ghidra run directory already exists' in source
    assert 'never overwrite previous projects or exports' in source
    assert "expected_entry_instruction_present=true" in source
    assert "refusing to report a successful analysis" in source


def test_decompilation_exporter_covers_every_discovered_function_with_a_manifest() -> None:
    source = DECOMPILER.read_text(encoding="utf-8")
    assert "DecompInterface" in source
    assert "getFunctions(true)" in source
    assert "ghidra_decompile_manifest.csv" in source
    assert '"SUCCESS"' in source and '"INCOMPLETE"' in source
    assert "decompileFunction(" in source and "timeoutSeconds, monitor" in source
    assert "not original source" in source


def test_runner_invokes_full_function_decompilation_outside_repository() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert 'DECOMP_DIR="$RUN_DIR/decompiled"' in source
    assert 'Export1945Decompilation.java "$DECOMP_DIR" 30' in source
    assert 'ghidra_decompile_manifest.csv' in source
    assert 'ghidra_decompile_summary.json' in source
    assert 'Function pseudocode:' in source
    assert 'RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"' in source
    assert '  -overwrite \\n' not in source
    assert 'validate_ghidra_decompilation.py' in source


def _write_decompile_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    import csv

    fields = ["entry", "name", "prototype", "status", "elapsed_ms", "output_file", "error"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_decompile_manifest_validator_accepts_and_labels_partial_export(tmp_path: Path) -> None:
    import json

    from validate_ghidra_decompilation import validate

    output_dir = tmp_path / "decompiled"
    (output_dir / "functions").mkdir(parents=True)
    (output_dir / "functions" / "0x00100008.c").write_text("void entry(void) {}\n", encoding="utf-8")
    manifest = output_dir / "ghidra_decompile_manifest.csv"
    _write_decompile_manifest(manifest, [
        {"entry": "0x00100008", "name": "entry", "prototype": "void entry(void)",
         "status": "SUCCESS", "elapsed_ms": "20", "output_file": "functions/0x00100008.c", "error": ""},
        {"entry": "0x00100100", "name": "sub_100100", "prototype": "undefined sub_100100(void)",
         "status": "INCOMPLETE", "elapsed_ms": "30000", "output_file": "functions/0x00100100.c", "error": "timeout"},
    ])

    result = validate(manifest, output_dir)
    assert result["status"] == "partial"
    assert result["total_functions"] == 2
    assert result["success"] == 1
    assert result["incomplete"] == 1
    assert result["pseudocode_is_original_source"] is False
    assert json.loads(json.dumps(result))["coverage_ratio"] == 0.5


def test_decompile_manifest_validator_rejects_missing_success_output(tmp_path: Path) -> None:
    import pytest

    from validate_ghidra_decompilation import validate

    output_dir = tmp_path / "decompiled"
    output_dir.mkdir()
    manifest = output_dir / "ghidra_decompile_manifest.csv"
    _write_decompile_manifest(manifest, [{
        "entry": "0x00100008", "name": "entry", "prototype": "void entry(void)",
        "status": "SUCCESS", "elapsed_ms": "20", "output_file": "functions/missing.c", "error": "",
    }])
    with pytest.raises(ValueError, match="outputs missing/empty"):
        validate(manifest, output_dir)


def test_decompile_manifest_validator_rejects_output_path_traversal(tmp_path: Path) -> None:
    import pytest

    from validate_ghidra_decompilation import validate

    output_dir = tmp_path / "decompiled"
    output_dir.mkdir()
    outside = tmp_path / "outside.c"
    outside.write_text("void entry(void) {}\n", encoding="utf-8")
    manifest = output_dir / "ghidra_decompile_manifest.csv"
    _write_decompile_manifest(manifest, [{
        "entry": "0x00100008", "name": "entry", "prototype": "void entry(void)",
        "status": "SUCCESS", "elapsed_ms": "20", "output_file": "../outside.c", "error": "",
    }])
    with pytest.raises(ValueError, match="escapes decompilation directory"):
        validate(manifest, output_dir)
