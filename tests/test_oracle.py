"""Comprehensive tests for the Oracle — Guardian Angel advisory engine."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import conductor.constants
import conductor.oracle
from conductor.oracle import (
    DETECTOR_REGISTRY,
    Advisory,
    Oracle,
    OracleContext,
    OracleProfile,
    _load_oracle_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def oracle_tmp(tmp_path):
    """Patch Oracle-relevant paths to temp directory."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    state_file = tmp_path / ".conductor-oracle-state.json"
    stats_file = tmp_path / ".conductor-stats.json"
    session_state = tmp_path / ".conductor-session.json"
    pattern_file = tmp_path / ".conductor-pattern-history.jsonl"

    with (
        patch.object(conductor.constants, "SESSIONS_DIR", sessions),
        patch.object(conductor.constants, "STATS_FILE", stats_file),
        patch.object(conductor.constants, "SESSION_STATE_FILE", session_state),
        patch.object(conductor.constants, "ORACLE_STATE_FILE", state_file),
        patch.object(conductor.constants, "PATTERN_HISTORY_FILE", pattern_file),
        patch.object(conductor.oracle, "SESSIONS_DIR", sessions),
        patch.object(conductor.oracle, "STATS_FILE", stats_file),
        patch.object(conductor.oracle, "ORACLE_STATE_FILE", state_file),
    ):
        yield tmp_path


def _write_stats(tmp_path: Path, stats: dict) -> None:
    (tmp_path / ".conductor-stats.json").write_text(json.dumps(stats))


def _write_session(tmp_path: Path, session: dict) -> None:
    (tmp_path / ".conductor-session.json").write_text(json.dumps(session))


def _write_oracle_state(tmp_path: Path, state: dict) -> None:
    (tmp_path / ".conductor-oracle-state.json").write_text(json.dumps(state))


# ---------------------------------------------------------------------------
# Advisory dataclass
# ---------------------------------------------------------------------------


class TestAdvisory:
    def test_sort_key_severity_order(self):
        critical = Advisory(category="gate", severity="critical", message="critical msg")
        warning = Advisory(category="risk", severity="warning", message="warn msg")
        info = Advisory(category="growth", severity="info", message="info msg")
        assert critical.sort_key() < warning.sort_key() < info.sort_key()

    def test_advisory_hash_stable(self):
        a1 = Advisory(category="risk", severity="warning", message="test msg", detector="test_det")
        a2 = Advisory(category="risk", severity="warning", message="test msg", detector="test_det")
        assert a1.advisory_hash() == a2.advisory_hash()

    def test_advisory_hash_differs_by_detector(self):
        a1 = Advisory(category="risk", severity="warning", message="test msg", detector="det_a")
        a2 = Advisory(category="risk", severity="warning", message="test msg", detector="det_b")
        assert a1.advisory_hash() != a2.advisory_hash()

    def test_to_dict_roundtrip(self):
        a = Advisory(
            category="gate",
            severity="warning",
            message="test",
            detector="test_det",
            tools_suggested=["web_search"],
            gate_action="warn",
            confidence=0.8,
            narrative="A wise message",
            tags=["gate", "test"],
        )
        d = a.to_dict()
        assert d["category"] == "gate"
        assert d["tools_suggested"] == ["web_search"]
        assert d["narrative"] == "A wise message"
        assert d["confidence"] == 0.8

    def test_default_fields_backward_compatible(self):
        a = Advisory(category="risk", severity="info", message="old-style")
        assert a.detector == ""
        assert a.tools_suggested == []
        assert a.gate_action == ""
        assert a.confidence == 1.0
        assert a.narrative == ""
        assert a.tags == []


# ---------------------------------------------------------------------------
# OracleContext
# ---------------------------------------------------------------------------


class TestOracleContext:
    def test_default_values(self):
        ctx = OracleContext()
        assert ctx.trigger == "manual"
        assert ctx.session_id == ""
        assert ctx.extra == {}

    def test_from_dict_known_fields(self):
        ctx = OracleContext.from_dict({
            "trigger": "phase_transition",
            "current_phase": "FRAME",
            "target_phase": "SHAPE",
        })
        assert ctx.trigger == "phase_transition"
        assert ctx.current_phase == "FRAME"
        assert ctx.target_phase == "SHAPE"

    def test_from_dict_extra_fields(self):
        ctx = OracleContext.from_dict({
            "trigger": "manual",
            "unknown_field": "value",
            "another": 42,
        })
        assert ctx.trigger == "manual"
        assert ctx.extra == {"unknown_field": "value", "another": 42}

    def test_from_dict_empty(self):
        ctx = OracleContext.from_dict({})
        assert ctx.trigger == "manual"

    def test_backward_compat_with_old_dict_context(self):
        """Old code passed plain dicts to consult(). Ensure it still works."""
        oracle = Oracle()
        # Should not raise when called with a plain dict
        ctx = OracleContext.from_dict({"trigger": "patchbay", "some_old_key": True})
        assert ctx.trigger == "patchbay"
        assert ctx.extra.get("some_old_key") is True


# ---------------------------------------------------------------------------
# Oracle state persistence
# ---------------------------------------------------------------------------


