"""CLI compatibility and release guardrail tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent


def run_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_conductor_help_contains_stable_commands() -> None:
    result = run_cmd("-m", "conductor", "--help")
    assert result.returncode == 0
    for token in ("session", "audit", "validate", "doctor", "migrate", "patch", "plugins", "policy", "observability", "handoff", "edge"):
        assert token in result.stdout


def test_conductor_validate_help_contains_format_and_strict() -> None:
    result = run_cmd("-m", "conductor", "validate", "--help")
    assert result.returncode == 0
    assert "--strict" in result.stdout
    assert "--format" in result.stdout


def test_router_validate_json_output_contract() -> None:
    result = run_cmd("router.py", "validate", "workflow-dsl.yaml", "--format", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert set(payload.keys()) >= {"file", "strict", "ok", "errors", "warnings"}


def test_release_guardrails_script_runs() -> None:
    result = run_cmd("tools/release_guardrails.py")
    assert result.returncode == 0
    assert "release guardrails passed" in result.stdout
