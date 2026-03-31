"""Timecard — punch-in, punch-out, and content-forensic signatures.

Records the baseline state at dispatch (punch-in) and the delta at return
(punch-out). Signatures bind agent identity to specific diffs via content
hashes for attribution and audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .constants import STATE_DIR


TIMECARD_DIR = STATE_DIR / "timecards"


@dataclass
class ContextEntry:
    """A file provided as context in the dispatch container."""

    path: str = ""
    sha: str = ""
    bytes_: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "sha": self.sha, "bytes": self.bytes_}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ContextEntry:
        return cls(
            path=str(d.get("path", "")),
            sha=str(d.get("sha", "")),
            bytes_=int(d.get("bytes", 0)),
        )


@dataclass
class ScopeBoundary:
    """Defines what the agent is and isn't allowed to touch."""

    files_in_scope: list[str] = field(default_factory=list)
    files_forbidden: list[str] = field(default_factory=list)
    actions_permitted: list[str] = field(default_factory=list)
    actions_forbidden: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_in_scope": self.files_in_scope,
            "files_forbidden": self.files_forbidden,
            "actions_permitted": self.actions_permitted,
            "actions_forbidden": self.actions_forbidden,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScopeBoundary:
        return cls(
            files_in_scope=list(d.get("files_in_scope", [])),
            files_forbidden=list(d.get("files_forbidden", [])),
            actions_permitted=list(d.get("actions_permitted", [])),
            actions_forbidden=list(d.get("actions_forbidden", [])),
        )


@dataclass
class PunchIn:
    """State at dispatch time — the baseline."""

    timestamp: str
    dispatched_by: str
    repo: str
    branch: str
    head_sha: str
    working_tree_clean: bool
    envelope_sha: str
    work_type: str
    write_permission: str
    context_manifest: list[ContextEntry] = field(default_factory=list)
    constraints_injected: list[dict[str, str]] = field(default_factory=list)
    scope_boundary: ScopeBoundary = field(default_factory=ScopeBoundary)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "dispatched_by": self.dispatched_by,
            "repo": self.repo,
            "branch": self.branch,
            "head_sha": self.head_sha,
            "working_tree_clean": self.working_tree_clean,
            "envelope_sha": self.envelope_sha,
            "work_type": self.work_type,
            "write_permission": self.write_permission,
            "context_manifest": [c.to_dict() for c in self.context_manifest],
            "constraints_injected": self.constraints_injected,
            "scope_boundary": self.scope_boundary.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PunchIn:
        return cls(
            timestamp=str(d.get("timestamp", "")),
            dispatched_by=str(d.get("dispatched_by", "")),
            repo=str(d.get("repo", "")),
            branch=str(d.get("branch", "")),
            head_sha=str(d.get("head_sha", "")),
            working_tree_clean=bool(d.get("working_tree_clean", True)),
            envelope_sha=str(d.get("envelope_sha", "")),
            work_type=str(d.get("work_type", "")),
            write_permission=str(d.get("write_permission", "")),
            context_manifest=[
                ContextEntry.from_dict(c) for c in d.get("context_manifest", [])
            ],
            constraints_injected=list(d.get("constraints_injected", [])),
            scope_boundary=ScopeBoundary.from_dict(d.get("scope_boundary", {})),
        )


