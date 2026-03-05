"""Tests for canonical handoff envelopes, routing simulation, and edge health."""

from __future__ import annotations

import json
from itertools import permutations
from pathlib import Path
from unittest.mock import patch

from router import Ontology, RoutingEngine

from conductor.constants import ONTOLOGY_PATH, ROUTING_PATH
from conductor.handoff import (
    HANDOFF_LOG_FILE,
    ROUTE_DECISION_LOG_FILE,
    TRACE_LOG_FILE,
    create_handoff_envelope,
    edge_health_report,
    get_trace_bundle,
    simulate_route_handoff,
    validate_handoff_payload,
)


def _find_fallback_pair(ontology: Ontology, engine: RoutingEngine) -> tuple[str, str]:
    cluster_ids = list(ontology.clusters.keys())
    for source_id, target_id in permutations(cluster_ids, 2):
        if engine.find_routes(source_id, target_id):
            continue
        src = ontology.clusters[source_id]
        tgt = ontology.clusters[target_id]
        if engine.find_path(src.domain, tgt.domain):
            return source_id, target_id
    raise RuntimeError("No fallback pair found in ontology/routing matrix for test.")


def test_create_and_validate_handoff_envelope() -> None:
    payload = create_handoff_envelope(
        source_cluster="web_search",
        target_cluster="knowledge_graph",
        objective="Fetch and persist facts",
        input_artifacts=["query:example"],
    )
    report = validate_handoff_payload(payload)
    assert report["valid"] is True
    assert report["issues"] == []


def test_validate_handoff_fails_missing_required_field() -> None:
    payload = {
        "trace_id": "x",
        "source_cluster": "web_search",
    }
    report = validate_handoff_payload(payload)
    assert report["valid"] is False
    assert report["issues"]


def test_simulate_route_handoff_direct_and_trace_lookup(tmp_path) -> None:
    ontology = Ontology(ONTOLOGY_PATH)
    engine = RoutingEngine(ROUTING_PATH, ontology)

    handoff_file = tmp_path / "handoffs.jsonl"
    trace_file = tmp_path / "traces.jsonl"
    route_file = tmp_path / "decisions.jsonl"

    with patch("conductor.handoff.HANDOFF_LOG_FILE", handoff_file), \
         patch("conductor.handoff.TRACE_LOG_FILE", trace_file), \
         patch("conductor.handoff.ROUTE_DECISION_LOG_FILE", route_file), \
         patch("conductor.handoff.log_event"):
        result = simulate_route_handoff(
            ontology=ontology,
            engine=engine,
            source_cluster="web_search",
            target_cluster="knowledge_graph",
            objective="Direct route smoke test",
        )
        assert result["ok"] is True
        assert result["trace"]["status"] in {"ok", "fallback"}

        trace_id = result["handoff"]["trace_id"]
        bundle = get_trace_bundle(trace_id)

    assert bundle["trace_id"] == trace_id
    assert bundle["handoff"] is not None
    assert bundle["trace"] is not None
    assert bundle["route_decision"] is not None


def test_simulate_route_handoff_fallback_path(tmp_path) -> None:
    ontology = Ontology(ONTOLOGY_PATH)
    engine = RoutingEngine(ROUTING_PATH, ontology)
    source_id, target_id = _find_fallback_pair(ontology, engine)

    with patch("conductor.handoff.HANDOFF_LOG_FILE", tmp_path / "handoffs.jsonl"), \
         patch("conductor.handoff.TRACE_LOG_FILE", tmp_path / "traces.jsonl"), \
         patch("conductor.handoff.ROUTE_DECISION_LOG_FILE", tmp_path / "decisions.jsonl"), \
         patch("conductor.handoff.log_event"):
        result = simulate_route_handoff(
            ontology=ontology,
            engine=engine,
            source_cluster=source_id,
            target_cluster=target_id,
            objective="Fallback route test",
        )

    assert result["trace"]["status"] == "fallback"
    assert result["route_decision"]["decision"] == "fallback"
    assert result["route_decision"]["selected_path"]
    assert "fallback_tools" in result["route_decision"]


def test_simulate_route_handoff_invalid_cluster_fails(tmp_path) -> None:
    ontology = Ontology(ONTOLOGY_PATH)
    engine = RoutingEngine(ROUTING_PATH, ontology)

    with patch("conductor.handoff.HANDOFF_LOG_FILE", tmp_path / "handoffs.jsonl"), \
         patch("conductor.handoff.TRACE_LOG_FILE", tmp_path / "traces.jsonl"), \
         patch("conductor.handoff.ROUTE_DECISION_LOG_FILE", tmp_path / "decisions.jsonl"), \
         patch("conductor.handoff.log_event"):
        result = simulate_route_handoff(
            ontology=ontology,
            engine=engine,
            source_cluster="missing-source-cluster",
            target_cluster="knowledge_graph",
            objective="Failure path test",
        )
    assert result["ok"] is False
    assert result["trace"]["status"] == "fail"
    assert result["trace"]["failure_bucket"] == "invalid_cluster_reference"


def test_edge_health_report_contract_shape(tmp_path) -> None:
    traces = [
        {
            "trace_id": "t1",
            "handoff_id": "h1",
            "status": "ok",
            "latency_ms": 1.2,
            "schema_pass": True,
            "failure_bucket": "",
            "retry_count": 0,
            "fallback_used": False,
            "context_loss": False,
            "timestamp": "2026-03-04T00:00:00+00:00",
        },
        {
            "trace_id": "t2",
            "handoff_id": "h2",
            "status": "fail",
            "latency_ms": 3.5,
            "schema_pass": True,
            "failure_bucket": "route_unresolved",
            "retry_count": 1,
            "fallback_used": False,
            "context_loss": False,
            "timestamp": "2026-03-04T00:00:01+00:00",
        },
    ]
    trace_file = tmp_path / "traces.jsonl"
    trace_file.write_text("\n".join(json.dumps(item) for item in traces) + "\n")

    with patch("conductor.handoff.TRACE_LOG_FILE", trace_file):
        report = edge_health_report(window=200)

    assert report["total_traces"] == 2
    assert set(report.keys()) >= {
        "handoff_success_rate",
        "schema_pass_rate",
        "fallback_rate",
        "p95_edge_latency_ms",
        "context_loss_rate",
        "failure_buckets",
    }
