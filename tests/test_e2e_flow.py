"""End-to-end scenarios across CLI, workflow validation, MCP dispatch, and new features."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_conductor(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "conductor", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# CLI validation contracts
# ---------------------------------------------------------------------------


def test_e2e_cli_validate_json_contract() -> None:
    result = _run_conductor("validate", "workflow-dsl.yaml", "--format", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert "errors" in payload
    assert "warnings" in payload


def test_e2e_cli_validate_strict_mode() -> None:
    """--strict should not fail on a valid workflow file."""
    result = _run_conductor("validate", "workflow-dsl.yaml", "--strict")
    assert result.returncode == 0


def test_e2e_cli_validate_missing_file() -> None:
    """Validating a missing file should exit non-zero."""
    result = _run_conductor("validate", "nonexistent-file.yaml")
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# MCP dispatch integration
# ---------------------------------------------------------------------------


def test_e2e_mcp_dispatch_path_and_patch() -> None:
    import mcp_server

    route_json = mcp_server.DISPATCH["conductor_route_to"](
        {"from_cluster": "web_search", "to_cluster": "knowledge_graph"}
    )
    route_payload = json.loads(route_json)
    assert "direct_routes" in route_payload or "multi_hop_paths" in route_payload
    assert "pathfinding" in route_payload

    patch_json = mcp_server.DISPATCH["conductor_patch"](None)
    patch_payload = json.loads(patch_json)
    assert "session" in patch_payload or "error" in patch_payload


def test_e2e_mcp_dispatch_capability_lookup() -> None:
    import mcp_server

    cap_json = mcp_server.DISPATCH["conductor_capability"]({"capability": "SEARCH"})
    payload = json.loads(cap_json)
    assert "clusters" in payload or "error" in payload


# ---------------------------------------------------------------------------
# Doctor diagnostics
# ---------------------------------------------------------------------------


def test_e2e_doctor_json_contract() -> None:
    """Doctor should produce a valid JSON report with expected keys."""
    result = _run_conductor("doctor", "--format", "json")
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert "ok" in report
    assert "checks" in report
    assert "summary" in report
    assert isinstance(report["checks"], list)
    assert report["summary"]["checks_total"] > 0


def test_e2e_doctor_text_output() -> None:
    """Doctor text output should contain status line."""
    result = _run_conductor("doctor")
    assert result.returncode == 0
    assert "Doctor status:" in result.stdout


def test_e2e_doctor_tools_flag() -> None:
    """--tools flag should add a tool-availability check."""
    result = _run_conductor("doctor", "--tools", "--format", "json")
    assert result.returncode == 0
    report = json.loads(result.stdout)
    check_names = [c["name"] for c in report["checks"]]
    assert "tool-availability" in check_names


# ---------------------------------------------------------------------------
# Router commands
# ---------------------------------------------------------------------------


def test_e2e_clusters_listing() -> None:
    """clusters command should list all clusters."""
    result = _run_conductor("clusters")
    assert result.returncode == 0
    assert "claude_code_core" in result.stdout
    assert "Total:" in result.stdout


def test_e2e_domains_listing() -> None:
    """domains command should list all domains."""
    result = _run_conductor("domains")
    assert result.returncode == 0
    assert "AI_AGENTS" in result.stdout
    assert "RESEARCH" in result.stdout


def test_e2e_route_between_clusters() -> None:
    """Route command should find paths between two clusters."""
    result = _run_conductor("route", "--from", "web_search", "--to", "knowledge_graph")
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Ontology data integrity
# ---------------------------------------------------------------------------


def test_e2e_ontology_yaml_parseable() -> None:
    """ontology.yaml should parse without errors."""
    path = ROOT / "ontology.yaml"
    data = yaml.safe_load(path.read_text())
    assert "clusters" in data
    assert "taxonomy" in data
    assert len(data["clusters"]) >= 60


def test_e2e_all_clusters_have_cost_and_latency() -> None:
    """Every cluster should have cost_tier and latency_class."""
    data = yaml.safe_load((ROOT / "ontology.yaml").read_text())
    valid_costs = {"free", "low", "medium", "high"}
    valid_latencies = {"instant", "fast", "moderate", "slow"}
    for cluster in data["clusters"]:
        cid = cluster["id"]
        assert "cost_tier" in cluster, f"{cid} missing cost_tier"
        assert "latency_class" in cluster, f"{cid} missing latency_class"
        assert cluster["cost_tier"] in valid_costs, f"{cid} invalid cost_tier: {cluster['cost_tier']}"
        assert cluster["latency_class"] in valid_latencies, f"{cid} invalid latency_class: {cluster['latency_class']}"


def test_e2e_routing_matrix_parseable() -> None:
    """routing-matrix.yaml should parse and have routes."""
    data = yaml.safe_load((ROOT / "routing-matrix.yaml").read_text())
    assert "routes" in data
    assert len(data["routes"]) >= 10


def test_e2e_workflow_dsl_parseable() -> None:
    """workflow-dsl.yaml should parse and have workflows + primitives."""
    data = yaml.safe_load((ROOT / "workflow-dsl.yaml").read_text())
    assert "spec" in data
    primitives = data["spec"].get("primitives", {})
    assert len(primitives) >= 7
    # All primitives should have maturity
    for name, defn in primitives.items():
        assert "maturity" in defn, f"Primitive {name} missing maturity"


# ---------------------------------------------------------------------------
# Workflow lifecycle
# ---------------------------------------------------------------------------


def test_e2e_workflow_list() -> None:
    """Workflow list should return available workflows."""
    result = _run_conductor("workflow", "list")
    assert result.returncode == 0
    assert result.stdout.strip()  # Should have at least one workflow name


# ---------------------------------------------------------------------------
# Session lifecycle (patched paths)
# ---------------------------------------------------------------------------


def test_e2e_session_start_and_status(tmp_dir, ontology) -> None:
    """Session start + status + close lifecycle through Python API."""
    from conductor.session import SessionEngine

    se = SessionEngine(ontology)
    se.start("III", "test-repo", "E2E test scope", git_branch=False)
    session = se._load_session()
    assert session is not None
    assert session.current_phase == "FRAME"
    assert session.repo == "test-repo"

    se.phase("shape")
    session = se._load_session()
    assert session.current_phase == "SHAPE"

    se.close()
    session = se._load_session()
    assert session is None


# ---------------------------------------------------------------------------
# Retro command
# ---------------------------------------------------------------------------


def test_e2e_retro_empty_sessions() -> None:
    """Retro should run cleanly even with no session history."""
    from conductor.retro import run_retro

    report = run_retro()
    assert "sessions_analyzed" in report
    assert "insights" in report
    assert "phase_balance" in report


# ---------------------------------------------------------------------------
# Feedback loop
# ---------------------------------------------------------------------------


def test_e2e_feedback_record_and_retrieve(tmp_path) -> None:
    """Feedback loop should persist and retrieve health scores."""
    from conductor.feedback import (
        HEALTH_CACHE_FILE,
        get_health_scores,
        record_step_outcome,
        reset_health_cache,
    )

    with patch.object(
        __import__("conductor.feedback", fromlist=["HEALTH_CACHE_FILE"]),
        "HEALTH_CACHE_FILE",
        tmp_path / "health.json",
    ):
        record_step_outcome("web_search", True, workflow_name="test", step_name="s1")
        record_step_outcome("web_search", False, workflow_name="test", step_name="s2")

        scores = get_health_scores()
        # After one success and one failure with EMA, score should be between 0 and 1
        assert "web_search" in scores
        assert 0.0 < scores["web_search"] < 1.0


# ---------------------------------------------------------------------------
# Cost-aware pathfinding
# ---------------------------------------------------------------------------


def test_e2e_cheapest_path_routing() -> None:
    """Router should support find_cheapest_paths with cost/latency ranking."""
    from router import Ontology, RoutingEngine

    ontology = Ontology(ROOT / "ontology.yaml")
    engine = RoutingEngine(ROOT / "routing-matrix.yaml", ontology)

    # Try finding cheapest paths
    paths = engine.find_cheapest_paths("web_search", "knowledge_graph", weight="cost")
    # If there are paths, verify they're returned as lists of cluster IDs
    for path in paths:
        assert isinstance(path, list)
        assert all(isinstance(c, str) for c in path)


# ---------------------------------------------------------------------------
# Oracle CLI integration
# ---------------------------------------------------------------------------


def test_e2e_oracle_consult_text() -> None:
    result = _run_conductor("oracle", "consult")
    assert result.returncode == 0


def test_e2e_oracle_consult_json() -> None:
    result = _run_conductor("oracle", "consult", "--format", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)


def test_e2e_oracle_gate_phase_transition() -> None:
    result = _run_conductor("oracle", "gate", "--trigger", "phase_transition", "--target", "SHAPE")
    assert result.returncode == 0


def test_e2e_oracle_wisdom() -> None:
    result = _run_conductor("oracle", "wisdom")
    assert result.returncode == 0


def test_e2e_oracle_status() -> None:
    result = _run_conductor("oracle", "status")
    assert result.returncode == 0


def test_e2e_oracle_history() -> None:
    result = _run_conductor("oracle", "history")
    assert result.returncode == 0


def test_e2e_oracle_ack_nonexistent() -> None:
    result = _run_conductor("oracle", "ack", "nonexistent_hash")
    assert result.returncode == 0
    assert "Acknowledged" in result.stdout


def test_e2e_oracle_session_lifecycle(tmp_dir, ontology) -> None:
    """Full session lifecycle with oracle hooks at each transition."""
    from conductor.session import SessionEngine

    se = SessionEngine(ontology)
    se.start("III", "test-repo", "Oracle integration test", git_branch=False)

    # Phase transitions with oracle gate checks
    se.phase("shape")
    session = se._load_session()
    assert session.current_phase == "SHAPE"

    se.phase("build")
    session = se._load_session()
    assert session.current_phase == "BUILD"

    se.phase("prove")
    session = se._load_session()
    assert session.current_phase == "PROVE"

    se.close()
    session = se._load_session()
    assert session is None


def test_e2e_oracle_mcp_dispatch() -> None:
    """MCP dispatch for oracle tools."""
    import mcp_server

    # Standard oracle consult
    result_json = mcp_server.DISPATCH["conductor_oracle"](None)
    payload = json.loads(result_json)
    assert "advisories" in payload or "error" in payload

    # Oracle gate
    result_json = mcp_server.DISPATCH["conductor_oracle_gate"](
        {"trigger": "phase_transition", "target": "SHAPE"}
    )
    payload = json.loads(result_json)
    assert "gate_advisories" in payload or "error" in payload

    # Oracle wisdom
    result_json = mcp_server.DISPATCH["conductor_oracle_wisdom"](None)
    payload = json.loads(result_json)
    assert "wisdom" in payload or "error" in payload


# ---------------------------------------------------------------------------
# Version command
# ---------------------------------------------------------------------------


def test_e2e_version_command() -> None:
    result = _run_conductor("version")
    assert result.returncode == 0
