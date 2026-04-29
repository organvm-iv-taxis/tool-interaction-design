"""Tests for session-as-seed primitives (black-hole geometry).

Covers SeedEnvelope serialization, plant_seed implementation-language rejection,
record_growth_signal mutation, re_plant_seed gating on cross_verify, and end-to-end
markdown rendering of the four seed-specific sections.
"""

from __future__ import annotations

import json

import pytest

from conductor.fleet_handoff import format_markdown
from conductor.seed import (
    IMPLEMENTATION_VERBS,
    SEED_SIDECAR_FILENAME,
    SeedEnvelope,
    SeedValidationError,
    plant_seed,
    re_plant_seed,
    read_seed_envelope,
    record_growth_signal,
    write_seed_envelope,
)


# ---------------------------------------------------------------------------
# plant_seed validation
# ---------------------------------------------------------------------------


def test_plant_seed_returns_envelope_for_declarative_intent() -> None:
    envelope = plant_seed(
        name="missing-reconciliation-between-A-and-B",
        intent="The unfilled handler at the boundary between subsystem A and subsystem B.",
        session_id="sess-001",
        organ="ORGAN-IV",
        repo="tool-interaction-design",
        scope="reconciliation seam",
        irf_id="IRF-IV-042",
        constraints_locked=["snake_case for all DB columns"],
        files_locked=["governance-rules.json"],
        signal_entailments=["entailed by AX-6: code edge requires reconciliation receipt"],
    )

    assert isinstance(envelope, SeedEnvelope)
    assert envelope.vacuum_coordinates["name"] == "missing-reconciliation-between-A-and-B"
    assert envelope.vacuum_coordinates["irf_id"] == "IRF-IV-042"
    assert envelope.signal_entailments == ["entailed by AX-6: code edge requires reconciliation receipt"]
    assert envelope.current_state.startswith("PLANTED ")
    assert len(envelope.vacuum_restore_points) == 1
    assert envelope.vacuum_restore_points[0]["phase"] == "PLANT"


@pytest.mark.parametrize("verb", ["implement", "build", "create", "scaffold", "refactor"])
def test_plant_seed_rejects_implementation_language(verb: str) -> None:
    with pytest.raises(SeedValidationError) as excinfo:
        plant_seed(
            name="x",
            intent=f"Please {verb} the new component.",
            session_id="sess-002",
            organ="ORGAN-IV",
            repo="r",
            scope="s",
            constraints_locked=["c"],
        )
    assert verb in str(excinfo.value)


def test_plant_seed_allows_implementation_language_with_override() -> None:
    envelope = plant_seed(
        name="filling-is-the-point",
        intent="Implement the missing module — explicit fill session.",
        session_id="sess-003",
        organ="ORGAN-IV",
        repo="r",
        scope="s",
        constraints_locked=["c"],
        allow_implementation_language=True,
    )
    assert isinstance(envelope, SeedEnvelope)


def test_plant_seed_rejects_empty_constraints() -> None:
    """Locked constraints are a required gravity source — not optional."""
    with pytest.raises(SeedValidationError, match="constraints_locked"):
        plant_seed(
            name="x",
            intent="The absence of Y.",
            session_id="sess-004",
            organ="ORGAN-IV",
            repo="r",
            scope="s",
            constraints_locked=[],
        )


def test_plant_seed_rejects_unnamed_vacuum() -> None:
    with pytest.raises(SeedValidationError, match="name"):
        plant_seed(
            name="",
            intent="The absence of Y.",
            session_id="sess-005",
            organ="ORGAN-IV",
            repo="r",
            scope="s",
            constraints_locked=["c"],
        )


# ---------------------------------------------------------------------------
# Growth signals + re-plant
# ---------------------------------------------------------------------------


def _planted() -> SeedEnvelope:
    return plant_seed(
        name="missing-X",
        intent="The unfilled handler at X.",
        session_id="sess-100",
        organ="ORGAN-IV",
        repo="r",
        scope="s",
        constraints_locked=["c"],
    )


def test_record_growth_signal_appends_and_updates_state() -> None:
    envelope = _planted()
    record_growth_signal(
        envelope,
        agent="codex",
        work_type="boilerplate_generation",
        summary="scaffolded handler stub",
        files_changed=["src/handler.py"],
    )

    assert len(envelope.growth_signals) == 1
    assert envelope.growth_signals[0]["agent"] == "codex"
    assert "src/handler.py" in envelope.growth_signals[0]["files_changed"]
    assert envelope.current_state.startswith("GROWING ")


