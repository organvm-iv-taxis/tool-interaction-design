"""Session-as-Seed primitives — black-hole geometry of sessions.

A session opens a black hole. The conductor (human, optionally Claude as relay)
plants a named vacuum with gravity. External agents of differing dispositions are
pulled in and grow the planted idea through phased passes. Between each agent's
pass, the seed is re-planted: vacuum restored, growth signals archived, filling-
pressure cleared.

Governed by: praxis-perpetua/standards/SOP--session-as-seed.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .fleet_handoff import (
    GuardrailedHandoffBrief,
    HandoffBrief,
    write_active_handoff,
)


IMPLEMENTATION_VERBS = (
    "implement",
    "build",
    "create",
    "scaffold",
    "generate",
    "write",
    "refactor",
    "add",
    "update",
    "modify",
    "install",
    "configure",
    "setup",
    "develop",
    "code",
)


class SeedValidationError(ValueError):
    """Raised when a planted seed contains implementation language or fails gravity checks."""


@dataclass
class SeedEnvelope(GuardrailedHandoffBrief):
    """A black-hole envelope: named vacuum + locked constraints + zero proposed fill.

    Extends GuardrailedHandoffBrief with the four black-hole-specific fields:
    - vacuum_coordinates: name + IRF ID + atomized scope of the absence
    - signal_entailments: what the system logically requires but has not yet produced
    - current_state: refreshed live across phases (NOT optional; tombstone-detector)
    - growth_signals: append-only log of agent approaches and what they brought
    - vacuum_restore_points: append-only log of re-plant timestamps + phase headers
    """

    vacuum_coordinates: dict[str, str] = field(default_factory=dict)
    signal_entailments: list[str] = field(default_factory=list)
    current_state: str = ""
    growth_signals: list[dict[str, str]] = field(default_factory=list)
    vacuum_restore_points: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "vacuum_coordinates": self.vacuum_coordinates,
            "signal_entailments": self.signal_entailments,
            "current_state": self.current_state,
            "growth_signals": self.growth_signals,
            "vacuum_restore_points": self.vacuum_restore_points,
            "envelope_kind": "seed",
        })
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SeedEnvelope:
        return cls(
            from_agent=str(d.get("from_agent", "")),
            to_agent=str(d.get("to_agent", "")),
            session_id=str(d.get("session_id", "")),
            phase=str(d.get("phase", "")),
            organ=str(d.get("organ", "")),
            repo=str(d.get("repo", "")),
            scope=str(d.get("scope", "")),
            summary=str(d.get("summary", "")),
            key_files=list(d.get("key_files", [])),
            decisions=list(d.get("decisions", [])),
            open_questions=list(d.get("open_questions", [])),
            warnings=list(d.get("warnings", [])),
            timestamp=str(d.get("timestamp", "")),
            constraints_locked=list(d.get("constraints_locked", [])),
            files_locked=list(d.get("files_locked", [])),
            work_completed=list(d.get("work_completed", [])),
            conventions=dict(d.get("conventions", {})),
            work_type=str(d.get("work_type", "")),
            verification_required=bool(d.get("verification_required", False)),
            receiver_restrictions=dict(d.get("receiver_restrictions", {})),
            vacuum_coordinates=dict(d.get("vacuum_coordinates", {})),
            signal_entailments=list(d.get("signal_entailments", [])),
            current_state=str(d.get("current_state", "")),
            growth_signals=list(d.get("growth_signals", [])),
            vacuum_restore_points=list(d.get("vacuum_restore_points", [])),
        )


def _detect_implementation_verbs(intent: str) -> list[str]:
    """Return the implementation verbs found in intent as standalone words.

    Standalone = whitespace- or punctuation-bounded, case-insensitive. This is the
    load-bearing gravity check: implementation language fills the void, killing
    the black hole.
    """
    found: list[str] = []
    lowered = intent.lower()
    for verb in IMPLEMENTATION_VERBS:
        if re.search(rf"\b{verb}\b", lowered):
            found.append(verb)
    return found


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def plant_seed(
    *,
    name: str,
    intent: str,
    session_id: str,
    organ: str,
    repo: str,
    scope: str,
    irf_id: str = "",
    constraints_locked: list[str] | None = None,
    files_locked: list[str] | None = None,
    conventions: dict[str, str] | None = None,
    signal_entailments: list[str] | None = None,
    from_agent: str = "conductor",
    allow_implementation_language: bool = False,
) -> SeedEnvelope:
    """Plant a named vacuum at the singularity of a session.

    The intent must be a *declarative naming of the absence*, not an
    implementation directive. Implementation verbs (implement, build, create,
    scaffold, ...) are rejected unless allow_implementation_language=True.

    Raises SeedValidationError if the intent contains implementation language
    or if any of the four sources of gravity is missing.
    """
    if not name.strip():
        raise SeedValidationError("Vacuum requires a name; unnamed vacuums have no gravity.")
    if not intent.strip():
        raise SeedValidationError("Seed requires an intent (declarative naming of the absence).")
    if not constraints_locked:
        raise SeedValidationError(
            "Seed requires constraints_locked; locked constraints define the event horizon."
        )

    verbs = _detect_implementation_verbs(intent)
    if verbs and not allow_implementation_language:
        raise SeedValidationError(
            f"Intent contains implementation language: {verbs}. "
            "Implementation verbs fill the void and kill gravity. Re-phrase as a "
            "declarative naming of the absence (e.g., 'the unfilled handler at X', "
            "'the missing reconciliation between Y and Z'). Pass "
            "allow_implementation_language=True only when filling is the explicit "
            "intent of this session-open."
        )

    envelope = SeedEnvelope(
        from_agent=from_agent,
        to_agent="(unassigned — pulled by gravity)",
        session_id=session_id,
        phase="FRAME",
        organ=organ,
        repo=repo,
        scope=scope,
        summary=intent,
        key_files=[],
        decisions=[],
        open_questions=[],
        warnings=[],
        constraints_locked=list(constraints_locked),
        files_locked=list(files_locked or []),
        work_completed=[],
        conventions=dict(conventions or {}),
        work_type="seed_plant",
        verification_required=False,
        receiver_restrictions={},
        vacuum_coordinates={
            "name": name,
            "irf_id": irf_id,
            "scope": scope,
        },
        signal_entailments=list(signal_entailments or []),
        current_state=f"PLANTED {_now_iso()} — vacuum opened, awaiting first agent approach.",
        growth_signals=[],
        vacuum_restore_points=[
            {
                "timestamp": _now_iso(),
                "phase": "PLANT",
                "agent": from_agent,
                "note": "Initial plant; vacuum opened.",
            }
        ],
    )
    return envelope


def record_growth_signal(
    envelope: SeedEnvelope,
    *,
    agent: str,
    work_type: str,
    summary: str,
    files_changed: list[str] | None = None,
) -> SeedEnvelope:
    """Append a growth signal to the envelope (an agent has approached and brought matter).

    Mutates the envelope in place and returns it for chaining.
    """
    envelope.growth_signals.append({
        "timestamp": _now_iso(),
        "agent": agent,
        "work_type": work_type,
        "summary": summary,
        "files_changed": ", ".join(files_changed or []),
    })
    envelope.current_state = (
        f"GROWING {_now_iso()} — last approach: {agent} ({work_type}). "
        f"Awaiting cross-verify and re-plant."
    )
    return envelope


def re_plant_seed(
    envelope: SeedEnvelope,
    *,
    completing_phase: str,
    completing_agent: str,
    cross_verify_passed: bool,
    drift_reverted: list[str] | None = None,
    constraints_added: list[str] | None = None,
    note: str = "",
) -> SeedEnvelope:
    """Restore the vacuum after an agent's pass — the re-emptying ritual.

    Refuses to re-plant if cross_verify_passed is False (filling-pressure detected
    that has not been resolved). Otherwise: appends a Vacuum Restore Point under an
    immutable phase header, accepts any new locked constraints from the conductor,
    and refreshes current_state to indicate the void is restored.

    Raises SeedValidationError if cross_verify did not pass.
    """
    if not cross_verify_passed:
        raise SeedValidationError(
            "Cannot re-plant: cross_verify_passed=False. Resolve filling-pressure "
            "(reverted drift, accepted constraints) before re-planting. The vacuum "
            "cannot be restored over un-verified fill."
        )

    if constraints_added:
        envelope.constraints_locked = list(envelope.constraints_locked) + list(constraints_added)

    restore_point = {
        "timestamp": _now_iso(),
        "phase": f"RESTORE_AFTER_{completing_phase.upper()}",
        "agent": completing_agent,
        "drift_reverted": ", ".join(drift_reverted or []),
        "constraints_added": ", ".join(constraints_added or []),
        "note": note or f"Vacuum restored after {completing_agent}'s {completing_phase} pass.",
    }
    envelope.vacuum_restore_points.append(restore_point)

    envelope.current_state = (
        f"RESTORED {_now_iso()} — vacuum re-empty after {completing_agent} "
        f"({completing_phase}). Awaiting next agent of differing purpose."
    )
    return envelope


SEED_SIDECAR_FILENAME = "active-handoff.seed.json"


def write_seed_envelope(envelope: SeedEnvelope, repo_path: Path) -> Path:
    """Write the seed envelope to .conductor/active-handoff.md AND a JSON sidecar.

    The markdown file is the canonical relay surface that peer agents read.
    The JSON sidecar (.conductor/active-handoff.seed.json) preserves the typed
    envelope so re_plant can deserialize it back into a SeedEnvelope without
    parsing markdown. Both files are kept in sync on every plant and re-plant.
    """
    import json

    md_path = write_active_handoff(envelope, repo_path)

    sidecar = repo_path / ".conductor" / SEED_SIDECAR_FILENAME
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(envelope.to_dict(), indent=2, sort_keys=True))

    return md_path


def read_seed_envelope(repo_path: Path) -> SeedEnvelope | None:
    """Load the active SeedEnvelope from its JSON sidecar, or None if absent."""
    import json

    sidecar = repo_path / ".conductor" / SEED_SIDECAR_FILENAME
    if not sidecar.exists():
        return None
    try:
        data = json.loads(sidecar.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("envelope_kind") != "seed":
        return None
    return SeedEnvelope.from_dict(data)


__all__ = [
    "SeedEnvelope",
    "SeedValidationError",
    "IMPLEMENTATION_VERBS",
    "SEED_SIDECAR_FILENAME",
    "plant_seed",
    "record_growth_signal",
    "re_plant_seed",
    "write_seed_envelope",
    "read_seed_envelope",
]
