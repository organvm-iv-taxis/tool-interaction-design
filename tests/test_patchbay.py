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
    active_sessions = tmp_path / "active-sessions"
    active_sessions.mkdir()

    with patch.object(conductor.constants, "SESSIONS_DIR", sessions), \
         patch.object(conductor.constants, "TEMPLATES_DIR", templates), \
         patch.object(conductor.constants, "SESSION_STATE_FILE", state_file), \
         patch.object(conductor.constants, "STATS_FILE", stats_file), \
         patch.object(conductor.constants, "ACTIVE_SESSIONS_DIR", active_sessions), \
         patch.object(conductor.session, "SESSIONS_DIR", sessions), \
         patch.object(conductor.session, "TEMPLATES_DIR", templates), \
         patch.object(conductor.session, "SESSION_STATE_FILE", state_file), \
         patch.object(conductor.session, "STATS_FILE", stats_file), \
         patch.object(conductor.session, "ACTIVE_SESSIONS_DIR", active_sessions):
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
    def test_version_is_0_5_1(self):
        assert __version__ == "0.5.1"

    def test_version_matches_pyproject(self):
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject.read_text()
        assert f'version = "{__version__}"' in content


# ===========================================================================
# Additional WorkQueue coverage
# ===========================================================================


class TestWorkQueueEdgeCases:
    def test_malformed_last_validated_date(self, mini_registry, gov):
        """Malformed date string produces a stale WorkItem with score 75."""
        gov.registry["organs"]["ORGAN-III"]["repositories"].append(
            {"name": "bad-date-repo", "promotion_status": "CANDIDATE",
             "last_validated": "not-a-date", "ci_workflow": "ci.yml",
             "dependencies": [], "org": "test-org"}
        )
        wq = WorkQueue(gov)
        items = wq.compute()
        bad = [i for i in items if i.repo == "bad-date-repo"]
        assert len(bad) == 1
        assert bad[0].category == "stale"
        assert bad[0].score == 75
        assert "invalid" in bad[0].description

    def test_candidate_no_last_validated(self, mini_registry, gov):
        """CANDIDATE with empty last_validated produces score-75 stale item."""
        gov.registry["organs"]["ORGAN-III"]["repositories"].append(
            {"name": "no-date-repo", "promotion_status": "CANDIDATE",
             "last_validated": "", "ci_workflow": "ci.yml",
             "dependencies": [], "org": "test-org"}
        )
        wq = WorkQueue(gov)
        items = wq.compute()
        no_date = [i for i in items if i.repo == "no-date-repo"]
        assert len(no_date) == 1
        assert no_date[0].score == 75
        assert "no validation date" in no_date[0].description

    def test_local_docs_no_ci_score_20(self, gov):
        """LOCAL with docs DEPLOYED but no CI scores 20 (not 25)."""
        gov.registry["organs"]["ORGAN-III"]["repositories"].append(
            {"name": "docs-only", "promotion_status": "LOCAL",
             "documentation_status": "DEPLOYED", "ci_workflow": "",
             "dependencies": [], "org": "test-org"}
        )
        wq = WorkQueue(gov)
        items = wq.compute()
        promo = [i for i in items if i.repo == "docs-only" and i.category == "promotion_ready"]
        assert len(promo) == 1
        assert promo[0].score == 20
        assert "add CI" in promo[0].description

    def test_public_process_wip_violation(self, gov):
        """Adding 2nd PUBLIC_PROCESS triggers WIP violation (limit is 1)."""
        gov.registry["organs"]["ORGAN-III"]["repositories"].append(
            {"name": "pub-extra", "promotion_status": "PUBLIC_PROCESS",
             "dependencies": [], "org": "test-org"}
        )
        wq = WorkQueue(gov)
        items = wq.compute()
        viols = [i for i in items if i.category == "wip_violation"
                 and "PUBLIC_PROCESS" in i.description]
        assert len(viols) == 1
        assert viols[0].priority == "CRITICAL"

    def test_empty_registry_returns_empty(self, mini_registry, gov):
        """Empty organs dict produces no work items."""
        gov.registry["organs"] = {}
        wq = WorkQueue(gov)
        items = wq.compute()
        assert items == []

    def test_all_archived_no_missing_ci(self, mini_registry):
        """Registry with only ARCHIVED repos produces no missing_ci items."""
        reg_path, gov_path, _ = mini_registry
        registry = {
            "version": "2.0",
            "organs": {
                "ORGAN-I": {
                    "name": "Theory",
                    "repositories": [
                        {"name": "arch1", "promotion_status": "ARCHIVED",
                         "ci_workflow": "", "documentation_status": "EMPTY",
                         "dependencies": [], "org": "test"},
                        {"name": "arch2", "promotion_status": "ARCHIVED",
                         "ci_workflow": "", "documentation_status": "EMPTY",
                         "dependencies": [], "org": "test"},
                    ],
                },
            },
        }
        reg_path.write_text(json.dumps(registry, indent=2))
        with patch.object(conductor.governance, "REGISTRY_PATH", reg_path), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", gov_path):
            gov = GovernanceRuntime()
        wq = WorkQueue(gov)
        items = wq.compute()
        missing = [i for i in items if i.category in ("missing_ci", "missing_docs")]
        assert missing == []