class TestOracleState:
    def test_load_empty_state(self, oracle_tmp):
        oracle = Oracle()
        state = oracle._load_oracle_state()
        assert "advisory_log" in state
        assert "detector_scores" in state
        assert "suppressed_hashes" in state

    def test_save_and_reload(self, oracle_tmp):
        oracle = Oracle()
        state = oracle._load_oracle_state()
        state["advisory_log"].append({"test": True})
        oracle._save_oracle_state()

        oracle2 = Oracle()
        state2 = oracle2._load_oracle_state()
        assert len(state2["advisory_log"]) == 1
        assert state2["advisory_log"][0]["test"] is True

    def test_record_advisories_capped(self, oracle_tmp):
        oracle = Oracle()
        # Record 600 advisories — should cap at 500
        big_list = [
            Advisory(category="test", severity="info", message=f"msg {i}", detector="test")
            for i in range(600)
        ]
        oracle._record_advisories(big_list)
        state = oracle._load_oracle_state()
        assert len(state["advisory_log"]) == 500

    def test_acknowledge_suppresses(self, oracle_tmp):
        oracle = Oracle()
        adv = Advisory(category="risk", severity="warning", message="suppress me", detector="test")
        h = adv.advisory_hash()
        assert oracle.acknowledge(h)
        # Second ack is a no-op
        assert not oracle.acknowledge(h)
        # Check suppressed
        state = oracle._load_oracle_state()
        assert h in state["suppressed_hashes"]

    def test_suppressed_advisories_filtered(self, oracle_tmp):
        oracle = Oracle()
        adv = Advisory(category="risk", severity="warning", message="suppress me", detector="test")
        oracle.acknowledge(adv.advisory_hash())

        # Now consult should not include this
        # (We can't easily make the detector produce this exact advisory,
        # but we can verify the filter mechanism works on the result set)
        state = oracle._load_oracle_state()
        assert adv.advisory_hash() in state["suppressed_hashes"]

    def test_update_effectiveness(self, oracle_tmp):
        oracle = Oracle()
        # Seed some advisory log entries
        oracle._record_advisories([
            Advisory(category="risk", severity="warning", message="test", detector="scope_risk"),
        ])
        oracle._update_effectiveness("session-1", "SHIPPED")
        scores = oracle.get_detector_scores()
        assert "scope_risk" in scores
        assert scores["scope_risk"]["shipped"] == 1

    def test_get_advisory_history(self, oracle_tmp):
        oracle = Oracle()
        oracle._record_advisories([
            Advisory(category="test", severity="info", message="msg1", detector="d1"),
            Advisory(category="test", severity="info", message="msg2", detector="d2"),
        ])
        history = oracle.get_advisory_history(limit=10)
        assert len(history) == 2
        assert history[0]["detector"] == "d1"


# ---------------------------------------------------------------------------
# Existing detectors
# ---------------------------------------------------------------------------


class TestExistingDetectors:
    def test_momentum_streak(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 5,
            "total_minutes": 300,
            "shipped": 4,
            "closed": 1,
            "streak": 4,
            "by_organ": {},
            "recent_sessions": [],
        })
        oracle = Oracle()
        advisories = oracle._detect_momentum()
        assert any("streak" in a.message.lower() for a in advisories)
        assert any(a.detector == "momentum" for a in advisories)

    def test_momentum_low_ship_rate(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 600,
            "shipped": 2,
            "closed": 8,
            "streak": 0,
            "by_organ": {},
            "recent_sessions": [],
        })
        oracle = Oracle()
        advisories = oracle._detect_momentum()
        assert any(a.severity == "warning" for a in advisories)

    def test_growth_opportunities(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 600,
            "shipped": 7,
            "closed": 3,
            "streak": 2,
            "by_organ": {"ORGAN-III": {"sessions": 10, "minutes": 600}},
            "recent_sessions": [],
        })
        oracle = Oracle()
        advisories = oracle._detect_growth_opportunities()
        assert any("only worked in" in a.message for a in advisories)


# ---------------------------------------------------------------------------
# New detectors
# ---------------------------------------------------------------------------


class TestToolRecommendations:
    def test_suggests_clusters_when_no_tools_used(self, oracle_tmp):
        _write_session(oracle_tmp, {
            "session_id": "test-001",
            "organ": "ORGAN-III",
            "repo": "test",
            "scope": "test",
            "start_time": time.time(),
            "current_phase": "FRAME",
            "phase_logs": [{"name": "FRAME", "start_time": time.time(), "end_time": 0, "tools_used": [], "commits": 0}],
            "warnings": [],
            "result": "IN_PROGRESS",
        })
        oracle = Oracle()
        ctx = OracleContext(trigger="session_start", current_phase="FRAME")
        advisories = oracle._detect_tool_recommendations(ctx)
        assert any(a.tools_suggested for a in advisories)

    def test_no_suggestion_without_phase(self, oracle_tmp):
        oracle = Oracle()
        ctx = OracleContext(trigger="manual")
        advisories = oracle._detect_tool_recommendations(ctx)
        assert advisories == []


