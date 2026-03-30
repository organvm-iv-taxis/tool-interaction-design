#!/usr/bin/env python3
"""
conductor MCP server — Live intelligence layer
================================================
Serves the tool ontology, routing, governance state, and session
awareness as MCP tools that Claude Code can query in real-time.

Tools:
  conductor_route_to     — Find routes between tool clusters
  conductor_capability   — Find tools by capability
  conductor_wip_status   — Current governance/WIP state
  conductor_session_phase — What phase am I in, what's available?
  conductor_suggest      — Natural language → tool recommendation

Usage:
  python3 mcp_server.py              # Start MCP server on stdio
  # Or register in ~/.claude/mcp.json:
  # { "mcpServers": { "conductor": { "command": "python3", "args": ["mcp_server.py"] } } }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MCP_IMPORT_ERROR: ImportError | None = None
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
except ImportError as exc:
    MCP_IMPORT_ERROR = exc
    Server = None  # type: ignore[assignment]
    stdio_server = None  # type: ignore[assignment]

    class TextContent:  # type: ignore[no-redef]
        def __init__(self, *, type: str, text: str):
            self.type = type
            self.text = text

    class Tool:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any):
            self.kwargs = kwargs

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from router import Ontology, RoutingEngine
from conductor.router_extensions import install as _install_router_extensions
_install_router_extensions()
from conductor.constants import (
    ONTOLOGY_PATH,
    PHASE_INSTRUMENTS,
    PHASE_ROLES,
    ROLE_ACTIONS,
    ROUTING_PATH,
    SESSION_STATE_FILE,
    WORKFLOW_DSL_PATH,
    get_phase_clusters,
)
from conductor.contracts import assert_contract
from conductor.executor import WorkflowExecutor
from conductor.governance import GovernanceRuntime
from conductor.handoff import (
    cluster_health_metrics,
    edge_health_report,
    get_trace_bundle,
    validate_handoff_payload,
)
from conductor.patchbay import Patchbay
from conductor.session import SessionEngine


def _ensure_mcp_available() -> None:
    if MCP_IMPORT_ERROR is not None:
        raise RuntimeError("MCP SDK required: pip install mcp")

# ---------------------------------------------------------------------------
# Lazy globals
# ---------------------------------------------------------------------------

_ontology: Ontology | None = None
_engine: RoutingEngine | None = None


def get_ontology() -> Ontology:
    global _ontology
    if _ontology is None:
        _ontology = Ontology(ONTOLOGY_PATH)
    return _ontology


def get_engine() -> RoutingEngine:
    global _engine
    if _engine is None:
        _engine = RoutingEngine(ROUTING_PATH, get_ontology())
    return _engine


def get_session() -> dict | None:
    if SESSION_STATE_FILE.exists():
        try:
            return json.loads(SESSION_STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _encode_mcp_payload(payload: dict[str, Any]) -> str:
    """Validate and encode standard MCP JSON responses."""
    try:
        assert_contract("mcp_tool_response", payload)
        return json.dumps(payload, indent=2)
    except Exception as exc:
        fallback: dict[str, Any] = {
            "error": f"mcp_tool_response contract validation failed: {exc}",
        }
        if isinstance(payload, dict) and "error" in payload:
            fallback["upstream_error"] = str(payload.get("error"))
        return json.dumps(fallback, indent=2)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _route_payload(route: Any) -> dict[str, Any]:
    return {
        "id": route.id,
        "from": route.from_cluster,
        "to": route.to_cluster,
        "data_flow": route.data_flow,
        "protocol": route.protocol,
        "automatable": route.automatable,
        "description": route.description,
    }


def _path_legs(engine: RoutingEngine, path: list[str]) -> list[dict[str, Any]]:
    legs: list[dict[str, Any]] = []
    for source, target in zip(path, path[1:]):
        matches = engine.find_routes(source, target)
        if matches:
            preferred = matches[0]
            legs.append(_route_payload(preferred))
        else:
            legs.append(
                {
                    "id": "",
                    "from": source,
                    "to": target,
                    "data_flow": "",
                    "protocol": "",
                    "automatable": False,
                    "description": "No direct route metadata available for this hop.",
                }
            )
    return legs


def _fallback_sequence(engine: RoutingEngine, path: list[str]) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    for cluster_id in path:
        alternatives = engine.get_alternatives(cluster_id)
        if alternatives:
            sequence.append(
                {
                    "cluster": cluster_id,
                    "tools_ranked": alternatives.tools_ranked,
                }
            )
    return sequence


def route_to(from_cluster: str, to_cluster: str) -> str:
    engine = get_engine()
    ontology = get_ontology()
    
    # Inject real-time health telemetry
    try:
        health = cluster_health_metrics(window=200)
        engine.inject_health_metrics(health)
    except Exception:
        health = {}

    source = ontology.clusters.get(from_cluster)
    target = ontology.clusters.get(to_cluster)

    if source is None or target is None:
        return _encode_mcp_payload({"error": f"Unknown cluster(s): {from_cluster}, {to_cluster}"})

    routes = engine.find_routes(from_cluster, to_cluster)
    direct_routes = [_route_payload(route) for route in routes]
    cluster_paths = engine.find_cluster_paths(from_cluster, to_cluster)
    domain_paths = engine.find_path(source.domain, target.domain)

    if not direct_routes and not cluster_paths and not domain_paths:
        return _encode_mcp_payload({"error": f"No route found: {from_cluster} -> {to_cluster}"})

    path_rows = []
    for path in cluster_paths:
        # Calculate path health
        path_health = round(sum(engine.get_cluster_health(c) for c in path) / len(path), 4)
        path_rows.append({
            "clusters": path,
            "hops": max(0, len(path) - 1),
            "legs": _path_legs(engine, path),
            "reliability_score": path_health,
        })

    fallback_sequences = _fallback_sequence(engine, cluster_paths[0]) if cluster_paths else []

    return _encode_mcp_payload(
        {
            "from_cluster": from_cluster,
            "to_cluster": to_cluster,
            "direct_routes": direct_routes,
            "multi_hop_paths": [path for path in cluster_paths if len(path) > 2] or domain_paths,
            "pathfinding": {
                "cluster_paths": path_rows,
                "domain_paths": domain_paths,
            },
            "fallback_sequences": fallback_sequences,
            "telemetry": {
                "health_metrics_applied": bool(health),
                "source_health": engine.get_cluster_health(from_cluster),
                "target_health": engine.get_cluster_health(to_cluster),
            }
        }
    )


def capability(cap: str) -> str:
    ontology = get_ontology()
    engine = get_engine()

    clusters = ontology.by_capability(cap.upper())
    if not clusters:
        return _encode_mcp_payload({"error": f"No clusters with capability: {cap}"})

    result = [{"id": c.id, "label": c.label, "domain": c.domain,
               "tools_count": len(c.tools), "protocols": c.protocols}
              for c in clusters]

    preferred = engine.capability_tools(cap.upper())

    return _encode_mcp_payload({"clusters": result, "routing_priority": preferred})


def wip_status() -> str:
    try:
        gov = GovernanceRuntime()
        counts = {}
        for organ_key, organ_data in gov.registry.get("organs", {}).items():
            repos = organ_data.get("repositories", [])
            status_counts = {}
            for r in repos:
                s = r.get("promotion_status", "UNKNOWN")
                status_counts[s] = status_counts.get(s, 0) + 1
            counts[organ_key] = status_counts
        return _encode_mcp_payload({"wip_by_organ": counts})
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def session_phase() -> str:
    try:
        session = get_session()
        score = WorkflowExecutor(WORKFLOW_DSL_PATH).get_briefing()
        if not session:
            return _encode_mcp_payload({"active": False, "message": "No active session", "workflow_score": score})

        phase = session.get("current_phase", "UNKNOWN")
        return _encode_mcp_payload({
            "active": True,
            "session_id": session.get("session_id"),
            "organ": session.get("organ"),
            "repo": session.get("repo"),
            "scope": session.get("scope"),
            "current_phase": phase,
            "ai_role": PHASE_ROLES.get(phase, "Unknown"),
            "instrument": PHASE_INSTRUMENTS.get(phase, "Unknown"),
            "allowed_actions": ROLE_ACTIONS.get(phase, {}).get("allowed", []),
            "forbidden_actions": ROLE_ACTIONS.get(phase, {}).get("forbidden", []),
            "active_clusters": get_phase_clusters().get(phase, []),
            "warnings": session.get("warnings", []),
            "workflow_score": score,
        })
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def orchestra_briefing() -> str:
    try:
        session = get_session()
        score = WorkflowExecutor(WORKFLOW_DSL_PATH).get_briefing()
        if not session:
            return _encode_mcp_payload(
                {
                    "active": False,
                    "message": "No active session",
                    "workflow_score": score,
                }
            )

        phase = session.get("current_phase", "UNKNOWN")
        return _encode_mcp_payload(
            {
                "active": True,
                "session_id": session.get("session_id"),
                "organ": session.get("organ"),
                "repo": session.get("repo"),
                "scope": session.get("scope"),
                "phase": phase,
                "role": PHASE_ROLES.get(phase, "Unknown"),
                "instrument": PHASE_INSTRUMENTS.get(phase, "Unknown"),
                "allowed_actions": ROLE_ACTIONS.get(phase, {}).get("allowed", []),
                "forbidden_actions": ROLE_ACTIONS.get(phase, {}).get("forbidden", []),
                "active_clusters": get_phase_clusters().get(phase, []),
                "workflow_score": score,
            }
        )
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def patch(organ: str | None = None) -> str:
    """Full system briefing from the patchbay."""
    try:
        ontology = get_ontology()
        engine = SessionEngine(ontology)
        pb = Patchbay(ontology=ontology, engine=engine)
        organ_filter = None
        if organ:
            from conductor.constants import resolve_organ_key
            organ_filter = resolve_organ_key(organ)
        data = pb.briefing(organ_filter=organ_filter)
        return _encode_mcp_payload(data)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def suggest(task_description: str) -> str:
    ontology = get_ontology()
    engine = get_engine()

    task_lower = task_description.lower()

    # Keyword → capability mapping
    keyword_caps = {
        "search": "SEARCH", "find": "SEARCH", "look up": "SEARCH",
        "read": "READ", "view": "READ", "show": "READ",
        "write": "WRITE", "create": "WRITE", "add": "WRITE",
        "edit": "EDIT", "modify": "EDIT", "change": "EDIT", "update": "EDIT",
        "run": "EXECUTE", "execute": "EXECUTE", "test": "TEST",
        "deploy": "DEPLOY", "ship": "DEPLOY", "publish": "DEPLOY",
        "analyze": "ANALYZE", "review": "ANALYZE", "audit": "ANALYZE",
        "generate": "GENERATE", "build": "GENERATE",
        "monitor": "MONITOR", "watch": "MONITOR",
        "diagram": "VISUALIZE", "visualize": "VISUALIZE", "chart": "VISUALIZE",
    }

    matched_caps = []
    for keyword, cap in keyword_caps.items():
        if keyword in task_lower:
            matched_caps.append(cap)

    if not matched_caps:
        matched_caps = ["SEARCH"]  # Default

    suggestions = []
    seen = set()
    for cap in matched_caps:
        preferred = engine.capability_tools(cap)
        for cid in preferred[:3]:
            if cid not in seen:
                seen.add(cid)
                cluster = ontology.clusters.get(cid)
                if cluster:
                    suggestions.append({
                        "cluster": cid,
                        "label": cluster.label,
                        "capability": cap,
                        "tools_count": len(cluster.tools),
                    })

    # Check session context
    session = get_session()
    phase_note = None
    if session:
        phase = session.get("current_phase", "UNKNOWN")
        phase_clusters = set(get_phase_clusters().get(phase, []))
        for s in suggestions:
            s["in_current_phase"] = s["cluster"] in phase_clusters
        phase_note = f"Current phase: {phase}. Prefer tools from active clusters."

    return _encode_mcp_payload({
        "task": task_description,
        "suggestions": suggestions,
        "phase_context": phase_note,
    })


def edge_health(window: int = 200) -> str:
    try:
        payload = edge_health_report(window=window)
        return _encode_mcp_payload(payload)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def trace_get(trace_id: str) -> str:
    try:
        payload = get_trace_bundle(trace_id)
        if not any(payload.get(key) for key in ("handoff", "trace", "route_decision")):
            return _encode_mcp_payload({"error": f"Trace not found: {trace_id}"})
        return _encode_mcp_payload(payload)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def handoff_validate(payload: dict[str, Any]) -> str:
    try:
        result = validate_handoff_payload(payload)
        return _encode_mcp_payload(result)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def compose_mission(goal: str, from_cluster: str, to_cluster: str) -> str:
    """Synthesize a JIT workflow mission (Score) from a routing path."""
    engine = get_engine()
    ontology = get_ontology()
    
    if not engine or not ontology:
        return _encode_mcp_payload({"error": "Routing engine not initialized"})
        
    try:
        # Inject health for shadow tracing
        health = cluster_health_metrics(window=200)
        engine.inject_health_metrics(health)
    except Exception:
        pass

    from conductor.compiler import WorkflowCompiler
    compiler = WorkflowCompiler(engine, ontology)
    
    try:
        active = SessionEngine(ontology)._load_session()
        session_id = active.session_id if active else "adhoc-compose-mcp"
    except Exception:
        session_id = "adhoc-compose-mcp"

    try:
        state = compiler.compile_mission(
            goal=goal,
            start_cluster=from_cluster,
            end_cluster=to_cluster,
            session_id=session_id
        )
        return _encode_mcp_payload({
            "mission_id": state.workflow_name,
            "session_id": state.session_id,
            "hardened": state.metadata.get("hardened", False),
            "shadow_trace_health": state.metadata.get("shadow_trace_health", 1.0),
            "description": compiler.generate_description(state),
            "next_action": "Call conductor_workflow_step to execute the first step."
        })
    except Exception as e:
        return _encode_mcp_payload({"error": f"Failed to compile mission: {str(e)}"})


def oracle_consult(context: dict[str, Any] | None = None, include_narrative: bool = False) -> str:
    """Consult the Oracle for contextual advisories."""
    try:
        from conductor.oracle import Oracle, OracleContext
        oracle = Oracle()
        ctx = OracleContext.from_dict(context) if context else OracleContext(trigger="manual")
        advisories = oracle.consult(ctx, include_narrative=include_narrative)
        return _encode_mcp_payload({
            "count": len(advisories),
            "advisories": [a.to_dict() for a in advisories],
        })
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def oracle_gate(trigger: str, target: str = "", repo: str = "") -> str:
    """Decision-gate advisory for phase transitions and promotions."""
    try:
        from conductor.oracle import Oracle, OracleContext
        oracle = Oracle()
        session = get_session()
        ctx = OracleContext(
            trigger=trigger,
            session_id=session.get("session_id", "") if session else "",
            current_phase=session.get("current_phase", "") if session else "",
            target_phase=target,
            promotion_repo=repo,
            organ=session.get("organ", "") if session else "",
        )
        advisories = oracle.consult(ctx, gate_mode=True)
        gate_advisories = [a for a in advisories if a.gate_action]
        return _encode_mcp_payload({
            "trigger": trigger,
            "target": target,
            "gate_advisories": [a.to_dict() for a in gate_advisories],
            "all_clear": len(gate_advisories) == 0,
        })
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def oracle_wisdom() -> str:
    """Rich narrative wisdom from the Oracle."""
    try:
        from conductor.oracle import Oracle, OracleContext
        oracle = Oracle()
        session = get_session()
        ctx = OracleContext(
            trigger="manual",
            session_id=session.get("session_id", "") if session else "",
            current_phase=session.get("current_phase", "") if session else "",
            organ=session.get("organ", "") if session else "",
        )
        advisories = oracle.consult(ctx, max_advisories=3, include_narrative=True)
        narrative_advs = [a for a in advisories if a.narrative]
        return _encode_mcp_payload({
            "count": len(narrative_advs),
            "wisdom": [
                {"narrative": a.narrative, "category": a.category, "detector": a.detector}
                for a in narrative_advs
            ],
        })
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def oracle_profile() -> str:
    """Get the Oracle's behavioral profile for the current user."""
    try:
        from conductor.oracle import Oracle
        oracle = Oracle()
        profile = oracle.build_profile()
        return _encode_mcp_payload(profile.to_dict())
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def oracle_detectors() -> str:
    """Get the full detector manifest with effectiveness scores."""
    try:
        from conductor.oracle import Oracle
        oracle = Oracle()
        manifest = oracle.get_detector_manifest()
        return _encode_mcp_payload({
            "count": len(manifest),
            "detectors": manifest,
        })
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def oracle_trends() -> str:
    """Get trend summary: ship rate, duration over recent windows."""
    try:
        from conductor.oracle import Oracle
        oracle = Oracle()
        summary = oracle.get_trend_summary()
        return _encode_mcp_payload(summary)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def oracle_diagnose() -> str:
    """Run Oracle self-diagnostics."""
    try:
        from conductor.oracle import Oracle
        oracle = Oracle()
        diag = oracle.diagnose()
        return _encode_mcp_payload(diag)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def oracle_calibrate(detector: str, action: str = "reset") -> str:
    """Calibrate a detector's effectiveness score."""
    try:
        from conductor.oracle import Oracle
        oracle = Oracle()
        result = oracle.calibrate_detector(detector, action)
        return _encode_mcp_payload(result)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


