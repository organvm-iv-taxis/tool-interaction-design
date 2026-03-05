"""Tests for conductor — session engine, governance runtime, product extractor."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent to path so we can import conductor
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from conductor import (
    MAX_CANDIDATE_PER_ORGAN,
    MAX_PUBLIC_PROCESS_PER_ORGAN,
    PHASE_CLUSTERS,
    PHASES,
    PROMOTION_STATES,
    PROMOTION_TRANSITIONS,
    VALID_TRANSITIONS,
    ConductorError,
    GovernanceError,
    GovernanceRuntime,
    Session,
    SessionEngine,
    SessionError,
    __version__,
    atomic_write,
    get_phase_clusters,
    resolve_organ_key,
    organ_short,
)
from conductor.product import ProductExtractor
import conductor.constants
import conductor.product
import conductor.session
import conductor.governance
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
        with pytest.raises(SessionError, match="already active"):
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
        with pytest.raises(SessionError, match="Cannot transition"):
            engine.phase("build")

    def test_invalid_transition_frame_to_prove(self, engine, tmp_dir):
        engine.start("III", "repo", "Test")
        with pytest.raises(SessionError, match="Cannot transition"):
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
        with pytest.raises(SessionError, match="No active session"):
            engine.close()

    def test_phase_without_session_errors(self, engine, tmp_dir):
        with pytest.raises(SessionError, match="No active session"):
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
    def _make_gov(self, mini_registry, auto_confirm: bool = False):
        reg_path, gov_path, _ = mini_registry
        import conductor.governance
        confirm_fn = (lambda _: True) if auto_confirm else None
        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            return GovernanceRuntime(confirm_fn=confirm_fn)

    def test_loads_registry(self, mini_registry):
        gov = self._make_gov(mini_registry)
        repos = gov._all_repos()
        assert len(repos) == 5

    def test_invalid_registry_schema_raises(self, tmp_path):
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps({"version": "2.0", "organs": []}))
        gov_path = tmp_path / "governance.json"
        gov_path.write_text(json.dumps({"version": "1.0"}))

        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            with pytest.raises(GovernanceError, match="Registry schema"):
                GovernanceRuntime()

    def test_invalid_governance_schema_raises(self, tmp_path):
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps({"version": "2.0", "organs": {}}))
        gov_path = tmp_path / "governance.json"
        gov_path.write_text(json.dumps({"version": "1.0", "organ_requirements": []}))

        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            with pytest.raises(GovernanceError, match="Governance schema"):
                GovernanceRuntime()

    def test_wip_check_counts(self, mini_registry, capsys):
        gov = self._make_gov(mini_registry)
        gov.wip_check()
        out = capsys.readouterr().out
        assert "CANDIDATE" in out or "CAND" in out

    def test_promote_blocked_by_wip_limit(self, mini_registry):
        """With 3 CANDIDATE repos, promoting another to CANDIDATE should be blocked."""
        gov = self._make_gov(mini_registry, auto_confirm=True)
        # repo-d is LOCAL, try to promote to CANDIDATE (already 3 CANDIDATE)
        with pytest.raises(GovernanceError, match="CANDIDATE"):
            gov.wip_promote("repo-d", "CANDIDATE")

    def test_promote_invalid_transition(self, mini_registry):
        """LOCAL → GRADUATED should be rejected (must go through CANDIDATE first)."""
        gov = self._make_gov(mini_registry, auto_confirm=True)
        with pytest.raises(GovernanceError, match="Cannot transition"):
            gov.wip_promote("repo-d", "GRADUATED")

    def test_promote_nonexistent_repo(self, mini_registry):
        gov = self._make_gov(mini_registry, auto_confirm=True)
        with pytest.raises(GovernanceError, match="not found"):
            gov.wip_promote("nonexistent", "CANDIDATE")

    def test_audit_runs_without_error(self, mini_registry, capsys):
        gov = self._make_gov(mini_registry)
        gov.audit(organ="III")
        out = capsys.readouterr().out
        assert "Commerce" in out
        assert "5 repos" in out

    def test_auto_promote_dry_run_proposes_healthy_repo(self, mini_registry):
        gov = self._make_gov(mini_registry)
        repos = gov.registry["organs"]["ORGAN-III"]["repositories"]
        for repo in repos:
            if repo["name"] == "repo-c":
                repo["promotion_status"] = "LOCAL"
                repo["documentation_status"] = "DEPLOYED"
                repo["ci_workflow"] = "ci.yml"
                repo["implementation_status"] = "ACTIVE"

        report = gov.auto_promote(dry_run=True)
        assert report["summary"]["dry_run"] is True
        assert any(
            row["repo"] == "repo-c" and row["target"] == "CANDIDATE"
            for row in report["proposed"]
        )

    def test_auto_promote_apply_updates_registry(self, mini_registry):
        gov = self._make_gov(mini_registry)
        repos = gov.registry["organs"]["ORGAN-III"]["repositories"]
        for repo in repos:
            if repo["name"] == "repo-c":
                repo["promotion_status"] = "LOCAL"
                repo["documentation_status"] = "DEPLOYED"
                repo["ci_workflow"] = "ci.yml"
                repo["implementation_status"] = "ACTIVE"

        report = gov.auto_promote(dry_run=False)
        assert report["summary"]["promoted"] >= 1
        updated = next(repo for repo in repos if repo["name"] == "repo-c")
        assert updated["promotion_status"] == "CANDIDATE"


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


# ===========================================================================
# Session ID uniqueness (P2.1 / W8)
# ===========================================================================


class TestSessionIdUniqueness:
    def test_different_timestamps_produce_different_ids(self, engine, tmp_dir):
        """Two sessions with same scope but different timestamps get different IDs."""
        s1 = engine.start("III", "repo", "Same scope")
        id1 = s1.session_id
        engine.close()
        # Second session — time has moved, so hash differs
        s2 = engine.start("III", "repo", "Same scope")
        id2 = s2.session_id
        assert id1 != id2

    def test_session_id_contains_hash_suffix(self, engine, tmp_dir):
        """Session ID ends with a 6-char hex hash."""
        session = engine.start("III", "repo", "Test feature")
        parts = session.session_id.split("-")
        suffix = parts[-1]
        assert len(suffix) == 6
        int(suffix, 16)  # should not raise — valid hex


# ===========================================================================
# Git operations (mocked subprocess)
# ===========================================================================


class TestGitOperations:
    def test_create_branch_success(self, engine, tmp_dir):
        """_create_branch calls git checkout -b with correct branch name."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("conductor.session.subprocess.run", return_value=mock_result) as mock_run:
            engine._create_branch("ORGAN-III", "my-feature")
        # Should call: git rev-parse, git branch --list, git checkout -b
        assert mock_run.call_count == 3
        checkout_call = mock_run.call_args_list[2]
        assert "checkout" in checkout_call[0][0]
        assert "-b" in checkout_call[0][0]
        assert "feat/iii/my-feature" in checkout_call[0][0]

    def test_create_branch_no_git(self, engine, tmp_dir):
        """_create_branch handles missing git gracefully."""
        with patch("conductor.session.subprocess.run", side_effect=FileNotFoundError):
            engine._create_branch("ORGAN-III", "test")  # should not raise

    def test_commit_breadcrumb_success(self, engine, tmp_dir, capsys):
        """_commit_breadcrumb calls git add + git commit."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        session = Session(
            session_id="test-session", organ="ORGAN-III", repo="repo",
            scope="test", start_time=time.time(), result="SHIPPED",
        )
        with patch("conductor.session.subprocess.run", return_value=mock_result) as mock_run:
            engine._commit_breadcrumb(session)
        # Should call: git rev-parse, git add, git commit
        assert mock_run.call_count == 3

    def test_commit_breadcrumb_reports_failure(self, engine, tmp_dir, capsys):
        """_commit_breadcrumb prints warning on git failure."""
        results = [
            MagicMock(returncode=0, stdout="", stderr=""),   # rev-parse
            MagicMock(returncode=1, stdout="", stderr="error"),  # git add fails
        ]
        session = Session(
            session_id="test-session", organ="ORGAN-III", repo="repo",
            scope="test", start_time=time.time(), result="SHIPPED",
        )
        with patch("conductor.session.subprocess.run", side_effect=results):
            engine._commit_breadcrumb(session)
        out = capsys.readouterr().out
        assert "WARNING" in out


# ===========================================================================
# Phase clusters config override
# ===========================================================================


class TestPhaseClusterOverride:
    def test_default_clusters_returned_without_config(self):
        """get_phase_clusters returns defaults when no .conductor.yaml exists."""
        with patch.object(conductor.constants, "CONFIG_FILE") as mock_config:
            mock_config.exists.return_value = False
            clusters = get_phase_clusters()
        assert clusters == PHASE_CLUSTERS

    def test_config_overrides_phase_clusters(self, tmp_path):
        """get_phase_clusters merges .conductor.yaml overrides."""
        import yaml
        config = {"phases": {"FRAME": ["custom_cluster_a", "custom_cluster_b"]}}
        config_file = tmp_path / ".conductor.yaml"
        config_file.write_text(yaml.dump(config))

        with patch.object(conductor.constants, "CONFIG_FILE", config_file):
            clusters = get_phase_clusters()

        assert clusters["FRAME"] == ["custom_cluster_a", "custom_cluster_b"]
        # Other phases unchanged
        assert clusters["SHAPE"] == PHASE_CLUSTERS["SHAPE"]
        assert clusters["BUILD"] == PHASE_CLUSTERS["BUILD"]


# ===========================================================================
# Template scaffolding with adversarial scope
# ===========================================================================


class TestTemplateScaffolding:
    def test_adversarial_scope_in_templates(self, engine, tmp_dir):
        """Scope containing template markers gets double-substituted (known behavior).

        str.replace is applied sequentially, so {{ scope }} expands first,
        then {{ organ }} in the expanded text gets replaced too.
        This test documents that behavior — not a bug, just a consequence of
        using simple string replacement over a real template engine.
        """
        session = engine.start("III", "repo", "Fix {{ organ }} bug")
        session_dir = tmp_dir / "sessions" / session.session_id
        spec = (session_dir / "spec.md").read_text()
        # The {{ organ }} inside the scope gets replaced with the actual organ
        assert "Fix ORGAN-III bug" in spec


class TestScopeSlugHardening:
    def test_scope_slug_is_sanitized_for_session_id_and_paths(self, engine, tmp_dir):
        session = engine.start("III", "repo", "../../Escape ??? name", git_branch=False)
        session_dir = tmp_dir / "sessions" / session.session_id

        assert session_dir.exists()
        assert ".." not in session.session_id
        assert "/" not in session.session_id
        assert session_dir.resolve().is_relative_to((tmp_dir / "sessions").resolve())

    def test_scope_with_no_slug_chars_falls_back_to_session(self, engine, tmp_dir):
        session = engine.start("III", "repo", "!!!", git_branch=False)
        assert re.search(r"-session-[0-9a-f]{6}$", session.session_id)

    def test_create_branch_sanitizes_slug_argument(self, engine, tmp_dir):
        results = [
            MagicMock(returncode=0, stdout="true", stderr=""),  # rev-parse
            MagicMock(returncode=0, stdout="", stderr=""),      # branch --list
            MagicMock(returncode=0, stdout="", stderr=""),      # checkout -b
        ]
        with patch("conductor.session.subprocess.run", side_effect=results) as mock_run:
            engine._create_branch("ORGAN-III", "../Bad Scope@@")

        checkout_call = mock_run.call_args_list[2]
        checkout_cmd = checkout_call[0][0]
        assert checkout_cmd[-1] == "feat/iii/bad-scope"


# ===========================================================================
# Promotion state machine (constants)
# ===========================================================================


class TestPromotionStateMachine:
    def test_all_promotion_states_have_transitions(self):
        """Every state in PROMOTION_STATES is a key in PROMOTION_TRANSITIONS."""
        for state in PROMOTION_STATES:
            assert state in PROMOTION_TRANSITIONS

    def test_no_self_transitions(self):
        """No promotion state allows self-transition."""
        for state, targets in PROMOTION_TRANSITIONS.items():
            assert state not in targets, f"{state} allows self-transition"

    def test_archived_is_terminal(self):
        """ARCHIVED has no outgoing transitions."""
        assert PROMOTION_TRANSITIONS["ARCHIVED"] == []

    def test_all_targets_are_valid_states(self):
        """All transition targets are valid promotion states."""
        for state, targets in PROMOTION_TRANSITIONS.items():
            for t in targets:
                assert t in PROMOTION_STATES, f"{t} (from {state}) is not a valid state"


# ===========================================================================
# Export process-kit force guard (P2.4 / SP4)
# ===========================================================================


class TestExportForceGuard:
    def test_refuses_nonempty_output_without_force(self, tmp_path, mini_registry):
        """export_process_kit raises if output dir exists and is non-empty."""
        gov = self._make_gov(mini_registry)
        pe = ProductExtractor(gov)
        output = tmp_path / "kit"
        output.mkdir()
        (output / "existing.txt").write_text("content")
        with pytest.raises(ConductorError, match="already exists"):
            pe.export_process_kit(output_dir=output)

    def test_allows_nonempty_output_with_force(self, tmp_path, mini_registry):
        """export_process_kit succeeds with --force on non-empty dir."""
        gov = self._make_gov(mini_registry)
        pe = ProductExtractor(gov)
        output = tmp_path / "kit"
        output.mkdir()
        (output / "existing.txt").write_text("content")
        pe.export_process_kit(output_dir=output, force=True)
        assert (output / "CLAUDE.md").exists()

    def test_allows_empty_output_without_force(self, tmp_path, mini_registry):
        """export_process_kit succeeds on empty existing dir without --force."""
        gov = self._make_gov(mini_registry)
        pe = ProductExtractor(gov)
        output = tmp_path / "kit"
        output.mkdir()
        pe.export_process_kit(output_dir=output)
        assert (output / "CLAUDE.md").exists()

    def _make_gov(self, mini_registry):
        reg_path, gov_path, _ = mini_registry
        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            return GovernanceRuntime()


# ===========================================================================
# Corrupted session state
# ===========================================================================


class TestCorruptedSessionState:
    def test_corrupted_state_raises_session_error(self, tmp_dir):
        """Loading a corrupted session state file raises SessionError."""
        state_file = tmp_dir / ".conductor-session.json"
        state_file.write_text("{invalid json")
        engine = SessionEngine()
        with pytest.raises(SessionError, match="corrupted"):
            engine._load_session()


# ===========================================================================
# Governance audit with bad organ
# ===========================================================================


class TestGovernanceAuditEdge:
    def test_audit_unknown_organ_raises(self, mini_registry):
        reg_path, gov_path, _ = mini_registry
        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            gov = GovernanceRuntime()
        with pytest.raises(GovernanceError, match="not found"):
            gov.audit(organ="NONEXISTENT")

    def test_promote_invalid_state_raises(self, mini_registry):
        reg_path, gov_path, _ = mini_registry
        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            gov = GovernanceRuntime(confirm_fn=lambda _: True)
        with pytest.raises(GovernanceError, match="Invalid state"):
            gov.wip_promote("repo-a", "FANTASY_STATE")


# ===========================================================================
# P3: mine_patterns with synthetic session logs (BS1)
# ===========================================================================


class TestMinePatterns:
    def _make_extractor(self, mini_registry, sessions_dir):
        reg_path, gov_path, _ = mini_registry
        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            gov = GovernanceRuntime()
        return ProductExtractor(gov), sessions_dir

    def test_mine_patterns_no_sessions(self, mini_registry, tmp_path, capsys):
        """mine_patterns reports no logs when sessions dir is empty."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        pe, _ = self._make_extractor(mini_registry, sessions_dir)
        with patch.object(conductor.constants, "SESSIONS_DIR", sessions_dir), \
             patch.object(conductor.product, "SESSIONS_DIR", sessions_dir):
                pe.mine_patterns()
        out = capsys.readouterr().out
        assert "No session logs found" in out

    def test_mine_patterns_with_synthetic_logs(self, mini_registry, tmp_path, capsys):
        """mine_patterns analyzes synthetic session logs correctly."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        pe, _ = self._make_extractor(mini_registry, sessions_dir)

        for i in range(4):
            session_dir = sessions_dir / f"2026-03-{i:02d}-III-test-{i}"
            session_dir.mkdir()
            log = {
                "session_id": f"2026-03-{i:02d}-III-test-{i}",
                "organ": "ORGAN-III",
                "repo": "test-repo",
                "scope": f"Test {i}",
                "duration_minutes": 30 + i * 10,
                "phases": {
                    "FRAME": {"duration": 8 + i, "tools_used": ["web_search"], "commits": 0, "visits": 1},
                    "BUILD": {"duration": 15 + i * 5, "tools_used": ["claude_code_core", "git_core"], "commits": 2, "visits": 1},
                },
                "warnings": [],
                "result": "SHIPPED" if i < 3 else "CLOSED",
                "timestamp": f"2026-03-{i:02d}T12:00:00+00:00",
            }
            (session_dir / "session-log.yaml").write_text(yaml.dump(log))

        with patch.object(conductor.product, "SESSIONS_DIR", sessions_dir), \
             patch.object(conductor.product, "PHASES", PHASES):
            pe.mine_patterns()

        out = capsys.readouterr().out
        assert "Sessions analyzed: 4" in out
        assert "Ship rate: 3/4 (75%)" in out
        assert "web_search" in out or "claude_code_core" in out

    def test_mine_patterns_export_essay(self, mini_registry, tmp_path, capsys):
        """mine_patterns with export_essay generates essay draft."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        exports_dir = tmp_path / "exports"
        pe, _ = self._make_extractor(mini_registry, sessions_dir)

        for i in range(3):
            session_dir = sessions_dir / f"2026-03-{i:02d}-III-test-{i}"
            session_dir.mkdir()
            log = {
                "session_id": f"2026-03-{i:02d}-III-test-{i}",
                "organ": "ORGAN-III", "repo": "test", "scope": f"Test {i}",
                "duration_minutes": 30,
                "phases": {"FRAME": {"duration": 10, "tools_used": ["web_search"], "commits": 0, "visits": 1}},
                "warnings": [], "result": "SHIPPED",
                "timestamp": f"2026-03-{i:02d}T12:00:00+00:00",
            }
            (session_dir / "session-log.yaml").write_text(yaml.dump(log))

        with patch.object(conductor.product, "SESSIONS_DIR", sessions_dir), \
             patch.object(conductor.product, "EXPORTS_DIR", exports_dir), \
             patch.object(conductor.product, "PHASES", PHASES):
            pe.mine_patterns(export_essay=True)

        essay = exports_dir / "pattern-essay-draft.md"
        assert essay.exists()
        content = essay.read_text()
        assert "3 Conductor Sessions" in content
        assert "100%" in content  # 3/3 shipped