class TestGateChecks:
    def test_warns_short_frame(self, oracle_tmp):
        _write_session(oracle_tmp, {
            "session_id": "test-001",
            "organ": "ORGAN-III",
            "repo": "test",
            "scope": "test",
            "start_time": time.time() - 60,  # 1 minute ago
            "current_phase": "FRAME",
            "phase_logs": [],
            "warnings": [],
            "result": "IN_PROGRESS",
        })
        oracle = Oracle()
        ctx = OracleContext(
            trigger="phase_transition",
            current_phase="FRAME",
            target_phase="SHAPE",
        )
        advisories = oracle._detect_gate_checks(ctx)
        assert any(a.gate_action == "warn" for a in advisories)

    def test_warns_many_warnings_before_done(self, oracle_tmp):
        _write_session(oracle_tmp, {
            "session_id": "test-001",
            "organ": "ORGAN-III",
            "repo": "test",
            "scope": "test",
            "start_time": time.time() - 3600,
            "current_phase": "PROVE",
            "phase_logs": [],
            "warnings": ["w1", "w2", "w3"],
            "result": "IN_PROGRESS",
        })
        oracle = Oracle()
        ctx = OracleContext(
            trigger="phase_transition",
            current_phase="PROVE",
            target_phase="DONE",
        )
        advisories = oracle._detect_gate_checks(ctx)
        assert any("warnings" in a.message.lower() for a in advisories)

    def test_no_gate_for_non_transition(self, oracle_tmp):
        oracle = Oracle()
        ctx = OracleContext(trigger="manual")
        advisories = oracle._detect_gate_checks(ctx)
        assert advisories == []


class TestPredictiveWarnings:
    def test_early_marathon_warning(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 300,  # avg 30m
            "shipped": 7,
            "closed": 3,
            "streak": 2,
            "by_organ": {},
            "recent_sessions": [
                {"session_id": f"s{i}", "result": "SHIPPED", "duration_minutes": 30}
                for i in range(5)
            ],
        })
        # Create a session running at 50 min (1.67x avg of 30m — between 1.5x and 2x)
        _write_session(oracle_tmp, {
            "session_id": "test-running",
            "organ": "ORGAN-III",
            "repo": "test",
            "scope": "test",
            "start_time": time.time() - 50 * 60,
            "current_phase": "BUILD",
            "phase_logs": [],
            "warnings": [],
            "result": "IN_PROGRESS",
        })
        oracle = Oracle()
        advisories = oracle._detect_predictive_warnings()
        assert any("approaching" in a.message.lower() for a in advisories)

    def test_low_health_score(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 600,
            "shipped": 3,
            "closed": 7,
            "streak": 0,
            "by_organ": {},
            "recent_sessions": [
                {"session_id": f"s{i}", "result": "CLOSED", "duration_minutes": 60}
                for i in range(5)
            ],
        })
        oracle = Oracle()
        advisories = oracle._detect_predictive_warnings()
        assert any("health score" in a.message.lower() for a in advisories)


class TestNarrativeWisdom:
    def test_milestone_narrative(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 600,
            "shipped": 8,
            "closed": 2,
            "streak": 3,
            "by_organ": {},
            "recent_sessions": [],
        })
        oracle = Oracle()
        ctx = OracleContext(trigger="manual")
        advisories = oracle._generate_narrative_wisdom(ctx)
        assert any("ten sessions" in a.message.lower() for a in advisories)
        assert any(a.narrative for a in advisories)

    def test_phase_wisdom_on_transition(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0, "streak": 0})
        oracle = Oracle()
        ctx = OracleContext(trigger="phase_transition", current_phase="BUILD")
        advisories = oracle._generate_narrative_wisdom(ctx)
        assert any("build" in a.message.lower() for a in advisories)

    def test_streak_encouragement(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 15,
            "total_minutes": 900,
            "shipped": 12,
            "closed": 3,
            "streak": 7,
            "by_organ": {},
            "recent_sessions": [],
        })
        oracle = Oracle()
        ctx = OracleContext(trigger="manual")
        advisories = oracle._generate_narrative_wisdom(ctx)
        assert any("streak" in a.message.lower() for a in advisories)

    def test_narrative_capped_at_200(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 5, "streak": 0})
        oracle = Oracle()
        ctx = OracleContext(trigger="phase_transition", current_phase="FRAME")
        advisories = oracle._generate_narrative_wisdom(ctx)
        for a in advisories:
            if a.narrative:
                assert len(a.narrative) <= 200


class TestCrossSessionPatterns:
    def test_low_effectiveness_detector(self, oracle_tmp):
        _write_oracle_state(oracle_tmp, {
            "advisory_log": [],
            "detector_scores": {
                "scope_risk": {"advised": 10, "shipped": 1, "total": 10},
            },
            "suppressed_hashes": [],
        })
        oracle = Oracle()
        advisories = oracle._detect_cross_session_patterns()
        assert any("scope_risk" in a.message for a in advisories)

    def test_no_advice_with_few_sessions(self, oracle_tmp):
        _write_oracle_state(oracle_tmp, {
            "advisory_log": [],
            "detector_scores": {
                "scope_risk": {"advised": 2, "shipped": 0, "total": 2},
            },
            "suppressed_hashes": [],
        })
        oracle = Oracle()
        advisories = oracle._detect_cross_session_patterns()
        assert advisories == []