# ---------------------------------------------------------------------------
# Guardian Angel MCP handlers
# ---------------------------------------------------------------------------


def guardian_counsel(context: dict[str, Any] | None = None) -> str:
    """Guardian Angel enhanced consult with wisdom enrichment."""
    try:
        from conductor.guardian import GuardianAngel
        from conductor.oracle import OracleContext
        guardian = GuardianAngel()
        ctx = OracleContext.from_dict(context) if context else None
        advisories = guardian.counsel(ctx)
        return _encode_mcp_payload({
            "count": len(advisories),
            "advisories": [a.to_dict() for a in advisories],
        })
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def guardian_whisper(action: str, context: dict[str, Any] | None = None) -> str:
    """Lightweight ambient guidance for a specific action."""
    try:
        from conductor.guardian import GuardianAngel
        from conductor.oracle import OracleContext
        guardian = GuardianAngel()
        ctx = OracleContext.from_dict(context) if context else None
        adv = guardian.whisper(action, ctx)
        return _encode_mcp_payload(adv.to_dict() if adv else {"whisper": None})
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def guardian_teach(topic: str) -> str:
    """On-demand pedagogical lookup of a principle."""
    try:
        from conductor.guardian import GuardianAngel
        guardian = GuardianAngel()
        result = guardian.teach(topic)
        return _encode_mcp_payload(result)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def guardian_landscape(decision: str, context: dict[str, Any] | None = None) -> str:
    """Risk-reward landscape mapping for a decision."""
    try:
        from conductor.guardian import GuardianAngel
        from conductor.oracle import OracleContext
        guardian = GuardianAngel()
        ctx = OracleContext.from_dict(context) if context else None
        result = guardian.landscape(decision, ctx)
        return _encode_mcp_payload(result)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def guardian_mastery() -> str:
    """Growth and mastery report."""
    try:
        from conductor.guardian import GuardianAngel
        guardian = GuardianAngel()
        report = guardian.growth_report()
        return _encode_mcp_payload(report)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def mark_internalized(wisdom_id: str, evidence: str = "") -> str:
    """Mark a wisdom principle as internalized."""
    try:
        from conductor.oracle import Oracle
        oracle = Oracle()
        oracle._mark_internalized(wisdom_id, evidence)
        report = oracle.get_mastery_report()
        return _encode_mcp_payload(report)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def guardian_corpus(search: str | None = None) -> str:
    """Browse or search the Guardian wisdom corpus."""
    try:
        from conductor.guardian import GuardianAngel
        guardian = GuardianAngel()
        result = guardian.corpus_search(search)
        return _encode_mcp_payload(result)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def preflight(agent: str = "unknown", cwd: str | None = None) -> str:
    """Run preflight: infer context, build runway briefing, auto-start session."""
    try:
        from conductor.preflight import run_preflight

        result = run_preflight(
            agent=agent or "unknown",
            cwd=cwd or str(Path.cwd()),
            auto_start=True,
            json_output=True,
        )
        return _encode_mcp_payload(result.to_dict())
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def active_sessions_list() -> str:
    """List all currently active sessions across all agents."""
    try:
        engine = SessionEngine()
        sessions = engine.active_sessions()
        return _encode_mcp_payload({
            "count": len(sessions),
            "sessions": [s.to_dict() for s in sessions],
        })
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def session_start(organ: str, repo: str, scope: str, agent: str = "unknown") -> str:
    """Start a new Conductor session with FRAME→SHAPE→BUILD→PROVE lifecycle."""
    try:
        ontology = get_ontology()
        engine = SessionEngine(ontology)
        session = engine.start(organ, repo, scope, git_branch=False, agent=agent)
        phase = session.current_phase
        return _encode_mcp_payload({
            "session_id": session.session_id,
            "organ": session.organ,
            "repo": session.repo,
            "scope": session.scope,
            "current_phase": phase,
            "ai_role": PHASE_ROLES.get(phase, "Unknown"),
            "active_clusters": get_phase_clusters().get(phase, []),
            "agent": session.agent,
            "message": f"Session started in {phase} phase. Explore before building.",
        })
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def session_transition(target_phase: str, agent: str = "") -> str:
    """Transition to a new phase. Hard gate: FRAME→SHAPE→BUILD→PROVE only."""
    try:
        ontology = get_ontology()
        engine = SessionEngine(ontology)
        engine.phase(target_phase, agent=agent)
        # Read back the session state after transition
        session = engine._load_session()
        if not session:
            return _encode_mcp_payload({"error": "Session closed after transition"})
        phase = session.current_phase
        return _encode_mcp_payload({
            "session_id": session.session_id,
            "current_phase": phase,
            "ai_role": PHASE_ROLES.get(phase, "Unknown"),
            "active_clusters": get_phase_clusters().get(phase, []),
            "duration_minutes": session.duration_minutes,
            "message": f"Transitioned to {phase}.",
        })
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def gate_check() -> str:
    """Check for blocking advisories before major actions."""
    try:
        from conductor.guardian import GuardianAngel
        from conductor.oracle import OracleContext
        guardian = GuardianAngel()
        session = get_session()
        ctx = OracleContext(
            trigger="gate_check",
            session_id=session.get("session_id", "") if session else "",
            current_phase=session.get("current_phase", "") if session else "",
            organ=session.get("organ", "") if session else "",
        )
        advisories = guardian.counsel(ctx, gate_mode=True)
        gate_advisories = [a for a in advisories if a.gate_action]
        return _encode_mcp_payload({
            "has_session": session is not None,
            "current_phase": session.get("current_phase", "") if session else "NONE",
            "gate_advisories": [a.to_dict() for a in gate_advisories],
            "all_clear": len(gate_advisories) == 0,
            "advisory_count": len(advisories),
            "top_advisories": [a.to_dict() for a in advisories[:3]],
        })
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


