"""Tests for preflight dispatch guidance and pending verification detection."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestDispatchGuidance:
    def test_dispatch_guidance_returns_tuple(self):
        from conductor.preflight import _get_dispatch_guidance

        wt, agent, msg = _get_dispatch_guidance("scaffold CRUD endpoints", "BUILD")
        assert wt == "boilerplate_generation"
        # Should recommend a non-Claude agent or None
        # (depends on fleet.yaml state, but work_type should be classified)

    def test_dispatch_guidance_architecture_stays_claude(self):
        from conductor.preflight import _get_dispatch_guidance

        wt, agent, msg = _get_dispatch_guidance("design the API contract and module boundaries", "SHAPE")
        assert wt == "architecture"
        # Architecture is strategic — only Claude qualifies, so no dispatch
        assert agent is None
        assert msg is None

    def test_dispatch_guidance_unclassified_returns_none(self):
        from conductor.preflight import _get_dispatch_guidance

        wt, agent, msg = _get_dispatch_guidance("xyzzy foobar baz", "BUILD")
        assert wt is None
        assert agent is None
        assert msg is None

    def test_dispatch_guidance_mechanical_suggests_dispatch(self):
        from conductor.preflight import _get_dispatch_guidance

        wt, agent, msg = _get_dispatch_guidance("naming convention conversion to snake_case", "BUILD")
        # mechanical_refactoring — should classify and possibly dispatch
        assert wt is not None


class TestPendingVerification:
    def test_no_handoff_returns_none(self, tmp_path):
        from conductor.preflight import _check_pending_verification

        result = _check_pending_verification(tmp_path)
        assert result is None

    def test_active_handoff_detected(self, tmp_path):
        from conductor.fleet_handoff import GuardrailedHandoffBrief, write_active_handoff
        from conductor.preflight import _check_pending_verification

        brief = GuardrailedHandoffBrief(
            from_agent="claude",
            to_agent="gemini",
            session_id="test",
            phase="BUILD",
            organ="META",
            repo="test",
            scope="test",
            summary="Test",
            work_type="boilerplate_generation",
            verification_required=True,
        )
        write_active_handoff(brief, tmp_path)

        result = _check_pending_verification(tmp_path)
        assert result is not None
        assert result["from_agent"] == "claude"
        assert result["to_agent"] == "gemini"
        assert result["work_type"] == "boilerplate_generation"

    def test_cleared_handoff_returns_none(self, tmp_path):
        from conductor.fleet_handoff import (
            GuardrailedHandoffBrief,
            clear_active_handoff,
            write_active_handoff,
        )
        from conductor.preflight import _check_pending_verification

        brief = GuardrailedHandoffBrief(
            from_agent="claude", to_agent="codex",
            session_id="test", phase="BUILD", organ="META",
            repo="test", scope="test", summary="Test",
        )
        write_active_handoff(brief, tmp_path)
        clear_active_handoff(tmp_path)

        result = _check_pending_verification(tmp_path)
        assert result is None


class TestPreflightResultFields:
    def test_result_has_dispatch_fields(self):
        from conductor.preflight import PreflightResult

        result = PreflightResult()
        assert result.dispatch_work_type is None
        assert result.dispatch_recommended_agent is None
        assert result.dispatch_guidance is None
        assert result.pending_verification is False
        assert result.pending_handoff_from is None
        assert result.pending_handoff_to is None

    def test_result_to_dict_includes_dispatch(self):
        from conductor.preflight import PreflightResult

        result = PreflightResult(
            dispatch_work_type="boilerplate_generation",
            dispatch_recommended_agent="Codex CLI",
            dispatch_guidance="Consider dispatching",
            pending_verification=True,
            pending_handoff_from="claude",
            pending_handoff_to="gemini",
        )
        d = result.to_dict()
        assert d["dispatch_work_type"] == "boilerplate_generation"
        assert d["pending_verification"] is True
        assert d["pending_handoff_from"] == "claude"