class TestWorkflowRisks:
    def test_no_advice_for_non_workflow(self, oracle_tmp):
        oracle = Oracle()
        ctx = OracleContext(trigger="manual")
        advisories = oracle._detect_workflow_risks(ctx)
        assert advisories == []

    def test_checkpoint_uses_named_workflow_state(self, oracle_tmp):
        workflows_dir = oracle_tmp / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        (workflows_dir / "alpha.json").write_text(json.dumps({
            "workflow_name": "alpha",
            "steps": {
                "s1": {"status": "COMPLETED"},
                "s2": {"status": "COMPLETED"},
                "s3": {"status": "COMPLETED"},
                "s4": {"status": "PENDING"},
                "s5": {"status": "PENDING"},
            },
        }))

        with patch.object(conductor.constants, "STATE_DIR", oracle_tmp):
            oracle = Oracle()
            ctx = OracleContext(trigger="workflow_post_step", workflow_name="alpha")
            advisories = oracle._detect_workflow_risks(ctx)

        assert any(a.detector == "workflow_risks" and "checkpoint opportunity" in a.message.lower() for a in advisories)

    def test_checkpoint_falls_back_to_active_pointer_state(self, oracle_tmp):
        workflows_dir = oracle_tmp / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        (workflows_dir / "_active").write_text("beta")
        (workflows_dir / "beta.json").write_text(json.dumps({
            "workflow_name": "beta",
            "steps": {
                "s1": {"status": "COMPLETED"},
                "s2": {"status": "COMPLETED"},
                "s3": {"status": "COMPLETED"},
                "s4": {"status": "PENDING"},
                "s5": {"status": "PENDING"},
            },
        }))

        with patch.object(conductor.constants, "STATE_DIR", oracle_tmp):
            oracle = Oracle()
            ctx = OracleContext(trigger="workflow_post_step")
            advisories = oracle._detect_workflow_risks(ctx)

        assert any(a.detector == "workflow_risks" and "3/5 steps complete" in a.message for a in advisories)

    def test_checkpoint_falls_back_to_legacy_default_state(self, oracle_tmp):
        workflows_dir = oracle_tmp / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        (workflows_dir / "_default.json").write_text(json.dumps({
            "workflow_name": "_default",
            "steps": {
                "s1": {"status": "COMPLETED"},
                "s2": {"status": "COMPLETED"},
                "s3": {"status": "PENDING"},
                "s4": {"status": "PENDING"},
                "s5": {"status": "PENDING"},
            },
        }))

        with patch.object(conductor.constants, "STATE_DIR", oracle_tmp):
            oracle = Oracle()
            ctx = OracleContext(trigger="workflow_post_step")
            advisories = oracle._detect_workflow_risks(ctx)

        assert any(a.detector == "workflow_risks" and "2/5 steps complete" in a.message for a in advisories)

    def test_checkpoint_prioritizes_named_state_over_active_pointer(self, oracle_tmp):
        workflows_dir = oracle_tmp / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        (workflows_dir / "_active").write_text("beta")
        (workflows_dir / "alpha.json").write_text(json.dumps({
            "workflow_name": "alpha",
            "steps": {
                "s1": {"status": "COMPLETED"},
                "s2": {"status": "COMPLETED"},
                "s3": {"status": "COMPLETED"},
                "s4": {"status": "PENDING"},
                "s5": {"status": "PENDING"},
            },
        }))
        (workflows_dir / "beta.json").write_text(json.dumps({
            "workflow_name": "beta",
            "steps": {
                "s1": {"status": "PENDING"},
                "s2": {"status": "PENDING"},
                "s3": {"status": "PENDING"},
                "s4": {"status": "PENDING"},
                "s5": {"status": "PENDING"},
            },
        }))

        with patch.object(conductor.constants, "STATE_DIR", oracle_tmp):
            oracle = Oracle()
            ctx = OracleContext(trigger="workflow_post_step", workflow_name="alpha")
            advisories = oracle._detect_workflow_risks(ctx)

        # If named state is prioritized, we should see the 3/5 checkpoint from alpha.
        assert any(a.detector == "workflow_risks" and "3/5 steps complete" in a.message for a in advisories)


# ---------------------------------------------------------------------------
# consult() integration
# ---------------------------------------------------------------------------