def workflow_status() -> str:
    from conductor.executor import WorkflowExecutor
    from conductor.constants import WORKFLOW_DSL_PATH
    executor = WorkflowExecutor(WORKFLOW_DSL_PATH)
    briefing = executor.get_briefing()
    return _encode_mcp_payload(briefing)

def workflow_step(tool_output: Any = None, checkpoint_action: str | None = None) -> str:
    from conductor.executor import WorkflowExecutor
    from conductor.constants import WORKFLOW_DSL_PATH
    executor = WorkflowExecutor(WORKFLOW_DSL_PATH)
    briefing = executor.get_briefing()
    if not briefing.get("active"):
        return _encode_mcp_payload({"error": "No active workflow. Start one using conductor_compose_mission or conductor CLI."})
    
    current_step = briefing.get("current_step")
    if not current_step:
        return _encode_mcp_payload({"error": "Workflow is active but has no current step to execute.", "status": briefing.get("status")})
    
    try:
        result = executor.run_step(
            step_name=current_step,
            tool_output=tool_output,
            checkpoint_action=checkpoint_action
        )
        return _encode_mcp_payload(result)
    except Exception as e:
        return _encode_mcp_payload({"error": f"Failed to run step '{current_step}': {str(e)}"})


# ---------------------------------------------------------------------------
# Directive ingestion
# ---------------------------------------------------------------------------


