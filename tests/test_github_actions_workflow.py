"""Parse and sanity-check the CI workflow used to build the diagnostic/prototype APK."""
from __future__ import annotations

import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_android_workflow_is_parseable_and_builds_lint_apk() -> None:
    path = ROOT / ".github/workflows/android-ci.yml"
    raw = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)
    assert isinstance(workflow, dict)
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    assert "push" in triggers and "pull_request" in triggers and "workflow_dispatch" in triggers
    assert workflow.get("permissions", {}).get("contents") == "read"
    jobs = workflow["jobs"]
    assert jobs["android-debug-apk"]["needs"] == "host-tests"
    all_steps = [step for job in jobs.values() for step in job["steps"]]
    runs = "\n".join(str(step.get("run", "")) for step in all_steps)
    actions = "\n".join(str(step.get("uses", "")) for step in all_steps)
    assert "pytest -q" in runs
    assert "tools/verify_disc_manifest.py" in runs
    assert "tools/check_repository_hygiene.py" in runs
    assert ":app:lintDebug" in runs
    assert ":app:assembleDebug" in runs
    assert "actions/checkout@" in actions
    assert "actions/upload-artifact@" in actions
    assert "persist-credentials: false" in raw
    push = triggers.get("push")
    assert not isinstance(push, dict) or "branches" not in push, "push trigger must include recovery/feature branches"