# ===========================================================================
# Patchbay formatting and edge cases
# ===========================================================================


class TestPatchbayFormatting:
    def test_format_text_active_session(self, tmp_dir, gov):
        """format_text with active session renders phase history, clusters, next command."""
        engine = SessionEngine()
        engine.start("III", "test-repo", "Test scope")
        engine.phase("shape")

        pb = Patchbay(engine=engine)
        pb.gov = gov
        pb.wq = WorkQueue(gov)
        data = pb.briefing()
        text = pb.format_text(data)

        assert "SESSION: ACTIVE" in text
        assert "test-repo" in text
        assert "FRAME(" in text  # Phase history
        assert "SHAPE(" in text
        assert "conductor session phase build" in text  # Next command
        assert "PULSE (abbreviated)" in text

    def test_format_text_with_stats(self, tmp_dir, gov):
        """format_text renders STATS section when sessions exist."""
        engine = SessionEngine()
        engine.start("III", "repo", "Test")
        engine.phase("shape")
        engine.phase("build")
        engine.phase("prove")
        engine.phase("done")
        engine.close()

        pb = Patchbay(engine=engine)
        pb.gov = gov
        pb.wq = WorkQueue(gov)
        data = pb.briefing()
        text = pb.format_text(data)

        assert "STATS" in text
        assert "Sessions: 1" in text
        assert "Ship rate: 100%" in text
        assert "Streak: 1" in text

    def test_format_text_no_stats_when_zero(self, tmp_dir, gov):
        """format_text omits STATS section when total_sessions is 0."""
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()
            text = pb.format_text(data)

        assert "STATS\n" not in text

    def test_format_text_last_closed_session(self, tmp_dir, gov):
        """format_text shows last closed session when no active session."""
        engine = SessionEngine()
        engine.start("III", "repo", "Feature X")
        engine.close()

        pb = Patchbay(engine=engine)
        pb.gov = gov
        pb.wq = WorkQueue(gov)
        data = pb.briefing()
        text = pb.format_text(data)

        assert "SESSION: none active" in text
        assert "Last closed:" in text

    def test_format_section_text_pulse(self, tmp_dir, gov):
        """format_section_text renders pulse section."""
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()
            section_data = {"timestamp": data["timestamp"], "pulse": data["pulse"]}
            text = pb.format_section_text(section_data)

        assert "PULSE" in text
        assert "ORGAN" in text
        assert "REPOS" in text

    def test_format_section_text_queue(self, tmp_dir, gov):
        """format_section_text renders queue section."""
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()
            section_data = {"timestamp": data["timestamp"], "queue": data["queue"]}
            text = pb.format_section_text(section_data)

        assert "QUEUE" in text

    def test_format_section_text_stats(self, tmp_dir, gov):
        """format_section_text renders stats section."""
        engine = SessionEngine()
        engine.start("III", "repo", "Test")
        engine.close()

        pb = Patchbay(engine=engine)
        pb.gov = gov
        pb.wq = WorkQueue(gov)
        data = pb.briefing()
        section_data = {"timestamp": data["timestamp"], "stats": data["stats"]}
        text = pb.format_section_text(section_data)

        assert "STATS" in text
        assert "Sessions:" in text

    def test_format_section_text_unknown_falls_back_to_json(self, tmp_dir, gov):
        """format_section_text returns JSON for unknown section keys."""
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            data = {"timestamp": "2026-03-04T00:00:00", "unknown_section": {"foo": "bar"}}
            text = pb.format_section_text(data)

        parsed = json.loads(text)
        assert parsed["unknown_section"]["foo"] == "bar"


