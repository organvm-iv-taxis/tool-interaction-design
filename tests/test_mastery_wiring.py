"""Tests for conductor internal wiring fixes — mastery dedup, phase propagation, internalization."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import conductor.constants
import conductor.oracle
from conductor.oracle import Oracle
from conductor.session import _update_stats


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def oracle_tmp(tmp_path):
    """Patch Oracle-relevant paths to temp directory."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    state_file = tmp_path / "oracle-state.json"
    stats_file = tmp_path / "stats.json"
    session_state = tmp_path / "session.json"
    pattern_file = tmp_path / "pattern-history.jsonl"

    with (
        patch.object(conductor.constants, "SESSIONS_DIR", sessions),
        patch.object(conductor.constants, "STATS_FILE", stats_file),
        patch.object(conductor.constants, "SESSION_STATE_FILE", session_state),
        patch.object(conductor.constants, "ORACLE_STATE_FILE", state_file),
        patch.object(conductor.constants, "PATTERN_HISTORY_FILE", pattern_file),
        patch.object(conductor.oracle, "SESSIONS_DIR", sessions),
        patch.object(conductor.oracle, "STATS_FILE", stats_file),
        patch.object(conductor.oracle, "ORACLE_STATE_FILE", state_file),
        patch.object(conductor.oracle, "SESSION_STATE_FILE", session_state),
    ):
        yield tmp_path


# ---------------------------------------------------------------------------
# Fix 1: Per-session deduplication of wisdom encounters
# ---------------------------------------------------------------------------


class TestWisdomDedup:
    """_record_wisdom_shown should only increment once per session."""

    def test_first_encounter_increments(self, oracle_tmp):
        oracle = Oracle()
        oracle._record_wisdom_shown("biz.ship_speed")
        mastery = oracle._load_mastery()
        assert mastery["encountered"]["biz.ship_speed"]["times_shown"] == 1

    def test_same_session_does_not_increment(self, oracle_tmp):
        """With an active session, repeated calls should NOT increment."""
        session_state = oracle_tmp / "session.json"
        session_state.write_text(json.dumps({"session_id": "test-session-001"}))

        oracle = Oracle()
        oracle._record_wisdom_shown("biz.ship_speed")
        oracle._record_wisdom_shown("biz.ship_speed")
        oracle._record_wisdom_shown("biz.ship_speed")

        mastery = oracle._load_mastery()
        assert mastery["encountered"]["biz.ship_speed"]["times_shown"] == 1
        assert mastery["encountered"]["biz.ship_speed"]["last_session"] == "test-session-001"

    def test_different_session_increments(self, oracle_tmp):
        """A new session should increment the counter."""
        session_state = oracle_tmp / "session.json"

        # Session 1
        session_state.write_text(json.dumps({"session_id": "session-001"}))
        oracle = Oracle()
        oracle._record_wisdom_shown("biz.ship_speed")

        # Session 2
        session_state.write_text(json.dumps({"session_id": "session-002"}))
        oracle._oracle_state = None  # force reload
        oracle._record_wisdom_shown("biz.ship_speed")

        mastery = oracle._load_mastery()
        assert mastery["encountered"]["biz.ship_speed"]["times_shown"] == 2
        assert mastery["encountered"]["biz.ship_speed"]["last_session"] == "session-002"

    def test_no_active_session_still_increments(self, oracle_tmp):
        """Without an active session, each call increments (backward compat)."""
        oracle = Oracle()
        oracle._record_wisdom_shown("biz.mvp")
        oracle._oracle_state = None
        oracle._record_wisdom_shown("biz.mvp")

        mastery = oracle._load_mastery()
        assert mastery["encountered"]["biz.mvp"]["times_shown"] == 2

    def test_current_session_id_reads_state_file(self, oracle_tmp):
        """_current_session_id should read from SESSION_STATE_FILE."""
        session_state = oracle_tmp / "session.json"
        session_state.write_text(json.dumps({"session_id": "abc-123"}))
        oracle = Oracle()
        assert oracle._current_session_id() == "abc-123"

    def test_current_session_id_missing_file(self, oracle_tmp):
        """_current_session_id returns '' when no session file."""
        oracle = Oracle()
        assert oracle._current_session_id() == ""


