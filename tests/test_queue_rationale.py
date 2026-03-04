"""Queue scoring rationale visibility tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import conductor.governance
from conductor.patchbay import Patchbay
from conductor.session import SessionEngine
from conductor.workqueue import WorkQueue


def test_work_items_include_weighted_rationale(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "organs": {
                    "ORGAN-III": {
                        "repositories": [
                            {
                                "name": "repo-a",
                                "promotion_status": "CANDIDATE",
                                "last_validated": "2026-01-01",
                                "documentation_status": "DEPLOYED",
                                "ci_workflow": "ci.yml",
                            }
                        ]
                    }
                },
            }
        )
    )
    governance = tmp_path / "governance.json"
    governance.write_text(json.dumps({"schema_version": "1", "organ_requirements": {}}))

    with patch.object(conductor.governance, "REGISTRY_PATH", registry), \
         patch.object(conductor.governance, "GOVERNANCE_PATH", governance):
        gov = conductor.governance.GovernanceRuntime()
        queue = WorkQueue(gov).compute()

    assert queue
    assert queue[0].rationale
    assert "base" in queue[0].rationale
    assert "factors" in queue[0].rationale
    assert "total" in queue[0].rationale


def test_patchbay_queue_json_exposes_rationale(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"schema_version": "1", "organs": {}}))
    governance = tmp_path / "governance.json"
    governance.write_text(json.dumps({"schema_version": "1", "organ_requirements": {}}))

    with patch.object(conductor.governance, "REGISTRY_PATH", registry), \
         patch.object(conductor.governance, "GOVERNANCE_PATH", governance):
        pb = Patchbay(engine=SessionEngine())
        payload = pb.briefing()

    queue_items = payload["queue"]["items"]
    if queue_items:
        assert "rationale" in queue_items[0]