# ===========================================================================
# P3: enforce_generate dry-run output (BS2)
# ===========================================================================


class TestEnforceGenerate:
    def test_enforce_generate_dry_run(self, tmp_path, capsys):
        """enforce_generate --dry-run lists artifacts without writing files."""
        gov_rules = {
            "version": "1.0",
            "organ_requirements": {
                "ORGAN-III": {"requires_tests": True, "requires_revenue_fields": False},
            },
        }
        gov_path = tmp_path / "governance.json"
        gov_path.write_text(json.dumps(gov_rules))
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps({"version": "2.0", "organs": {}}))

        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            gov = GovernanceRuntime()

        generated_dir = tmp_path / "generated"
        with patch.object(conductor.governance, "GENERATED_DIR", generated_dir):
            gov.enforce_generate(dry_run=True)

        out = capsys.readouterr().out
        assert "Would generate" in out
        assert "rulesets/" in out
        assert "workflows/" in out
        assert "PULL_REQUEST_TEMPLATE.md" in out
        # Dry run should not create files
        assert not generated_dir.exists()

    def test_enforce_generate_writes_files(self, tmp_path, capsys):
        """enforce_generate without dry-run creates actual artifact files."""
        gov_rules = {"version": "1.0", "organ_requirements": {}}
        gov_path = tmp_path / "governance.json"
        gov_path.write_text(json.dumps(gov_rules))
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps({"version": "2.0", "organs": {}}))

        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            gov = GovernanceRuntime()

        generated_dir = tmp_path / "generated"
        with patch.object(conductor.governance, "GENERATED_DIR", generated_dir):
            gov.enforce_generate(dry_run=False)

        assert generated_dir.exists()
        # Should have rulesets, workflows, PR template, issue form
        assert (generated_dir / "PULL_REQUEST_TEMPLATE.md").exists()
        assert any(generated_dir.rglob("*.yml"))
        assert any(generated_dir.rglob("*.json"))

    def test_enforce_generate_no_governance_raises(self, tmp_path):
        """enforce_generate raises GovernanceError if no governance rules loaded."""
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps({"version": "2.0", "organs": {}}))
        gov_path = tmp_path / "governance-missing.json"  # does not exist

        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            gov = GovernanceRuntime()

        with pytest.raises(GovernanceError, match="No governance rules"):
            gov.enforce_generate()