# ---------------------------------------------------------------------------
# Fix 3: Phase data in stats
# ---------------------------------------------------------------------------


class TestPhaseDataInStats:
    """_update_stats should include phase durations in recent_sessions."""

    def test_phases_included_in_recent(self, oracle_tmp):
        stats_file = oracle_tmp / "stats.json"
        with patch.object(conductor.constants, "STATS_FILE", stats_file), \
             patch("conductor.session.STATS_FILE", stats_file):
            session_log = {
                "session_id": "test-001",
                "result": "SHIPPED",
                "organ": "META-ORGANVM",
                "duration_minutes": 30,
                "phases": {
                    "FRAME": {"duration": 5, "visits": 1},
                    "SHAPE": {"duration": 3, "visits": 1},
                    "BUILD": {"duration": 15, "visits": 1},
                    "PROVE": {"duration": 7, "visits": 1},
                },
            }
            stats = _update_stats(session_log)
            recent = stats["recent_sessions"][-1]
            assert "phases" in recent
            assert recent["phases"]["FRAME"] == 5
            assert recent["phases"]["BUILD"] == 15

    def test_phases_empty_when_no_phase_data(self, oracle_tmp):
        stats_file = oracle_tmp / "stats.json"
        with patch.object(conductor.constants, "STATS_FILE", stats_file), \
             patch("conductor.session.STATS_FILE", stats_file):
            session_log = {
                "session_id": "test-002",
                "result": "CLOSED",
                "organ": "ORGAN-I",
                "duration_minutes": 10,
            }
            stats = _update_stats(session_log)
            recent = stats["recent_sessions"][-1]
            assert recent["phases"] == {}

    def test_phases_skips_non_dict_entries(self, oracle_tmp):
        stats_file = oracle_tmp / "stats.json"
        with patch.object(conductor.constants, "STATS_FILE", stats_file), \
             patch("conductor.session.STATS_FILE", stats_file):
            session_log = {
                "session_id": "test-003",
                "result": "SHIPPED",
                "organ": "META-ORGANVM",
                "duration_minutes": 20,
                "phases": {
                    "FRAME": {"duration": 10},
                    "invalid": "not a dict",
                },
            }
            stats = _update_stats(session_log)
            recent = stats["recent_sessions"][-1]
            assert "FRAME" in recent["phases"]
            assert "invalid" not in recent["phases"]


# ---------------------------------------------------------------------------
# Fix 4: Mark internalized via Oracle
# ---------------------------------------------------------------------------


class TestMarkInternalized:
    """Oracle._mark_internalized should close the mastery loop."""

    def test_internalize_updates_score(self, oracle_tmp):
        oracle = Oracle()
        # First encounter it
        oracle._record_wisdom_shown("biz.ship_speed")
        oracle._record_wisdom_shown("biz.mvp")

        # Internalize one
        oracle._mark_internalized("biz.ship_speed", evidence="Consistently ships within appetite")

        mastery = oracle._load_mastery()
        assert "biz.ship_speed" in mastery["internalized"]
        assert mastery["internalized"]["biz.ship_speed"]["evidence"] == "Consistently ships within appetite"
        assert mastery["mastery_score"] == 0.5  # 1 of 2

    def test_internalize_removes_from_growth_areas(self, oracle_tmp):
        oracle = Oracle()
        oracle._record_wisdom_shown("biz.focus")

        # Manually add to growth areas
        mastery = oracle._load_mastery()
        mastery["growth_areas"] = ["biz.focus"]
        oracle._save_mastery(mastery)

        oracle._mark_internalized("biz.focus")

        mastery = oracle._load_mastery()
        assert "biz.focus" not in mastery.get("growth_areas", [])

    def test_mastery_report_reflects_internalization(self, oracle_tmp):
        oracle = Oracle()
        oracle._record_wisdom_shown("practice.tdd")
        oracle._mark_internalized("practice.tdd", evidence="Always writes tests first")

        report = oracle.get_mastery_report()
        assert report["principles_internalized"] == 1
        assert report["mastery_score"] == 1.0
