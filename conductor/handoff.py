"""Canonical tool handoff envelopes, traces, and edge-health reporting."""

from __future__ import annotations

import json
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import BASE, ConductorError
from .contracts import assert_contract, validate_contract
from .observability import log_event

HANDOFF_LOG_FILE = BASE / ".conductor-handoffs.jsonl"
TRACE_LOG_FILE = BASE / ".conductor-traces.jsonl"
ROUTE_DECISION_LOG_FILE = BASE / ".conductor-route-decisions.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    except (OSError, json.JSONDecodeError):
        return []
    return rows


def _tail(rows: list[dict[str, Any]], window: int) -> list[dict[str, Any]]:
    if window <= 0:
        return rows
    return rows[-window:]


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    data = sorted(values)
    idx = max(0, min(len(data) - 1, int((len(data) - 1) * 0.95)))
    return float(data[idx])


def create_handoff_envelope(
    *,
    source_cluster: str,
    target_cluster: str,
    objective: str,
    input_artifacts: list[str] | None = None,
    constraints: dict[str, Any] | None = None,
    expected_output_contract: str = "mcp_tool_response",
    policy_context: dict[str, Any] | None = None,
    deadline_ms: int = 5000,
    priority: str = "high",
) -> dict[str, Any]:
    payload = {
        "handoff_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "source_cluster": source_cluster,
        "target_cluster": target_cluster,
        "objective": objective,
        "input_artifacts": input_artifacts or [],
        "constraints": constraints or {},
        "expected_output_contract": expected_output_contract,
        "policy_context": policy_context or {},
        "deadline_ms": deadline_ms,
        "priority": priority,
        "created_at": _now_iso(),
    }
    assert_contract("tool_handoff_v1", payload)
    return payload


def validate_handoff_payload(payload: dict[str, Any]) -> dict[str, Any]:
    issues = validate_contract("tool_handoff_v1", payload)
    return {
        "valid": len(issues) == 0,
        "issues": [
            {"code": issue.code, "path": issue.path, "message": issue.message}
            for issue in issues
        ],
    }


def _record_handoff(payload: dict[str, Any]) -> None:
    assert_contract("tool_handoff_v1", payload)
    _append_jsonl(HANDOFF_LOG_FILE, payload)


def _record_route_decision(payload: dict[str, Any]) -> None:
    assert_contract("tool_route_decision_v1", payload)
    _append_jsonl(ROUTE_DECISION_LOG_FILE, payload)


def _record_trace(payload: dict[str, Any]) -> None:
    assert_contract("tool_execution_trace_v1", payload)
    _append_jsonl(TRACE_LOG_FILE, payload)


def simulate_route_handoff(
    *,
    ontology: Any,
    engine: Any,
    source_cluster: str,
    target_cluster: str,
    objective: str,
    deadline_ms: int = 5000,
    priority: str = "high",
) -> dict[str, Any]:
    """Run route simulation with validate -> fallback repair behavior."""
    started = time.perf_counter()
    handoff = create_handoff_envelope(
        source_cluster=source_cluster,
        target_cluster=target_cluster,
        objective=objective,
        deadline_ms=deadline_ms,
        priority=priority,
        policy_context={"mode": "simulation"},
    )
    _record_handoff(handoff)

    status = "fail"
    failure_bucket = "route_unresolved"
    fallback_used = False
    retry_count = 0
    selected_path: list[str] = []
    candidate_paths: list[list[str]] = []
    direct_routes_payload: list[dict[str, Any]] = []
    fallback_tools: list[str] = []
    reason = "No route found."

    source = ontology.clusters.get(source_cluster) if ontology else None
    target = ontology.clusters.get(target_cluster) if ontology else None
    if source is None or target is None:
        failure_bucket = "invalid_cluster_reference"
        reason = "Source or target cluster does not exist in ontology."
    else:
        direct_routes = engine.find_routes(source_cluster, target_cluster)
        direct_routes_payload = [
            {
                "id": route.id,
                "data_flow": route.data_flow,
                "protocol": route.protocol,
                "automatable": route.automatable,
                "description": route.description,
            }
            for route in direct_routes
        ]
        if direct_routes_payload:
            status = "ok"
            failure_bucket = ""
            selected_path = [source_cluster, target_cluster]
            candidate_paths = [selected_path]
            reason = "Direct route available."
        else:
            # Repair step: fallback to graph path if no direct route exists.
            candidate_paths = engine.find_cluster_paths(source_cluster, target_cluster)
            if not candidate_paths:
                candidate_paths = engine.find_path(source.domain, target.domain)

            alternatives = engine.get_alternatives(source_cluster)
            if alternatives:
                fallback_tools = list(alternatives.tools_ranked[:3])
                retry_count = len(fallback_tools)
            else:
                retry_count = 1

            if candidate_paths:
                status = "fallback"
                fallback_used = True
                failure_bucket = ""
                selected_path = candidate_paths[0]
                if fallback_tools:
                    reason = (
                        "No direct route; selected fallback multi-hop path and prepared "
                        "alternative tool retry sequence."
                    )
                else:
                    reason = "No direct route; selected fallback multi-hop path."

    latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
    route_decision = {
        "trace_id": handoff["trace_id"],
        "handoff_id": handoff["handoff_id"],
        "decision": "direct" if status == "ok" else "fallback" if status == "fallback" else "fail",
        "selected_path": selected_path,
        "candidate_paths": candidate_paths,
        "fallback_tools": fallback_tools,
        "reason": reason,
        "timestamp": _now_iso(),
    }
    _record_route_decision(route_decision)

    trace = {
        "trace_id": handoff["trace_id"],
        "handoff_id": handoff["handoff_id"],
        "status": status,
        "latency_ms": latency_ms,
        "schema_pass": True,
        "failure_bucket": failure_bucket,
        "retry_count": retry_count,
        "fallback_used": fallback_used,
        "context_loss": False,
        "fallback_tools": fallback_tools,
        "timestamp": _now_iso(),
    }
    _record_trace(trace)
    log_event(
        "handoff.simulate",
        {
            "trace_id": handoff["trace_id"],
            "handoff_id": handoff["handoff_id"],
            "source_cluster": source_cluster,
            "target_cluster": target_cluster,
            "status": status,
            "fallback_used": fallback_used,
            "retry_count": retry_count,
        },
        failed=status == "fail",
        failure_bucket=failure_bucket or None,
    )

    return {
        "ok": status in {"ok", "fallback"},
        "handoff": handoff,
        "route_decision": route_decision,
        "trace": trace,
        "direct_routes": direct_routes_payload,
        "fallback_tools": fallback_tools,
    }