# ===========================================================================
# _next_command coverage
# ===========================================================================


class TestNextCommand:
    def test_frame_command(self):
        assert Patchbay._next_command("FRAME") == "conductor session phase shape"

    def test_shape_command(self):
        assert Patchbay._next_command("SHAPE") == "conductor session phase build"

    def test_build_command(self):
        assert Patchbay._next_command("BUILD") == "conductor session phase prove"

    def test_prove_command(self):
        assert Patchbay._next_command("PROVE") == "conductor session phase done"

    def test_done_command(self):
        assert Patchbay._next_command("DONE") == "conductor session close"

    def test_unknown_phase_defaults_to_close(self):
        assert Patchbay._next_command("INVALID") == "conductor session close"


# ===========================================================================
# _suggest_next coverage
# ===========================================================================


class TestSuggestNext:
    def test_suggest_frame_phase(self, tmp_dir, gov):
        engine = SessionEngine()
        engine.start("III", "repo", "Test")

        pb = Patchbay(engine=engine)
        pb.gov = gov
        pb.wq = WorkQueue(gov)
        suggestion = pb._suggest_next()

        assert "FRAME" in suggestion
        assert "shape" in suggestion

    def test_suggest_shape_phase(self, tmp_dir, gov):
        engine = SessionEngine()
        engine.start("III", "repo", "Test")
        engine.phase("shape")

        pb = Patchbay(engine=engine)
        pb.gov = gov
        pb.wq = WorkQueue(gov)
        suggestion = pb._suggest_next()

        assert "build" in suggestion

    def test_suggest_build_phase(self, tmp_dir, gov):
        engine = SessionEngine()
        engine.start("III", "repo", "Test")
        engine.phase("shape")
        engine.phase("build")

        pb = Patchbay(engine=engine)
        pb.gov = gov
        pb.wq = WorkQueue(gov)
        suggestion = pb._suggest_next()

        assert "prove" in suggestion

    def test_suggest_prove_phase(self, tmp_dir, gov):
        engine = SessionEngine()
        engine.start("III", "repo", "Test")
        engine.phase("shape")
        engine.phase("build")
        engine.phase("prove")

        pb = Patchbay(engine=engine)
        pb.gov = gov
        pb.wq = WorkQueue(gov)
        suggestion = pb._suggest_next()

        assert "done" in suggestion

    def test_suggest_done_phase(self, tmp_dir, gov):
        engine = SessionEngine()
        engine.start("III", "repo", "Test")
        engine.phase("shape")
        engine.phase("build")
        engine.phase("prove")
        engine.phase("done")

        pb = Patchbay(engine=engine)
        pb.gov = gov
        pb.wq = WorkQueue(gov)
        suggestion = pb._suggest_next()

        assert "close" in suggestion

    def test_suggest_empty_queue(self, tmp_dir, gov):
        """Empty work queue suggests starting a new session."""
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            gov.registry["organs"] = {}
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            suggestion = pb._suggest_next()

        assert "clean" in suggestion.lower()


# ===========================================================================
# Graceful degradation
# ===========================================================================


class TestGracefulDegradation:
    def test_section_error_does_not_crash_briefing(self, tmp_dir, gov):
        """If one section throws, other sections still render."""
        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)

            # Sabotage _pulse_section to raise
            original_pulse = pb._pulse_section
            def broken_pulse(organ_filter=None):
                raise RuntimeError("pulse broke")
            pb._pulse_section = broken_pulse

            data = pb.briefing()

        assert "error" in data["pulse"]
        assert data["pulse"]["error"] == "pulse broke"
        # Other sections still populated
        assert "active" in data["session"]
        assert "total" in data["queue"]
        assert "total_sessions" in data["stats"]

    def test_corrupted_stats_file_returns_defaults(self, tmp_dir):
        """Corrupted stats JSON returns default dict."""
        stats_file = tmp_dir / ".conductor-stats.json"
        stats_file.write_text("{{{corrupted json")

        stats = _load_stats()
        assert stats["total_sessions"] == 0
        assert stats["streak"] == 0
        assert stats["recent_sessions"] == []

    def test_session_section_handles_corrupted_state(self, tmp_dir, gov):
        """Corrupted session state file doesn't crash _session_section."""
        state_file = tmp_dir / ".conductor-session.json"
        state_file.write_text("{{{not json")

        engine = SessionEngine()
        pb = Patchbay(engine=engine)
        pb.gov = gov
        pb.wq = WorkQueue(gov)
        # _session_section catches the exception from _load_session
        section = pb._session_section()
        assert section["active"] is False


