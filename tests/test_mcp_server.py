"""Tests for mcp_server dispatch helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import mcp_server


def test_conductor_patch_dispatch_accepts_none_arguments():
    with patch.object(mcp_server, "patch", return_value='{"ok": true}') as mock_patch:
        result = mcp_server.DISPATCH["conductor_patch"](None)

    assert result == '{"ok": true}'
    mock_patch.assert_called_once_with(None)


def test_conductor_patch_dispatch_forwards_organ_argument():
    with patch.object(mcp_server, "patch", return_value='{"ok": true}') as mock_patch:
        result = mcp_server.DISPATCH["conductor_patch"]({"organ": "III"})

    assert result == '{"ok": true}'
    mock_patch.assert_called_once_with("III")


def test_conductor_edge_health_dispatch_defaults_window():
    with patch.object(mcp_server, "edge_health", return_value='{"ok": true}') as mock_edge_health:
        result = mcp_server.DISPATCH["conductor_edge_health"](None)

    assert result == '{"ok": true}'
    mock_edge_health.assert_called_once_with(200)


def test_conductor_trace_get_dispatch_forwards_trace_id():
    with patch.object(mcp_server, "trace_get", return_value='{"ok": true}') as mock_trace_get:
        result = mcp_server.DISPATCH["conductor_trace_get"]({"trace_id": "trace-123"})

    assert result == '{"ok": true}'
    mock_trace_get.assert_called_once_with("trace-123")


def test_conductor_handoff_validate_dispatch_forwards_payload():
    payload = {"trace_id": "t-1"}
    with patch.object(mcp_server, "handoff_validate", return_value='{"valid": false}') as mock_validate:
        result = mcp_server.DISPATCH["conductor_handoff_validate"]({"payload": payload})

    assert result == '{"valid": false}'
    mock_validate.assert_called_once_with(payload)


def test_conductor_orchestra_briefing_dispatch():
    with patch.object(
        mcp_server,
        "orchestra_briefing",
        return_value='{"active": true, "role": "Architect"}',
    ) as mock_orchestra:
        result = mcp_server.DISPATCH["conductor_orchestra_briefing"](None)

    assert result == '{"active": true, "role": "Architect"}'
    mock_orchestra.assert_called_once_with()


def test_conductor_guardian_corpus_dispatch_accepts_none_arguments():
    with patch.object(mcp_server, "guardian_corpus", return_value='{"total_entries": 71}') as mock_guardian_corpus:
        result = mcp_server.DISPATCH["conductor_guardian_corpus"](None)

    assert result == '{"total_entries": 71}'
    mock_guardian_corpus.assert_called_once_with(None)


def test_conductor_guardian_corpus_dispatch_forwards_search_argument():
    with patch.object(mcp_server, "guardian_corpus", return_value='{"count": 2}') as mock_guardian_corpus:
        result = mcp_server.DISPATCH["conductor_guardian_corpus"]({"search": "tdd"})

    assert result == '{"count": 2}'
    mock_guardian_corpus.assert_called_once_with("tdd")


def test_route_to_returns_pathfinding_shape():
    payload = json.loads(mcp_server.route_to("web_search", "knowledge_graph"))
    assert "pathfinding" in payload
    assert "fallback_sequences" in payload
    assert "direct_routes" in payload


def test_main_returns_one_when_mcp_unavailable():
    with patch.object(mcp_server, "MCP_IMPORT_ERROR", ImportError("missing mcp")):
        assert mcp_server.main() == 1


def test_encode_mcp_payload_falls_back_when_contract_validation_fails():
    with patch.object(mcp_server, "assert_contract", side_effect=RuntimeError("jsonschema missing")):
        encoded = mcp_server._encode_mcp_payload({"ok": True})

    payload = json.loads(encoded)
    assert "error" in payload
    assert "contract validation failed" in payload["error"]


def test_encode_mcp_payload_preserves_upstream_error_in_fallback():
    with patch.object(mcp_server, "assert_contract", side_effect=RuntimeError("jsonschema missing")):
        encoded = mcp_server._encode_mcp_payload({"error": "boom"})

    payload = json.loads(encoded)
    assert "error" in payload
    assert payload.get("upstream_error") == "boom"