# ===========================================================================
# P3: Cumulative stats across multiple sessions (BS3)
# ===========================================================================


class TestCumulativeStats:
    def test_stats_accumulate_across_sessions(self, engine, tmp_dir):
        """Closing multiple sessions accumulates stats correctly."""
        # Session 1: SHIPPED
        engine.start("III", "repo", "Feature A")
        engine.phase("shape")
        engine.phase("build")
        engine.phase("prove")
        engine.phase("done")
        engine.close()

        # Session 2: CLOSED (no DONE transition)
        engine.start("III", "repo", "Feature B")
        engine.phase("shape")
        engine.close()

        stats_file = tmp_dir / ".conductor-stats.json"
        assert stats_file.exists()
        stats = json.loads(stats_file.read_text())
        assert stats["total_sessions"] == 2
        assert stats["shipped"] == 1
        assert stats["closed"] == 1
        assert stats["by_organ"]["ORGAN-III"]["sessions"] == 2

    def test_stats_show_on_start(self, engine, tmp_dir, capsys):
        """After accumulating stats, session start shows lifetime summary."""
        engine.start("III", "repo", "A")
        engine.close()
        capsys.readouterr()  # clear

        engine.start("III", "repo", "B")
        out = capsys.readouterr().out
        assert "Lifetime:" in out
        assert "1 sessions" in out


