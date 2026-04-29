"""Fleet handoff — generate context briefs when switching between agents."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import STATE_DIR

HANDOFF_LOG_PATH = STATE_DIR / "handoff-log.jsonl"


@dataclass
class HandoffBrief:
    """Context package for handing off between agents."""

    from_agent: str
    to_agent: str
    session_id: str
    phase: str
    organ: str
    repo: str
    scope: str
    summary: str
    key_files: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "session_id": self.session_id,
            "phase": self.phase,
            "organ": self.organ,
            "repo": self.repo,
            "scope": self.scope,
            "summary": self.summary,
            "key_files": self.key_files,
            "decisions": self.decisions,
            "open_questions": self.open_questions,
            "warnings": self.warnings,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HandoffBrief:
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
        )


@dataclass
class GuardrailedHandoffBrief(HandoffBrief):
    """Extended handoff with enforceable constraints for the receiving agent."""

    constraints_locked: list[str] = field(default_factory=list)
    files_locked: list[str] = field(default_factory=list)
    work_completed: list[str] = field(default_factory=list)
    conventions: dict[str, str] = field(default_factory=dict)
    work_type: str = ""
    verification_required: bool = False
    receiver_restrictions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "constraints_locked": self.constraints_locked,
            "files_locked": self.files_locked,
            "work_completed": self.work_completed,
            "conventions": self.conventions,
            "work_type": self.work_type,
            "verification_required": self.verification_required,
            "receiver_restrictions": self.receiver_restrictions,
        })
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GuardrailedHandoffBrief:
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
        )


def generate_handoff(
    session: Any,
    from_agent: str,
    to_agent: str,
    summary: str,
    key_files: list[str] | None = None,
    decisions: list[str] | None = None,
    open_questions: list[str] | None = None,
) -> HandoffBrief:
    """Generate a handoff brief from the active session state."""
    return HandoffBrief(
        from_agent=from_agent,
        to_agent=to_agent,
        session_id=session.session_id,
        phase=session.current_phase,
        organ=session.organ,
        repo=session.repo,
        scope=session.scope,
        summary=summary,
        key_files=key_files or [],
        decisions=decisions or [],
        open_questions=open_questions or [],
        warnings=list(session.warnings) if hasattr(session, "warnings") else [],
    )


def generate_guardrailed_handoff(
    session: Any,
    from_agent: str,
    to_agent: str,
    summary: str,
    work_type: str = "",
    key_files: list[str] | None = None,
    decisions: list[str] | None = None,
    open_questions: list[str] | None = None,
    constraints_locked: list[str] | None = None,
    files_locked: list[str] | None = None,
    work_completed: list[str] | None = None,
    conventions: dict[str, str] | None = None,
    receiver_restrictions: dict[str, Any] | None = None,
) -> GuardrailedHandoffBrief:
    """Generate a guardrailed handoff from the active session state.

    Auto-populates verification_required based on receiver_restrictions
    (if self_audit_trusted is False, verification is required).
    """
    verification_required = False
    restr = receiver_restrictions or {}
    guardrails = restr.get("guardrails", {})
    if not guardrails.get("self_audit_trusted", True):
        verification_required = True

    return GuardrailedHandoffBrief(
        from_agent=from_agent,
        to_agent=to_agent,
        session_id=session.session_id,
        phase=session.current_phase,
        organ=session.organ,
        repo=session.repo,
        scope=session.scope,
        summary=summary,
        key_files=key_files or [],
        decisions=decisions or [],
        open_questions=open_questions or [],
        warnings=list(session.warnings) if hasattr(session, "warnings") else [],
        constraints_locked=constraints_locked or [],
        files_locked=files_locked or [],
        work_completed=work_completed or [],
        conventions=conventions or {},
        work_type=work_type,
        verification_required=verification_required,
        receiver_restrictions=receiver_restrictions or {},
    )


def format_markdown(brief: HandoffBrief) -> str:
    """Render a handoff brief as markdown for injection into agent context."""
    lines = [
        f"# Agent Handoff: {brief.from_agent} → {brief.to_agent}",
        "",
        f"**Session:** {brief.session_id}",
        f"**Phase:** {brief.phase}",
        f"**Organ:** {brief.organ} | **Repo:** {brief.repo}",
        f"**Scope:** {brief.scope}",
        f"**Timestamp:** {brief.timestamp}",
        "",
        "## Summary",
        "",
        brief.summary,
        "",
    ]

    if brief.key_files:
        lines.append("## Key Files")
        lines.append("")
        for f in brief.key_files:
            lines.append(f"- `{f}`")
        lines.append("")

    if brief.decisions:
        lines.append("## Decisions Made")
        lines.append("")
        for d in brief.decisions:
            lines.append(f"- {d}")
        lines.append("")

    if brief.open_questions:
        lines.append("## Open Questions")
        lines.append("")
        for q in brief.open_questions:
            lines.append(f"- {q}")
        lines.append("")

    if brief.warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in brief.warnings:
            lines.append(f"- {w}")
        lines.append("")

    # Guardrailed fields (only present on GuardrailedHandoffBrief)
    if isinstance(brief, GuardrailedHandoffBrief):
        if brief.work_type:
            lines.append(f"**Work Type:** {brief.work_type}")
            lines.append("")

        if brief.verification_required:
            lines.append("**⚠ CROSS-VERIFICATION REQUIRED** — Do not trust the "
                         "originating agent's self-assessment. Verify all output.")
            lines.append("")

        if brief.constraints_locked:
            lines.append("## Locked Constraints (DO NOT OVERRIDE)")
            lines.append("")
            for c in brief.constraints_locked:
                lines.append(f"- {c}")
            lines.append("")

        if brief.files_locked:
            lines.append("## Locked Files (DO NOT MODIFY)")
            lines.append("")
            for f in brief.files_locked:
                lines.append(f"- `{f}`")
            lines.append("")

        if brief.work_completed:
            lines.append("## Work Already Completed (DO NOT REPEAT)")
            lines.append("")
            for w in brief.work_completed:
                lines.append(f"- {w}")
            lines.append("")

        if brief.conventions:
            lines.append("## Active Conventions")
            lines.append("")
            for key, val in brief.conventions.items():
                lines.append(f"- **{key}:** {val}")
            lines.append("")

        if brief.receiver_restrictions:
            restr = brief.receiver_restrictions.get("restrictions", {})
            if restr.get("never_touch"):
                lines.append("## Receiver Restrictions")
                lines.append("")
                lines.append("Files you MUST NOT touch:")
                for pat in restr["never_touch"]:
                    lines.append(f"- `{pat}`")
                lines.append("")

    # Seed envelope — black-hole geometry sections.
    # Local import to avoid a circular dependency (seed.py imports from this module).
    try:
        from .seed import SeedEnvelope  # noqa: WPS433 — runtime import is intentional
    except ImportError:  # pragma: no cover — seed module always present in repo
        SeedEnvelope = None  # type: ignore[assignment]

    if SeedEnvelope is not None and isinstance(brief, SeedEnvelope):
        if brief.vacuum_coordinates:
            lines.append("## Vacuum Coordinates")
            lines.append("")
            for key, val in brief.vacuum_coordinates.items():
                if val:
                    lines.append(f"- **{key}:** {val}")
            lines.append("")

        if brief.signal_entailments:
            lines.append("## Gravity Signature (signal-closure entailments)")
            lines.append("")
            for entailment in brief.signal_entailments:
                lines.append(f"- {entailment}")
            lines.append("")

        # Current State is REQUIRED — its presence is the peer-readability test.
        lines.append("## Current State")
        lines.append("")
        lines.append(brief.current_state or "(empty — peer-readability test will fail)")
        lines.append("")

        if brief.growth_signals:
            lines.append("## Growth Signals (append-only)")
            lines.append("")
            for sig in brief.growth_signals:
                ts = sig.get("timestamp", "")
                agent = sig.get("agent", "")
                work_type = sig.get("work_type", "")
                summary = sig.get("summary", "")
                files = sig.get("files_changed", "")
                lines.append(f"- **{ts}** — `{agent}` ({work_type}): {summary}")
                if files:
                    lines.append(f"  - files: {files}")
            lines.append("")

        if brief.vacuum_restore_points:
            lines.append("## Vacuum Restore Points (append-only)")
            lines.append("")
            for rp in brief.vacuum_restore_points:
                ts = rp.get("timestamp", "")
                phase = rp.get("phase", "")
                agent = rp.get("agent", "")
                note = rp.get("note", "")
                lines.append(f"- **{ts}** [{phase}] `{agent}` — {note}")
                drift = rp.get("drift_reverted", "")
                added = rp.get("constraints_added", "")
                if drift:
                    lines.append(f"  - drift reverted: {drift}")
                if added:
                    lines.append(f"  - constraints added: {added}")
            lines.append("")

    return "\n".join(lines)


def write_handoff(brief: HandoffBrief, repo_path: Path) -> Path:
    """Write a handoff brief to the repo's .conductor/ directory."""
    ts = brief.timestamp.replace(":", "-").replace("T", "_")[:19]
    handoff_dir = repo_path / ".conductor"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    filename = f"handoff-{ts}.md"
    out_path = handoff_dir / filename
    out_path.write_text(format_markdown(brief))
    return out_path


