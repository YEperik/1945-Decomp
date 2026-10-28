"""Preflight tests for the optional external R5900-aware Ghidra pipeline."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_ghidra_headless.sh"
EXPORTER = ROOT / "ghidra_scripts" / "Export1945Evidence.java"


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
        [str(RUNNER), str(image), str(tmp_path / "out")],
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
        [str(RUNNER), str(image), str(tmp_path / "out")],
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
        [str(RUNNER), str(image), str(output_path)],
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
    assert "expected_entry_instruction_present=true" in source
    assert "refusing to report a successful analysis" in source
