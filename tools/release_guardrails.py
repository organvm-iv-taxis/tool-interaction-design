#!/usr/bin/env python3
"""Release guardrails: semver, version alignment, changelog presence."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
INIT_FILE = ROOT / "conductor" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def extract_pyproject_version() -> str:
    content = PYPROJECT.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find project version in pyproject.toml")
    return match.group(1)


def extract_init_version() -> str:
    content = INIT_FILE.read_text()
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', content, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find __version__ in conductor/__init__.py")
    return match.group(1)


def main() -> int:
    py_ver = extract_pyproject_version()
    init_ver = extract_init_version()

    errors: list[str] = []
    if not SEMVER_RE.match(py_ver):
        errors.append(f"pyproject version is not strict semver: {py_ver}")
    if not SEMVER_RE.match(init_ver):
        errors.append(f"conductor __version__ is not strict semver: {init_ver}")
    if py_ver != init_ver:
        errors.append(f"version mismatch: pyproject={py_ver}, conductor={init_ver}")

    changelog = CHANGELOG.read_text() if CHANGELOG.exists() else ""
    if f"## [{py_ver}]" not in changelog:
        errors.append(f"CHANGELOG missing heading for current version: ## [{py_ver}]")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(f"release guardrails passed for version {py_ver}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
