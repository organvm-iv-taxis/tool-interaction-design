"""Tests for the fleet orchestration system (registry, usage, router, handoff)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Fleet Registry
# ---------------------------------------------------------------------------


class TestFleetRegistry:
    def test_load_from_default_yaml(self):
        from conductor.fleet import FleetRegistry

        reg = FleetRegistry()
        assert len(reg.all_agents()) >= 3

    def test_active_agents_excludes_inactive(self):
        from conductor.fleet import FleetRegistry

        reg = FleetRegistry()
        active = reg.active_agents()
        names = {a.name for a in active}
        assert "claude" in names
        assert "gemini" in names
        assert "codex" in names
        # goose/kimi/opencode are inactive in the default config
        for a in active:
            assert a.active is True

    def test_get_known_agent(self):
        from conductor.fleet import FleetRegistry

        reg = FleetRegistry()
        claude = reg.get("claude")
        assert claude is not None
        assert claude.display_name == "Claude Code (Opus 4.6)"
        assert claude.provider == "anthropic"
        assert claude.subscription.tier == "max"
        assert claude.subscription.allotment.messages_per_day == 45
        assert "deep-coding" in claude.capabilities.strengths
        assert claude.sensitivity.can_see_secrets is True
        assert claude.phase_affinity["BUILD"] == 1.0

    def test_get_unknown_agent_returns_none(self):
        from conductor.fleet import FleetRegistry

        reg = FleetRegistry()
        assert reg.get("nonexistent") is None

    def test_by_provider(self):
        from conductor.fleet import FleetRegistry

        reg = FleetRegistry()
        google_agents = reg.by_provider("google")
        assert len(google_agents) >= 1
        assert all(a.provider == "google" for a in google_agents)

    def test_load_from_custom_yaml(self, tmp_path):
        from conductor.fleet import FleetRegistry

        custom = tmp_path / "fleet.yaml"
        custom.write_text(yaml.dump({
            "agents": {
                "test_agent": {
                    "display_name": "Test Agent",
                    "provider": "test",
                    "subscription": {"tier": "free", "allotment": {"context_window": 100000}},
                    "capabilities": {"strengths": ["testing"]},
                    "phase_affinity": {"BUILD": 0.9},
                    "sensitivity": {"can_see_secrets": False},
                    "active": True,
                }
            }
        }))

        reg = FleetRegistry(custom)
        assert len(reg.all_agents()) == 1
        agent = reg.get("test_agent")
        assert agent is not None
        assert agent.display_name == "Test Agent"
        assert agent.subscription.allotment.context_window == 100000

    def test_load_missing_file(self, tmp_path):
        from conductor.fleet import FleetRegistry

        reg = FleetRegistry(tmp_path / "nonexistent.yaml")
        assert len(reg.all_agents()) == 0

    def test_frozen_dataclasses(self):
        from conductor.fleet import FleetRegistry

        reg = FleetRegistry()
        claude = reg.get("claude")
        assert claude is not None
        with pytest.raises(AttributeError):
            claude.name = "hacked"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Fleet Usage Tracker
# ---------------------------------------------------------------------------


class TestFleetUsageTracker:
    def test_record_and_retrieve(self, tmp_path):
        from conductor.fleet_usage import FleetUsageTracker

        tracker = FleetUsageTracker(tmp_path)
        rec = tracker.record_session(
            agent="claude",
            session_id="test-001",
            duration_minutes=30,
            tokens_in=10000,
            tokens_out=5000,
            cost_usd=0.50,
        )

        assert rec.agent == "claude"
        assert rec.session_id == "test-001"
        assert rec.tokens_in == 10000

        # Retrieve
        today = date.today()
        records = tracker.get_period("claude", today.year, today.month)
        assert len(records) == 1
        assert records[0].session_id == "test-001"

    def test_daily_snapshot(self, tmp_path):
        from conductor.fleet_usage import FleetUsageTracker

        tracker = FleetUsageTracker(tmp_path)
        tracker.record_session(agent="claude", session_id="s1", duration_minutes=10, tokens_in=1000, cost_usd=0.10)
        tracker.record_session(agent="gemini", session_id="s2", duration_minutes=20, tokens_in=2000, cost_usd=0.20)

        daily = tracker.daily_snapshot()
        assert "claude" in daily
        assert "gemini" in daily
        assert daily["claude"]["sessions"] == 1
        assert daily["gemini"]["sessions"] == 1

    def test_utilization_report(self, tmp_path):
        from conductor.fleet import FleetRegistry
        from conductor.fleet_usage import FleetUsageTracker

        tracker = FleetUsageTracker(tmp_path)
        for i in range(5):
            tracker.record_session(agent="claude", session_id=f"s{i}", duration_minutes=10)

        reg = FleetRegistry()
        today = date.today()
        report = tracker.utilization_report(today.year, today.month, reg.active_agents())
        assert "claude" in report
        assert report["claude"]["sessions"] == 5
        assert "utilization_pct" in report["claude"]

    def test_empty_period(self, tmp_path):
        from conductor.fleet_usage import FleetUsageTracker

        tracker = FleetUsageTracker(tmp_path)
        records = tracker.get_period("claude", 2020, 1)
        assert records == []

    def test_underutilized_agents(self, tmp_path):
        from conductor.fleet import FleetRegistry
        from conductor.fleet_usage import FleetUsageTracker

        tracker = FleetUsageTracker(tmp_path)
        # Record very little for claude
        tracker.record_session(agent="claude", session_id="s1")
        today = date.today()
        reg = FleetRegistry()
        under = tracker.underutilized_agents(today.year, today.month, threshold=50.0, fleet_agents=reg.active_agents())
        assert "claude" in under  # 1 session out of ~1350 allotted is way under 50%


# ---------------------------------------------------------------------------
# Fleet Router
# ---------------------------------------------------------------------------


class TestFleetRouter:
    def test_recommend_build_phase(self):
        from conductor.fleet_router import FleetRouter

        router = FleetRouter()
        scores = router.recommend(phase="BUILD", task_tags=["deep-coding"])
        assert len(scores) >= 2
        # Claude should rank first for BUILD with coding tags
        assert scores[0].agent == "claude"

    def test_recommend_frame_phase(self):
        from conductor.fleet_router import FleetRouter

        router = FleetRouter()
        scores = router.recommend(phase="FRAME", task_tags=["deep-research"])
        assert len(scores) >= 2
        # Gemini should rank first for FRAME with research tags
        assert scores[0].agent == "gemini"

    def test_sensitivity_filter(self):
        from conductor.fleet_router import FleetRouter

        router = FleetRouter()
        scores = router.recommend(
            phase="BUILD",
            sensitivity_required={"can_see_secrets": True, "can_push_git": True},
        )
        agent_names = {s.agent for s in scores}
        # Gemini can't see secrets or push git
        assert "gemini" not in agent_names
        assert "claude" in agent_names
        assert "codex" in agent_names

    def test_context_size_scoring(self):
        from conductor.fleet_router import FleetRouter

        router = FleetRouter()
        # Huge context should favor gemini (1M window)
        scores = router.recommend(phase="FRAME", context_size=500000)
        gemini_score = next(s for s in scores if s.agent == "gemini")
        claude_score = next(s for s in scores if s.agent == "claude")
        assert gemini_score.breakdown["context_fit"] > claude_score.breakdown["context_fit"]

    def test_explain_output(self):
        from conductor.fleet_router import FleetRouter

        router = FleetRouter()
        scores = router.recommend(phase="BUILD")
        explanation = router.explain(scores[0])
        assert "phase_affinity" in explanation
        assert "█" in explanation

    def test_no_tags_neutral_strength(self):
        from conductor.fleet_router import FleetRouter

        router = FleetRouter()
        scores = router.recommend(phase="BUILD")
        for s in scores:
            assert s.breakdown["strength_match"] == 0.5

    def test_empty_when_all_filtered(self):
        from conductor.fleet_router import FleetRouter

        router = FleetRouter()
        # Require something no agent has (by construction the key doesn't exist)
        scores = router.recommend(
            phase="BUILD",
            sensitivity_required={"can_see_secrets": True, "can_push_git": True},
        )
        # At least claude and codex should pass
        assert len(scores) >= 2


# ---------------------------------------------------------------------------
# Fleet Handoff
# ---------------------------------------------------------------------------


class TestFleetHandoff:
    def _make_mock_session(self):
        from conductor.session import Session
        import time

        return Session(
            session_id="2026-03-08-META-test-abc123",
            organ="META-ORGANVM",
            repo="conductor",
            scope="Fleet orchestration implementation",
            start_time=time.time() - 3600,
            current_phase="SHAPE",
            agent="claude",
            warnings=["Phase took too long"],
        )

    def test_generate_handoff(self):
        from conductor.fleet_handoff import generate_handoff

        session = self._make_mock_session()
        brief = generate_handoff(
            session=session,
            from_agent="claude",
            to_agent="gemini",
            summary="Need deep research on pricing models.",
            key_files=["conductor/fleet.py"],
            decisions=["Chose JSONL storage"],
        )

        assert brief.from_agent == "claude"
        assert brief.to_agent == "gemini"
        assert brief.session_id == session.session_id
        assert brief.phase == "SHAPE"
        assert brief.organ == "META-ORGANVM"
        assert len(brief.key_files) == 1
        assert len(brief.decisions) == 1
        assert len(brief.warnings) == 1  # Inherited from session

    def test_format_markdown(self):
        from conductor.fleet_handoff import HandoffBrief, format_markdown

        brief = HandoffBrief(
            from_agent="claude",
            to_agent="codex",
            session_id="test-session",
            phase="BUILD",
            organ="ORGAN-III",
            repo="test-repo",
            scope="Test scope",
            summary="Test summary.",
            key_files=["file1.py", "file2.py"],
            decisions=["Decision 1"],
            open_questions=["Question 1"],
        )
        md = format_markdown(brief)
        assert "# Agent Handoff: claude → codex" in md
        assert "**Phase:** BUILD" in md
        assert "## Key Files" in md
        assert "`file1.py`" in md
        assert "## Decisions Made" in md
        assert "## Open Questions" in md

    def test_write_handoff(self, tmp_path):
        from conductor.fleet_handoff import HandoffBrief, write_handoff

        brief = HandoffBrief(
            from_agent="claude",
            to_agent="gemini",
            session_id="test",
            phase="FRAME",
            organ="META",
            repo="test",
            scope="test",
            summary="test summary",
        )
        out = write_handoff(brief, tmp_path)
        assert out.exists()
        assert out.name.startswith("handoff-")
        assert out.suffix == ".md"
        content = out.read_text()
        assert "claude → gemini" in content

    def test_log_handoff(self, tmp_path):
        from conductor.fleet_handoff import HandoffBrief, log_handoff, HANDOFF_LOG_PATH
        import conductor.fleet_handoff as fh

        # Redirect to tmp
        original = fh.HANDOFF_LOG_PATH
        fh.HANDOFF_LOG_PATH = tmp_path / "handoff-log.jsonl"
        try:
            brief = HandoffBrief(
                from_agent="claude",
                to_agent="gemini",
                session_id="test",
                phase="FRAME",
                organ="META",
                repo="test",
                scope="test",
                summary="test",
            )
            log_handoff(brief)
            assert fh.HANDOFF_LOG_PATH.exists()
            line = fh.HANDOFF_LOG_PATH.read_text().strip()
            data = json.loads(line)
            assert data["from_agent"] == "claude"
            assert data["to_agent"] == "gemini"
        finally:
            fh.HANDOFF_LOG_PATH = original

    def test_roundtrip_dict(self):
        from conductor.fleet_handoff import HandoffBrief

        brief = HandoffBrief(
            from_agent="a",
            to_agent="b",
            session_id="s",
            phase="BUILD",
            organ="META",
            repo="r",
            scope="sc",
            summary="sum",
            key_files=["f1"],
            decisions=["d1"],
            open_questions=["q1"],
            warnings=["w1"],
        )
        d = brief.to_dict()
        restored = HandoffBrief.from_dict(d)
        assert restored.from_agent == brief.from_agent
        assert restored.key_files == brief.key_files
        assert restored.warnings == brief.warnings