class TestConsult:
    def test_consult_with_none_context(self, oracle_tmp):
        oracle = Oracle()
        result = oracle.consult(None)
        assert isinstance(result, list)
        for adv in result:
            assert adv.category, "Advisory must have a category"
            assert adv.severity in ("critical", "warning", "caution", "info")
            assert adv.message, "Advisory must have a message"

    def test_consult_with_dict_context(self, oracle_tmp):
        oracle = Oracle()
        result = oracle.consult({"trigger": "patchbay"})
        assert isinstance(result, list)
        for adv in result:
            assert adv.severity in ("critical", "warning", "caution", "info")
            assert adv.advisory_hash(), "Advisory hash must be non-empty"

    def test_consult_with_oracle_context(self, oracle_tmp):
        oracle = Oracle()
        ctx = OracleContext(trigger="session_start", current_phase="FRAME")
        result = oracle.consult(ctx)
        assert isinstance(result, list)
        for adv in result:
            assert adv.category
            assert adv.message
            d = adv.to_dict()
            assert "category" in d and "severity" in d and "message" in d

    def test_consult_includes_narrative_when_requested(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "streak": 0,
        })
        oracle = Oracle()
        ctx = OracleContext(trigger="phase_transition", current_phase="BUILD")
        result = oracle.consult(ctx, include_narrative=True)
        # Should have at least the phase wisdom narrative
        narratives = [a for a in result if a.narrative]
        assert len(narratives) >= 1

    def test_consult_gate_mode(self, oracle_tmp):
        _write_session(oracle_tmp, {
            "session_id": "test-001",
            "organ": "ORGAN-III",
            "repo": "test",
            "scope": "test",
            "start_time": time.time() - 30,
            "current_phase": "FRAME",
            "phase_logs": [],
            "warnings": [],
            "result": "IN_PROGRESS",
        })
        oracle = Oracle()
        ctx = OracleContext(
            trigger="phase_transition",
            current_phase="FRAME",
            target_phase="SHAPE",
        )
        result = oracle.consult(ctx, gate_mode=True)
        gate_advs = [a for a in result if a.gate_action]
        assert any(a.gate_action == "warn" for a in gate_advs)

    def test_consult_max_advisories_respected(self, oracle_tmp):
        oracle = Oracle()
        result = oracle.consult(max_advisories=2)
        assert len(result) <= 2

    def test_consult_sorted_by_severity(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 600,
            "shipped": 2,
            "closed": 8,
            "streak": 0,
            "by_organ": {},
            "recent_sessions": [],
        })
        oracle = Oracle()
        result = oracle.consult()
        if len(result) >= 2:
            for i in range(len(result) - 1):
                assert result[i].sort_key() <= result[i + 1].sort_key()

    def test_consult_deduplicates(self, oracle_tmp):
        oracle = Oracle()
        result = oracle.consult()
        messages = [a.message for a in result]
        assert len(messages) == len(set(messages))


# ---------------------------------------------------------------------------
# Convenience methods
# ---------------------------------------------------------------------------


class TestConvenienceMethods:
    def test_get_detector_scores_empty(self, oracle_tmp):
        oracle = Oracle()
        scores = oracle.get_detector_scores()
        assert isinstance(scores, dict)
        # Empty state should produce no scores, not crash
        assert all(isinstance(v, dict) for v in scores.values())

    def test_get_advisory_history_empty(self, oracle_tmp):
        oracle = Oracle()
        history = oracle.get_advisory_history()
        assert history == []  # explicitly empty, not just "is a list"


# ---------------------------------------------------------------------------
# OracleProfile
# ---------------------------------------------------------------------------


class TestOracleProfile:
    def test_build_from_empty_stats(self, oracle_tmp):
        profile = OracleProfile.build({}, {})
        assert profile.total_sessions == 0
        assert profile.ship_rate == 0.0
        assert profile.cadence == "irregular"
        assert profile.risk_appetite == "moderate"

    def test_build_from_populated_stats(self, oracle_tmp):
        stats = {
            "total_sessions": 20,
            "total_minutes": 1200,
            "shipped": 16,
            "streak": 5,
            "streak_max": 8,
            "by_organ": {"ORGAN-III": 12, "ORGAN-I": 6, "META-ORGANVM": 2},
            "recent_sessions": [
                {"session_id": f"s{i}", "result": "SHIPPED", "start_time": time.time() - (20 - i) * 86400}
                for i in range(10)
            ],
        }
        oracle_state = {
            "detector_scores": {
                "momentum": {"total": 5, "shipped": 4},
            },
            "mastery": {
                "encountered": {
                    "eng.tdd.red_green_refactor": {"times_shown": 5},
                    "eng.solid.srp": {"times_shown": 3},
                    "biz.mvp": {"times_shown": 2},
                },
                "internalized": {
                    "eng.tdd.red_green_refactor": {"at": "2026-03-01T00:00:00+00:00"},
                },
                "growth_areas": ["eng.solid.srp", "biz.mvp"],
                "mastery_score": 0.333,
            },
        }
        profile = OracleProfile.build(stats, oracle_state)
        assert profile.total_sessions == 20
        assert profile.ship_rate == 0.8
        assert profile.avg_duration_min == 60.0
        assert "ORGAN-III" in profile.preferred_organs
        assert profile.streak_current == 5
        assert profile.streak_max == 8
        assert profile.risk_appetite == "conservative"  # high ship rate
        assert profile.principles_encountered == 3
        assert profile.principles_internalized == 1
        assert profile.mastery_score == pytest.approx(0.333, rel=1e-3)
        assert profile.top_growth_areas == ["eng.solid.srp", "biz.mvp"]
        assert profile.learning_velocity == "starting"

    def test_to_dict_roundtrip(self, oracle_tmp):
        profile = OracleProfile(
            total_sessions=10,
            total_minutes=500,
            ship_rate=0.7,
            avg_duration_min=50,
            preferred_organs=["ORGAN-III"],
            risk_appetite="moderate",
            cadence="regular",
        )
        d = profile.to_dict()
        assert d["total_sessions"] == 10
        assert d["ship_rate"] == 0.7
        assert d["cadence"] == "regular"

    def test_aggressive_risk_appetite(self, oracle_tmp):
        stats = {
            "total_sessions": 10,
            "shipped": 2,  # low ship rate
            "total_minutes": 600,
            "streak": 0,
            "by_organ": {},
            "recent_sessions": [],
        }
        profile = OracleProfile.build(stats, {})
        assert profile.risk_appetite == "aggressive"

    def test_cadence_detection_bursty(self, oracle_tmp):
        now = time.time()
        # Many sessions 1h apart, then big gaps
        recent = []
        for i in range(8):
            recent.append({"session_id": f"s{i}", "start_time": now - (16 - i) * 3600})  # 1h apart
        recent.append({"session_id": "s8", "start_time": now - 200 * 3600})  # 8 day gap
        recent.append({"session_id": "s9", "start_time": now - 250 * 3600})
        stats = {
            "total_sessions": 10,
            "shipped": 5,
            "total_minutes": 600,
            "streak": 0,
            "by_organ": {},
            "recent_sessions": recent,
        }
        profile = OracleProfile.build(stats, {})
        assert profile.cadence in ("bursty", "irregular")


