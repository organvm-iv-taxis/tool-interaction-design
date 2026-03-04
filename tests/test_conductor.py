"""Tests for conductor — session engine, governance runtime, product extractor."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add parent to path so we can import conductor
sys.path.insert(0, str(Path(__file__).parent.parent))

from conductor import (
    MAX_CANDIDATE_PER_ORGAN,
    PHASE_CLUSTERS,
    PHASES,
    VALID_TRANSITIONS,
    GovernanceRuntime,
    Session,
    SessionEngine,
    atomic_write,
    resolve_organ_key,
    organ_short,
)
import conductor.constants
import conductor.session
from router import Ontology


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temp directory and patch conductor paths to use it."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    templates = tmp_path / "templates"
    templates.mkdir()
    # Create minimal templates
    for name in ("spec.md", "plan.md", "status.md"):
        (templates / name).write_text(f"# {{{{ scope }}}}\n{{{{ organ }}}} {{{{ repo }}}}")

    state_file = tmp_path / ".conductor-session.json"

    with patch.object(conductor.constants, "SESSIONS_DIR", sessions), \
         patch.object(conductor.constants, "TEMPLATES_DIR", templates), \
         patch.object(conductor.constants, "SESSION_STATE_FILE", state_file), \
         patch.object(conductor.session, "SESSIONS_DIR", sessions), \
         patch.object(conductor.session, "TEMPLATES_DIR", templates), \
         patch.object(conductor.session, "SESSION_STATE_FILE", state_file), \
         patch.object(conductor.session, "STATS_FILE", tmp_path / ".conductor-stats.json"):
        yield tmp_path


@pytest.fixture
def ontology():
    """Load the real ontology."""
    ontology_path = Path(__file__).parent.parent / "ontology.yaml"
    return Ontology(ontology_path)


@pytest.fixture
def engine(tmp_dir, ontology):
    """Create a SessionEngine with patched paths."""
    return SessionEngine(ontology)


@pytest.fixture
def mini_registry(tmp_path):
    """Create a minimal registry for governance tests."""
    registry = {
        "version": "2.0",
        "organs": {
            "ORGAN-III": {
                "name": "Commerce",
                "repositories": [
                    {"name": "repo-a", "promotion_status": "CANDIDATE", "tier": "standard",
                     "documentation_status": "DEPLOYED", "ci_workflow": "ci.yml",
                     "implementation_status": "ACTIVE", "dependencies": [], "org": "test-org"},
                    {"name": "repo-b", "promotion_status": "CANDIDATE", "tier": "standard",
                     "documentation_status": "DEPLOYED", "ci_workflow": "ci.yml",
                     "implementation_status": "ACTIVE", "dependencies": [], "org": "test-org"},
                    {"name": "repo-c", "promotion_status": "CANDIDATE", "tier": "standard",
                     "documentation_status": "DEPLOYED", "ci_workflow": "ci.yml",
                     "implementation_status": "ACTIVE", "dependencies": [], "org": "test-org"},
                    {"name": "repo-d", "promotion_status": "LOCAL", "tier": "standard",
                     "documentation_status": "EMPTY", "ci_workflow": "",
                     "implementation_status": "SKELETON", "dependencies": [], "org": "test-org"},
                    {"name": "repo-e", "promotion_status": "PUBLIC_PROCESS", "tier": "flagship",
                     "documentation_status": "DEPLOYED", "ci_workflow": "ci.yml",
                     "implementation_status": "ACTIVE", "dependencies": [], "org": "test-org"},
                ],
            },
        },
    }
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps(registry, indent=2))

    gov_rules = {"version": "1.0", "dependency_rules": {}, "promotion_rules": {}}
    gov_path = tmp_path / "governance.json"
    gov_path.write_text(json.dumps(gov_rules))

    return reg_path, gov_path, registry


# ===========================================================================
# Utility tests
# ===========================================================================


class TestUtils:
    def test_resolve_organ_key_short(self):
        assert resolve_organ_key("III") == "ORGAN-III"
        assert resolve_organ_key("META") == "META-ORGANVM"
        assert resolve_organ_key("i") == "ORGAN-I"

    def test_resolve_organ_key_already_full(self):
        assert resolve_organ_key("ORGAN-III") == "ORGAN-III"
        assert resolve_organ_key("META-ORGANVM") == "META-ORGANVM"

    def test_organ_short(self):
        assert organ_short("ORGAN-III") == "III"
        assert organ_short("META-ORGANVM") == "META"

    def test_atomic_write(self, tmp_path):
        path = tmp_path / "test.json"
        atomic_write(path, '{"key": "value"}')
        assert path.read_text() == '{"key": "value"}'
        # Verify no .tmp file left behind
        assert not path.with_suffix(".tmp").exists()

    def test_atomic_write_creates_parent(self, tmp_path):
        path = tmp_path / "subdir" / "test.json"
        atomic_write(path, "content")
        assert path.read_text() == "content"


# ===========================================================================
# Session Engine tests
# ===========================================================================


class TestSessionEngine:
    def test_start_creates_session(self, engine, tmp_dir):
        session = engine.start("III", "my-repo", "Add feature")
        assert session.organ == "ORGAN-III"
        assert session.repo == "my-repo"
        assert session.scope == "Add feature"
        assert session.current_phase == "FRAME"
        assert session.result == "IN_PROGRESS"

    def test_start_scaffolds_templates(self, engine, tmp_dir):
        session = engine.start("III", "my-repo", "Add feature")
        session_dir = tmp_dir / "sessions" / session.session_id
        assert (session_dir / "spec.md").exists()
        assert (session_dir / "plan.md").exists()
        assert (session_dir / "status.md").exists()

    def test_start_fills_template_variables(self, engine, tmp_dir):
        session = engine.start("III", "my-repo", "Add feature")
        session_dir = tmp_dir / "sessions" / session.session_id
        spec = (session_dir / "spec.md").read_text()
        assert "Add feature" in spec
        assert "ORGAN-III" in spec

    def test_start_blocks_if_active(self, engine, tmp_dir):
        engine.start("III", "repo-1", "First")
        with pytest.raises(SystemExit):
            engine.start("III", "repo-2", "Second")

    def test_phase_transitions_forward(self, engine, tmp_dir):
        engine.start("III", "repo", "Test")
        engine.phase("shape")
        session = engine._load_session()
        assert session.current_phase == "SHAPE"
        engine.phase("build")
        session = engine._load_session()
        assert session.current_phase == "BUILD"
        engine.phase("prove")
        session = engine._load_session()
        assert session.current_phase == "PROVE"

    def test_phase_transition_reshape(self, engine, tmp_dir):
        engine.start("III", "repo", "Test")
        engine.phase("shape")
        engine.phase("frame")  # reshape
        session = engine._load_session()
        assert session.current_phase == "FRAME"

    def test_phase_transition_fail_back(self, engine, tmp_dir):
        engine.start("III", "repo", "Test")
        engine.phase("shape")
        engine.phase("build")
        engine.phase("prove")
        engine.phase("build")  # fail → back to build
        session = engine._load_session()
        assert session.current_phase == "BUILD"

    def test_invalid_transition_rejected(self, engine, tmp_dir):
        engine.start("III", "repo", "Test")
        # FRAME → BUILD (skip SHAPE) — not allowed
        with pytest.raises(SystemExit):
            engine.phase("build")

    def test_invalid_transition_frame_to_prove(self, engine, tmp_dir):
        engine.start("III", "repo", "Test")
        with pytest.raises(SystemExit):
            engine.phase("prove")

    def test_close_generates_log(self, engine, tmp_dir):
        session = engine.start("III", "repo", "Test")
        engine.phase("shape")
        engine.phase("build")
        engine.phase("prove")
        engine.close()
        log_path = tmp_dir / "sessions" / session.session_id / "session-log.yaml"
        assert log_path.exists()

        import yaml
        log = yaml.safe_load(log_path.read_text())
        assert log["organ"] == "ORGAN-III"
        assert log["repo"] == "repo"
        assert "FRAME" in log["phases"]
        assert "SHAPE" in log["phases"]
        assert "BUILD" in log["phases"]
        assert "PROVE" in log["phases"]

    def test_close_clears_state(self, engine, tmp_dir):
        engine.start("III", "repo", "Test")
        engine.close()
        assert engine._load_session() is None

    def test_close_merges_reshape_phases(self, engine, tmp_dir):
        session = engine.start("III", "repo", "Test")
        engine.phase("shape")
        engine.phase("frame")  # reshape — second FRAME visit
        engine.phase("shape")  # second SHAPE visit
        engine.phase("build")
        engine.phase("prove")
        engine.close()

        import yaml
        log_path = tmp_dir / "sessions" / session.session_id / "session-log.yaml"
        log = yaml.safe_load(log_path.read_text())
        assert log["phases"]["FRAME"]["visits"] == 2
        assert log["phases"]["SHAPE"]["visits"] == 2
        assert log["phases"]["BUILD"]["visits"] == 1

    def test_phase_done_marks_shipped(self, engine, tmp_dir):
        engine.start("III", "repo", "Test")
        engine.phase("shape")
        engine.phase("build")
        engine.phase("prove")
        engine.phase("done")
        session = engine._load_session()
        assert session.result == "SHIPPED"

    def test_close_without_session_errors(self, engine, tmp_dir):
        with pytest.raises(SystemExit):
            engine.close()

    def test_phase_without_session_errors(self, engine, tmp_dir):
        with pytest.raises(SystemExit):
            engine.phase("shape")


# ===========================================================================
# State machine exhaustive tests
# ===========================================================================


class TestStateTransitions:
    """Verify every possible phase transition."""

    def test_all_valid_transitions_enumerated(self):
        """Every entry in VALID_TRANSITIONS maps to a real phase or DONE."""
        all_targets = set()
        for targets in VALID_TRANSITIONS.values():
            all_targets.update(targets)
        assert all_targets <= set(PHASES) | {"DONE"}

    def test_all_phases_have_clusters(self):
        """Every phase has an associated cluster list."""
        for phase in PHASES:
            assert phase in PHASE_CLUSTERS
            assert len(PHASE_CLUSTERS[phase]) > 0

    def test_no_self_transitions(self):
        """No phase allows transition to itself."""
        for phase, targets in VALID_TRANSITIONS.items():
            assert phase not in targets, f"{phase} allows self-transition"


# ===========================================================================
# Governance Runtime tests
# ===========================================================================


class TestGovernanceRuntime:
    def _make_gov(self, mini_registry):
        reg_path, gov_path, _ = mini_registry
        import conductor.governance
        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            return GovernanceRuntime()

    def test_loads_registry(self, mini_registry):
        gov = self._make_gov(mini_registry)
        repos = gov._all_repos()
        assert len(repos) == 5

    def test_wip_check_counts(self, mini_registry, capsys):
        gov = self._make_gov(mini_registry)
        gov.wip_check()
        out = capsys.readouterr().out
        assert "CANDIDATE" in out or "CAND" in out

    def test_promote_blocked_by_wip_limit(self, mini_registry):
        """With 3 CANDIDATE repos, promoting another to CANDIDATE should be blocked."""
        gov = self._make_gov(mini_registry)
        gov._skip_confirm = True
        # repo-d is LOCAL, try to promote to CANDIDATE (already 3 CANDIDATE)
        with pytest.raises(SystemExit):
            gov.wip_promote("repo-d", "CANDIDATE")

    def test_promote_invalid_transition(self, mini_registry):
        """LOCAL → GRADUATED should be rejected (must go through CANDIDATE first)."""
        gov = self._make_gov(mini_registry)
        gov._skip_confirm = True
        with pytest.raises(SystemExit):
            gov.wip_promote("repo-d", "GRADUATED")

    def test_promote_nonexistent_repo(self, mini_registry):
        gov = self._make_gov(mini_registry)
        gov._skip_confirm = True
        with pytest.raises(SystemExit):
            gov.wip_promote("nonexistent", "CANDIDATE")

    def test_audit_runs_without_error(self, mini_registry, capsys):
        gov = self._make_gov(mini_registry)
        gov.audit(organ="III")
        out = capsys.readouterr().out
        assert "Commerce" in out
        assert "5 repos" in out


# ===========================================================================
# Session data model tests
# ===========================================================================


class TestSessionModel:
    def test_roundtrip_serialization(self):
        session = Session(
            session_id="test-id",
            organ="ORGAN-III",
            repo="test-repo",
            scope="Test scope",
            start_time=1000.0,
            current_phase="BUILD",
            phase_logs=[{"name": "FRAME", "start_time": 1000, "end_time": 1060, "tools_used": ["WebSearch"], "commits": 0}],
            warnings=["test warning"],
            result="IN_PROGRESS",
        )
        d = session.to_dict()
        restored = Session.from_dict(d)
        assert restored.session_id == session.session_id
        assert restored.current_phase == session.current_phase
        assert restored.warnings == session.warnings
        assert restored.phase_logs == session.phase_logs