@dataclass
class PunchOut:
    """State at return time — what the agent delivered."""

    timestamp: str = ""
    reviewed_by: str = ""
    head_sha: str = ""
    commits_by_agent: int = 0
    commits_to_fix: int = 0
    files_created: list[dict[str, Any]] = field(default_factory=list)
    files_outside_scope: list[str] = field(default_factory=list)
    tests_added: int = 0
    tests_broken: int = 0
    self_report: dict[str, Any] = field(default_factory=dict)
    outcome: str = "pending"
    rating: int = 0
    violations: list[dict[str, str]] = field(default_factory=list)
    what_survived: list[str] = field(default_factory=list)
    what_reverted: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "reviewed_by": self.reviewed_by,
            "head_sha": self.head_sha,
            "commits_by_agent": self.commits_by_agent,
            "commits_to_fix": self.commits_to_fix,
            "files_created": self.files_created,
            "files_outside_scope": self.files_outside_scope,
            "tests_added": self.tests_added,
            "tests_broken": self.tests_broken,
            "self_report": self.self_report,
            "outcome": self.outcome,
            "rating": self.rating,
            "violations": self.violations,
            "what_survived": self.what_survived,
            "what_reverted": self.what_reverted,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PunchOut:
        return cls(
            timestamp=str(d.get("timestamp", "")),
            reviewed_by=str(d.get("reviewed_by", "")),
            head_sha=str(d.get("head_sha", "")),
            commits_by_agent=int(d.get("commits_by_agent", 0)),
            commits_to_fix=int(d.get("commits_to_fix", 0)),
            files_created=list(d.get("files_created", [])),
            files_outside_scope=list(d.get("files_outside_scope", [])),
            tests_added=int(d.get("tests_added", 0)),
            tests_broken=int(d.get("tests_broken", 0)),
            self_report=dict(d.get("self_report", {})),
            outcome=str(d.get("outcome", "pending")),
            rating=int(d.get("rating", 0)),
            violations=list(d.get("violations", [])),
            what_survived=list(d.get("what_survived", [])),
            what_reverted=list(d.get("what_reverted", [])),
        )


@dataclass
class Signature:
    """Content-forensic attribution — binds agent identity to a diff."""

    dispatch_id: str
    agent: str
    model: str
    envelope_hash: str = ""
    baseline_tree_hash: str = ""
    return_tree_hash: str = ""
    diff_hash: str = ""
    commits_attributed: list[dict[str, str]] = field(default_factory=list)

    @property
    def co_author_line(self) -> str:
        return f"Co-Authored-By: {self.agent} ({self.model}) <noreply@dispatch>"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispatch_id": self.dispatch_id,
            "agent": self.agent,
            "model": self.model,
            "envelope_hash": self.envelope_hash,
            "baseline_tree_hash": self.baseline_tree_hash,
            "return_tree_hash": self.return_tree_hash,
            "diff_hash": self.diff_hash,
            "commits_attributed": self.commits_attributed,
            "co_author_line": self.co_author_line,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Signature:
        return cls(
            dispatch_id=str(d.get("dispatch_id", "")),
            agent=str(d.get("agent", "")),
            model=str(d.get("model", "")),
            envelope_hash=str(d.get("envelope_hash", "")),
            baseline_tree_hash=str(d.get("baseline_tree_hash", "")),
            return_tree_hash=str(d.get("return_tree_hash", "")),
            diff_hash=str(d.get("diff_hash", "")),
            commits_attributed=list(d.get("commits_attributed", [])),
        )


@dataclass
class Timecard:
    """Complete timecard — punch-in + punch-out + signature."""

    dispatch_id: str
    punch_in: PunchIn
    punch_out: PunchOut | None = None
    signature: Signature | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "dispatch_id": self.dispatch_id,
            "punch_in": self.punch_in.to_dict(),
        }
        if self.punch_out is not None:
            d["punch_out"] = self.punch_out.to_dict()
        if self.signature is not None:
            d["signature"] = self.signature.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Timecard:
        pout = d.get("punch_out")
        sig = d.get("signature")
        return cls(
            dispatch_id=str(d.get("dispatch_id", "")),
            punch_in=PunchIn.from_dict(d.get("punch_in", {})),
            punch_out=PunchOut.from_dict(pout) if pout else None,
            signature=Signature.from_dict(sig) if sig else None,
        )


class TimecardStore:
    """YAML-backed storage for timecards."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or TIMECARD_DIR

    def save(self, tc: Timecard) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self.base_dir / f"{tc.dispatch_id}.yaml"
        path.write_text(yaml.dump(tc.to_dict(), default_flow_style=False, sort_keys=False))
        return path

    def load(self, dispatch_id: str) -> Timecard | None:
        path = self.base_dir / f"{dispatch_id}.yaml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text())
        if not data:
            return None
        return Timecard.from_dict(data)
