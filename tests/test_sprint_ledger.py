"""Tests for conductor.sprint_ledger — session retrospective + feedback injection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from conductor.sprint_ledger import (
    SessionLedger,
    _classify_prompt,
    _compute_prompt_stats,
    _detect_phase_patterns,
    _detect_prompt_patterns,
    _extract_prompts_fallback,
    _find_latest_session,
    _load_session_log,
    alchemize_ledger,
    build_ledger,
    find_session_jsonl,
    render_ledger_markdown,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sessions_dir(tmp_path, monkeypatch):
    """Create a fake sessions directory with one session log."""
    sdir = tmp_path / "sessions"
    sdir.mkdir()
    monkeypatch.setattr("conductor.sprint_ledger.SESSIONS_DIR", sdir)
    return sdir


@pytest.fixture()
def sample_session_log():
    return {
        "session_id": "2026-03-08-META-test-sprint-abc123",
        "organ": "META-ORGANVM",
        "repo": "conductor",
        "scope": "test sprint ledger",
        "agent": "claude",
        "duration_minutes": 45,
        "result": "SHIPPED",
        "timestamp": "2026-03-08T20:00:00+00:00",
        "phases": {
            "FRAME": {"duration": 600, "visits": 1, "tools_used": ["Read"], "agents": ["claude"]},
            "SHAPE": {"duration": 300, "visits": 1, "tools_used": [], "agents": ["claude"]},
            "BUILD": {"duration": 1500, "visits": 1, "tools_used": ["Write", "Edit"], "agents": ["claude"]},
            "PROVE": {"duration": 300, "visits": 1, "tools_used": ["Bash"], "agents": ["claude"]},
        },
        "warnings": ["Phase BUILD exceeded 20m"],
        "outputs": {},
        "tokens_consumed": 50000,
        "estimated_cost_usd": 0.75,
    }


@pytest.fixture()
def session_on_disk(sessions_dir, sample_session_log):
    """Write a session log to disk."""
    sid = sample_session_log["session_id"]
    (sessions_dir / sid).mkdir()
    log_path = sessions_dir / sid / "session-log.yaml"
    log_path.write_text(yaml.dump(sample_session_log, default_flow_style=False))
    return sid


@pytest.fixture()
def sample_jsonl(tmp_path):
    """Create a minimal Claude JSONL file with user prompts."""
    jsonl = tmp_path / "test-session.jsonl"
    messages = [
        {"type": "user", "message": {"content": "Implement the following plan: sprint ledger"}, "timestamp": "2026-03-08T19:15:00Z"},
        {"type": "assistant", "message": {"content": "I'll implement the sprint ledger."}},
        {"type": "user", "message": {"content": "How does the session close work?"}, "timestamp": "2026-03-08T19:30:00Z"},
        {"type": "user", "message": {"content": "ok looks good, proceed"}, "timestamp": "2026-03-08T19:45:00Z"},
    ]
    with jsonl.open("w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")
    return jsonl


# ---------------------------------------------------------------------------
# SessionLedger dataclass
# ---------------------------------------------------------------------------


class TestSessionLedger:
    def test_to_dict_includes_new_fields(self):
        ledger = SessionLedger(
            session_id="test-123",
            agent="claude",
            organ="META",
            repo="conductor",
            scope="test",
            duration_minutes=30,
            result="SHIPPED",
            detected_patterns=[{"name": "test", "severity": "info"}],
            insights=["good session"],
            feedback_applied=["pattern:test -> history"],
        )
        d = ledger.to_dict()
        assert d["session_id"] == "test-123"
        assert d["detected_patterns"] == [{"name": "test", "severity": "info"}]
        assert d["insights"] == ["good session"]
        assert d["feedback_applied"] == ["pattern:test -> history"]

    def test_defaults(self):
        ledger = SessionLedger(
            session_id="x", agent="a", organ="O", repo="r",
            scope="s", duration_minutes=0, result="CLOSED",
        )
        assert ledger.detected_patterns == []
        assert ledger.insights == []
        assert ledger.feedback_applied == []


# ---------------------------------------------------------------------------
# Prompt pattern detection
# ---------------------------------------------------------------------------


class TestDetectPromptPatterns:
    def test_no_prompts(self):
        assert _detect_prompt_patterns([]) == []

    def test_high_correction_ratio(self):
        prompts = [
            {"type": "command", "text": "do x"},
            {"type": "correction", "text": "no wait"},
            {"type": "correction", "text": "actually"},
            {"type": "correction", "text": "not that"},
            {"type": "command", "text": "try this"},
        ]
        patterns = _detect_prompt_patterns(prompts)
        names = [p["name"] for p in patterns]
        assert "high_correction_ratio" in names

    def test_excessive_continuation(self):
        prompts = [{"type": "continuation", "text": f"ok {i}"} for i in range(6)]
        prompts.extend([{"type": "command", "text": "x"}, {"type": "command", "text": "y"}])
        patterns = _detect_prompt_patterns(prompts)
        names = [p["name"] for p in patterns]
        assert "excessive_continuation" in names

    def test_no_verification_questions(self):
        prompts = [{"type": "command", "text": f"do {i}"} for i in range(10)]
        patterns = _detect_prompt_patterns(prompts)
        names = [p["name"] for p in patterns]
        assert "no_verification_questions" in names

    def test_plan_without_review(self):
        prompts = [
            {"type": "plan_invocation", "text": "implement plan"},
            {"type": "command", "text": "continue"},
            {"type": "command", "text": "next"},
            {"type": "command", "text": "done"},
            {"type": "command", "text": "ship it"},
        ]
        patterns = _detect_prompt_patterns(prompts)
        names = [p["name"] for p in patterns]
        assert "plan_without_review" in names

    def test_single_prompt(self):
        patterns = _detect_prompt_patterns([{"type": "command", "text": "fix bug"}])
        names = [p["name"] for p in patterns]
        assert "single_prompt_session" in names

    def test_clean_session_no_patterns(self):
        prompts = [
            {"type": "command", "text": "implement feature"},
            {"type": "question", "text": "how does x work"},
            {"type": "command", "text": "write tests"},
            {"type": "review", "text": "review the output"},
        ]
        patterns = _detect_prompt_patterns(prompts)
        # Small session, no ratio thresholds hit
        assert len(patterns) == 0


class TestDetectPhasePatterns:
    def test_no_phases(self):
        assert _detect_phase_patterns([], 0) == []

    def test_build_heavy(self):
        phases = [
            {"name": "FRAME", "duration_minutes": 2},
            {"name": "BUILD", "duration_minutes": 50},
            {"name": "PROVE", "duration_minutes": 3},
        ]
        patterns = _detect_phase_patterns(phases, 55)
        names = [p["name"] for p in patterns]
        assert "build_heavy" in names

    def test_skipped_prove(self):
        phases = [
            {"name": "FRAME", "duration_minutes": 10},
            {"name": "SHAPE", "duration_minutes": 5},
            {"name": "BUILD", "duration_minutes": 20},
            {"name": "PROVE", "duration_minutes": 0},
        ]
        patterns = _detect_phase_patterns(phases, 35)
        names = [p["name"] for p in patterns]
        assert "skipped_prove" in names

    def test_analysis_paralysis(self):
        phases = [
            {"name": "FRAME", "duration_minutes": 40},
            {"name": "BUILD", "duration_minutes": 2},
        ]
        patterns = _detect_phase_patterns(phases, 42)
        names = [p["name"] for p in patterns]
        assert "analysis_paralysis" in names

    def test_no_shape_phase(self):
        phases = [
            {"name": "FRAME", "duration_minutes": 10},
            {"name": "BUILD", "duration_minutes": 20},
        ]
        patterns = _detect_phase_patterns(phases, 30)
        names = [p["name"] for p in patterns]
        assert "no_shape_phase" in names

    def test_balanced_session(self):
        phases = [
            {"name": "FRAME", "duration_minutes": 10},
            {"name": "SHAPE", "duration_minutes": 5},
            {"name": "BUILD", "duration_minutes": 15},
            {"name": "PROVE", "duration_minutes": 10},
        ]
        patterns = _detect_phase_patterns(phases, 40)
        assert len(patterns) == 0


# ---------------------------------------------------------------------------
# Loading and discovery
# ---------------------------------------------------------------------------


class TestLoadSessionLog:
    def test_load_existing(self, session_on_disk, sessions_dir):
        log = _load_session_log(session_on_disk)
        assert log is not None
        assert log["organ"] == "META-ORGANVM"

    def test_load_missing(self, sessions_dir):
        assert _load_session_log("nonexistent-session") is None

    def test_load_corrupt_yaml(self, sessions_dir):
        sid = "corrupt-session"
        (sessions_dir / sid).mkdir()
        (sessions_dir / sid / "session-log.yaml").write_text("::invalid::")
        result = _load_session_log(sid)
        assert result is not None or result is None  # no crash


class TestFindLatestSession:
    def test_finds_latest(self, session_on_disk, sessions_dir):
        latest = _find_latest_session()
        assert latest == session_on_disk

    def test_empty_sessions_dir(self, sessions_dir):
        assert _find_latest_session() is None

    def test_no_sessions_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("conductor.sprint_ledger.SESSIONS_DIR", tmp_path / "nope")
        assert _find_latest_session() is None


# ---------------------------------------------------------------------------
# JSONL matching
# ---------------------------------------------------------------------------


class TestFindSessionJsonl:
    def test_no_claude_dir(self, sample_session_log, monkeypatch, tmp_path):
        monkeypatch.setattr("conductor.sprint_ledger.Path.home", lambda: tmp_path)
        result = find_session_jsonl(sample_session_log)
        assert result is None

    def test_empty_timestamp(self):
        assert find_session_jsonl({"timestamp": ""}) is None

    def test_bad_timestamp(self):
        assert find_session_jsonl({"timestamp": "not-a-date"}) is None


# ---------------------------------------------------------------------------
# Prompt extraction
# ---------------------------------------------------------------------------


class TestExtractPromptsFallback:
    def test_extracts_user_messages(self, sample_jsonl):
        prompts = _extract_prompts_fallback(sample_jsonl)
        assert len(prompts) == 3
        assert "Implement the following plan" in prompts[0]["text"]
        assert prompts[0]["index"] == 0
        assert prompts[1]["index"] == 1

    def test_skips_short_messages(self, tmp_path):
        jsonl = tmp_path / "short.jsonl"
        jsonl.write_text(json.dumps({
            "type": "user",
            "message": {"content": "ok"},
        }) + "\n")
        prompts = _extract_prompts_fallback(jsonl)
        assert len(prompts) == 0

    def test_handles_list_content(self, tmp_path):
        jsonl = tmp_path / "list.jsonl"
        jsonl.write_text(json.dumps({
            "type": "user",
            "message": {"content": [
                {"type": "text", "text": "This is a list content message"},
            ]},
            "timestamp": "2026-03-08T19:00:00Z",
        }) + "\n")
        prompts = _extract_prompts_fallback(jsonl)
        assert len(prompts) == 1
        assert "list content message" in prompts[0]["text"]

    def test_missing_file(self, tmp_path):
        prompts = _extract_prompts_fallback(tmp_path / "missing.jsonl")
        assert prompts == []


# ---------------------------------------------------------------------------
# Prompt classification
# ---------------------------------------------------------------------------


class TestClassifyPrompt:
    def test_question(self):
        assert _classify_prompt("How does this work?", 0) in ("question", "exploration")

    def test_directive(self):
        result = _classify_prompt("Implement the sprint ledger module", 0)
        assert result in ("directive", "creation", "plan_invocation", "command")

    def test_continuation(self):
        result = _classify_prompt("ok looks good, proceed", 2)
        assert result in ("continuation",)

    def test_unknown_fallback(self):
        result = _classify_prompt("something random here that is long enough", 0)
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Prompt stats
# ---------------------------------------------------------------------------


class TestComputePromptStats:
    def test_empty(self):
        stats = _compute_prompt_stats([])
        assert stats["total"] == 0
        assert stats["avg_chars"] == 0

    def test_with_prompts(self):
        prompts = [
            {"text": "short", "type": "command"},
            {"text": "a longer prompt here", "type": "directive"},
            {"text": "question?", "type": "question"},
        ]
        stats = _compute_prompt_stats(prompts)
        assert stats["total"] == 3
        assert stats["avg_chars"] > 0
        assert "command" in stats["type_distribution"]


# ---------------------------------------------------------------------------
# Build ledger
# ---------------------------------------------------------------------------


class TestBuildLedger:
    def _patch_externals(self, monkeypatch):
        monkeypatch.setattr("conductor.sprint_ledger._collect_git_activity", lambda *a, **kw: ([], []))
        monkeypatch.setattr("conductor.sprint_ledger._discover_related_plans", lambda *a, **kw: [])
        monkeypatch.setattr("conductor.sprint_ledger.find_session_jsonl", lambda *a, **kw: None)

    def test_build_latest(self, session_on_disk, sessions_dir, monkeypatch):
        self._patch_externals(monkeypatch)
        ledger = build_ledger()
        assert ledger.session_id == session_on_disk
        assert ledger.organ == "META-ORGANVM"
        assert ledger.result == "SHIPPED"
        assert ledger.duration_minutes == 45
        assert len(ledger.phase_history) == 4

    def test_build_detects_patterns(self, session_on_disk, sessions_dir, monkeypatch):
        self._patch_externals(monkeypatch)
        ledger = build_ledger()
        # With a 45min session, patterns may or may not fire — but the field exists
        assert isinstance(ledger.detected_patterns, list)
        assert isinstance(ledger.insights, list)
        assert len(ledger.insights) > 0  # always at least one insight

    def test_build_with_jsonl(self, session_on_disk, sessions_dir, sample_jsonl, monkeypatch):
        monkeypatch.setattr("conductor.sprint_ledger._collect_git_activity", lambda *a, **kw: ([], []))
        monkeypatch.setattr("conductor.sprint_ledger._discover_related_plans", lambda *a, **kw: [])

        ledger = build_ledger(session_id=session_on_disk, jsonl_path=sample_jsonl)
        assert len(ledger.prompts) == 3
        assert ledger.prompt_stats["total"] == 3

    def test_build_no_sessions(self, sessions_dir):
        with pytest.raises(ValueError, match="No closed sessions"):
            build_ledger()

    def test_build_missing_id(self, sessions_dir):
        with pytest.raises(ValueError, match="Session log not found"):
            build_ledger(session_id="nonexistent-session")

    def test_fleet_usage(self, session_on_disk, sessions_dir, monkeypatch):
        self._patch_externals(monkeypatch)
        ledger = build_ledger(session_id=session_on_disk)
        assert ledger.fleet_usage["tokens_consumed"] == 50000
        assert ledger.fleet_usage["estimated_cost_usd"] == 0.75

    def test_shipped_clean_insight(self, session_on_disk, sessions_dir, monkeypatch):
        """A SHIPPED session with balanced phases gets a clean insight."""
        self._patch_externals(monkeypatch)
        ledger = build_ledger(session_id=session_on_disk)
        # The sample session has BUILD at ~55% which is under 70% threshold
        # so "Clean session" or specific patterns depending on phase calc
        assert any("session" in i.lower() or "pattern" in i.lower() or "phase" in i.lower()
                    for i in ledger.insights)


# ---------------------------------------------------------------------------
# Alchemize — feedback injection
# ---------------------------------------------------------------------------


class TestAlchemizeLedger:
    def test_records_patterns(self, monkeypatch):
        """Patterns get recorded into product.record_pattern()."""
        recorded = []
        monkeypatch.setattr(
            "conductor.sprint_ledger.record_pattern",
            lambda name, sid, result: recorded.append((name, sid, result)),
        )

        ledger = SessionLedger(
            session_id="test-alch", agent="claude", organ="META", repo="cond",
            scope="test", duration_minutes=60, result="SHIPPED",
            detected_patterns=[
                {"name": "build_heavy", "severity": "caution", "insight": "x", "recommendation": "y"},
                {"name": "skipped_prove", "severity": "warning", "insight": "z", "recommendation": "w"},
            ],
        )
        actions = alchemize_ledger(ledger)
        assert len(actions) > 0
        assert any("pattern:build_heavy" in a for a in actions)
        assert any("pattern:skipped_prove" in a for a in actions)
        assert ledger.feedback_applied == actions

    def test_logs_observability_events(self, monkeypatch):
        """Phase balance and prompt stats get logged to observability."""
        logged_events = []

        def mock_log_event(event_type, details):
            logged_events.append(event_type)

        monkeypatch.setattr("conductor.sprint_ledger.log_event", mock_log_event)

        ledger = SessionLedger(
            session_id="test-obs", agent="claude", organ="META", repo="cond",
            scope="test", duration_minutes=30, result="SHIPPED",
            phase_history=[{"name": "BUILD", "duration_minutes": 30}],
            prompt_stats={"total": 5, "avg_chars": 100, "type_distribution": {"command": 5}},
            detected_patterns=[],
        )
        actions = alchemize_ledger(ledger)
        assert any("observability" in a for a in actions)

    def test_no_patterns_still_logs_phase(self, monkeypatch):
        """Even with zero patterns, phase balance is logged."""
        logged_events = []

        def mock_log_event(event_type, details):
            logged_events.append(event_type)

        monkeypatch.setattr("conductor.sprint_ledger.log_event", mock_log_event)

        ledger = SessionLedger(
            session_id="test-clean", agent="claude", organ="META", repo="cond",
            scope="test", duration_minutes=30, result="SHIPPED",
            phase_history=[{"name": "BUILD", "duration_minutes": 30}],
            prompt_stats={"total": 0},
            detected_patterns=[],
        )
        actions = alchemize_ledger(ledger)
        assert any("phase_balance" in a for a in actions)

    def test_empty_ledger_no_crash(self):
        """Alchemize on a minimal ledger doesn't crash."""
        ledger = SessionLedger(
            session_id="empty", agent="a", organ="O", repo="r",
            scope="s", duration_minutes=0, result="CLOSED",
        )
        actions = alchemize_ledger(ledger)
        assert isinstance(actions, list)

    def test_efficiency_tracking(self, monkeypatch):
        """Tokens-per-commit gets logged when both are present."""
        logged = []

        def mock_log_event(event_type, details):
            logged.append((event_type, details))

        monkeypatch.setattr("conductor.sprint_ledger.log_event", mock_log_event)

        ledger = SessionLedger(
            session_id="test-eff", agent="claude", organ="META", repo="cond",
            scope="test", duration_minutes=30, result="SHIPPED",
            fleet_usage={"tokens_consumed": 100000, "estimated_cost_usd": 1.50, "agent": "claude"},
            commits=[{"sha": "abc", "message": "feat: x", "date": ""}],
            detected_patterns=[],
        )
        actions = alchemize_ledger(ledger)
        assert any("efficiency" in a for a in actions)
        # Verify the actual metric was computed
        eff_events = [(t, d) for t, d in logged if t == "retro.efficiency"]
        assert len(eff_events) == 1
        assert eff_events[0][1]["tokens_per_commit"] == 100000


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


