"""Tests for doctor diagnostics and migration commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from conductor.doctor import run_doctor
from conductor.migrate import migrate_governance, migrate_registry, write_migration_output


BASE = Path(__file__).parent.parent


def test_migrate_registry_adds_schema_version(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"organs": {"ORGAN-III": {"repositories": [{"name": "demo"}]}}}))
    payload = migrate_registry(path)
    assert payload["schema_version"] == "1"
    assert payload["organs"]["ORGAN-III"]["repositories"][0]["name"] == "demo"


def test_migrate_governance_adds_schema_version(tmp_path):
    path = tmp_path / "governance.json"
    path.write_text(json.dumps({"organ_requirements": {"ORGAN-III": {"requires_tests": True}}}))
    payload = migrate_governance(path)
    assert payload["schema_version"] == "1"


def test_write_migration_output(tmp_path):
    payload = {"schema_version": "1"}
    output = tmp_path / "out.json"
    write_migration_output(payload, output)
    assert json.loads(output.read_text())["schema_version"] == "1"


def test_doctor_json_report_shape(tmp_path):
    registry = tmp_path / "registry-v2.json"
    governance = tmp_path / "governance-rules.json"
    workflow = BASE / "workflow-dsl.yaml"

    registry.write_text(json.dumps({
        "schema_version": "1",
        "organs": {"ORGAN-III": {"repositories": [{"name": "demo", "promotion_status": "LOCAL"}]}}
    }))
    governance.write_text(json.dumps({"schema_version": "1", "organ_requirements": {}}))

    with patch("conductor.doctor.REGISTRY_PATH", registry), patch("conductor.doctor.GOVERNANCE_PATH", governance):
        report = run_doctor(workflow, format_name="json")

    assert set(report.keys()) >= {"ok", "checks", "summary", "autofix_hints"}
    assert isinstance(report["checks"], list)