def ingest(content: str, source_agent: str, topic: str, tags: list[str] | None = None) -> str:
    """Ingest raw content from a directive, fan out to all targets.

    Produces 4 artifacts:
    1. Reference file in praxis-perpetua/research/
    2. Alchemia intake artifact in alchemia-ingestvm/intake/ai-transcripts/
    3. SOP stub in organvm-engine/.sops/ (if not already present)
    4. Engine guidance in response JSON
    """
    import hashlib
    import os
    import re
    from datetime import datetime, timezone

    workspace = Path(os.environ.get("ORGANVM_WORKSPACE_DIR", Path.home() / "Workspace"))
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    tag_list = tags or []
    artifacts: dict[str, Any] = {}

    # 1. Reference file -> praxis-perpetua/research/
    research_dir = workspace / "meta-organvm" / "praxis-perpetua" / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    ref_path = research_dir / f"{date_str}-{slug}.md"
    # Avoid clobbering existing files
    counter = 2
    while ref_path.exists():
        ref_path = research_dir / f"{date_str}-{slug}-v{counter}.md"
        counter += 1
    ref_content = (
        f"---\n"
        f"source: {source_agent}\n"
        f"date: {date_str}\n"
        f"topic: {topic}\n"
        f"tags: {json.dumps(tag_list)}\n"
        f"content_hash: {content_hash}\n"
        f"ingested_via: conductor_ingest\n"
        f"---\n"
        f"# {topic.replace('-', ' ').title()}\n\n"
        f"{content}\n"
    )
    ref_path.write_text(ref_content, encoding="utf-8")
    artifacts["reference"] = str(ref_path)

    # 2. Alchemia intake artifact
    intake_dir = workspace / "alchemia-ingestvm" / "intake" / "ai-transcripts"
    intake_dir.mkdir(parents=True, exist_ok=True)
    intake_path = intake_dir / f"{date_str}-{slug}.json"
    counter = 2
    while intake_path.exists():
        intake_path = intake_dir / f"{date_str}-{slug}-v{counter}.json"
        counter += 1
    intake_data = {
        "schema_version": "1.0",
        "source": source_agent,
        "source_type": "ai_transcript",
        "topic": topic,
        "tags": tag_list,
        "content_preview": content[:500],
        "content_hash": content_hash,
        "reference_path": str(ref_path),
        "status": "intake",
        "ingested_at": now.isoformat(),
    }
    intake_path.write_text(json.dumps(intake_data, indent=2), encoding="utf-8")
    artifacts["intake"] = str(intake_path)

    # 3. SOP stub (only if not already present)
    sops_dir = workspace / "meta-organvm" / "organvm-engine" / ".sops"
    sops_dir.mkdir(parents=True, exist_ok=True)
    sop_path = sops_dir / f"{slug}.md"
    if sop_path.exists():
        artifacts["sop"] = str(sop_path)
        artifacts["sop_status"] = "already_exists"
    else:
        title = topic.replace("-", " ").title()
        sop_content = (
            f"---\n"
            f"sop: true\n"
            f"name: {slug}\n"
            f"scope: system\n"
            f"phase: any\n"
            f"triggers: []\n"
            f"complements: []\n"
            f"overrides: null\n"
            f"---\n"
            f"# {title}\n\n"
            f"## Purpose\n\n"
            f"Generated from {source_agent} transcript on {date_str}.\n"
            f"Topic: {topic}\n\n"
            f"## Key Findings\n\n"
            f"<!-- Extract key findings from the ingested content -->\n\n"
            f"## Procedure\n\n"
            f"<!-- Define operational procedures based on findings -->\n\n"
            f"## Verification\n\n"
            f"<!-- How to confirm procedures are followed -->\n"
        )
        sop_path.write_text(sop_content, encoding="utf-8")
        artifacts["sop"] = str(sop_path)
        artifacts["sop_status"] = "created"

    # 4. Engine guidance
    artifacts["guidance"] = {
        "next_steps": [
            f"Review reference at {artifacts['reference']}",
            f"Run 'alchemia intake' to process {artifacts['intake']}",
            f"Run 'organvm sop discover --json | grep {slug}' to verify SOP",
            "Update SOP with extracted findings from the transcript",
        ],
        "prompting_module": "organvm_engine.prompting.standards" if "prompting" in slug else None,
    }

    return _encode_mcp_payload({
        "status": "ingested",
        "topic": topic,
        "source_agent": source_agent,
        "content_hash": content_hash,
        "artifacts": artifacts,
    })


