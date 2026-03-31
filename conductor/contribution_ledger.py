"""Dispatch receipt — structured record of each agent handoff and return.

Each dispatch creates a YAML receipt with two halves:
  - OutboundRecord: what was sent (prompt, context, scope, constraints)
  - ReturnRecord: what came back (outcome, violations, energy cost)

Storage: .conductor/dispatch-ledger/D-{YYYY-MMDD}-{NNN}.yaml
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .constants import STATE_DIR


DISPATCH_LEDGER_DIR = STATE_DIR / "dispatch-ledger"


def generate_dispatch_id() -> str:
    """Generate a dispatch ID in format D-YYYY-MMDD-NNN."""
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y-%m%d")
    # Find next sequence number
    ledger_dir = DISPATCH_LEDGER_DIR
    if not ledger_dir.exists():
        return f"D-{date_part}-001"
    existing = [
        f.stem for f in ledger_dir.glob(f"D-{date_part}-*.yaml")
    ]
    if not existing:
        return f"D-{date_part}-001"
    nums = []
    for name in existing:
        match = re.search(r"-(\d{3})$", name)
        if match:
            nums.append(int(match.group(1)))
    next_num = max(nums, default=0) + 1
    return f"D-{date_part}-{next_num:03d}"


@dataclass
class OutboundRecord:
    """What was sent to the agent at dispatch time."""

    dispatched_at: str
    prompt_hash: str
    envelope_path: str
    context_provided: list[str] = field(default_factory=list)
    context_missing: list[str] = field(default_factory=list)
    work_description: str = ""
    files_expected: list[str] = field(default_factory=list)
    write_permission: str = "direct_edit"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispatched_at": self.dispatched_at,
            "prompt_hash": self.prompt_hash,
            "envelope_path": self.envelope_path,
            "context_provided": self.context_provided,
            "context_missing": self.context_missing,
            "work_description": self.work_description,
            "files_expected": self.files_expected,
            "write_permission": self.write_permission,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OutboundRecord:
        return cls(
            dispatched_at=str(d.get("dispatched_at", "")),
            prompt_hash=str(d.get("prompt_hash", "")),
            envelope_path=str(d.get("envelope_path", "")),
            context_provided=list(d.get("context_provided", [])),
            context_missing=list(d.get("context_missing", [])),
            work_description=str(d.get("work_description", "")),
            files_expected=list(d.get("files_expected", [])),
            write_permission=str(d.get("write_permission", "direct_edit")),
        )


@dataclass
class ReturnRecord:
    """What came back when the agent's work was reviewed."""

    completed_at: str = ""
    outcome: str = "pending"  # clean | partial_fix | full_revert | abandoned
    rating: int = 0  # 1-10
    files_touched: list[str] = field(default_factory=list)
    files_unexpected: list[str] = field(default_factory=list)
    violations: list[dict[str, str]] = field(default_factory=list)
    fix_commits: int = 0
    what_worked: str = ""
    what_failed: str = ""
    prompt_patches_generated: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "completed_at": self.completed_at,
            "outcome": self.outcome,
            "rating": self.rating,
            "files_touched": self.files_touched,
            "files_unexpected": self.files_unexpected,
            "violations": self.violations,
            "fix_commits": self.fix_commits,
            "what_worked": self.what_worked,
            "what_failed": self.what_failed,
            "prompt_patches_generated": self.prompt_patches_generated,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReturnRecord:
        return cls(
            completed_at=str(d.get("completed_at", "")),
            outcome=str(d.get("outcome", "pending")),
            rating=int(d.get("rating", 0)),
            files_touched=list(d.get("files_touched", [])),
            files_unexpected=list(d.get("files_unexpected", [])),
            violations=list(d.get("violations", [])),
            fix_commits=int(d.get("fix_commits", 0)),
            what_worked=str(d.get("what_worked", "")),
            what_failed=str(d.get("what_failed", "")),
            prompt_patches_generated=list(d.get("prompt_patches_generated", [])),
        )


@dataclass
class DispatchReceipt:
    """Full dispatch record — outbound + return."""

    id: str
    agent: str
    model: str
    repo: str
    organ: str
    work_type: str
    cognitive_class: str
    outbound: OutboundRecord
    return_record: ReturnRecord | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "agent": self.agent,
            "model": self.model,
            "repo": self.repo,
            "organ": self.organ,
            "work_type": self.work_type,
            "cognitive_class": self.cognitive_class,
            "outbound": self.outbound.to_dict(),
        }
        if self.return_record is not None:
            d["return"] = self.return_record.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DispatchReceipt:
        ret = d.get("return")
        return cls(
            id=str(d.get("id", "")),
            agent=str(d.get("agent", "")),
            model=str(d.get("model", "")),
            repo=str(d.get("repo", "")),
            organ=str(d.get("organ", "")),
            work_type=str(d.get("work_type", "")),
            cognitive_class=str(d.get("cognitive_class", "")),
            outbound=OutboundRecord.from_dict(d.get("outbound", {})),
            return_record=ReturnRecord.from_dict(ret) if ret else None,
        )

    @property
    def is_closed(self) -> bool:
        return self.return_record is not None


class ReceiptStore:
    """YAML-backed storage for dispatch receipts."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or DISPATCH_LEDGER_DIR

    def save(self, receipt: DispatchReceipt) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self.base_dir / f"{receipt.id}.yaml"
        path.write_text(yaml.dump(receipt.to_dict(), default_flow_style=False, sort_keys=False))
        return path

    def load(self, dispatch_id: str) -> DispatchReceipt | None:
        path = self.base_dir / f"{dispatch_id}.yaml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text())
        if not data:
            return None
        return DispatchReceipt.from_dict(data)

    def list_all(self) -> list[DispatchReceipt]:
        if not self.base_dir.exists():
            return []
        receipts = []
        for f in sorted(self.base_dir.glob("D-*.yaml")):
            data = yaml.safe_load(f.read_text())
            if data:
                receipts.append(DispatchReceipt.from_dict(data))
        return receipts

    def list_pending(self) -> list[DispatchReceipt]:
        return [r for r in self.list_all() if not r.is_closed]

    def list_by_agent(self, agent: str) -> list[DispatchReceipt]:
        return [r for r in self.list_all() if r.agent == agent]
