"""Structural regression tests for the hosted Android CI workflow."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_android_ci_workflow_is_valid_and_runs_expected_checks():
    workflow_path = ROOT / ".github/workflows/android-ci.yml"
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert workflow["name"] == "Android CI"
    assert workflow["on"]["push"]["branches"] == ["main", "master"]
    assert "pull_request" in workflow["on"]
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["permissions"]["contents"] == "read"

    jobs = workflow["jobs"]
    host_job = jobs["host-tests"]
    android_job = jobs["android-debug-apk"]
    assert android_job["needs"] == "host-tests"

    host_steps = host_job["steps"]
    assert any("pytest -q" in step.get("run", "") for step in host_steps)
    assert any("compileall -q tools tests" in step.get("run", "") for step in host_steps)
    assert any("pip install --upgrade pip pytest pyyaml" in step.get("run", "") for step in host_steps)

    android_steps = android_job["steps"]
    java_step = next(step for step in android_steps if step.get("uses", "").startswith("actions/setup-java@"))
    gradle_setup = next(step for step in android_steps if step.get("uses", "").startswith("gradle/actions/setup-gradle@"))
    build_step = next(step for step in android_steps if "Run Android lint and build debug APK" == step.get("name"))
    artifact_step = next(step for step in android_steps if step.get("uses", "").startswith("actions/upload-artifact@"))

    assert java_step["with"]["java-version"] == "17"
    assert gradle_setup["with"]["gradle-version"] == "8.13"
    assert ":app:lintDebug" in build_step["run"]
    assert ":app:assembleDebug" in build_step["run"]
    assert artifact_step["with"]["path"] == "app/build/outputs/apk/debug/app-debug.apk"
    assert artifact_step["with"]["if-no-files-found"] == "error"
    assert artifact_step["with"]["retention-days"] == "14"

    for job in (host_job, android_job):
        checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@"))
        assert checkout["with"]["persist-credentials"] == "false"