def test_re_plant_seed_appends_restore_point_and_resets_state() -> None:
    envelope = _planted()
    record_growth_signal(envelope, agent="codex", work_type="code", summary="...")

    re_plant_seed(
        envelope,
        completing_phase="CODE",
        completing_agent="codex",
        cross_verify_passed=True,
        note="codex pass complete; vacuum re-empty",
    )

    # Initial PLANT + the new RESTORE_AFTER_CODE
    assert len(envelope.vacuum_restore_points) == 2
    assert envelope.vacuum_restore_points[-1]["phase"] == "RESTORE_AFTER_CODE"
    assert envelope.vacuum_restore_points[-1]["agent"] == "codex"
    assert envelope.current_state.startswith("RESTORED ")


def test_re_plant_seed_refuses_when_cross_verify_failed() -> None:
    envelope = _planted()
    with pytest.raises(SeedValidationError, match="cross_verify_passed=False"):
        re_plant_seed(
            envelope,
            completing_phase="CODE",
            completing_agent="codex",
            cross_verify_passed=False,
        )
    # The restore point list must NOT have grown when re-plant is refused.
    assert len(envelope.vacuum_restore_points) == 1


def test_re_plant_seed_accepts_new_constraints_from_conductor() -> None:
    envelope = _planted()
    re_plant_seed(
        envelope,
        completing_phase="CODE",
        completing_agent="codex",
        cross_verify_passed=True,
        constraints_added=["no async in handler.py"],
    )
    assert "no async in handler.py" in envelope.constraints_locked


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


def test_seed_envelope_roundtrips_through_dict() -> None:
    envelope = _planted()
    record_growth_signal(envelope, agent="codex", work_type="code", summary="...")
    re_plant_seed(envelope, completing_phase="CODE", completing_agent="codex", cross_verify_passed=True)

    payload = envelope.to_dict()
    assert payload["envelope_kind"] == "seed"

    restored = SeedEnvelope.from_dict(payload)
    assert restored.vacuum_coordinates == envelope.vacuum_coordinates
    assert restored.signal_entailments == envelope.signal_entailments
    assert restored.growth_signals == envelope.growth_signals
    assert restored.vacuum_restore_points == envelope.vacuum_restore_points
    assert restored.constraints_locked == envelope.constraints_locked


# ---------------------------------------------------------------------------
# Filesystem write + read
# ---------------------------------------------------------------------------


def test_write_seed_envelope_writes_markdown_and_sidecar(tmp_path) -> None:
    envelope = _planted()
    md_path = write_seed_envelope(envelope, tmp_path)

    assert md_path.exists()
    assert md_path.name == "active-handoff.md"
    assert md_path.parent.name == ".conductor"

    sidecar = tmp_path / ".conductor" / SEED_SIDECAR_FILENAME
    assert sidecar.exists()
    data = json.loads(sidecar.read_text())
    assert data["envelope_kind"] == "seed"


def test_read_seed_envelope_round_trips_from_disk(tmp_path) -> None:
    envelope = _planted()
    record_growth_signal(envelope, agent="gemini", work_type="research", summary="surveyed prior art")
    write_seed_envelope(envelope, tmp_path)

    loaded = read_seed_envelope(tmp_path)
    assert loaded is not None
    assert loaded.vacuum_coordinates == envelope.vacuum_coordinates
    assert loaded.growth_signals == envelope.growth_signals


def test_read_seed_envelope_returns_none_when_absent(tmp_path) -> None:
    assert read_seed_envelope(tmp_path) is None


# ---------------------------------------------------------------------------
# format_markdown rendering
# ---------------------------------------------------------------------------


def test_format_markdown_renders_seed_specific_sections() -> None:
    envelope = _planted()
    record_growth_signal(envelope, agent="codex", work_type="code", summary="stub handler")
    re_plant_seed(
        envelope, completing_phase="CODE", completing_agent="codex", cross_verify_passed=True
    )
    md = format_markdown(envelope)

    assert "## Vacuum Coordinates" in md
    assert "## Current State" in md
    assert "## Growth Signals (append-only)" in md
    assert "## Vacuum Restore Points (append-only)" in md
    # Inherited GuardrailedHandoffBrief sections are still rendered:
    assert "## Locked Constraints (DO NOT OVERRIDE)" in md


def test_format_markdown_current_state_is_required() -> None:
    """The presence of the Current State block is the peer-readability test."""
    envelope = _planted()
    md = format_markdown(envelope)
    assert "## Current State" in md
    # Initial plant produces a non-empty state (PLANTED ...).
    assert "(empty — peer-readability test will fail)" not in md


def test_implementation_verbs_are_exposed_for_inspection() -> None:
    """The verb list is part of the public contract; downstream tools may filter on it."""
    assert "implement" in IMPLEMENTATION_VERBS
    assert "build" in IMPLEMENTATION_VERBS
    assert "scaffold" in IMPLEMENTATION_VERBS
