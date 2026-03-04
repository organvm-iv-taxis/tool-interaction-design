"""Tests for mcp_server dispatch helpers."""

from __future__ import annotations

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


def test_main_returns_one_when_mcp_unavailable():
    with patch.object(mcp_server, "MCP_IMPORT_ERROR", ImportError("missing mcp")):
        assert mcp_server.main() == 1
