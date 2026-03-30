"""Tests for GuardrailedHandoffBrief — envelope generation, constraint propagation, markdown rendering."""

from __future__ import annotations

import json
import time

import pytest

from conductor.fleet_handoff import (
    GuardrailedHandoffBrief,
    HandoffBrief,
    format_markdown,
    generate_guardrailed_handoff,
)


class TestGuardrailedHandoffBrief:
    def test_inherits_from_handoff_brief(self):
        brief = GuardrailedHandoffBrief(
            from_agent="claude",
            to_agent="gemini",
            session_id="test",
            phase="BUILD",
            organ="META",
            repo="test",
            scope="test",
            summary="test",
        )
        assert isinstance(brief, HandoffBrief)

    def test_default_fields(self):
        brief = GuardrailedHandoffBrief(
            from_agent="claude",
            to_agent="gemini",
            session_id="test",
            phase="BUILD",
            organ="META",
            repo="test",
            scope="test",
            summary="test",
        )
        assert brief.constraints_locked == []
        assert brief.files_locked == []
        assert brief.work_completed == []
        assert brief.conventions == {}
        assert brief.work_type == ""
        assert brief.verification_required is False
        assert brief.receiver_restrictions == {}

    def test_to_dict_includes_guardrail_fields(self):
        brief = GuardrailedHandoffBrief(
            from_agent="claude",
            to_agent="gemini",
            session_id="test",
            phase="BUILD",
            organ="META",
            repo="test",
            scope="test",
            summary="test",
            constraints_locked=["snake_case for all DB columns"],
            files_locked=["schema.ts"],
            work_completed=["API endpoints for users"],
            conventions={"orm_naming": "snake_case"},
            work_type="boilerplate_generation",
            verification_required=True,
            receiver_restrictions={"restrictions": {"never_touch": ["package.json"]}},
        )
        d = brief.to_dict()
        assert d["constraints_locked"] == ["snake_case for all DB columns"]
        assert d["files_locked"] == ["schema.ts"]
        assert d["work_completed"] == ["API endpoints for users"]
        assert d["conventions"] == {"orm_naming": "snake_case"}
        assert d["work_type"] == "boilerplate_generation"
        assert d["verification_required"] is True
        assert d["receiver_restrictions"]["restrictions"]["never_touch"] == ["package.json"]
        # Also has base fields
        assert d["from_agent"] == "claude"
        assert d["to_agent"] == "gemini"

    def test_roundtrip_dict(self):
        brief = GuardrailedHandoffBrief(
            from_agent="claude",
            to_agent="codex",
            session_id="s-123",
            phase="BUILD",
            organ="ORGAN-III",
            repo="my-repo",
            scope="Feature X",
            summary="Done with schema",
            key_files=["schema.ts"],
            decisions=["Use Drizzle ORM"],
            constraints_locked=["snake_case columns"],
            files_locked=["schema.ts", "drizzle.config.ts"],
            work_completed=["Schema design", "Migration files"],
            conventions={"orm_naming": "snake_case", "imports": "named"},
            work_type="architecture",
            verification_required=True,
        )
        d = brief.to_dict()
        restored = GuardrailedHandoffBrief.from_dict(d)
        assert restored.constraints_locked == brief.constraints_locked
        assert restored.files_locked == brief.files_locked
        assert restored.work_completed == brief.work_completed
        assert restored.conventions == brief.conventions
        assert restored.work_type == brief.work_type
        assert restored.verification_required == brief.verification_required

    def test_json_roundtrip(self):
        brief = GuardrailedHandoffBrief(
            from_agent="a",
            to_agent="b",
            session_id="s",
            phase="BUILD",
            organ="META",
            repo="r",
            scope="sc",
            summary="sum",
            constraints_locked=["c1"],
            conventions={"k": "v"},
        )
        json_str = json.dumps(brief.to_dict())
        restored = GuardrailedHandoffBrief.from_dict(json.loads(json_str))
        assert restored.constraints_locked == ["c1"]
        assert restored.conventions == {"k": "v"}


