"""Contract validation tests for JSON output surfaces."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import conductor.governance
from conductor.contracts import validate_contract
from conductor.doctor import run_doctor
from conductor.handoff import create_handoff_envelope, edge_health_report
from conductor.patchbay import Patchbay
from conductor.session import SessionEngine


ROOT = Path(__file__).parent.parent


def run_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_router_validate_json_matches_contract() -> None:
    result = run_cmd("router.py", "validate", "workflow-dsl.yaml", "--format", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    issues = validate_contract("router_validate_output", payload)
    assert not issues


def test_doctor_json_matches_contract() -> None:
    report = run_doctor(ROOT / "workflow-dsl.yaml", format_name="json")
    issues = validate_contract("doctor_report", report)
    assert not issues


def test_patchbay_briefing_matches_contract(tmp_path) -> None:
    registry = tmp_path / "registry-v2.json"
    registry.write_text(json.dumps({"schema_version": "1", "organs": {}}))
    governance = tmp_path / "governance-rules.json"
    governance.write_text(json.dumps({"schema_version": "1", "organ_requirements": {}}))

    with patch.object(conductor.governance, "REGISTRY_PATH", registry), \
         patch.object(conductor.governance, "GOVERNANCE_PATH", governance):
        pb = Patchbay(engine=SessionEngine())
        payload = pb.briefing()
    issues = validate_contract("patchbay_briefing", payload)
    assert not issues


def test_handoff_envelope_matches_contract() -> None:
    payload = create_handoff_envelope(
        source_cluster="web_search",
        target_cluster="knowledge_graph",
        objective="Contract check",
    )
    issues = validate_contract("tool_handoff_v1", payload)
    assert not issues


def test_edge_health_matches_contract(tmp_path) -> None:
    trace_file = tmp_path / "traces.jsonl"
    trace_file.write_text(
        json.dumps(
            {
                "trace_id": "t1",
                "handoff_id": "h1",
                "status": "ok",
                "latency_ms": 1.0,
                "schema_pass": True,
                "failure_bucket": "",
                "retry_count": 0,
                "fallback_used": False,
                "context_loss": False,
                "timestamp": "2026-03-04T00:00:00+00:00",
            }
        )
        + "\n"
    )
    with patch("conductor.handoff.TRACE_LOG_FILE", trace_file):
        payload = edge_health_report(window=200)
    issues = validate_contract("tool_edge_health_v1", payload)
    assert not issues
