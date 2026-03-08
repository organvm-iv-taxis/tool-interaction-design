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