# ===========================================================================
# P3: wip_check with PUBLIC_PROCESS violations (BS4)
# ===========================================================================


class TestWipCheckPublicProcess:
    def test_wip_check_flags_public_process_violation(self, tmp_path, capsys):
        """wip_check flags PUBLIC_PROCESS violations when over limit."""
        registry = {
            "version": "2.0",
            "organs": {
                "ORGAN-I": {
                    "name": "Theory",
                    "repositories": [
                        {"name": f"pub-{i}", "promotion_status": "PUBLIC_PROCESS"}
                        for i in range(3)
                    ],
                },
            },
        }
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps(registry))
        gov_path = tmp_path / "governance.json"
        gov_path.write_text(json.dumps({"version": "1.0"}))

        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            gov = GovernanceRuntime()

        gov.wip_check()
        out = capsys.readouterr().out
        assert f"PUB>{MAX_PUBLIC_PROCESS_PER_ORGAN}" in out
        assert "WIP VIOLATIONS" in out
        assert "PUBLIC_PROCESS" in out

    def test_wip_check_no_violation_under_limit(self, mini_registry, capsys):
        """wip_check shows warnings (not violations) when at limits."""
        # mini_registry has 3 CANDIDATE (at limit 3) and 1 PUBLIC_PROCESS (at limit 1).
        # Both are AT the limit — not over — so no violations.
        # But both are >= 80% of their limit, so early warnings fire.
        reg_path, gov_path, _ = mini_registry
        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            gov = GovernanceRuntime()

        gov.wip_check()
        out = capsys.readouterr().out
        assert "WIP VIOLATIONS" not in out
        assert "WIP WARNINGS" in out

    def test_promote_blocked_by_public_process_limit(self, tmp_path):
        """Promoting to PUBLIC_PROCESS blocked when at limit."""
        registry = {
            "version": "2.0",
            "organs": {
                "ORGAN-I": {
                    "name": "Theory",
                    "repositories": [
                        {"name": "existing-pub", "promotion_status": "PUBLIC_PROCESS"},
                        {"name": "candidate-repo", "promotion_status": "CANDIDATE"},
                    ],
                },
            },
        }
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps(registry))
        gov_path = tmp_path / "governance.json"
        gov_path.write_text(json.dumps({"version": "1.0"}))

        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            gov = GovernanceRuntime(confirm_fn=lambda _: True)

        with pytest.raises(GovernanceError, match="PUBLIC_PROCESS"):
            gov.wip_promote("candidate-repo", "PUBLIC_PROCESS")


