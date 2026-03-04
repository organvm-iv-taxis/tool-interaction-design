"""Tests for conductor patchbay and work queue."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from conductor import __version__
from conductor.patchbay import Patchbay
from conductor.workqueue import WorkItem, WorkQueue
from conductor.session import SessionEngine, _load_stats, _save_stats
import conductor.constants
import conductor.governance
import conductor.session
from conductor.governance import GovernanceRuntime


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
    for name in ("spec.md", "plan.md", "status.md"):
        (templates / name).write_text(f"# {{{{ scope }}}}\n{{{{ organ }}}} {{{{ repo }}}}")

    state_file = tmp_path / ".conductor-session.json"
    stats_file = tmp_path / ".conductor-stats.json"

    with patch.object(conductor.constants, "SESSIONS_DIR", sessions), \
         patch.object(conductor.constants, "TEMPLATES_DIR", templates), \
         patch.object(conductor.constants, "SESSION_STATE_FILE", state_file), \
         patch.object(conductor.constants, "STATS_FILE", stats_file), \
         patch.object(conductor.session, "SESSIONS_DIR", sessions), \
         patch.object(conductor.session, "TEMPLATES_DIR", templates), \
         patch.object(conductor.session, "SESSION_STATE_FILE", state_file), \
         patch.object(conductor.session, "STATS_FILE", stats_file):
        yield tmp_path


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
                     "implementation_status": "ACTIVE", "dependencies": [], "org": "test-org",
                     "last_validated": "2026-01-01"},
                    {"name": "repo-b", "promotion_status": "CANDIDATE", "tier": "standard",
                     "documentation_status": "DEPLOYED", "ci_workflow": "ci.yml",
                     "implementation_status": "ACTIVE", "dependencies": [], "org": "test-org",
                     "last_validated": "2026-03-01"},
                    {"name": "repo-c", "promotion_status": "CANDIDATE", "tier": "standard",
                     "documentation_status": "DEPLOYED", "ci_workflow": "ci.yml",
                     "implementation_status": "ACTIVE", "dependencies": [], "org": "test-org",
                     "last_validated": "2026-03-01"},
                    {"name": "repo-d", "promotion_status": "LOCAL", "tier": "standard",
                     "documentation_status": "DEPLOYED", "ci_workflow": "ci.yml",
                     "implementation_status": "SKELETON", "dependencies": [], "org": "test-org"},
                    {"name": "repo-e", "promotion_status": "PUBLIC_PROCESS", "tier": "flagship",
                     "documentation_status": "DEPLOYED", "ci_workflow": "ci.yml",
                     "implementation_status": "ACTIVE", "dependencies": [], "org": "test-org"},
                    {"name": "repo-f", "promotion_status": "LOCAL", "tier": "standard",
                     "documentation_status": "EMPTY", "ci_workflow": "",
                     "implementation_status": "SKELETON", "dependencies": [], "org": "test-org"},
                    {"name": "repo-g", "promotion_status": "ARCHIVED", "tier": "standard",
                     "documentation_status": "DEPLOYED", "ci_workflow": "",
                     "implementation_status": "ACTIVE", "dependencies": [], "org": "test-org"},
                ],
            },
        },
    }
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps(registry, indent=2))
    gov_path = tmp_path / "governance.json"
    gov_path.write_text(json.dumps({"version": "1.0"}))
    return reg_path, gov_path, registry


@pytest.fixture
def gov(mini_registry):
    """Create a GovernanceRuntime with the mini registry."""
    reg_path, gov_path, _ = mini_registry
    with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
         patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
        return GovernanceRuntime()


# ===========================================================================
# WorkQueue tests
# ===========================================================================


class TestWorkQueue:
    def test_compute_returns_sorted_items(self, gov):
        wq = WorkQueue(gov)
        items = wq.compute()
        assert len(items) > 0
        # Should be sorted by score descending
        scores = [item.score for item in items]
        assert scores == sorted(scores, reverse=True)

    def test_wip_violations_detected(self, gov):
        """Mini registry has 3 CANDIDATE (at limit, not over). Add a 4th to test violation."""
        # Modify registry to have 4 CANDIDATE
        gov.registry["organs"]["ORGAN-III"]["repositories"].append(
            {"name": "repo-extra", "promotion_status": "CANDIDATE", "tier": "standard",
             "documentation_status": "DEPLOYED", "ci_workflow": "ci.yml",
             "implementation_status": "ACTIVE", "dependencies": [], "org": "test-org",
             "last_validated": "2026-03-01"}
        )
        wq = WorkQueue(gov)
        items = wq.compute()
        violations = [i for i in items if i.category == "wip_violation"]
        assert len(violations) >= 1
        assert violations[0].priority == "CRITICAL"
        assert violations[0].score >= 100

    def test_stale_candidates_detected(self, gov):
        """repo-a has last_validated 2026-01-01 which is >30d old."""
        wq = WorkQueue(gov)
        items = wq.compute()
        stale = [i for i in items if i.category == "stale"]
        assert len(stale) >= 1
        assert any(i.repo == "repo-a" for i in stale)

    def test_missing_infrastructure_detected(self, gov):
        """repo-f has empty ci_workflow and EMPTY documentation."""
        wq = WorkQueue(gov)
        items = wq.compute()
        missing_ci = [i for i in items if i.category == "missing_ci"]
        missing_docs = [i for i in items if i.category == "missing_docs"]
        assert any(i.repo == "repo-f" for i in missing_ci)
        assert any(i.repo == "repo-f" for i in missing_docs)

    def test_archived_repos_excluded_from_missing_infra(self, gov):
        """repo-g is ARCHIVED and has no CI — should NOT appear in missing_ci."""
        wq = WorkQueue(gov)
        items = wq.compute()
        missing_ci = [i for i in items if i.category == "missing_ci"]
        assert not any(i.repo == "repo-g" for i in missing_ci)

    def test_promotion_candidates_detected(self, gov):
        """repo-d is LOCAL with DEPLOYED docs and CI — should be promotion_ready."""
        wq = WorkQueue(gov)
        items = wq.compute()
        promotion = [i for i in items if i.category == "promotion_ready"]
        assert any(i.repo == "repo-d" for i in promotion)

    def test_organ_filter(self, gov):
        """Filtering to a nonexistent organ returns empty queue."""
        wq = WorkQueue(gov)
        items = wq.compute(organ_filter="ORGAN-I")
        assert len(items) == 0

    def test_work_item_has_suggested_command(self, gov):
        """Every work item has a non-empty suggested_command."""
        wq = WorkQueue(gov)
        items = wq.compute()
        for item in items:
            assert item.suggested_command


# ===========================================================================
# Patchbay tests
# ===========================================================================


class TestPatchbay:
    def test_briefing_returns_all_sections(self, tmp_dir, gov):
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()

        assert "timestamp" in data
        assert "session" in data
        assert "pulse" in data
        assert "queue" in data
        assert "stats" in data
        assert "suggested_action" in data

    def test_session_section_no_active(self, tmp_dir, gov):
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()

        assert data["session"]["active"] is False

    def test_session_section_with_active_session(self, tmp_dir, gov):
        engine = SessionEngine()
        engine.start("III", "test-repo", "Test feature")

        pb = Patchbay(engine=engine)
        pb.gov = gov
        pb.wq = WorkQueue(gov)
        data = pb.briefing()

        assert data["session"]["active"] is True
        assert data["session"]["organ"] == "ORGAN-III"
        assert data["session"]["repo"] == "test-repo"
        assert data["session"]["current_phase"] == "FRAME"

    def test_pulse_counts_repos(self, tmp_dir, gov):
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()

        pulse = data["pulse"]
        assert pulse["total_repos"] == 7
        organ_data = pulse["organs"]["ORGAN-III"]
        assert organ_data["candidate"] == 3
        assert organ_data["public_process"] == 1

    def test_format_text_produces_string(self, tmp_dir, gov):
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()
            text = pb.format_text(data)

        assert "PATCHBAY" in text
        assert "PULSE" in text
        assert "QUEUE" in text

    def test_format_json_produces_valid_json(self, tmp_dir, gov):
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()
            json_str = pb.format_json(data)

        parsed = json.loads(json_str)
        assert "session" in parsed
        assert "pulse" in parsed

    def test_organ_filter_limits_pulse(self, tmp_dir, gov):
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing(organ_filter="ORGAN-III")

        assert "ORGAN-III" in data["pulse"]["organs"]
        assert len(data["pulse"]["organs"]) == 1

    def test_suggested_action_no_session(self, tmp_dir, gov):
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()

        # Should suggest something from the work queue
        assert data["suggested_action"]
        assert isinstance(data["suggested_action"], str)

    def test_suggested_action_active_session(self, tmp_dir, gov):
        engine = SessionEngine()
        engine.start("III", "test-repo", "Test scope")

        pb = Patchbay(engine=engine)
        pb.gov = gov
        pb.wq = WorkQueue(gov)
        data = pb.briefing()

        assert "shape" in data["suggested_action"].lower()


# ===========================================================================
# Stats extension tests
# ===========================================================================


class TestStatsExtensions:
    def test_streak_increments_on_shipped(self, tmp_dir):
        engine = SessionEngine()

        # Ship 3 in a row
        for i in range(3):
            engine.start("III", "repo", f"Feature {i}")
            engine.phase("shape")
            engine.phase("build")
            engine.phase("prove")
            engine.phase("done")
            engine.close()

        stats = _load_stats()
        assert stats["streak"] == 3

    def test_streak_resets_on_closed(self, tmp_dir):
        engine = SessionEngine()

        # Ship one
        engine.start("III", "repo", "Feature A")
        engine.phase("shape")
        engine.phase("build")
        engine.phase("prove")
        engine.phase("done")
        engine.close()

        # Close without shipping
        engine.start("III", "repo", "Feature B")
        engine.close()

        stats = _load_stats()
        assert stats["streak"] == 0

    def test_last_session_id_tracked(self, tmp_dir):
        engine = SessionEngine()
        session = engine.start("III", "repo", "Feature")
        session_id = session.session_id
        engine.close()

        stats = _load_stats()
        assert stats["last_session_id"] == session_id

    def test_recent_sessions_capped_at_10(self, tmp_dir):
        engine = SessionEngine()

        for i in range(12):
            engine.start("III", "repo", f"Feature {i}")
            engine.close()

        stats = _load_stats()
        assert len(stats["recent_sessions"]) == 10
        # Most recent should be last — session ID contains the slug "feature-11"
        assert "feature-11" in stats["recent_sessions"][-1]["session_id"]

    def test_recent_sessions_contain_required_fields(self, tmp_dir):
        engine = SessionEngine()
        engine.start("III", "repo", "Test")
        engine.close()

        stats = _load_stats()
        entry = stats["recent_sessions"][0]
        assert "session_id" in entry
        assert "result" in entry
        assert "organ" in entry
        assert "duration_minutes" in entry


# ===========================================================================
# Version test
# ===========================================================================


class TestPatchbayVersion:
    def test_version_is_0_5_0(self):
        assert __version__ == "0.5.0"

    def test_version_matches_pyproject(self):
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject.read_text()
        assert f'version = "{__version__}"' in content