def get_trace_bundle(trace_id: str) -> dict[str, Any]:
    handoffs = [row for row in _read_jsonl(HANDOFF_LOG_FILE) if row.get("trace_id") == trace_id]
    traces = [row for row in _read_jsonl(TRACE_LOG_FILE) if row.get("trace_id") == trace_id]
    decisions = [row for row in _read_jsonl(ROUTE_DECISION_LOG_FILE) if row.get("trace_id") == trace_id]
    return {
        "trace_id": trace_id,
        "handoff": handoffs[-1] if handoffs else None,
        "trace": traces[-1] if traces else None,
        "route_decision": decisions[-1] if decisions else None,
    }


def edge_health_report(window: int = 200) -> dict[str, Any]:
    traces = _tail(_read_jsonl(TRACE_LOG_FILE), window)
    total = len(traces)
    success = sum(1 for row in traces if row.get("status") in {"ok", "fallback"})
    schema_pass = sum(1 for row in traces if bool(row.get("schema_pass")))
    fallback = sum(1 for row in traces if bool(row.get("fallback_used")))
    context_loss = sum(1 for row in traces if bool(row.get("context_loss")))
    latencies = [float(row.get("latency_ms", 0.0)) for row in traces]
    failure_buckets = Counter(
        str(row.get("failure_bucket", "")).strip()
        for row in traces
        if str(row.get("failure_bucket", "")).strip()
    )

    payload = {
        "window": window,
        "generated_at": _now_iso(),
        "total_traces": total,
        "handoff_success_rate": round(success / total, 4) if total else 0.0,
        "schema_pass_rate": round(schema_pass / total, 4) if total else 0.0,
        "fallback_rate": round(fallback / total, 4) if total else 0.0,
        "p95_edge_latency_ms": round(_p95(latencies), 3),
        "context_loss_rate": round(context_loss / total, 4) if total else 0.0,
        "failure_buckets": dict(failure_buckets),
    }
    assert_contract("tool_edge_health_v1", payload)
    return payload


def cluster_health_metrics(window: int = 500) -> dict[str, float]:
    """Compute success rate (0.0-1.0) per cluster ID based on recent traces.
    
    Uses both source and target cluster roles in traces.
    """
    traces = _tail(_read_jsonl(TRACE_LOG_FILE), window)
    handoffs = {h["trace_id"]: h for h in _read_jsonl(HANDOFF_LOG_FILE)}
    
    cluster_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "success": 0})
    
    for t in traces:
        tid = t.get("trace_id")
        h = handoffs.get(tid)
        if not h: continue
        
        src = h.get("source_cluster")
        tgt = h.get("target_cluster")
        ok = t.get("status") in {"ok", "fallback"}
        
        for cid in [src, tgt]:
            if cid:
                cluster_stats[cid]["total"] += 1
                if ok:
                    cluster_stats[cid]["success"] += 1
                    
    return {
        cid: round(stats["success"] / stats["total"], 4)
        for cid, stats in cluster_stats.items()
        if stats["total"] > 0
    }


def assert_handoff_payload(payload: dict[str, Any]) -> None:
    """Raise ConductorError when payload fails the handoff contract."""
    report = validate_handoff_payload(payload)
    if not report["valid"]:
        rendered = "; ".join(
            f"{issue['code']} {issue['path']}: {issue['message']}"
            for issue in report["issues"][:5]
        )
        raise ConductorError(f"Handoff payload failed contract: {rendered}")