class TestConductorCliValidate:
    def _run(self, *args):
        result = subprocess.run(
            [sys.executable, "-m", "conductor", *args],
            cwd=str(Path(__file__).parent.parent),
            capture_output=True,
            text=True,
            timeout=20,
        )
        return result

    def test_validate_command(self):
        workflow_path = Path(__file__).parent.parent / "workflow-dsl.yaml"
        result = self._run("validate", str(workflow_path))
        assert result.returncode == 0
        assert "valid" in result.stdout.lower()

    def test_validate_strict_fails_on_warning(self, tmp_path):
        wf = {
            "name": "strict-warning",
            "steps": [
                {"name": "build", "cluster": "claude_code_core", "depends_on": ["plan"]},
                {"name": "plan", "cluster": "sequential_thinking"},
            ],
        }
        path = tmp_path / "strict_warning.yaml"
        path.write_text(yaml.dump(wf))

        result = self._run("validate", str(path), "--strict")
        assert result.returncode == 1
        assert "STRICT-WARNING" in result.stdout


# ===========================================================================
# P3: Version attribute (W5)
# ===========================================================================


class TestVersion:
    def test_version_is_string(self):
        assert isinstance(__version__, str)

    def test_version_matches_pyproject(self):
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject.read_text()
        assert f'version = "{__version__}"' in content
