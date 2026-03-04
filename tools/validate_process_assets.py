#!/usr/bin/env python3
"""Validate process contracts, templates, and required playbook assets."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent


REQUIRED_PLAYBOOKS = [
    "intake.md",
    "design.md",
    "implementation.md",
    "verification.md",
    "release.md",
    "incident.md",
    "weekly-sprint-rhythm.md",
]

REQUIRED_PLAYBOOK_SECTIONS = [
    "## Purpose",
    "## Entry Criteria",
    "## Procedure",
    "## Exit Criteria",
    "## Outputs",
]

REQUIRED_RISK_FILES = [
    "pre-mortem-template.md",
    "recovery-drill-checklist.md",
]

REQUIRED_ROADMAP_FILES = [
    "90-day-implementation.md",
    "baseline-audit.md",
    "gap-ledger.md",
    "monetization-lanes.md",
]


def _validate_template(contract_path: Path, template_path: Path) -> list[str]:
    schema = json.loads(contract_path.read_text())
    payload = yaml.safe_load(template_path.read_text())

    errors: list[str] = []
    validator = Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path)):
        path = "$"
        if err.absolute_path:
            path += "." + ".".join(str(part) for part in err.absolute_path)
        errors.append(f"{template_path}: {path} {err.message}")
    return errors


def _validate_playbooks() -> list[str]:
    errors: list[str] = []
    playbook_dir = ROOT / "process" / "playbooks"

    for name in REQUIRED_PLAYBOOKS:
        path = playbook_dir / name
        if not path.exists():
            errors.append(f"missing playbook: {path}")
            continue
        text = path.read_text()
        for section in REQUIRED_PLAYBOOK_SECTIONS:
            if section not in text:
                errors.append(f"{path}: missing section '{section}'")
    return errors


def _validate_risk_assets() -> list[str]:
    errors: list[str] = []
    risk_dir = ROOT / "process" / "risk"
    for name in REQUIRED_RISK_FILES:
        path = risk_dir / name
        if not path.exists():
            errors.append(f"missing risk asset: {path}")
    return errors


def _validate_roadmap_assets() -> list[str]:
    errors: list[str] = []
    roadmap_dir = ROOT / "process" / "roadmap"
    for name in REQUIRED_ROADMAP_FILES:
        path = roadmap_dir / name
        if not path.exists():
            errors.append(f"missing roadmap asset: {path}")
    return errors


def main() -> int:
    errors: list[str] = []

    pairs = [
        (
            ROOT / "process" / "contracts" / "work-item.schema.json",
            ROOT / "process" / "templates" / "work-item.example.yaml",
        ),
        (
            ROOT / "process" / "contracts" / "sprint-report.schema.json",
            ROOT / "process" / "templates" / "sprint-report.example.yaml",
        ),
        (
            ROOT / "process" / "contracts" / "release-readiness.schema.json",
            ROOT / "process" / "templates" / "release-readiness.example.yaml",
        ),
        (
            ROOT / "process" / "scorecards" / "weekly-scorecard.schema.json",
            ROOT / "process" / "scorecards" / "weekly-scorecard.example.yaml",
        ),
    ]

    for contract_path, template_path in pairs:
        if not contract_path.exists():
            errors.append(f"missing contract schema: {contract_path}")
            continue
        if not template_path.exists():
            errors.append(f"missing template: {template_path}")
            continue
        errors.extend(_validate_template(contract_path, template_path))

    errors.extend(_validate_playbooks())
    errors.extend(_validate_risk_assets())
    errors.extend(_validate_roadmap_assets())

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("process asset validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