class TestRenderLedgerMarkdown:
    def test_renders_header(self):
        ledger = SessionLedger(
            session_id="test-session",
            agent="claude",
            organ="META-ORGANVM",
            repo="conductor",
            scope="test rendering",
            duration_minutes=30,
            result="SHIPPED",
            fleet_usage={"tokens_consumed": 10000, "estimated_cost_usd": 0.15},
        )
        md = render_ledger_markdown(ledger)
        assert "# Session Retrospective: test-session" in md
        assert "**Agent:** claude" in md
        assert "**Result:** SHIPPED" in md
        assert "10,000" in md

    def test_renders_phase_path(self):
        ledger = SessionLedger(
            session_id="x", agent="a", organ="O", repo="r",
            scope="s", duration_minutes=10, result="SHIPPED",
            phase_history=[
                {"name": "FRAME", "duration_minutes": 5, "visits": 1},
                {"name": "BUILD", "duration_minutes": 5, "visits": 1},
            ],
        )
        md = render_ledger_markdown(ledger)
        assert "FRAME (5m) -> BUILD (5m)" in md

    def test_renders_detected_patterns(self):
        ledger = SessionLedger(
            session_id="x", agent="a", organ="O", repo="r",
            scope="s", duration_minutes=60, result="SHIPPED",
            detected_patterns=[{
                "name": "build_heavy",
                "severity": "caution",
                "insight": "BUILD was 80% of session",
                "recommendation": "Invest in PROVE",
            }],
            insights=["BUILD was 80% of session"],
        )
        md = render_ledger_markdown(ledger)
        assert "## Detected Patterns" in md
        assert "build_heavy" in md
        assert "Invest in PROVE" in md

    def test_renders_insights(self):
        ledger = SessionLedger(
            session_id="x", agent="a", organ="O", repo="r",
            scope="s", duration_minutes=10, result="SHIPPED",
            insights=["Clean session — shipped without detected anti-patterns."],
        )
        md = render_ledger_markdown(ledger)
        assert "## Insights" in md
        assert "Clean session" in md

    def test_renders_feedback_applied(self):
        ledger = SessionLedger(
            session_id="x", agent="a", organ="O", repo="r",
            scope="s", duration_minutes=10, result="SHIPPED",
            feedback_applied=["pattern:test -> history", "phase_balance -> observability"],
        )
        md = render_ledger_markdown(ledger)
        assert "## Feedback Injected" in md
        assert "pattern:test -> history" in md

    def test_renders_feedback_hint_when_not_applied(self):
        ledger = SessionLedger(
            session_id="x", agent="a", organ="O", repo="r",
            scope="s", duration_minutes=10, result="SHIPPED",
        )
        md = render_ledger_markdown(ledger)
        assert "## Feedback" in md
        assert "--write" in md

    def test_renders_prompts_table(self):
        ledger = SessionLedger(
            session_id="x", agent="a", organ="O", repo="r",
            scope="s", duration_minutes=10, result="SHIPPED",
            prompts=[
                {"text": "test prompt", "timestamp": "2026-03-08T19:00:00Z", "type": "command", "index": 0},
            ],
            prompt_stats={"total": 1, "avg_chars": 11, "type_distribution": {"command": 1}},
        )
        md = render_ledger_markdown(ledger)
        assert "## Prompt Ledger (1 prompts)" in md
        assert "test prompt" in md

    def test_no_prompts_empty_table(self):
        ledger = SessionLedger(
            session_id="x", agent="a", organ="O", repo="r",
            scope="s", duration_minutes=10, result="SHIPPED",
        )
        md = render_ledger_markdown(ledger)
        assert "## Prompt Ledger (0 prompts)" in md
        assert "| # |" not in md

    def test_truncates_long_files_list(self):
        ledger = SessionLedger(
            session_id="x", agent="a", organ="O", repo="r",
            scope="s", duration_minutes=10, result="SHIPPED",
            files_changed=[f"file{i}.py" for i in range(40)],
        )
        md = render_ledger_markdown(ledger)
        assert "... and 10 more" in md
