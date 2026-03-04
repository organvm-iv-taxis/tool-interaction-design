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
from conductor.constants import (
    ONTOLOGY_PATH,
    ROUTING_PATH,
    PHASE_ROLES,
    PHASES,
    SESSION_STATE_FILE,
    get_phase_clusters,
)
from conductor.contracts import assert_contract
from conductor.governance import GovernanceRuntime
from conductor.patchbay import Patchbay
from conductor.session import Session, SessionEngine


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
    assert_contract("mcp_tool_response", payload)
    return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def route_to(from_cluster: str, to_cluster: str) -> str:
    engine = get_engine()
    ontology = get_ontology()

    routes = engine.find_routes(from_cluster, to_cluster)
    if routes:
        result = [{"id": r.id, "data_flow": r.data_flow, "protocol": r.protocol,
                    "automatable": r.automatable, "description": r.description}
                   for r in routes]
        return _encode_mcp_payload({"direct_routes": result})

    # Try multi-hop
    src = ontology.clusters.get(from_cluster)
    tgt = ontology.clusters.get(to_cluster)
    if src and tgt:
        paths = engine.find_path(src.domain, tgt.domain)
        if paths:
            return _encode_mcp_payload({"multi_hop_paths": paths})

    return _encode_mcp_payload({"error": f"No route found: {from_cluster} -> {to_cluster}"})


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
        if not session:
            return _encode_mcp_payload({"active": False, "message": "No active session"})

        phase = session.get("current_phase", "UNKNOWN")
        return _encode_mcp_payload({
            "active": True,
            "session_id": session.get("session_id"),
            "organ": session.get("organ"),
            "repo": session.get("repo"),
            "scope": session.get("scope"),
            "current_phase": phase,
            "ai_role": PHASE_ROLES.get(phase, "Unknown"),
            "active_clusters": get_phase_clusters().get(phase, []),
            "warnings": session.get("warnings", []),
        })
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


# ---------------------------------------------------------------------------
# MCP Server setup
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="conductor_route_to",
        description="Find routes between tool clusters in the ontology. Returns direct routes or multi-hop paths.",
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
]

DISPATCH = {
    "conductor_route_to": lambda args: route_to((args or {})["from_cluster"], (args or {})["to_cluster"]),
    "conductor_capability": lambda args: capability((args or {})["capability"]),
    "conductor_wip_status": lambda args: wip_status(),
    "conductor_session_phase": lambda args: session_phase(),
    "conductor_suggest": lambda args: suggest((args or {})["task_description"]),
    "conductor_patch": lambda args: patch((args or {}).get("organ")),
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
