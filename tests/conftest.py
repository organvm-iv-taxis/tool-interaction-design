"""Shared fixtures for conductor test suite."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import conductor.constants
import conductor.governance
import conductor.session
from conductor.governance import GovernanceRuntime
from conductor.session import SessionEngine
from router import Ontology


# ---------------------------------------------------------------------------
# Core path-patching fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temp directory and patch conductor paths to use it.

    Patches SESSIONS_DIR, TEMPLATES_DIR, SESSION_STATE_FILE, and STATS_FILE
    in both conductor.constants and conductor.session so all code paths
    resolve to the temporary directory.
    """
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    templates = tmp_path / "templates"
    templates.mkdir()
    for name in ("spec.md", "plan.md", "status.md"):
        (templates / name).write_text(f"# {{{{ scope }}}}\n{{{{ organ }}}} {{{{ repo }}}}")

    state_file = tmp_path / ".conductor-session.json"
    stats_file = tmp_path / ".conductor-stats.json"
    active_sessions = tmp_path / "active-sessions"
    active_sessions.mkdir()

    with (
        patch.object(conductor.constants, "SESSIONS_DIR", sessions),
        patch.object(conductor.constants, "TEMPLATES_DIR", templates),
        patch.object(conductor.constants, "SESSION_STATE_FILE", state_file),
        patch.object(conductor.constants, "STATS_FILE", stats_file),
        patch.object(conductor.constants, "ACTIVE_SESSIONS_DIR", active_sessions),
        patch.object(conductor.session, "SESSIONS_DIR", sessions),
        patch.object(conductor.session, "TEMPLATES_DIR", templates),
        patch.object(conductor.session, "SESSION_STATE_FILE", state_file),
        patch.object(conductor.session, "STATS_FILE", stats_file),
        patch.object(conductor.session, "ACTIVE_SESSIONS_DIR", active_sessions),
    ):
        yield tmp_path


# ---------------------------------------------------------------------------
# Ontology / engine fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ontology():
    """Load the real ontology from ontology.yaml."""
    ontology_path = Path(__file__).parent.parent / "ontology.yaml"
    return Ontology(ontology_path)


@pytest.fixture
def session_engine(tmp_dir, ontology):
    """Create a SessionEngine with patched paths."""
    return SessionEngine(ontology)


# ---------------------------------------------------------------------------
# Governance fixtures
# ---------------------------------------------------------------------------


MINI_REGISTRY_DATA = {
    "version": "2.0",
    "organs": {
        "ORGAN-III": {
            "name": "Commerce",
            "repositories": [
                {
                    "name": "repo-a",
                    "promotion_status": "CANDIDATE",
                    "tier": "standard",
                    "documentation_status": "DEPLOYED",
                    "ci_workflow": "ci.yml",
                    "implementation_status": "ACTIVE",
                    "dependencies": [],
                    "org": "test-org",
                    "last_validated": "2026-01-01",
                },
                {
                    "name": "repo-b",
                    "promotion_status": "CANDIDATE",
                    "tier": "standard",
                    "documentation_status": "DEPLOYED",
                    "ci_workflow": "ci.yml",
                    "implementation_status": "ACTIVE",
                    "dependencies": [],
                    "org": "test-org",
                    "last_validated": "2026-03-01",
                },
                {
                    "name": "repo-c",
                    "promotion_status": "CANDIDATE",
                    "tier": "standard",
                    "documentation_status": "DEPLOYED",
                    "ci_workflow": "ci.yml",
                    "implementation_status": "ACTIVE",
                    "dependencies": [],
                    "org": "test-org",
                    "last_validated": "2026-03-01",
                },
                {
                    "name": "repo-d",
                    "promotion_status": "LOCAL",
                    "tier": "standard",
                    "documentation_status": "DEPLOYED",
                    "ci_workflow": "ci.yml",
                    "implementation_status": "SKELETON",
                    "dependencies": [],
                    "org": "test-org",
                },
                {
                    "name": "repo-e",
                    "promotion_status": "PUBLIC_PROCESS",
                    "tier": "flagship",
                    "documentation_status": "DEPLOYED",
                    "ci_workflow": "ci.yml",
                    "implementation_status": "ACTIVE",
                    "dependencies": [],
                    "org": "test-org",
                },
                {
                    "name": "repo-f",
                    "promotion_status": "LOCAL",
                    "tier": "standard",
                    "documentation_status": "EMPTY",
                    "ci_workflow": "",
                    "implementation_status": "SKELETON",
                    "dependencies": [],
                    "org": "test-org",
                },
                {
                    "name": "repo-g",
                    "promotion_status": "ARCHIVED",
                    "tier": "standard",
                    "documentation_status": "DEPLOYED",
                    "ci_workflow": "",
                    "implementation_status": "ACTIVE",
                    "dependencies": [],
                    "org": "test-org",
                },
            ],
        },
    },
}


@pytest.fixture
def mini_registry(tmp_path):
    """Create a minimal registry and governance file for governance tests.

    Returns (registry_path, governance_path, registry_data).
    """
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps(MINI_REGISTRY_DATA, indent=2))
    gov_path = tmp_path / "governance.json"
    gov_path.write_text(json.dumps({"version": "1.0"}))
    return reg_path, gov_path, MINI_REGISTRY_DATA


@pytest.fixture
def gov(mini_registry):
    """Create a GovernanceRuntime with the mini registry."""
    reg_path, gov_path, _ = mini_registry
    with (
        patch.object(conductor.governance, "REGISTRY_PATH", reg_path),
        patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path),
    ):
        return GovernanceRuntime()
