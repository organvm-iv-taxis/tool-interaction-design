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

    assert isinstance(report, dict)
    assert "ok" in report
    assert "checks" in report and isinstance(report["checks"], list)
    assert "summary" in report and isinstance(report["summary"], dict)
    assert "autofix_hints" in report and isinstance(report["autofix_hints"], list)
    assert "applied_fixes" in report and isinstance(report["applied_fixes"], list)

    check_names = {check["name"] for check in report["checks"]}
    assert {
        "schema:registry",
        "schema:governance",
        "schema:workflow",
        "phase-config",
        "legacy-artifacts",
        "cross-file-integrity",
    }.issubset(check_names)

    summary = report["summary"]
    assert summary["checks_total"] >= 6
    assert summary["checks_ok"] <= summary["checks_total"]
    assert summary["errors"] >= 0
    assert summary["warnings"] >= 0


def test_legacy_artifacts_check(tmp_path):
    # Mock BASE to use tmp_path
    with patch("conductor.constants.BASE", tmp_path), \
         patch("conductor.doctor.REGISTRY_PATH", tmp_path / "registry.json"), \
         patch("conductor.doctor.GOVERNANCE_PATH", tmp_path / "governance.json"):
        
        # 1. No legacy artifacts
        from conductor.doctor import _legacy_artifacts_check
        check = _legacy_artifacts_check()
        assert check.ok is True
        
        # 2. With legacy artifacts
        legacy_file = tmp_path / ".conductor-legacy.json"
        legacy_file.write_text("{}")
        
        check = _legacy_artifacts_check()
        assert check.ok is False
        assert "Found 1 legacy artifacts" in check.errors[0]


def test_doctor_report_fails_on_legacy_artifacts(tmp_path):
    workflow = BASE / "workflow-dsl.yaml"
    registry = tmp_path / "registry-v2.json"
    governance = tmp_path / "governance-rules.json"
    registry.write_text(json.dumps({"schema_version": "1", "organs": {}}))
    governance.write_text(json.dumps({"schema_version": "1", "organ_requirements": {}}))
    (tmp_path / ".conductor-old.json").write_text("{}")

    with (
        patch("conductor.constants.BASE", tmp_path),
        patch("conductor.doctor.REGISTRY_PATH", registry),
        patch("conductor.doctor.GOVERNANCE_PATH", governance),
    ):
        report = run_doctor(workflow, format_name="json")

    assert report["ok"] is False
    legacy = next(check for check in report["checks"] if check["name"] == "legacy-artifacts")
    assert legacy["ok"] is False
    assert any("Found 1 legacy artifacts" in error for error in legacy["errors"])
    assert report["summary"]["errors"] >= 1