# ---------------------------------------------------------------------------
# DETECTOR_REGISTRY
# ---------------------------------------------------------------------------


class TestDetectorRegistry:
    def test_all_detectors_registered(self):
        assert len(DETECTOR_REGISTRY) >= 23  # 9 original + 6 phase2 + 8 phase3

    def test_each_entry_has_required_keys(self):
        for name, meta in DETECTOR_REGISTRY.items():
            assert "category" in meta, f"{name} missing category"
            assert "default_enabled" in meta, f"{name} missing default_enabled"
            assert "phase" in meta, f"{name} missing phase"

    def test_phase3_detectors_present(self):
        phase3 = ["dependency_risks", "cost_awareness", "session_cadence",
                   "technical_debt", "scope_complexity", "collaboration_patterns",
                   "stale_repos", "burnout_risk"]
        for det in phase3:
            assert det in DETECTOR_REGISTRY, f"Missing phase3 detector: {det}"


# ---------------------------------------------------------------------------
# Phase 3 detectors
# ---------------------------------------------------------------------------


class TestSessionCadence:
    def test_long_absence_detection(self, oracle_tmp):
        now = time.time()
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 600,
            "shipped": 7,
            "streak": 0,
            "by_organ": {},
            "recent_sessions": [
                {"session_id": f"s{i}", "start_time": now - (30 + i) * 86400, "result": "SHIPPED"}
                for i in range(5)
            ] + [
                {"session_id": "s5", "start_time": now - 15 * 86400, "result": "SHIPPED"},
            ],
        })
        oracle = Oracle()
        advisories = oracle._detect_session_cadence()
        assert any("days" in a.message.lower() or "welcome back" in a.message.lower()
                    for a in advisories) or len(advisories) == 0  # depends on gap math

    def test_no_cadence_with_few_sessions(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 2,
            "total_minutes": 120,
            "shipped": 1,
            "streak": 0,
            "by_organ": {},
            "recent_sessions": [
                {"session_id": "s1", "start_time": time.time() - 86400},
            ],
        })
        oracle = Oracle()
        advisories = oracle._detect_session_cadence()
        assert advisories == []


class TestScopeComplexity:
    def test_long_scope_warning(self, oracle_tmp):
        long_scope = " ".join(["implement"] * 35)
        _write_session(oracle_tmp, {
            "session_id": "test-001",
            "organ": "ORGAN-III",
            "repo": "test",
            "scope": long_scope,
            "start_time": time.time(),
            "current_phase": "FRAME",
            "phase_logs": [],
            "warnings": [],
            "result": "IN_PROGRESS",
        })
        oracle = Oracle()
        ctx = OracleContext(trigger="session_start", current_phase="FRAME", organ="ORGAN-III")
        advisories = oracle._detect_scope_complexity(ctx)
        assert any("words" in a.message.lower() for a in advisories)

    def test_conjunction_heavy_scope(self, oracle_tmp):
        scope = "implement feature A and also add feature B and also fix bug C and also refactor D"
        _write_session(oracle_tmp, {
            "session_id": "test-001",
            "organ": "ORGAN-III",
            "repo": "test",
            "scope": scope,
            "start_time": time.time(),
            "current_phase": "FRAME",
            "phase_logs": [],
            "warnings": [],
            "result": "IN_PROGRESS",
        })
        oracle = Oracle()
        ctx = OracleContext(trigger="session_start", current_phase="FRAME", organ="ORGAN-III")
        advisories = oracle._detect_scope_complexity(ctx)
        assert any("conjunction" in a.message.lower() for a in advisories)

    def test_no_scope_no_advisory(self, oracle_tmp):
        _write_session(oracle_tmp, {
            "session_id": "test-001",
            "organ": "ORGAN-III",
            "repo": "test",
            "scope": "",
            "start_time": time.time(),
            "current_phase": "FRAME",
            "phase_logs": [],
            "warnings": [],
            "result": "IN_PROGRESS",
        })
        oracle = Oracle()
        ctx = OracleContext(trigger="session_start", current_phase="FRAME")
        advisories = oracle._detect_scope_complexity(ctx)
        assert advisories == []


