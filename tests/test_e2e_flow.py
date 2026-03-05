"""End-to-end scenarios across CLI, workflow validation, and MCP dispatch."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import mcp_server


ROOT = Path(__file__).parent.parent


def test_e2e_cli_validate_json_contract() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "conductor", "validate", "workflow-dsl.yaml", "--format", "json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert "errors" in payload
    assert "warnings" in payload


def test_e2e_mcp_dispatch_path_and_patch() -> None:
    route_json = mcp_server.DISPATCH["conductor_route_to"]({"from_cluster": "web_search", "to_cluster": "knowledge_graph"})
    route_payload = json.loads(route_json)
    assert "direct_routes" in route_payload or "multi_hop_paths" in route_payload
    assert "pathfinding" in route_payload

    patch_json = mcp_server.DISPATCH["conductor_patch"](None)
    patch_payload = json.loads(patch_json)
    assert "session" in patch_payload or "error" in patch_payload