class TestGenerateGuardrailedHandoff:
    def _make_mock_session(self):
        from conductor.session import Session

        return Session(
            session_id="2026-03-30-III-test-abc123",
            organ="ORGAN-III",
            repo="test-repo",
            scope="Feature X",
            start_time=time.time() - 3600,
            current_phase="BUILD",
            agent="claude",
            warnings=["Phase took too long"],
        )

    def test_basic_generation(self):
        session = self._make_mock_session()
        brief = generate_guardrailed_handoff(
            session=session,
            from_agent="claude",
            to_agent="gemini",
            summary="Need boilerplate generated.",
            work_type="boilerplate_generation",
            constraints_locked=["snake_case for ORM"],
            files_locked=["schema.ts"],
            conventions={"orm_naming": "snake_case"},
        )
        assert brief.from_agent == "claude"
        assert brief.to_agent == "gemini"
        assert brief.work_type == "boilerplate_generation"
        assert brief.constraints_locked == ["snake_case for ORM"]
        assert brief.conventions == {"orm_naming": "snake_case"}
        assert len(brief.warnings) == 1

    def test_auto_verification_when_untrusted(self):
        session = self._make_mock_session()
        brief = generate_guardrailed_handoff(
            session=session,
            from_agent="claude",
            to_agent="gemini",
            summary="Test",
            receiver_restrictions={
                "guardrails": {"self_audit_trusted": False}
            },
        )
        assert brief.verification_required is True

    def test_no_verification_when_trusted(self):
        session = self._make_mock_session()
        brief = generate_guardrailed_handoff(
            session=session,
            from_agent="claude",
            to_agent="codex",
            summary="Test",
            receiver_restrictions={
                "guardrails": {"self_audit_trusted": True}
            },
        )
        assert brief.verification_required is False


class TestGuardrailedMarkdown:
    def test_renders_verification_warning(self):
        brief = GuardrailedHandoffBrief(
            from_agent="claude",
            to_agent="gemini",
            session_id="test",
            phase="BUILD",
            organ="META",
            repo="test",
            scope="test",
            summary="test",
            verification_required=True,
        )
        md = format_markdown(brief)
        assert "CROSS-VERIFICATION REQUIRED" in md

    def test_renders_locked_constraints(self):
        brief = GuardrailedHandoffBrief(
            from_agent="claude",
            to_agent="gemini",
            session_id="test",
            phase="BUILD",
            organ="META",
            repo="test",
            scope="test",
            summary="test",
            constraints_locked=["snake_case for all columns"],
        )
        md = format_markdown(brief)
        assert "Locked Constraints" in md
        assert "snake_case" in md

    def test_renders_work_completed(self):
        brief = GuardrailedHandoffBrief(
            from_agent="claude",
            to_agent="codex",
            session_id="test",
            phase="BUILD",
            organ="META",
            repo="test",
            scope="test",
            summary="test",
            work_completed=["API endpoints", "Schema design"],
        )
        md = format_markdown(brief)
        assert "Work Already Completed" in md
        assert "DO NOT REPEAT" in md

    def test_renders_receiver_restrictions(self):
        brief = GuardrailedHandoffBrief(
            from_agent="claude",
            to_agent="gemini",
            session_id="test",
            phase="BUILD",
            organ="META",
            repo="test",
            scope="test",
            summary="test",
            receiver_restrictions={
                "restrictions": {"never_touch": ["package.json", "*.config.ts"]}
            },
        )
        md = format_markdown(brief)
        assert "Receiver Restrictions" in md
        assert "package.json" in md

    def test_base_handoff_no_guardrail_sections(self):
        brief = HandoffBrief(
            from_agent="claude",
            to_agent="codex",
            session_id="test",
            phase="BUILD",
            organ="META",
            repo="test",
            scope="test",
            summary="test",
        )
        md = format_markdown(brief)
        assert "Locked Constraints" not in md
        assert "CROSS-VERIFICATION" not in md