# ---------------------------------------------------------------------------
# Fleet orchestration tools
# ---------------------------------------------------------------------------


def fleet_status() -> str:
    from conductor.fleet import FleetRegistry
    from conductor.fleet_usage import FleetUsageTracker
    from datetime import date

    registry = FleetRegistry()
    tracker = FleetUsageTracker()
    today = date.today()
    daily = tracker.daily_snapshot(today)

    agents = []
    for agent in registry.active_agents():
        usage = daily.get(agent.name, {})
        agents.append({
            "name": agent.name,
            "display_name": agent.display_name,
            "provider": agent.provider,
            "tier": agent.subscription.tier,
            "strengths": list(agent.capabilities.strengths),
            "phase_affinity": agent.phase_affinity,
            "today_sessions": usage.get("sessions", 0),
            "today_tokens": usage.get("total_tokens", 0),
            "today_cost": usage.get("total_cost_usd", 0.0),
        })

    return _encode_mcp_payload({
        "date": today.isoformat(),
        "active_agents": len(agents),
        "agents": agents,
    })


def fleet_recommend(phase: str, task_tags: list | None = None, sensitivity: dict | None = None, context_size: int = 0) -> str:
    from conductor.fleet_router import FleetRouter

    router = FleetRouter()
    scores = router.recommend(
        phase=phase,
        task_tags=task_tags or [],
        sensitivity_required=sensitivity or {},
        context_size=context_size,
    )

    recommendations = []
    for s in scores:
        recommendations.append({
            "agent": s.agent,
            "display_name": s.display_name,
            "score": s.score,
            "breakdown": s.breakdown,
            "explanation": router.explain(s),
        })

    return _encode_mcp_payload({
        "phase": phase,
        "recommendations": recommendations,
        "top_pick": recommendations[0]["agent"] if recommendations else None,
    })


def fleet_dispatch(description: str, phase: str = "BUILD", work_type: str | None = None) -> str:
    from conductor.task_dispatcher import TaskDispatcher
    from conductor.fleet import FleetRegistry

    dispatcher = TaskDispatcher()
    plan = dispatcher.plan(
        description=description,
        phase=phase.upper(),
        work_type=work_type,
    )

    registry = FleetRegistry()
    ranked = []
    for s in plan.ranked_agents:
        agent = registry.get(s.agent)
        entry = {
            "agent": s.agent,
            "display_name": s.display_name,
            "score": s.score,
            "self_audit_trusted": agent.guardrails.self_audit_trusted if agent else True,
            "max_files_before_checkpoint": agent.guardrails.max_files_before_checkpoint if agent else 50,
        }
        if agent and agent.restrictions.never_touch:
            entry["never_touch"] = list(agent.restrictions.never_touch)
        ranked.append(entry)

    result = {
        "work_type": plan.work_type,
        "cognitive_class": plan.cognitive_class,
        "verification_policy": plan.verification_policy,
        "recommended_agent": plan.recommended,
        "ranked_agents": ranked,
        "excluded_agents": plan.excluded_agents,
    }

    # Add dispatch guidance
    if plan.recommended and plan.recommended != "claude":
        result["dispatch_guidance"] = (
            f"This work should be dispatched to {plan.recommended}. "
            f"Generate a guardrailed handoff with conductor_fleet_guardrailed_handoff, "
            f"then present it to the user for handoff."
        )
    elif plan.recommended == "claude":
        result["dispatch_guidance"] = (
            "This work stays with Claude. Proceed directly."
        )
    else:
        result["dispatch_guidance"] = "No agent qualifies. Review work type classification."

    return _encode_mcp_payload(result)


def fleet_guardrailed_handoff(
    to_agent: str,
    summary: str,
    work_type: str = "",
    constraints_locked: list | None = None,
    files_locked: list | None = None,
    work_completed: list | None = None,
    conventions: dict | None = None,
) -> str:
    from conductor.fleet import FleetRegistry
    from conductor.fleet_handoff import GuardrailedHandoffBrief, format_markdown, log_handoff
    from conductor.session import SessionEngine

    registry = FleetRegistry()
    receiver = registry.get(to_agent)

    # Build receiver restrictions from fleet.yaml
    receiver_restrictions: dict = {}
    verification_required = False
    if receiver:
        receiver_restrictions = {
            "restrictions": {
                "never_touch": list(receiver.restrictions.never_touch),
                "never_decide": list(receiver.restrictions.never_decide),
                "max_cognitive_class": receiver.restrictions.max_cognitive_class,
            },
            "guardrails": {
                "self_audit_trusted": receiver.guardrails.self_audit_trusted,
                "max_files_before_checkpoint": receiver.guardrails.max_files_before_checkpoint,
            },
        }
        if not receiver.guardrails.self_audit_trusted:
            verification_required = True

    # Try to get session context
    engine = SessionEngine()
    session = engine._load_session()
    session_id = session.session_id if session else "no-session"
    phase = session.current_phase if session else "BUILD"
    organ = session.organ if session else "UNKNOWN"
    repo = session.repo if session else "unknown"
    scope = session.scope if session else ""
    from_agent = session.agent if session else "claude"
    warnings = list(session.warnings) if session and hasattr(session, "warnings") else []

    brief = GuardrailedHandoffBrief(
        from_agent=from_agent,
        to_agent=to_agent,
        session_id=session_id,
        phase=phase,
        organ=organ,
        repo=repo,
        scope=scope,
        summary=summary,
        constraints_locked=constraints_locked or [],
        files_locked=files_locked or [],
        work_completed=work_completed or [],
        conventions=conventions or {},
        work_type=work_type,
        verification_required=verification_required,
        receiver_restrictions=receiver_restrictions,
        warnings=warnings,
    )

    log_handoff(brief)
    md = format_markdown(brief)

    # Write active handoff for receiving agent to read
    from conductor.fleet_handoff import write_active_handoff
    from conductor.constants import BASE
    active_path = write_active_handoff(brief, BASE)

    return _encode_mcp_payload({
        "handoff_markdown": md,
        "to_agent": to_agent,
        "verification_required": verification_required,
        "active_handoff_path": str(active_path),
        "envelope": brief.to_dict(),
    })


