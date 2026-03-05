"""CLI tests for newly added governance/plugin/observability flows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "conductor", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        env=merged_env,
    )


def _write_corpus(corpus: Path) -> None:
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "registry-v2.json").write_text(
        json.dumps(
            {
                "version": "2.0",
                "organs": {
                    "ORGAN-III": {
                        "repositories": [
                            {
                                "name": "r1",
                                "promotion_status": "CANDIDATE",
                                "documentation_status": "DEPLOYED",
                                "ci_workflow": "ci.yml",
                                "implementation_status": "ACTIVE",
                            },
                            {
                                "name": "r2",
                                "promotion_status": "CANDIDATE",
                                "documentation_status": "DEPLOYED",
                                "ci_workflow": "ci.yml",
                                "implementation_status": "ACTIVE",
                            },
                            {
                                "name": "r3",
                                "promotion_status": "LOCAL",
                                "documentation_status": "DEPLOYED",
                                "ci_workflow": "ci.yml",
                                "implementation_status": "ACTIVE",
                            },
                            {
                                "name": "r4",
                                "promotion_status": "PUBLIC_PROCESS",
                                "documentation_status": "DEPLOYED",
                                "ci_workflow": "ci.yml",
                                "implementation_status": "ACTIVE",
                            },
                            {
                                "name": "r5",
                                "promotion_status": "PUBLIC_PROCESS",
                                "documentation_status": "DEPLOYED",
                                "ci_workflow": "ci.yml",
                                "implementation_status": "ACTIVE",
                            },
                        ]
                    }
                },
            }
        )
    )
    (corpus / "governance-rules.json").write_text(
        json.dumps({"version": "1.0", "organ_requirements": {}})
    )


def test_policy_simulate_json_uses_requested_bundle(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    _write_corpus(corpus)

    result = run(
        "policy",
        "simulate",
        "--bundle",
        "strict",
        "--format",
        "json",
        env={"ORGANVM_CORPUS_DIR": str(corpus)},
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["bundle"] == "strict"
    assert payload["limits"]["max_candidate_per_organ"] == 2
    assert payload["summary"]["violations_total"] >= 1


def test_observability_report_writes_json(tmp_path) -> None:
    output = tmp_path / "obs-report.json"
    result = run("observability", "report", "--format", "json", "--output", str(output))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "metrics" in payload
    assert "trends" in payload
    written = json.loads(output.read_text())
    assert "generated_at" in written


def test_doctor_apply_migrates_schema_version(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    _write_corpus(corpus)

    result = run(
        "doctor",
        "--workflow",
        "workflow-dsl.yaml",
        "--format",
        "json",
        "--apply",
        env={"ORGANVM_CORPUS_DIR": str(corpus)},
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "applied_fixes" in payload
    registry = json.loads((corpus / "registry-v2.json").read_text())
    governance = json.loads((corpus / "governance-rules.json").read_text())
    assert registry["schema_version"] == "1"
    assert governance["schema_version"] == "1"


def test_wip_auto_promote_cli_apply(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    _write_corpus(corpus)

    preview = run(
        "wip",
        "auto-promote",
        "--format",
        "json",
        env={"ORGANVM_CORPUS_DIR": str(corpus)},
    )
    assert preview.returncode == 0
    preview_payload = json.loads(preview.stdout)
    assert preview_payload["summary"]["dry_run"] is True
    assert preview_payload["summary"]["eligible"] >= 1

    apply = run(
        "wip",
        "auto-promote",
        "--apply",
        "--format",
        "json",
        env={"ORGANVM_CORPUS_DIR": str(corpus)},
    )
    assert apply.returncode == 0
    apply_payload = json.loads(apply.stdout)
    assert apply_payload["summary"]["promoted"] >= 1


def test_plugins_doctor_json_contract_shape() -> None:
    result = run("plugins", "doctor", "--format", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert set(payload.keys()) >= {"ok", "summary", "providers"}


def test_handoff_validate_cli_json(tmp_path) -> None:
    payload_file = tmp_path / "handoff.json"
    payload_file.write_text(
        json.dumps(
            {
                "handoff_id": "h-1",
                "trace_id": "t-1",
                "source_cluster": "web_search",
                "target_cluster": "knowledge_graph",
                "objective": "Fetch and store facts",
                "input_artifacts": ["query:x"],
                "constraints": {},
                "expected_output_contract": "mcp_tool_response",
                "policy_context": {"mode": "test"},
                "deadline_ms": 5000,
                "priority": "high",
                "created_at": "2026-03-04T00:00:00+00:00",
            }
        )
    )
    result = run("handoff", "validate", "--input", str(payload_file), "--format", "json")
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["valid"] is True


def test_route_simulate_and_edge_health_cli_json() -> None:
    route_result = run(
        "route",
        "simulate",
        "--from",
        "web_search",
        "--to",
        "knowledge_graph",
        "--objective",
        "CLI route simulation",
        "--format",
        "json",
    )
    assert route_result.returncode == 0
    route_payload = json.loads(route_result.stdout)
    assert set(route_payload.keys()) >= {"ok", "handoff", "route_decision", "trace"}
    assert route_payload["handoff"]["trace_id"]

    health_result = run("edge", "health", "--format", "json")
    assert health_result.returncode == 0
    health_payload = json.loads(health_result.stdout)
    assert set(health_payload.keys()) >= {"total_traces", "handoff_success_rate", "schema_pass_rate"}


def test_workflow_cli_runtime_lifecycle() -> None:
    state_file = ROOT / ".conductor-workflow-state.json"
    state_file.unlink(missing_ok=True)
    try:
        start_result = run(
            "workflow",
            "start",
            "--name",
            "research-to-spec",
            "--input-json",
            '{"problem":"workflow smoke test"}',
            "--format",
            "json",
        )
        assert start_result.returncode == 0
        start_payload = json.loads(start_result.stdout)
        assert start_payload["workflow"] == "research-to-spec"
        assert start_payload["current_step"]

        step_result = run(
            "workflow",
            "step",
            "--name",
            start_payload["current_step"],
            "--format",
            "json",
        )
        assert step_result.returncode == 0
        step_payload = json.loads(step_result.stdout)
        assert step_payload["status"] in {"CONTINUE", "CHECKPOINT", "FINISHED"}

        status_result = run("workflow", "status", "--format", "json")
        assert status_result.returncode == 0
        status_payload = json.loads(status_result.stdout)
        assert status_payload["active"] is True
    finally:
        run("workflow", "clear")
        state_file.unlink(missing_ok=True)
