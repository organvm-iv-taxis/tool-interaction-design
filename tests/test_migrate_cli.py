"""CLI tests for migrate commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "conductor", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_migrate_registry_cli(tmp_path) -> None:
    source = tmp_path / "registry.json"
    source.write_text(json.dumps({"organs": {"ORGAN-III": {"repositories": [{"name": "demo"}]}}}))
    target = tmp_path / "registry.out.json"

    result = run("migrate", "registry", "--input", str(source), "--output", str(target))
    assert result.returncode == 0
    payload = json.loads(target.read_text())
    assert payload["schema_version"] == "1"


def test_migrate_governance_cli(tmp_path) -> None:
    source = tmp_path / "governance.json"
    source.write_text(json.dumps({"organ_requirements": {"ORGAN-III": {"requires_tests": True}}}))

    result = run("migrate", "governance", "--input", str(source), "--in-place")
    assert result.returncode == 0
    payload = json.loads(source.read_text())
    assert payload["schema_version"] == "1"
