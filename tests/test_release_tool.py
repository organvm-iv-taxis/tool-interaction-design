"""Tests for release automation helper script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_release_prepare_dry_run_outputs_next_version() -> None:
    result = subprocess.run(
        [sys.executable, "tools/release.py", "prepare", "--part", "patch", "--dry-run"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    assert "current_version=" in result.stdout
    assert "next_version=" in result.stdout
    assert "tag=v" in result.stdout