def fleet_cross_verify(changed_files: list, diff_content: str = "") -> str:
    import json as _json
    from conductor.constants import STATE_DIR
    from conductor.cross_verify import CrossVerifier
    from conductor.fleet_handoff import GuardrailedHandoffBrief

    handoff_log = STATE_DIR / "handoff-log.jsonl"
    if not handoff_log.exists():
        return _encode_mcp_payload({"error": "No handoff log found. Generate a handoff first."})

    lines = handoff_log.read_text().strip().splitlines()
    if not lines:
        return _encode_mcp_payload({"error": "Handoff log is empty."})

    last = _json.loads(lines[-1])
    if "constraints_locked" not in last:
        return _encode_mcp_payload({"error": "Last handoff is not guardrailed. Nothing to verify."})

    brief = GuardrailedHandoffBrief.from_dict(last)
    verifier = CrossVerifier()
    report = verifier.verify(
        handoff=brief,
        changed_files=changed_files,
        diff_content=diff_content,
        verifier_agent="claude",
    )

    # Auto-clear active handoff on verification pass
    if report.passed:
        from conductor.fleet_handoff import clear_active_handoff
        from conductor.constants import BASE
        cleared = clear_active_handoff(BASE)
        result = report.to_dict()
        result["active_handoff_cleared"] = cleared
        return _encode_mcp_payload(result)

    return _encode_mcp_payload(report.to_dict())


def retro_session(session_id: str | None = None) -> str:
    """Generate a per-session retrospective and inject feedback into system loops."""
    from conductor.sprint_ledger import alchemize_ledger, build_ledger

    try:
        sid = None if (not session_id or session_id == "latest") else session_id
        ledger = build_ledger(session_id=sid)
        # MCP calls always inject feedback — agents don't collect without acting
        actions = alchemize_ledger(ledger)
        payload = ledger.to_dict()
        payload["feedback_actions"] = actions
        return _encode_mcp_payload(payload)
    except Exception as e:
        return _encode_mcp_payload({"error": str(e)})