# ===========================================================================
# Queue truncation
# ===========================================================================


class TestQueueTruncation:
    def test_queue_section_caps_at_10(self, mini_registry, gov):
        """_queue_section returns at most 10 items."""
        # Add enough repos to generate >10 items
        for i in range(15):
            gov.registry["organs"]["ORGAN-III"]["repositories"].append(
                {"name": f"extra-{i}", "promotion_status": "LOCAL",
                 "documentation_status": "EMPTY", "ci_workflow": "",
                 "dependencies": [], "org": "test-org"}
            )

        with patch.object(conductor.session, "SESSION_STATE_FILE", Path("/tmp/nonexistent")):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()

        queue = data["queue"]
        assert len(queue["items"]) <= 10
        assert queue["total"] > 10  # total reflects actual count

    def test_format_text_queue_shows_max_5(self, mini_registry, gov):
        """format_text shows at most 5 queue items."""
        for i in range(15):
            gov.registry["organs"]["ORGAN-III"]["repositories"].append(
                {"name": f"xtra-{i}", "promotion_status": "LOCAL",
                 "documentation_status": "EMPTY", "ci_workflow": "",
                 "dependencies": [], "org": "test-org"}
            )

        with patch.object(conductor.session, "SESSION_STATE_FILE", Path("/tmp/nonexistent")):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()
            text = pb.format_text(data)

        # Count "-> " lines within the QUEUE section only (between QUEUE header and next section)
        lines = text.split("\n")
        in_queue = False
        queue_commands = []
        for line in lines:
            if "QUEUE" in line and "top" in line:
                in_queue = True
                continue
            if in_queue and (line.strip().startswith("STATS") or line.strip().startswith("NEXT ACTION") or line.strip().startswith("ORACLE") or line.strip().startswith("GUARDIAN")):
                break
            if in_queue and line.strip().startswith("->"):
                queue_commands.append(line)
        assert len(queue_commands) <= 5


# ===========================================================================
# Patchbay pulse edge cases
# ===========================================================================


class TestPulseEdgeCases:
    def test_empty_registry_pulse(self, mini_registry, gov):
        """Empty organs produces empty pulse."""
        gov.registry["organs"] = {}

        with patch.object(conductor.session, "SESSION_STATE_FILE", Path("/tmp/nonexistent")):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()

        assert data["pulse"]["total_repos"] == 0
        assert data["pulse"]["organs"] == {}
        assert data["pulse"]["violations_count"] == 0

    def test_archived_repos_counted_in_pulse(self, mini_registry, gov):
        """ARCHIVED repos appear in pulse total and archived count."""
        with patch.object(conductor.session, "SESSION_STATE_FILE", Path("/tmp/nonexistent")):
            engine = SessionEngine()
            pb = Patchbay(engine=engine)
            pb.gov = gov
            pb.wq = WorkQueue(gov)
            data = pb.briefing()

        organ = data["pulse"]["organs"]["ORGAN-III"]
        assert organ["archived"] == 1  # repo-g
        assert organ["total"] == 7  # all 7 repos counted


# ===========================================================================
# MCP server patch function
# ===========================================================================


class TestMCPPatch:
    def test_mcp_patch_returns_valid_json(self, tmp_dir, gov):
        """mcp_server.patch() returns valid JSON briefing."""
        try:
            from mcp_server import patch as mcp_patch
        except (ImportError, SystemExit):
            pytest.skip("MCP SDK not installed")

        with patch.object(conductor.session, "SESSION_STATE_FILE", tmp_dir / ".conductor-session.json"), \
             patch.object(conductor.governance, "REGISTRY_PATH", tmp_dir / "reg.json"), \
             patch.object(conductor.governance, "GOVERNANCE_PATH", tmp_dir / "gov.json"):
            # Write minimal registry
            (tmp_dir / "reg.json").write_text(json.dumps({
                "version": "2.0", "organs": {}
            }))
            (tmp_dir / "gov.json").write_text(json.dumps({"version": "1.0"}))

            result = mcp_patch(organ=None)
            parsed = json.loads(result)

        assert "timestamp" in parsed or "error" in parsed
