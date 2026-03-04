#!/usr/bin/env python3
"""Validate project documents against versioned JSON schemas."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from conductor.schemas import validate_document

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    failures: list[str] = []

    registry_path = ROOT / ".ci-corpus" / "registry-v2.json"
    governance_path = ROOT / ".ci-corpus" / "governance-rules.json"
    workflow_path = ROOT / "workflow-dsl.yaml"

    if registry_path.exists():
        registry_payload = json.loads(registry_path.read_text())
        issues = validate_document("registry", registry_payload)
        if issues:
            failures.extend(f"registry: {issue.path} {issue.message}" for issue in issues)

    if governance_path.exists():
        governance_payload = json.loads(governance_path.read_text())
        issues = validate_document("governance", governance_payload)
        if issues:
            failures.extend(f"governance: {issue.path} {issue.message}" for issue in issues)

    if workflow_path.exists():
        workflow_payload = yaml.safe_load(workflow_path.read_text())
        issues = validate_document("workflow", workflow_payload)
        if issues:
            failures.extend(f"workflow: {issue.path} {issue.message}" for issue in issues)

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1

    print("schema validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
