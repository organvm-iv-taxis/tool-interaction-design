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
