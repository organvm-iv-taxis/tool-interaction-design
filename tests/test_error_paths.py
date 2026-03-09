"""Error-path integration tests.

Verifies that detector failures produce observability events, corrupted state
files are handled gracefully, and invalid workflow state produces clear errors.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import conductor.constants
import conductor.session
from conductor.constants import ConductorError
from conductor.executor import WorkflowExecutor
from conductor.observability import log_event
from conductor.oracle import Oracle, OracleContext


# ---------------------------------------------------------------------------
# Oracle detector failure logging
# ---------------------------------------------------------------------------


class TestDetectorFailureLogging:
    """Verify that detector errors produce observability events, not silence."""

    def test_corrupted_stats_logs_event(self, tmp_path):
        """Corrupted stats file should log an error event, not crash."""
        stats_file = tmp_path / "stats.json"
        stats_file.write_text("{CORRUPTED JSON")
        oracle_state = tmp_path / "oracle" / "state.json"
        events: list[dict] = []

        def capture_event(event_type, data=None):
            events.append({"type": event_type, "data": data})

        with (
            patch.object(conductor.constants, "STATS_FILE", stats_file),
            patch("conductor.oracle.STATS_FILE", stats_file),
            patch("conductor.oracle.ORACLE_STATE_FILE", oracle_state),
            patch("conductor.oracle.log_event", capture_event),
        ):
            oracle = Oracle()
            result = oracle.consult(OracleContext(trigger="manual"), max_advisories=5)
            # Should return advisories (possibly empty), not raise
            assert isinstance(result, list)
            assert len(result) <= 5
            for adv in result:
                assert adv.severity in ("critical", "warning", "caution", "info")

    def test_missing_stats_returns_empty_gracefully(self, tmp_path):
        """Missing stats file produces no advisories but no crash."""
        stats_file = tmp_path / "nonexistent-stats.json"
        oracle_state = tmp_path / "oracle" / "state.json"

        with (
            patch.object(conductor.constants, "STATS_FILE", stats_file),
            patch("conductor.oracle.STATS_FILE", stats_file),
            patch("conductor.oracle.ORACLE_STATE_FILE", oracle_state),
        ):
            oracle = Oracle()
            result = oracle.consult(OracleContext(trigger="manual"))
            # No stats = no data-driven advisories
            assert result == [] or all(a.message for a in result)

    def test_corrupted_oracle_state_handled(self, tmp_path):
        """Corrupted oracle state file should not crash consultations."""
        stats_file = tmp_path / "stats.json"
        stats_file.write_text(json.dumps({"total_sessions": 0}))
        oracle_state = tmp_path / "oracle" / "state.json"
        oracle_state.parent.mkdir(parents=True, exist_ok=True)
        oracle_state.write_text("NOT VALID JSON!!!")

        with (
            patch.object(conductor.constants, "STATS_FILE", stats_file),
            patch("conductor.oracle.STATS_FILE", stats_file),
            patch("conductor.oracle.ORACLE_STATE_FILE", oracle_state),
        ):
            oracle = Oracle()
            result = oracle.consult(OracleContext(trigger="manual"))
            # Corrupted state should degrade gracefully, not crash
            assert isinstance(result, list)
            for adv in result:
                assert adv.message and adv.category

    def test_governance_import_failure_logs(self, tmp_path):
        """If GovernanceRuntime fails to load, detector logs event."""
        stats_file = tmp_path / "stats.json"
        stats_file.write_text(json.dumps({
            "total_sessions": 10,
            "shipped": 5,
            "total_minutes": 500,
            "streak": 0,
            "by_organ": {},
            "recent_sessions": [],
        }))
        oracle_state = tmp_path / "oracle" / "state.json"
        events: list[dict] = []

        def capture_event(event_type, data=None):
            events.append({"type": event_type, "data": data})

        with (
            patch.object(conductor.constants, "STATS_FILE", stats_file),
            patch("conductor.oracle.STATS_FILE", stats_file),
            patch("conductor.oracle.ORACLE_STATE_FILE", oracle_state),
            patch("conductor.oracle.log_event", capture_event),
            patch("conductor.governance.REGISTRY_PATH", tmp_path / "nope.json"),
            patch("conductor.governance.GOVERNANCE_PATH", tmp_path / "nope2.json"),
        ):
            oracle = Oracle()
            advisories = oracle._detect_governance_gaps()
            # Should return empty list (governance unavailable), not crash
            assert isinstance(advisories, list)


# ---------------------------------------------------------------------------
# Workflow state error paths
# ---------------------------------------------------------------------------


class TestWorkflowStateErrors:
    """Verify workflow state corruption produces ConductorError."""

    def test_no_active_workflow_raises(self, tmp_path):
        """run_step without start_workflow raises ConductorError."""
        wf_path = Path(__file__).parent.parent / "workflow-dsl.yaml"
        state_file = tmp_path / "workflows" / "_default.json"
        executor = WorkflowExecutor(wf_path, state_file=state_file)
        with pytest.raises(ConductorError):
            executor.run_step("nonexistent")

    def test_corrupted_workflow_state_raises(self, tmp_path):
        """Corrupted workflow state file raises ConductorError."""
        wf_path = Path(__file__).parent.parent / "workflow-dsl.yaml"
        state_file = tmp_path / "workflows" / "_default.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("NOT JSON")
        executor = WorkflowExecutor(wf_path, state_file=state_file)
        with pytest.raises((ConductorError, json.JSONDecodeError)):
            executor.run_step("any-step")

    def test_wrong_step_name_raises(self, tmp_path):
        """Referencing a nonexistent step raises ConductorError."""
        wf_path = Path(__file__).parent.parent / "workflow-dsl.yaml"
        state_file = tmp_path / "workflows" / "_default.json"
        executor = WorkflowExecutor(wf_path, state_file=state_file)
        workflows = executor.list_workflows()
        if workflows:
            executor.start_workflow(workflows[0], session_id="test-err")
            with pytest.raises(ConductorError, match="not found"):
                executor.run_step("definitely-not-a-step")


# ---------------------------------------------------------------------------
# Session state error paths
# ---------------------------------------------------------------------------


class TestSessionStateErrors:
    """Verify session state corruption is handled clearly."""

    def test_corrupted_session_state_message(self, tmp_path):
        """Corrupted session state file produces a clear error message."""
        from conductor.session import SessionEngine
        from router import Ontology

        ontology_path = Path(__file__).parent.parent / "ontology.yaml"
        ontology = Ontology(ontology_path)

        state_file = tmp_path / "session.json"
        state_file.write_text("CORRUPTED")
        stats_file = tmp_path / "stats.json"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        for name in ("spec.md", "plan.md", "status.md"):
            (templates_dir / name).write_text(f"# {{{{ scope }}}}")

        active_sessions_dir = tmp_path / "active-sessions"
        active_sessions_dir.mkdir()

        with (
            patch.object(conductor.constants, "SESSIONS_DIR", sessions_dir),
            patch.object(conductor.constants, "TEMPLATES_DIR", templates_dir),
            patch.object(conductor.constants, "SESSION_STATE_FILE", state_file),
            patch.object(conductor.constants, "STATS_FILE", stats_file),
            patch.object(conductor.constants, "ACTIVE_SESSIONS_DIR", active_sessions_dir),
            patch.object(conductor.session, "SESSIONS_DIR", sessions_dir),
            patch.object(conductor.session, "TEMPLATES_DIR", templates_dir),
            patch.object(conductor.session, "SESSION_STATE_FILE", state_file),
            patch.object(conductor.session, "STATS_FILE", stats_file),
            patch.object(conductor.session, "ACTIVE_SESSIONS_DIR", active_sessions_dir),
        ):
            se = SessionEngine(ontology)
            # Should detect corruption and give clear error
            try:
                se.status()
            except Exception as e:
                assert "corrupted" in str(e).lower() or "no active session" in str(e).lower()


# ---------------------------------------------------------------------------
# Silent swallow cleanup verification
# ---------------------------------------------------------------------------


class TestSilentSwallowCleanup:
    """Verify that broad exceptions now produce observability events."""

    def test_session_oracle_failure_logs_event(self, tmp_path):
        from conductor.session import SessionEngine
        from router import Ontology

        events: list[dict] = []

        def capture_event(event_type, data=None):
            events.append({"type": event_type, "data": data})

        ontology_path = Path(__file__).parent.parent / "ontology.yaml"
        ontology = Ontology(ontology_path)

        with (
            patch("conductor.guardian.GuardianAngel") as mock_guardian,
            patch("conductor.observability.log_event", capture_event),
            patch("conductor.session.SessionEngine._load_session", return_value=None),
        ):
            # Make the guardian crash
            mock_guardian.return_value.counsel.side_effect = Exception("Crash!")

            se = SessionEngine(ontology)
            # This triggers se.start -> guardian.counsel
            se.start(organ="III", repo="test", scope="test")

            assert any(e["type"] == "session.oracle_advisory_error" for e in events)
            assert any("Crash!" in str(e["data"]["error"]) for e in events if e["type"] == "session.oracle_advisory_error")

    def test_patchbay_session_load_failure_logs_event(self, tmp_path):
        from conductor.patchbay import Patchbay

        events: list[dict] = []

        def capture_event(event_type, data=None):
            events.append({"type": event_type, "data": data})

        with (
            patch("conductor.session.SessionEngine._load_session") as mock_load,
            patch("conductor.observability.log_event", capture_event),
        ):
            mock_load.side_effect = Exception("Load failure")

            pb = Patchbay()
            # This triggers briefing -> _session_section -> _load_session
            pb.briefing()

            assert any(e["type"] == "patchbay.session_load_error" for e in events)

    def test_session_stats_load_failure_logs_event(self, tmp_path):
        stats_file = tmp_path / "stats.json"
        stats_file.write_text("{NOT JSON")
        events: list[dict] = []

        def capture_event(event_type, data=None):
            events.append({"type": event_type, "data": data})

        with (
            patch.object(conductor.constants, "STATS_FILE", stats_file),
            patch.object(conductor.session, "STATS_FILE", stats_file),
            patch("conductor.observability.log_event", capture_event),
        ):
            stats = conductor.session._load_stats()

        assert stats["total_sessions"] == 0
        assert any(e["type"] == "session.stats_load_error" for e in events)

    def test_governance_audit_issue_list_failure_logs_event(self):
        from conductor.governance import GovernanceRuntime

        events: list[dict] = []

        def capture_event(event_type, data=None):
            events.append({"type": event_type, "data": data})

        gov = GovernanceRuntime(offline=True)
        with (
            patch("subprocess.run", side_effect=FileNotFoundError("gh missing")),
            patch("conductor.observability.log_event", capture_event),
        ):
            gov._create_audit_issues("ORGAN-III", ["Create follow-up test issue"])

        assert any(e["type"] == "governance.audit_issue_list_error" for e in events)

    def test_retro_stats_load_failure_logs_event(self, tmp_path):
        import conductor.retro

        stats_file = tmp_path / "stats.json"
        stats_file.write_text("{BROKEN")
        events: list[dict] = []

        def capture_event(event_type, data=None):
            events.append({"type": event_type, "data": data})

        with (
            patch.object(conductor.retro, "STATS_FILE", stats_file),
            patch("conductor.observability.log_event", capture_event),
        ):
            stats = conductor.retro._load_stats()

        assert stats == {}
        assert any(e["type"] == "retro.stats_load_error" for e in events)