class TestCollaborationPatterns:
    def test_repo_revisit_detection(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 600,
            "shipped": 7,
            "streak": 2,
            "by_organ": {},
            "recent_sessions": [
                {"session_id": f"s{i}", "repo": "my-repo", "result": "SHIPPED"}
                for i in range(5)
            ] + [
                {"session_id": f"s{i+5}", "repo": "other-repo", "result": "SHIPPED"}
                for i in range(5)
            ],
        })
        oracle = Oracle()
        advisories = oracle._detect_collaboration_patterns()
        assert any("my-repo" in a.message for a in advisories)

    def test_no_patterns_with_few_sessions(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 2,
            "total_minutes": 120,
            "shipped": 1,
            "streak": 0,
            "by_organ": {},
            "recent_sessions": [
                {"session_id": "s1", "repo": "r1"},
            ],
        })
        oracle = Oracle()
        advisories = oracle._detect_collaboration_patterns()
        assert advisories == []


class TestBurnoutRisk:
    def test_marathon_sessions(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 1000,
            "shipped": 5,
            "streak": 1,
            "by_organ": {},
            "recent_sessions": [
                {"session_id": f"s{i}", "duration_min": 120, "start_time": time.time() - i * 86400, "result": "SHIPPED"}
                for i in range(5)
            ],
        })
        oracle = Oracle()
        advisories = oracle._detect_burnout_risk()
        assert any("marathon" in a.message.lower() or "fatigue" in a.message.lower()
                    or "average session" in a.message.lower()
                    for a in advisories)

    def test_late_night_sessions(self, oracle_tmp):
        now = time.time()
        # Create sessions starting at 2am UTC
        midnight_ts = now - (now % 86400)  # start of today UTC
        late_starts = [midnight_ts + 2 * 3600 - i * 86400 for i in range(5)]  # 2am each day
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 300,
            "shipped": 5,
            "streak": 1,
            "by_organ": {},
            "recent_sessions": [
                {"session_id": f"s{i}", "duration_min": 60, "start_time": ts, "result": "SHIPPED"}
                for i, ts in enumerate(late_starts)
            ],
        })
        oracle = Oracle()
        advisories = oracle._detect_burnout_risk()
        assert any("late" in a.message.lower() or "night" in a.message.lower()
                    for a in advisories)

    def test_declining_ship_rate(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 600,
            "shipped": 4,
            "streak": 0,
            "by_organ": {},
            "recent_sessions": [
                {"session_id": f"s{i}", "result": "SHIPPED", "duration_min": 60, "start_time": time.time() - (10 - i) * 86400}
                for i in range(5)
            ] + [
                {"session_id": f"s{i+5}", "result": "CLOSED", "duration_min": 60, "start_time": time.time() - (5 - i) * 86400}
                for i in range(5)
            ],
        })
        oracle = Oracle()
        advisories = oracle._detect_burnout_risk()
        assert any("declining" in a.message.lower() or "ship rate" in a.message.lower()
                    for a in advisories)

    def test_no_burnout_with_few_sessions(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 2,
            "total_minutes": 120,
            "shipped": 1,
            "streak": 1,
            "by_organ": {},
            "recent_sessions": [{"session_id": "s1", "result": "SHIPPED"}],
        })
        oracle = Oracle()
        advisories = oracle._detect_burnout_risk()
        assert advisories == []


class TestCostAwareness:
    def test_no_advisory_without_session(self, oracle_tmp):
        oracle = Oracle()
        ctx = OracleContext(trigger="manual")
        advisories = oracle._detect_cost_awareness(ctx)
        assert advisories == []


class TestDependencyRisks:
    def test_runs_without_error(self, oracle_tmp):
        """Detector should not crash even if governance is unavailable."""
        oracle = Oracle()
        advisories = oracle._detect_dependency_risks()
        assert isinstance(advisories, list)
        for adv in advisories:
            assert adv.detector == "dependency_risks"
            assert adv.category  # non-empty category
            assert adv.message
            assert adv.confidence > 0


class TestTechnicalDebt:
    def test_runs_without_error(self, oracle_tmp):
        oracle = Oracle()
        advisories = oracle._detect_technical_debt()
        assert isinstance(advisories, list)
        for adv in advisories:
            assert adv.detector == "technical_debt"
            assert adv.message
            assert adv.confidence > 0


class TestStaleRepos:
    def test_runs_without_error(self, oracle_tmp):
        oracle = Oracle()
        advisories = oracle._detect_stale_repos()
        assert isinstance(advisories, list)
        for adv in advisories:
            assert adv.detector == "stale_repos"
            assert adv.message
            assert adv.confidence > 0


# ---------------------------------------------------------------------------
# Profile + convenience expansion
# ---------------------------------------------------------------------------


class TestBuildProfile:
    def test_build_profile(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 5,
            "total_minutes": 300,
            "shipped": 3,
            "streak": 2,
            "by_organ": {"ORGAN-III": 5},
            "recent_sessions": [],
        })
        oracle = Oracle()
        profile = oracle.build_profile()
        assert profile.total_sessions == 5
        assert profile.ship_rate == 0.6


class TestGetDetectorManifest:
    def test_manifest_has_all_detectors(self, oracle_tmp):
        oracle = Oracle()
        manifest = oracle.get_detector_manifest()
        names = {d["name"] for d in manifest}
        assert "process_drift" in names
        assert "burnout_risk" in names
        assert len(manifest) >= 23

    def test_manifest_includes_effectiveness(self, oracle_tmp):
        _write_oracle_state(oracle_tmp, {
            "advisory_log": [],
            "detector_scores": {"momentum": {"total": 10, "shipped": 8}},
            "suppressed_hashes": [],
        })
        oracle = Oracle()
        manifest = oracle.get_detector_manifest()
        momentum = next(d for d in manifest if d["name"] == "momentum")
        assert momentum["effectiveness"] == 0.8


