"""Tests for active handoff file lifecycle — write, read, clear."""

from __future__ import annotations

from conductor.fleet_handoff import (
    GuardrailedHandoffBrief,
    clear_active_handoff,
    read_active_handoff,
    write_active_handoff,
)


class TestWriteActiveHandoff:
    def test_creates_file(self, tmp_path):
        brief = GuardrailedHandoffBrief(
            from_agent="claude",
            to_agent="gemini",
            session_id="test",
            phase="BUILD",
            organ="META",
            repo="test",
            scope="test",
            summary="Scaffold endpoints",
            work_type="boilerplate_generation",
            verification_required=True,
        )
        path = write_active_handoff(brief, tmp_path)
        assert path.exists()
        assert path.name == "active-handoff.md"
        content = path.read_text()
        assert "claude → gemini" in content
        assert "boilerplate_generation" in content
        assert "CROSS-VERIFICATION REQUIRED" in content

    def test_overwrites_previous(self, tmp_path):
        brief1 = GuardrailedHandoffBrief(
            from_agent="claude", to_agent="gemini",
            session_id="s1", phase="BUILD", organ="META",
            repo="test", scope="test", summary="First",
        )
        brief2 = GuardrailedHandoffBrief(
            from_agent="claude", to_agent="codex",
            session_id="s2", phase="BUILD", organ="META",
            repo="test", scope="test", summary="Second",
        )
        write_active_handoff(brief1, tmp_path)
        write_active_handoff(brief2, tmp_path)
        content = (tmp_path / ".conductor" / "active-handoff.md").read_text()
        assert "codex" in content
        assert "Second" in content


class TestReadActiveHandoff:
    def test_reads_metadata(self, tmp_path):
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
        meta = read_active_handoff(tmp_path)
        assert meta is not None
        assert meta["from_agent"] == "claude"
        assert meta["to_agent"] == "gemini"
        assert meta["work_type"] == "boilerplate_generation"
        assert meta["verification_required"] == "true"

    def test_returns_none_when_no_handoff(self, tmp_path):
        assert read_active_handoff(tmp_path) is None

    def test_returns_none_for_empty_file(self, tmp_path):
        d = tmp_path / ".conductor"
        d.mkdir()
        (d / "active-handoff.md").write_text("")
        assert read_active_handoff(tmp_path) is None


class TestClearActiveHandoff:
    def test_clears_existing(self, tmp_path):
        brief = GuardrailedHandoffBrief(
            from_agent="claude", to_agent="gemini",
            session_id="test", phase="BUILD", organ="META",
            repo="test", scope="test", summary="Test",
        )
        write_active_handoff(brief, tmp_path)
        assert (tmp_path / ".conductor" / "active-handoff.md").exists()
        result = clear_active_handoff(tmp_path)
        assert result is True
        assert not (tmp_path / ".conductor" / "active-handoff.md").exists()

    def test_returns_false_when_nothing_to_clear(self, tmp_path):
        assert clear_active_handoff(tmp_path) is False

    def test_read_after_clear_returns_none(self, tmp_path):
        brief = GuardrailedHandoffBrief(
            from_agent="claude", to_agent="codex",
            session_id="test", phase="BUILD", organ="META",
            repo="test", scope="test", summary="Test",
        )
        write_active_handoff(brief, tmp_path)
        clear_active_handoff(tmp_path)
        assert read_active_handoff(tmp_path) is None


class TestFullCycle:
    def test_write_read_clear_cycle(self, tmp_path):
        """Full lifecycle: write → read → clear → read returns None."""
        brief = GuardrailedHandoffBrief(
            from_agent="claude",
            to_agent="gemini",
            session_id="cycle-test",
            phase="BUILD",
            organ="ORGAN-III",
            repo="my-app",
            scope="scaffold CRUD endpoints",
            summary="Need 12 CRUD endpoints scaffolded",
            work_type="boilerplate_generation",
            constraints_locked=["snake_case for all DB columns"],
            files_locked=["schema.ts"],
            conventions={"orm_naming": "snake_case"},
            verification_required=True,
        )

        # Write
        path = write_active_handoff(brief, tmp_path)
        assert path.exists()

        # Read
        meta = read_active_handoff(tmp_path)
        assert meta["from_agent"] == "claude"
        assert meta["to_agent"] == "gemini"

        # Clear
        cleared = clear_active_handoff(tmp_path)
        assert cleared

        # Read again — gone
        assert read_active_handoff(tmp_path) is None
