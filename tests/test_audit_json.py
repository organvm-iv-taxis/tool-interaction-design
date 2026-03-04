"""Tests for JSON output formats on governance/validation commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import conductor.governance
from conductor.governance import GovernanceRuntime
from router import Ontology, RoutingEngine, WorkflowValidator


def test_governance_audit_report_json_shape(tmp_path) -> None:
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps({
        "schema_version": "1",
        "organs": {
            "ORGAN-III": {
                "name": "Commerce",
                "repositories": [{"name": "repo-a", "promotion_status": "LOCAL", "ci_workflow": "ci.yml", "documentation_status": "DEPLOYED"}]
            }
        }
    }))
    gov_path = tmp_path / "governance.json"
    gov_path.write_text(json.dumps({"schema_version": "1", "organ_requirements": {}}))

    with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
         patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
        gov = GovernanceRuntime()

    report = gov.audit_report(organ="III")
    assert set(report.keys()) >= {"scope", "organs", "limits"}
    assert "ORGAN-III" in report["organs"]


def test_workflow_validate_report_to_dict() -> None:
    base = Path(__file__).parent.parent
    ontology = Ontology(base / "ontology.yaml")
    engine = RoutingEngine(base / "routing-matrix.yaml", ontology)
    validator = WorkflowValidator(ontology, engine)
    report = validator.validate_report(base / "workflow-dsl.yaml")
    payload = report.to_dict()
    assert set(payload.keys()) == {"ok", "errors", "warnings"}