def log_handoff(brief: HandoffBrief) -> None:
    """Append handoff record to the central handoff log."""
    HANDOFF_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HANDOFF_LOG_PATH.open("a") as f:
        f.write(json.dumps(brief.to_dict()) + "\n")


ACTIVE_HANDOFF_FILENAME = "active-handoff.md"


def write_active_handoff(brief: GuardrailedHandoffBrief, repo_path: Path) -> Path:
    """Write the active handoff to the canonical path that receiving agents read.

    This is the stable file that GEMINI.md/AGENTS.md tell agents to check.
    Timestamped handoffs are the log; this is the live contract.
    """
    handoff_dir = repo_path / ".conductor"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    out_path = handoff_dir / ACTIVE_HANDOFF_FILENAME
    out_path.write_text(format_markdown(brief))
    return out_path


def clear_active_handoff(repo_path: Path) -> bool:
    """Clear the active handoff after verification passes. Returns True if cleared."""
    path = repo_path / ".conductor" / ACTIVE_HANDOFF_FILENAME
    if path.exists():
        path.unlink()
        return True
    return False


def read_active_handoff(repo_path: Path) -> dict[str, str] | None:
    """Read the active handoff metadata (from_agent, to_agent, work_type) if one exists.

    Returns None if no active handoff. Parses the markdown header for key fields.
    """
    path = repo_path / ".conductor" / ACTIVE_HANDOFF_FILENAME
    if not path.exists():
        return None
    content = path.read_text()
    # Parse key fields from markdown
    result: dict[str, str] = {}
    for line in content.splitlines():
        if line.startswith("# Agent Handoff:"):
            parts = line.replace("# Agent Handoff:", "").strip().split("→")
            if len(parts) == 2:
                result["from_agent"] = parts[0].strip()
                result["to_agent"] = parts[1].strip()
        elif line.startswith("**Work Type:**"):
            result["work_type"] = line.replace("**Work Type:**", "").strip()
        elif "CROSS-VERIFICATION REQUIRED" in line:
            result["verification_required"] = "true"
    return result if result else None