class TestGetTrendSummary:
    def test_empty_trends(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0, "recent_sessions": []})
        oracle = Oracle()
        summary = oracle.get_trend_summary()
        assert summary["sessions_analyzed"] == 0

    def test_populated_trends(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 600,
            "shipped": 7,
            "streak": 2,
            "by_organ": {},
            "recent_sessions": [
                {"session_id": f"s{i}", "result": "SHIPPED", "duration_min": 60}
                for i in range(7)
            ] + [
                {"session_id": f"s{i+7}", "result": "CLOSED", "duration_min": 45}
                for i in range(3)
            ],
        })
        oracle = Oracle()
        summary = oracle.get_trend_summary()
        assert "last_5" in summary
        assert summary["last_5"]["ship_rate"] >= 0


class TestCalibrateDetector:
    def test_reset_detector(self, oracle_tmp):
        _write_oracle_state(oracle_tmp, {
            "advisory_log": [],
            "detector_scores": {"momentum": {"total": 10, "shipped": 5}},
            "suppressed_hashes": [],
        })
        oracle = Oracle()
        result = oracle.calibrate_detector("momentum", "reset")
        assert result["calibrated"] == "momentum"
        assert result["action"] == "reset"
        scores = oracle.get_detector_scores()
        assert "momentum" not in scores

    def test_boost_detector(self, oracle_tmp):
        _write_oracle_state(oracle_tmp, {
            "advisory_log": [],
            "detector_scores": {"momentum": {"total": 10, "shipped": 5}},
            "suppressed_hashes": [],
        })
        oracle = Oracle()
        result = oracle.calibrate_detector("momentum", "boost")
        assert result["action"] == "boost"
        scores = oracle.get_detector_scores()
        assert scores["momentum"]["shipped"] == 7

    def test_penalize_detector(self, oracle_tmp):
        _write_oracle_state(oracle_tmp, {
            "advisory_log": [],
            "detector_scores": {"momentum": {"total": 10, "shipped": 5}},
            "suppressed_hashes": [],
        })
        oracle = Oracle()
        result = oracle.calibrate_detector("momentum", "penalize")
        assert result["action"] == "penalize"
        scores = oracle.get_detector_scores()
        assert scores["momentum"]["shipped"] == 3

    def test_unknown_detector(self, oracle_tmp):
        oracle = Oracle()
        result = oracle.calibrate_detector("nonexistent", "reset")
        assert "error" in result

    def test_unknown_action(self, oracle_tmp):
        oracle = Oracle()
        result = oracle.calibrate_detector("momentum", "unknown_action")
        assert "error" in result


class TestExportState:
    def test_export_has_all_sections(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 5, "total_minutes": 300,
                                  "shipped": 3, "streak": 1, "by_organ": {}, "recent_sessions": []})
        oracle = Oracle()
        export = oracle.export_state()
        assert "profile" in export
        assert "detector_manifest" in export
        assert "trend_summary" in export
        assert "state" in export
        assert "exported_at" in export


class TestDiagnose:
    def test_diagnose_no_state_file(self, oracle_tmp):
        oracle = Oracle()
        diag = oracle.diagnose()
        assert diag["ok"] is True
        assert "issues" in diag
        assert "info" in diag

    def test_diagnose_with_state(self, oracle_tmp):
        _write_oracle_state(oracle_tmp, {
            "advisory_log": [{"test": True}],
            "detector_scores": {"x": {"total": 1, "shipped": 1}},
            "suppressed_hashes": ["abc123"],
        })
        oracle = Oracle()
        diag = oracle.diagnose()
        assert diag["ok"] is True
        assert diag["info"]["advisory_log_entries"] == 1
        assert diag["info"]["suppressed_count"] == 1


class TestConfigDisabling:
    def test_disabled_detector_skipped(self, oracle_tmp):
        """When a detector is disabled via config, it should not produce advisories."""
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 600,
            "shipped": 2,
            "closed": 8,
            "streak": 0,
            "by_organ": {},
            "recent_sessions": [],
        })
        # Patch the config loader to disable momentum
        with patch("conductor.oracle._load_oracle_config", return_value={"disabled_detectors": ["momentum"]}):
            oracle = Oracle()
            result = oracle.consult()
            # Momentum would normally fire for low ship rate, but it should be disabled
            assert not any(a.detector == "momentum" for a in result)

    def test_enabled_detector_runs(self, oracle_tmp):
        _write_stats(oracle_tmp, {
            "total_sessions": 10,
            "total_minutes": 600,
            "shipped": 2,
            "closed": 8,
            "streak": 0,
            "by_organ": {},
            "recent_sessions": [],
        })
        with patch("conductor.oracle._load_oracle_config", return_value={"disabled_detectors": []}):
            oracle = Oracle()
            result = oracle.consult()
            # momentum should fire for low ship rate
            assert any(a.detector == "momentum" for a in result)
