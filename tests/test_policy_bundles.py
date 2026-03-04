"""Tests for environment policy bundles."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from conductor.governance import GovernanceRuntime
from conductor.policy import load_policy


def test_load_default_policy() -> None:
    policy = load_policy()
    assert policy.name
    assert policy.max_candidate_per_organ >= 1


def test_load_strict_policy_from_env() -> None:
    with patch.dict("os.environ", {"CONDUCTOR_POLICY_BUNDLE": "strict"}):
        policy = load_policy()
    assert policy.name == "strict"
    assert policy.strict_validation_default is True


def test_governance_runtime_uses_policy_limits(tmp_path) -> None:
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps({"schema_version": "1", "organs": {}}))
    gov_path = tmp_path / "governance.json"
    gov_path.write_text(json.dumps({"schema_version": "1", "organ_requirements": {}}))

    with patch.dict("os.environ", {"CONDUCTOR_POLICY_BUNDLE": "strict"}), \
         patch("conductor.governance.REGISTRY_PATH", reg_path), \
         patch("conductor.governance.GOVERNANCE_PATH", gov_path):
        runtime = GovernanceRuntime()

    assert runtime.max_candidate_per_organ == 2
