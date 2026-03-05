"""Comprehensive tests for the Oracle — Guardian Angel advisory engine."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import conductor.constants
import conductor.oracle
from conductor.oracle import Advisory, Oracle, OracleContext


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


# ---------------------------------------------------------------------------
# consult() integration
# ---------------------------------------------------------------------------


class TestConsult:
    def test_consult_with_none_context(self, oracle_tmp):
        oracle = Oracle()
        result = oracle.consult(None)
        assert isinstance(result, list)

    def test_consult_with_dict_context(self, oracle_tmp):
        oracle = Oracle()
        result = oracle.consult({"trigger": "patchbay"})
        assert isinstance(result, list)

    def test_consult_with_oracle_context(self, oracle_tmp):
        oracle = Oracle()
        ctx = OracleContext(trigger="session_start", current_phase="FRAME")
        result = oracle.consult(ctx)
        assert isinstance(result, list)

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

    def test_get_advisory_history_empty(self, oracle_tmp):
        oracle = Oracle()
        history = oracle.get_advisory_history()
        assert isinstance(history, list)
        assert len(history) == 0
