"""Tests for process operating-system assets."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_validate_process_assets_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, "tools/validate_process_assets.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "process asset validation passed" in result.stdout