# ---------------------------------------------------------------------------
# MCP Server setup
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="conductor_route_to",
        description="Find routes between tool clusters and return pathfinding directions with fallback tool sequences.",
        inputSchema={
            "type": "object",
            "properties": {
                "from_cluster": {"type": "string", "description": "Source cluster ID (e.g., web_search)"},
                "to_cluster": {"type": "string", "description": "Target cluster ID (e.g., knowledge_graph)"},
            },
            "required": ["from_cluster", "to_cluster"],
        },
    ),
    Tool(
        name="conductor_capability",
        description="Find tool clusters by capability (SEARCH, READ, WRITE, DEPLOY, etc.).",
        inputSchema={
            "type": "object",
            "properties": {
                "capability": {"type": "string", "description": "Capability name (e.g., SEARCH, DEPLOY, ANALYZE)"},
            },
            "required": ["capability"],
        },
    ),
    Tool(
        name="conductor_wip_status",
        description="Get current WIP (work-in-progress) status across all organs — promotion states, CANDIDATE counts.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="conductor_session_phase",
        description="Get current session phase (FRAME/SHAPE/BUILD/PROVE), active clusters, and AI role.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="conductor_orchestra_briefing",
        description="Live orchestra briefing: current phase role/instrument and active workflow score.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="conductor_suggest",
        description="Given a natural language task description, suggest which tool clusters to use.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_description": {"type": "string", "description": "What you want to accomplish"},
            },
            "required": ["task_description"],
        },
    ),
    Tool(
        name="conductor_patch",
        description="Full system briefing — session state, system pulse, work queue, stats, and suggested action.",
        inputSchema={
            "type": "object",
            "properties": {
                "organ": {"type": "string", "description": "Optional organ filter (e.g., III, META)"},
            },
        },
    ),
    Tool(
        name="conductor_edge_health",
        description="Compute edge health metrics from recorded handoff traces.",
        inputSchema={
            "type": "object",
            "properties": {
                "window": {"type": "integer", "description": "Last N traces to include (default 200)"},
            },
        },
    ),
    Tool(
        name="conductor_trace_get",
        description="Fetch one trace bundle by trace_id (handoff + route decision + execution trace).",
        inputSchema={
            "type": "object",
            "properties": {
                "trace_id": {"type": "string", "description": "Trace identifier"},
            },
            "required": ["trace_id"],
        },
    ),
    Tool(
        name="conductor_handoff_validate",
        description="Validate a tool-handoff payload against the canonical handoff contract.",
        inputSchema={
            "type": "object",
            "properties": {
                "payload": {"type": "object", "description": "Candidate handoff payload"},
            },
            "required": ["payload"],
        },
    ),
    Tool(
        name="conductor_compose_mission",
        description="Synthesize a dynamic JIT Workflow Score based on a high-level goal and routing path.",
        inputSchema={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "High-level goal description"},
                "from_cluster": {"type": "string", "description": "Starting tool cluster ID"},
                "to_cluster": {"type": "string", "description": "Target tool cluster ID"},
            },
            "required": ["goal", "from_cluster", "to_cluster"],
        },
    ),
    Tool(
        name="conductor_oracle",
        description="Consult the Oracle for contextual advisories — process drift, risk detection, momentum, growth opportunities.",
        inputSchema={
            "type": "object",
            "properties": {
                "context": {"type": "object", "description": "Optional context (trigger, current_phase, target_phase, organ, etc.)"},
                "include_narrative": {"type": "boolean", "description": "Include rich narrative wisdom (default false)"},
            },
        },
    ),
    Tool(
        name="conductor_oracle_gate",
        description="Decision-gate advisory for phase transitions and promotions — checks readiness before critical transitions.",
        inputSchema={
            "type": "object",
            "properties": {
                "trigger": {"type": "string", "description": "Trigger type: phase_transition or promotion"},
                "target": {"type": "string", "description": "Target phase (SHAPE, BUILD, PROVE, DONE) or promotion state"},
                "repo": {"type": "string", "description": "Repository name (for promotion gates)"},
            },
            "required": ["trigger"],
        },
    ),
    Tool(
        name="conductor_oracle_wisdom",
        description="Rich narrative wisdom from the Oracle — milestone acknowledgments, phase metaphors, streak encouragement.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="conductor_oracle_profile",
        description="Behavioral profile from cross-session analysis — ship rate, cadence, risk appetite, preferred organs, active hours.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="conductor_oracle_detectors",
        description="List all Oracle detectors with categories, enabled status, and effectiveness scores.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="conductor_oracle_trends",
        description="Trend summary — ship rate, duration, and session counts over recent windows (last 5/10/20 sessions).",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="conductor_oracle_diagnose",
        description="Oracle self-diagnostics — detector health, state file integrity, data freshness.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="conductor_oracle_calibrate",
        description="Calibrate a detector's effectiveness score (reset, boost, or penalize).",
        inputSchema={
            "type": "object",
            "properties": {
                "detector": {"type": "string", "description": "Detector name (e.g., process_drift, burnout_risk)"},
                "action": {"type": "string", "enum": ["reset", "boost", "penalize"], "description": "Calibration action"},
            },
            "required": ["detector"],
        },
    ),
    # Guardian Angel tools
    Tool(
        name="conductor_guardian_counsel",
        description="Guardian Angel enhanced consult — Oracle advisories enriched with canonical wisdom, mastery tracking, and pedagogical teaching.",
        inputSchema={
            "type": "object",
            "properties": {
                "context": {"type": "object", "description": "Optional context (trigger, current_phase, target_phase, organ, etc.)"},
            },
        },
    ),
    Tool(
        name="conductor_guardian_whisper",
        description="Lightweight ambient guidance — check if an action has any canonical warnings before proceeding.",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action description to check (e.g., 'rewriting the auth module')"},
                "context": {"type": "object", "description": "Optional session context"},
            },
            "required": ["action"],
        },
    ),
    Tool(
        name="conductor_guardian_teach",
        description="On-demand teaching — look up a principle by topic/ID, get pedagogical explanation and mastery history.",
        inputSchema={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic or principle ID (e.g., 'tdd', 'SOLID', 'mvp', 'eng.tdd')"},
            },
            "required": ["topic"],
        },
    ),
    Tool(
        name="conductor_guardian_landscape",
        description="Map risk-reward poles for a decision with personalized positioning based on behavioral profile.",
        inputSchema={
            "type": "object",
            "properties": {
                "decision": {"type": "string", "description": "Decision description (e.g., 'rewrite vs refactor the API layer')"},
                "context": {"type": "object", "description": "Optional session context"},
            },
            "required": ["decision"],
        },
    ),
    Tool(
        name="conductor_guardian_mastery",
        description="Full mastery and growth report — principles encountered, internalized, learning velocity, growth areas.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="conductor_mark_internalized",
        description="Mark a wisdom principle as internalized (behavioral change confirmed). Closes the mastery loop.",
        inputSchema={
            "type": "object",
            "properties": {
                "wisdom_id": {"type": "string", "description": "Wisdom ID to mark (e.g., 'biz.ship_speed', 'practice.tdd')"},
                "evidence": {"type": "string", "description": "Optional evidence of behavioral change"},
            },
            "required": ["wisdom_id"],
        },
    ),
    Tool(
        name="conductor_guardian_corpus",
        description="Browse or search the Guardian wisdom corpus with optional query text.",
        inputSchema={
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Optional search query (e.g., 'tdd', 'mvp', 'scylla')"},
            },
        },
    ),
    # Preflight / multi-session
    Tool(
        name="conductor_preflight",
        description="Run preflight: infer organ/repo from cwd, show runway briefing (active agents, work items, collisions), auto-start a session.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Agent identity (claude, gemini, codex, etc.)"},
                "cwd": {"type": "string", "description": "Working directory to infer organ/repo from"},
            },
        },
    ),
    Tool(
        name="conductor_active_sessions",
        description="List all currently active Conductor sessions across all agents.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # Session lifecycle tools
    Tool(
        name="conductor_session_start",
        description="Start a new Conductor session with FRAME→SHAPE→BUILD→PROVE lifecycle. Must be called before any work begins.",
        inputSchema={
            "type": "object",
            "properties": {
                "organ": {"type": "string", "description": "Organ key (I, II, III, IV, V, VI, VII, META)"},
                "repo": {"type": "string", "description": "Repository name within the organ"},
                "scope": {"type": "string", "description": "Brief description of what this session will accomplish"},
                "agent": {"type": "string", "description": "Agent identity (claude, gemini, codex, etc.). Defaults to 'unknown'."},
            },
            "required": ["organ", "repo", "scope"],
        },
    ),
    Tool(
        name="conductor_session_transition",
        description="Transition to next phase. Hard gate: must follow FRAME→SHAPE→BUILD→PROVE order. Cannot skip phases.",
        inputSchema={
            "type": "object",
            "properties": {
                "target_phase": {"type": "string", "enum": ["SHAPE", "BUILD", "PROVE", "DONE", "FRAME"], "description": "Target phase to transition to"},
                "agent": {"type": "string", "description": "Agent identity for this transition (claude, gemini, codex, etc.)"},
            },
            "required": ["target_phase"],
        },
    ),
    Tool(
        name="conductor_gate_check",
        description="Check for blocking advisories before major actions. Returns gate advisories from Guardian Angel.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="conductor_workflow_status",
        description="Get the briefing of the current active workflow (including current step, status, and suggested tool call).",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="conductor_workflow_step",
        description="Advance the active workflow by completing the current step, optionally providing the tool output or an action for checkpoints.",
        inputSchema={
            "type": "object",
            "properties": {
                "tool_output": {"description": "Output from the tool executed for the step (if applicable)"},
                "checkpoint_action": {"type": "string", "description": "For CHECKPOINT steps, provide 'approve', 'modify', or 'abort'."},
            },
        },
    ),
    # Directive ingestion
    Tool(
        name="conductor_ingest",
        description="Ingest raw content from a directive prefix (ingest:). Fans out to reference file, alchemia intake, SOP stub, and engine guidance.",
        inputSchema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Raw content to ingest (e.g., transcript text)"},
                "source_agent": {"type": "string", "description": "Source agent: gemini, claude, chatgpt, grok, perplexity, or manual"},
                "topic": {"type": "string", "description": "Topic slug (e.g., prompting-standards)"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for classification",
                },
            },
            "required": ["content", "source_agent", "topic"],
        },
    ),
    # Fleet orchestration
    Tool(
        name="conductor_fleet_status",
        description="Fleet status — active agents, today's usage, subscription tiers. No parameters needed.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="conductor_fleet_recommend",
        description="Recommend the best agent for a task based on phase, capabilities, utilization, and context fit.",
        inputSchema={
            "type": "object",
            "properties": {
                "phase": {"type": "string", "description": "Conductor phase: FRAME, SHAPE, BUILD, or PROVE"},
                "task_tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task descriptors for strength matching (e.g., deep-research, refactoring)",
                },
                "sensitivity": {
                    "type": "object",
                    "properties": {
                        "can_see_secrets": {"type": "boolean"},
                        "can_push_git": {"type": "boolean"},
                    },
                    "description": "Sensitivity requirements (agents not meeting these are excluded)",
                },
                "context_size": {"type": "integer", "description": "Estimated context size in tokens"},
            },
            "required": ["phase"],
        },
    ),
    Tool(
        name="conductor_fleet_dispatch",
        description=(
            "Classify cognitive work and route to the best-fit agent. "
            "Use BEFORE starting any non-trivial work to check if it should be dispatched to a worker bee "
            "(Gemini for velocity, Codex for scaffolding) or kept on Claude (architecture, audit, strategy). "
            "Returns ranked agents with exclusion reasons. "
            "If the recommended agent is NOT Claude, generate a guardrailed handoff instead of doing the work yourself."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Natural language description of the work to be done",
                },
                "phase": {
                    "type": "string",
                    "description": "Conductor phase: FRAME, SHAPE, BUILD, or PROVE (default: BUILD)",
                },
                "work_type": {
                    "type": "string",
                    "description": (
                        "Explicit work type override. If omitted, auto-classified from description. "
                        "Options: architecture, boilerplate_generation, research, mechanical_refactoring, "
                        "audit, content_generation, testing, debugging"
                    ),
                },
            },
            "required": ["description"],
        },
    ),
    Tool(
        name="conductor_fleet_guardrailed_handoff",
        description=(
            "Generate a guardrailed handoff envelope when dispatching work to another agent. "
            "The envelope carries locked constraints, locked files, completed work, conventions, "
            "and receiver restrictions. It also sets verification_required=true if the receiver's "
            "self-audit is untrusted. Output this as markdown for the user to hand to the receiving agent."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "to_agent": {"type": "string", "description": "Target agent (gemini, codex, opencode, goose)"},
                "summary": {"type": "string", "description": "What work is being handed off"},
                "work_type": {"type": "string", "description": "Classified work type"},
                "constraints_locked": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Constraints the receiver MUST NOT override (e.g., 'snake_case for all DB columns')",
                },
                "files_locked": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files the receiver MUST NOT modify",
                },
                "work_completed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Work already done — receiver should NOT repeat this",
                },
                "conventions": {
                    "type": "object",
                    "description": "Active conventions (e.g., {orm_naming: snake_case, imports: named})",
                },
            },
            "required": ["to_agent", "summary"],
        },
    ),
    Tool(
        name="conductor_fleet_cross_verify",
        description=(
            "Verify that another agent's output conforms to the guardrailed handoff constraints. "
            "Use AFTER receiving work back from a dispatched agent, especially one with self_audit_trusted=false. "
            "Checks: locked file violations, never-touch pattern matches, convention drift."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "changed_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files the receiving agent modified",
                },
                "diff_content": {
                    "type": "string",
                    "description": "Unified diff content for convention checking (optional)",
                },
            },
            "required": ["changed_files"],
        },
    ),
    # Sprint ledger / retro session
    Tool(
        name="conductor_retro_session",
        description="Generate a per-session retrospective ledger with prompt extraction, phase analysis, git activity, and fleet usage.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID to analyze, or 'latest' for most recent (default: latest)"},
            },
        },
    ),
]

DISPATCH = {
    "conductor_route_to": lambda args: route_to((args or {})["from_cluster"], (args or {})["to_cluster"]),
    "conductor_capability": lambda args: capability((args or {})["capability"]),
    "conductor_wip_status": lambda args: wip_status(),
    "conductor_session_phase": lambda args: session_phase(),
    "conductor_orchestra_briefing": lambda args: orchestra_briefing(),
    "conductor_suggest": lambda args: suggest((args or {})["task_description"]),
    "conductor_patch": lambda args: patch((args or {}).get("organ")),
    "conductor_edge_health": lambda args: edge_health(int((args or {}).get("window", 200))),
    "conductor_trace_get": lambda args: trace_get((args or {})["trace_id"]),
    "conductor_handoff_validate": lambda args: handoff_validate((args or {})["payload"]),
    "conductor_compose_mission": lambda args: compose_mission((args or {})["goal"], (args or {})["from_cluster"], (args or {})["to_cluster"]),
    "conductor_oracle": lambda args: oracle_consult((args or {}).get("context"), bool((args or {}).get("include_narrative"))),
    "conductor_oracle_gate": lambda args: oracle_gate((args or {})["trigger"], (args or {}).get("target", ""), (args or {}).get("repo", "")),
    "conductor_oracle_wisdom": lambda args: oracle_wisdom(),
    "conductor_oracle_profile": lambda args: oracle_profile(),
    "conductor_oracle_detectors": lambda args: oracle_detectors(),
    "conductor_oracle_trends": lambda args: oracle_trends(),
    "conductor_oracle_diagnose": lambda args: oracle_diagnose(),
    "conductor_oracle_calibrate": lambda args: oracle_calibrate((args or {})["detector"], (args or {}).get("action", "reset")),
    # Guardian Angel
    "conductor_guardian_counsel": lambda args: guardian_counsel((args or {}).get("context")),
    "conductor_guardian_whisper": lambda args: guardian_whisper((args or {})["action"], (args or {}).get("context")),
    "conductor_guardian_teach": lambda args: guardian_teach((args or {})["topic"]),
    "conductor_guardian_landscape": lambda args: guardian_landscape((args or {})["decision"], (args or {}).get("context")),
    "conductor_guardian_mastery": lambda args: guardian_mastery(),
    "conductor_mark_internalized": lambda args: mark_internalized((args or {})["wisdom_id"], (args or {}).get("evidence", "")),
    "conductor_guardian_corpus": lambda args: guardian_corpus((args or {}).get("search")),
    # Preflight / multi-session
    "conductor_preflight": lambda args: preflight((args or {}).get("agent", "unknown"), (args or {}).get("cwd")),
    "conductor_active_sessions": lambda args: active_sessions_list(),
    # Session lifecycle
    "conductor_session_start": lambda args: session_start((args or {})["organ"], (args or {})["repo"], (args or {})["scope"], (args or {}).get("agent", "unknown")),
    "conductor_session_transition": lambda args: session_transition((args or {})["target_phase"], (args or {}).get("agent", "")),
    "conductor_gate_check": lambda args: gate_check(),
    "conductor_workflow_status": lambda args: workflow_status(),
    "conductor_workflow_step": lambda args: workflow_step((args or {}).get("tool_output"), (args or {}).get("checkpoint_action")),
    # Fleet orchestration
    "conductor_fleet_status": lambda args: fleet_status(),
    "conductor_fleet_recommend": lambda args: fleet_recommend(
        (args or {})["phase"],
        (args or {}).get("task_tags"),
        (args or {}).get("sensitivity"),
        int((args or {}).get("context_size", 0)),
    ),
    "conductor_fleet_dispatch": lambda args: fleet_dispatch(
        (args or {})["description"],
        (args or {}).get("phase", "BUILD"),
        (args or {}).get("work_type"),
    ),
    "conductor_fleet_guardrailed_handoff": lambda args: fleet_guardrailed_handoff(
        (args or {})["to_agent"],
        (args or {})["summary"],
        (args or {}).get("work_type", ""),
        (args or {}).get("constraints_locked"),
        (args or {}).get("files_locked"),
        (args or {}).get("work_completed"),
        (args or {}).get("conventions"),
    ),
    "conductor_fleet_cross_verify": lambda args: fleet_cross_verify(
        (args or {})["changed_files"],
        (args or {}).get("diff_content", ""),
    ),
    # Sprint ledger
    "conductor_retro_session": lambda args: retro_session((args or {}).get("session_id")),
    # Directive ingestion
    "conductor_ingest": lambda args: ingest(
        (args or {})["content"],
        (args or {})["source_agent"],
        (args or {})["topic"],
        (args or {}).get("tags"),
    ),
}


async def run_server():
    _ensure_mcp_available()
    assert Server is not None
    assert stdio_server is not None
    server = Server("conductor")

    @server.list_tools()
    async def list_tools():
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None):
        handler = DISPATCH.get(name)
        if not handler:
            return [TextContent(type="text", text=_encode_mcp_payload({"error": f"Unknown tool: {name}"}))]

        try:
            result = handler(arguments)
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=_encode_mcp_payload({"error": str(e)}))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    import asyncio
    try:
        asyncio.run(run_server())
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
