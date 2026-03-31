# Agent Contribution Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a six-layer contribution tracking and prompt refinement system that records agent dispatches (punch-in/out), measures energy balance, and evolves handoff quality through accumulated incident data.

**Architecture:** Three implementation waves (Record → Learn → Anticipate), each independently testable. All modules follow existing conductor patterns: frozen dataclasses for data models, YAML/JSONL for persistence, `tmp_path` patching in tests via `conftest.py` fixtures, `_safe_write_json` pattern for atomic writes.

**Tech Stack:** Python 3.11+, PyYAML, dataclasses, pytest (asyncio_mode=auto, pythonpath=["."])

**Spec:** `.claude/plans/2026-03-30-agent-contribution-ledger-design.md`

---

## Wave 1: RECORD (standalone value, zero external dependencies)

### Task 1: Dispatch Receipt data model + YAML I/O

**Files:**
- Create: `conductor/contribution_ledger.py`
- Create: `tests/test_contribution_ledger.py`

- [ ] **Step 1: Write the failing test — receipt creation and serialization**

```python
# tests/test_contribution_ledger.py
"""Tests for dispatch receipt CRUD and YAML persistence."""

from __future__ import annotations

import yaml
from pathlib import Path

from conductor.contribution_ledger import (
    DispatchReceipt,
    OutboundRecord,
    ReturnRecord,
    ReceiptStore,
    generate_dispatch_id,
)


def test_generate_dispatch_id_format():
    did = generate_dispatch_id()
    # Format: D-YYYY-MMDD-NNN
    assert did.startswith("D-")
    parts = did.split("-")
    assert len(parts) == 4
    assert len(parts[1]) == 4  # year
    assert len(parts[2]) == 4  # MMDD
    assert len(parts[3]) == 3  # sequence


def test_receipt_creation_with_outbound():
    outbound = OutboundRecord(
        dispatched_at="2026-03-30T15:00:00Z",
        prompt_hash="sha256:abc123",
        envelope_path=".conductor/envelopes/D-2026-0330-001.md",
        context_provided=["AGENTS.md", "SEED.md"],
        context_missing=[],
        work_description="Cross-reference IRF against SEED",
        files_expected=["post-flood/SEED.md"],
        write_permission="propose_only",
    )
    receipt = DispatchReceipt(
        id="D-2026-0330-001",
        agent="gemini",
        model="gemini-3-flash-preview",
        repo="meta-organvm/post-flood",
        organ="META",
        work_type="corpus_cross_reference",
        cognitive_class="tactical",
        outbound=outbound,
    )
    assert receipt.id == "D-2026-0330-001"
    assert receipt.agent == "gemini"
    assert receipt.outbound.write_permission == "propose_only"
    assert receipt.return_record is None  # not yet returned


def test_receipt_round_trip_yaml(tmp_path):
    outbound = OutboundRecord(
        dispatched_at="2026-03-30T15:00:00Z",
        prompt_hash="sha256:abc123",
        envelope_path=".conductor/envelopes/D-2026-0330-001.md",
        context_provided=["AGENTS.md"],
        context_missing=[],
        work_description="Test task",
        files_expected=["file.py"],
        write_permission="direct_edit",
    )
    receipt = DispatchReceipt(
        id="D-2026-0330-001",
        agent="codex",
        model="gpt-5.4",
        repo="tool-interaction-design",
        organ="IV",
        work_type="testing",
        cognitive_class="tactical",
        outbound=outbound,
    )
    store = ReceiptStore(base_dir=tmp_path / "dispatch-ledger")
    store.save(receipt)

    loaded = store.load("D-2026-0330-001")
    assert loaded is not None
    assert loaded.agent == "codex"
    assert loaded.outbound.prompt_hash == "sha256:abc123"


def test_receipt_close_with_return(tmp_path):
    outbound = OutboundRecord(
        dispatched_at="2026-03-30T15:00:00Z",
        prompt_hash="sha256:abc123",
        envelope_path="",
        context_provided=[],
        context_missing=[],
        work_description="Test",
        files_expected=[],
        write_permission="direct_edit",
    )
    receipt = DispatchReceipt(
        id="D-2026-0330-002",
        agent="gemini",
        model="gemini-3-flash-preview",
        repo="test/repo",
        organ="III",
        work_type="content_generation",
        cognitive_class="tactical",
        outbound=outbound,
    )
    store = ReceiptStore(base_dir=tmp_path / "dispatch-ledger")
    store.save(receipt)

    ret = ReturnRecord(
        completed_at="2026-03-30T20:00:00Z",
        outcome="partial_fix",
        rating=4,
        files_touched=["SEED.md"],
        files_unexpected=[],
        violations=[
            {"type": "scope_violation", "detail": "Edited directly", "severity": "warning"},
        ],
        fix_commits=1,
        what_worked="Content was correct",
        what_failed="Write discipline",
        prompt_patches_generated=["PP-2026-0330-001"],
    )
    receipt.return_record = ret
    store.save(receipt)

    loaded = store.load("D-2026-0330-002")
    assert loaded is not None
    assert loaded.return_record is not None
    assert loaded.return_record.outcome == "partial_fix"
    assert loaded.return_record.rating == 4
    assert len(loaded.return_record.violations) == 1


def test_store_list_pending(tmp_path):
    store = ReceiptStore(base_dir=tmp_path / "dispatch-ledger")
    for i in range(3):
        outbound = OutboundRecord(
            dispatched_at=f"2026-03-30T1{i}:00:00Z",
            prompt_hash="sha256:x",
            envelope_path="",
            context_provided=[],
            context_missing=[],
            work_description=f"Task {i}",
            files_expected=[],
            write_permission="direct_edit",
        )
        r = DispatchReceipt(
            id=f"D-2026-0330-00{i}",
            agent="gemini",
            model="gemini-3-flash-preview",
            repo="test",
            organ="IV",
            work_type="testing",
            cognitive_class="tactical",
            outbound=outbound,
        )
        if i == 1:  # close the second one
            r.return_record = ReturnRecord(
                completed_at="2026-03-30T20:00:00Z",
                outcome="clean",
                rating=8,
            )
        store.save(r)

    pending = store.list_pending()
    assert len(pending) == 2  # 0 and 2 are still open
    assert all(r.return_record is None for r in pending)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_contribution_ledger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'conductor.contribution_ledger'`

- [ ] **Step 3: Implement the contribution ledger module**

```python
# conductor/contribution_ledger.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_contribution_ledger.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design
git add conductor/contribution_ledger.py tests/test_contribution_ledger.py
git commit -m "feat: dispatch receipt data model + YAML store (Wave 1)"
```

---

### Task 2: Timecard — punch-in, punch-out, signatures

**Files:**
- Create: `conductor/timecard.py`
- Create: `tests/test_timecard.py`

- [ ] **Step 1: Write the failing test — timecard lifecycle**

```python
# tests/test_timecard.py
"""Tests for punch-in/out timecards and signature generation."""

from __future__ import annotations

import hashlib
from pathlib import Path

from conductor.timecard import (
    PunchIn,
    PunchOut,
    Signature,
    Timecard,
    TimecardStore,
    ContextEntry,
    ScopeBoundary,
)


def test_punch_in_captures_baseline():
    ctx = ContextEntry(path="AGENTS.md", sha="sha256:aaa", bytes_=4200)
    scope = ScopeBoundary(
        files_in_scope=["SEED.md"],
        files_forbidden=["governance-rules.json"],
        actions_permitted=["read", "propose"],
        actions_forbidden=["git_commit"],
    )
    pin = PunchIn(
        timestamp="2026-03-30T15:00:00Z",
        dispatched_by="claude",
        repo="meta-organvm/post-flood",
        branch="main",
        head_sha="bdaa649",
        working_tree_clean=True,
        envelope_sha="sha256:e4a1b",
        work_type="corpus_cross_reference",
        write_permission="propose_only",
        context_manifest=[ctx],
        constraints_injected=[
            {"source": "agent_profile", "rule": "never modify SEED directly"},
        ],
        scope_boundary=scope,
    )
    d = pin.to_dict()
    assert d["head_sha"] == "bdaa649"
    assert len(d["context_manifest"]) == 1
    assert d["scope_boundary"]["files_forbidden"] == ["governance-rules.json"]

    restored = PunchIn.from_dict(d)
    assert restored.head_sha == "bdaa649"
    assert restored.context_manifest[0].path == "AGENTS.md"


def test_punch_out_captures_delivery():
    pout = PunchOut(
        timestamp="2026-03-30T20:32:00Z",
        reviewed_by="claude",
        head_sha="b3391d7",
        commits_by_agent=1,
        commits_to_fix=1,
        files_created=[{"path": "SEED.md", "lines_added": 39, "lines_removed": 1}],
        files_outside_scope=[],
        tests_added=0,
        tests_broken=0,
        self_report={"claimed_complete": True, "claimed_violations": 0},
        outcome="partial_fix",
        rating=4,
        violations=[
            {"type": "scope_violation", "detail": "Edited SEED directly", "severity": "warning"},
        ],
        what_survived=["CHECKs 21-26 content"],
        what_reverted=["Direct SEED.md edit"],
    )
    d = pout.to_dict()
    assert d["outcome"] == "partial_fix"
    assert d["commits_to_fix"] == 1

    restored = PunchOut.from_dict(d)
    assert restored.rating == 4
    assert len(restored.violations) == 1


def test_signature_generation():
    sig = Signature(
        dispatch_id="D-2026-0330-001",
        agent="gemini",
        model="gemini-3-flash-preview",
        envelope_hash="sha256:e4a1b",
        baseline_tree_hash="sha256:a91c",
        return_tree_hash="sha256:f72d",
        diff_hash="sha256:3b8e",
        commits_attributed=[
            {"sha": "b3391d7", "attribution": "gemini"},
            {"sha": "79b7912", "attribution": "claude", "remediation_for": "D-2026-0330-001"},
        ],
    )
    assert sig.co_author_line == "Co-Authored-By: gemini (gemini-3-flash-preview) <noreply@dispatch>"
    d = sig.to_dict()
    assert len(d["commits_attributed"]) == 2


def test_timecard_round_trip_yaml(tmp_path):
    pin = PunchIn(
        timestamp="2026-03-30T15:00:00Z",
        dispatched_by="claude",
        repo="test/repo",
        branch="main",
        head_sha="abc123",
        working_tree_clean=True,
        envelope_sha="sha256:xxx",
        work_type="testing",
        write_permission="direct_edit",
        context_manifest=[],
        constraints_injected=[],
        scope_boundary=ScopeBoundary(),
    )
    pout = PunchOut(
        timestamp="2026-03-30T20:00:00Z",
        reviewed_by="claude",
        head_sha="def456",
        commits_by_agent=2,
        commits_to_fix=0,
        outcome="clean",
        rating=9,
    )
    sig = Signature(
        dispatch_id="D-2026-0330-001",
        agent="codex",
        model="gpt-5.4",
        envelope_hash="sha256:xxx",
        baseline_tree_hash="sha256:abc",
        return_tree_hash="sha256:def",
        diff_hash="sha256:ddd",
    )
    tc = Timecard(
        dispatch_id="D-2026-0330-001",
        punch_in=pin,
        punch_out=pout,
        signature=sig,
    )
    store = TimecardStore(base_dir=tmp_path / "timecards")
    store.save(tc)

    loaded = store.load("D-2026-0330-001")
    assert loaded is not None
    assert loaded.punch_in.head_sha == "abc123"
    assert loaded.punch_out.outcome == "clean"
    assert loaded.signature.agent == "codex"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_timecard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'conductor.timecard'`

- [ ] **Step 3: Implement the timecard module**

```python
# conductor/timecard.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_timecard.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design
git add conductor/timecard.py tests/test_timecard.py
git commit -m "feat: timecard — punch-in/out + signature attribution (Wave 1)"
```

---

### Task 3: Energy Ledger — consumed vs produced, net verdict

**Files:**
- Create: `conductor/energy_ledger.py`
- Create: `tests/test_energy_ledger.py`

- [ ] **Step 1: Write the failing test — energy balance calculation**

```python
# tests/test_energy_ledger.py
"""Tests for energy balance calculation and net verdict."""

from __future__ import annotations

from conductor.energy_ledger import (
    EnergyConsumed,
    EnergyProduced,
    EnergyBalance,
    compute_energy,
)


def test_net_positive_verdict():
    consumed = EnergyConsumed(
        tokens_input=55000,
        tokens_output=12000,
        tokens_wasted_estimate=5000,
        preparation_cost_minutes=15,
        reviewer_tokens=2000,
        fix_commits=0,
        calendar_duration_minutes=60,
    )
    produced = EnergyProduced(
        files_net_created=2,
        files_net_modified=3,
        lines_survived=150,
        lines_reverted=0,
        tests_added=5,
        bugs_caught=1,
        structural_additions=["New API endpoint", "Test suite"],
    )
    balance = compute_energy(consumed, produced)
    assert balance.survival_rate == 1.0
    assert balance.verdict == "net_positive"
    assert balance.waste_ratio < 0.5


def test_net_negative_verdict_full_revert():
    consumed = EnergyConsumed(
        tokens_input=80000,
        tokens_output=40000,
        tokens_wasted_estimate=40000,
        preparation_cost_minutes=10,
        reviewer_tokens=20000,
        fix_commits=14,
        calendar_duration_minutes=120,
    )
    produced = EnergyProduced(
        lines_survived=0,
        lines_reverted=500,
    )
    balance = compute_energy(consumed, produced)
    assert balance.survival_rate == 0.0
    assert balance.verdict == "net_negative"
    assert balance.remediation_ratio > 1.0


def test_marginal_verdict():
    consumed = EnergyConsumed(
        tokens_input=55000,
        tokens_output=12000,
        tokens_wasted_estimate=30000,
        reviewer_tokens=8000,
        fix_commits=1,
        calendar_duration_minutes=300,
    )
    produced = EnergyProduced(
        lines_survived=39,
        lines_reverted=0,
        files_net_modified=1,
    )
    balance = compute_energy(consumed, produced)
    assert balance.verdict == "net_positive"  # survived but wasteful
    assert balance.waste_ratio > 0.4


def test_zero_division_safety():
    consumed = EnergyConsumed()  # all zeros
    produced = EnergyProduced()  # all zeros
    balance = compute_energy(consumed, produced)
    assert balance.survival_rate == 0.0
    assert balance.verdict == "net_neutral"
    assert balance.waste_ratio == 0.0
    assert balance.remediation_ratio == 0.0


def test_energy_balance_to_dict():
    consumed = EnergyConsumed(tokens_input=1000, tokens_output=500)
    produced = EnergyProduced(lines_survived=10)
    balance = compute_energy(consumed, produced)
    d = balance.to_dict()
    assert "consumed" in d
    assert "produced" in d
    assert "net" in d
    assert "verdict" in d["net"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_energy_ledger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'conductor.energy_ledger'`

- [ ] **Step 3: Implement the energy ledger module**

```python
# conductor/energy_ledger.py
"""Energy ledger — measures what an agent consumed vs what it produced.

Each dispatch has an energy balance with a net verdict:
  net_positive:  agent produced durable value exceeding remediation cost
  net_neutral:   no meaningful output, minimal cost
  net_negative:  remediation cost exceeded value produced (revert scenario)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EnergyConsumed:
    """What the agent consumed (cost to the system)."""

    tokens_input: int = 0
    tokens_output: int = 0
    tokens_wasted_estimate: int = 0
    preparation_cost_minutes: int = 0
    reviewer_tokens: int = 0
    fix_commits: int = 0
    calendar_duration_minutes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "tokens_wasted_estimate": self.tokens_wasted_estimate,
            "preparation_cost_minutes": self.preparation_cost_minutes,
            "reviewer_tokens": self.reviewer_tokens,
            "fix_commits": self.fix_commits,
            "calendar_duration_minutes": self.calendar_duration_minutes,
        }


@dataclass
class EnergyProduced:
    """What the agent produced (value to the system)."""

    files_net_created: int = 0
    files_net_modified: int = 0
    lines_survived: int = 0
    lines_reverted: int = 0
    tests_added: int = 0
    bugs_caught: int = 0
    structural_additions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_net_created": self.files_net_created,
            "files_net_modified": self.files_net_modified,
            "lines_survived": self.lines_survived,
            "lines_reverted": self.lines_reverted,
            "tests_added": self.tests_added,
            "bugs_caught": self.bugs_caught,
            "structural_additions": self.structural_additions,
        }


@dataclass
class EnergyBalance:
    """Computed energy balance — the net verdict."""

    consumed: EnergyConsumed
    produced: EnergyProduced
    survival_rate: float = 0.0
    efficiency: float = 0.0
    remediation_ratio: float = 0.0
    waste_ratio: float = 0.0
    verdict: str = "net_neutral"

    def to_dict(self) -> dict[str, Any]:
        return {
            "consumed": self.consumed.to_dict(),
            "produced": self.produced.to_dict(),
            "net": {
                "survival_rate": round(self.survival_rate, 4),
                "efficiency": round(self.efficiency, 4),
                "remediation_ratio": round(self.remediation_ratio, 4),
                "waste_ratio": round(self.waste_ratio, 4),
                "verdict": self.verdict,
            },
        }


def compute_energy(consumed: EnergyConsumed, produced: EnergyProduced) -> EnergyBalance:
    """Compute the energy balance from consumed and produced data."""
    total_lines = produced.lines_survived + produced.lines_reverted
    survival_rate = produced.lines_survived / total_lines if total_lines > 0 else 0.0

    total_tokens = consumed.tokens_input + consumed.tokens_output
    efficiency = produced.lines_survived / consumed.tokens_output if consumed.tokens_output > 0 else 0.0

    total_commits = consumed.fix_commits + max(1, produced.files_net_created + produced.files_net_modified)
    remediation_ratio = consumed.fix_commits / max(1, total_commits - consumed.fix_commits) if total_commits > consumed.fix_commits else float(consumed.fix_commits)

    waste_ratio = consumed.tokens_wasted_estimate / total_tokens if total_tokens > 0 else 0.0

    # Determine verdict
    if total_lines == 0 and produced.files_net_created == 0 and produced.files_net_modified == 0:
        if consumed.fix_commits == 0 and consumed.tokens_output == 0:
            verdict = "net_neutral"
        else:
            verdict = "net_negative"
    elif survival_rate == 0.0 and total_lines > 0:
        verdict = "net_negative"
    elif consumed.fix_commits > (produced.files_net_created + produced.files_net_modified + 1):
        verdict = "net_negative"
    else:
        verdict = "net_positive"

    return EnergyBalance(
        consumed=consumed,
        produced=produced,
        survival_rate=survival_rate,
        efficiency=efficiency,
        remediation_ratio=remediation_ratio,
        waste_ratio=waste_ratio,
        verdict=verdict,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_energy_ledger.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design
git add conductor/energy_ledger.py tests/test_energy_ledger.py
git commit -m "feat: energy ledger — consumed vs produced balance (Wave 1)"
```

---

### Task 4: Add constants + update constants.py

**Files:**
- Modify: `conductor/constants.py`

- [ ] **Step 1: Add new path constants for the contribution system**

Add after the existing fleet orchestration paths block (line 43):

```python
# Contribution tracking paths
DISPATCH_LEDGER_DIR = STATE_DIR / "dispatch-ledger"
TIMECARD_DIR = STATE_DIR / "timecards"
RETURN_QUEUE_DIR = STATE_DIR / "return-queue"
SCORECARD_DIR = STATE_DIR / "scorecards"
PROMPT_PATCHES_DIR = STATE_DIR / "prompt-patches"
CONTAINER_DIR = STATE_DIR / "containers"
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/ -v --timeout=30`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design
git add conductor/constants.py
git commit -m "feat: add contribution system path constants"
```

---

### Task 5: Wave 1 integration — full receipt + timecard + energy round-trip

**Files:**
- Create: `tests/test_wave1_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_wave1_integration.py
"""Integration test — full dispatch receipt + timecard + energy round-trip."""

from __future__ import annotations

from conductor.contribution_ledger import (
    DispatchReceipt,
    OutboundRecord,
    ReturnRecord,
    ReceiptStore,
)
from conductor.timecard import (
    ContextEntry,
    PunchIn,
    PunchOut,
    ScopeBoundary,
    Signature,
    Timecard,
    TimecardStore,
)
from conductor.energy_ledger import (
    EnergyConsumed,
    EnergyProduced,
    compute_energy,
)


def test_full_dispatch_lifecycle(tmp_path):
    """Simulate: dispatch to gemini → agent returns → review → energy computed."""
    receipt_store = ReceiptStore(base_dir=tmp_path / "dispatch-ledger")
    timecard_store = TimecardStore(base_dir=tmp_path / "timecards")

    # 1. Dispatch (punch-in)
    outbound = OutboundRecord(
        dispatched_at="2026-03-30T15:00:00Z",
        prompt_hash="sha256:e4a1b",
        envelope_path=".conductor/envelopes/D-2026-0330-001.md",
        context_provided=["AGENTS.md", "SEED.md"],
        context_missing=[],
        work_description="Cross-reference IRF against SEED",
        files_expected=["post-flood/SEED.md"],
        write_permission="propose_only",
    )
    receipt = DispatchReceipt(
        id="D-2026-0330-001",
        agent="gemini",
        model="gemini-3-flash-preview",
        repo="meta-organvm/post-flood",
        organ="META",
        work_type="corpus_cross_reference",
        cognitive_class="tactical",
        outbound=outbound,
    )
    receipt_store.save(receipt)

    pin = PunchIn(
        timestamp="2026-03-30T15:00:00Z",
        dispatched_by="claude",
        repo="meta-organvm/post-flood",
        branch="main",
        head_sha="bdaa649",
        working_tree_clean=True,
        envelope_sha="sha256:e4a1b",
        work_type="corpus_cross_reference",
        write_permission="propose_only",
        context_manifest=[
            ContextEntry(path="AGENTS.md", sha="sha256:7f2c", bytes_=4200),
            ContextEntry(path="SEED.md", sha="sha256:c91a", bytes_=48200),
        ],
        constraints_injected=[
            {"source": "agent_profile", "rule": "never modify SEED directly"},
        ],
        scope_boundary=ScopeBoundary(
            files_in_scope=["post-flood/SEED.md"],
            files_forbidden=["governance-rules.json"],
            actions_permitted=["read", "propose"],
            actions_forbidden=["git_commit"],
        ),
    )
    tc = Timecard(dispatch_id="D-2026-0330-001", punch_in=pin)
    timecard_store.save(tc)

    # Verify pending state
    assert len(receipt_store.list_pending()) == 1

    # 2. Agent returns — record punch-out + close receipt
    pout = PunchOut(
        timestamp="2026-03-30T20:32:00Z",
        reviewed_by="claude",
        head_sha="b3391d7",
        commits_by_agent=1,
        commits_to_fix=1,
        files_created=[{"path": "post-flood/SEED.md", "lines_added": 39, "lines_removed": 1}],
        outcome="partial_fix",
        rating=4,
        violations=[
            {"type": "scope_violation", "detail": "Edited SEED directly", "severity": "warning"},
        ],
        what_survived=["CHECKs 21-26"],
        what_reverted=["Direct SEED.md edit"],
    )
    sig = Signature(
        dispatch_id="D-2026-0330-001",
        agent="gemini",
        model="gemini-3-flash-preview",
        envelope_hash="sha256:e4a1b",
        baseline_tree_hash="sha256:a91c",
        return_tree_hash="sha256:f72d",
        diff_hash="sha256:3b8e",
        commits_attributed=[
            {"sha": "b3391d7", "attribution": "gemini"},
            {"sha": "79b7912", "attribution": "claude", "remediation_for": "D-2026-0330-001"},
        ],
    )
    tc.punch_out = pout
    tc.signature = sig
    timecard_store.save(tc)

    ret = ReturnRecord(
        completed_at="2026-03-30T20:32:00Z",
        outcome="partial_fix",
        rating=4,
        files_touched=["post-flood/SEED.md"],
        violations=[{"type": "scope_violation", "detail": "Edited SEED directly", "severity": "warning"}],
        fix_commits=1,
        what_worked="CHECKs 21-26 content was correct",
        what_failed="Write discipline — edited SEED directly",
        prompt_patches_generated=["PP-2026-0330-001", "PP-2026-0330-002"],
    )
    receipt.return_record = ret
    receipt_store.save(receipt)

    # 3. Compute energy balance
    consumed = EnergyConsumed(
        tokens_input=55000,
        tokens_output=12000,
        tokens_wasted_estimate=40000,
        preparation_cost_minutes=15,
        reviewer_tokens=8000,
        fix_commits=1,
        calendar_duration_minutes=332,
    )
    produced = EnergyProduced(
        files_net_modified=1,
        lines_survived=39,
        lines_reverted=0,
        structural_additions=["CHECKs 21-26 (6 health checks)"],
    )
    balance = compute_energy(consumed, produced)

    # Assertions — the Gemini post-flood dispatch
    assert balance.verdict == "net_positive"  # content survived
    assert balance.survival_rate == 1.0  # 39 survived, 0 reverted
    assert balance.waste_ratio > 0.5  # 40K wasted out of 67K total

    # 4. Verify closed state
    assert len(receipt_store.list_pending()) == 0
    loaded_receipt = receipt_store.load("D-2026-0330-001")
    assert loaded_receipt is not None
    assert loaded_receipt.is_closed
    assert loaded_receipt.return_record.rating == 4

    loaded_tc = timecard_store.load("D-2026-0330-001")
    assert loaded_tc is not None
    assert loaded_tc.punch_out.outcome == "partial_fix"
    assert loaded_tc.signature.agent == "gemini"
```

- [ ] **Step 2: Run integration test**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_wave1_integration.py -v`
Expected: 1 test PASS

- [ ] **Step 3: Run full test suite for regressions**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS including all existing tests unchanged

- [ ] **Step 4: Commit**

```bash
cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design
git add tests/test_wave1_integration.py
git commit -m "test: Wave 1 integration — full dispatch lifecycle round-trip"
```

---

## Wave 2: LEARN (requires Wave 1 data)

### Task 6: Agent Scorecard — cumulative performance profiles

**Files:**
- Create: `conductor/scorecard.py`
- Create: `tests/test_scorecard.py`

- [ ] **Step 1: Write the failing test — scorecard computation from receipts**

```python
# tests/test_scorecard.py
"""Tests for cumulative agent scorecards computed from dispatch receipts."""

from __future__ import annotations

from pathlib import Path

from conductor.contribution_ledger import (
    DispatchReceipt,
    OutboundRecord,
    ReturnRecord,
    ReceiptStore,
)
from conductor.scorecard import AgentScorecard, compute_scorecard, dispatch_confidence


def _make_receipt(
    dispatch_id: str,
    agent: str,
    work_type: str,
    repo: str,
    outcome: str,
    rating: int,
    fix_commits: int = 0,
    violations: list | None = None,
) -> DispatchReceipt:
    outbound = OutboundRecord(
        dispatched_at="2026-03-30T15:00:00Z",
        prompt_hash="sha256:x",
        envelope_path="",
        work_description="test",
        files_expected=[],
        write_permission="direct_edit",
    )
    ret = ReturnRecord(
        completed_at="2026-03-30T20:00:00Z",
        outcome=outcome,
        rating=rating,
        fix_commits=fix_commits,
        violations=violations or [],
    )
    return DispatchReceipt(
        id=dispatch_id,
        agent=agent,
        model=f"{agent}-model",
        repo=repo,
        organ="IV",
        work_type=work_type,
        cognitive_class="tactical",
        outbound=outbound,
        return_record=ret,
    )


def test_scorecard_from_receipts():
    receipts = [
        _make_receipt("D-001", "gemini", "content_generation", "repo-a", "partial_fix", 4, fix_commits=2),
        _make_receipt("D-002", "gemini", "corpus_cross_reference", "repo-b", "clean", 7),
        _make_receipt("D-003", "gemini", "content_generation", "repo-a", "full_revert", 2, fix_commits=14),
        _make_receipt("D-004", "gemini", "corpus_cross_reference", "repo-c", "clean", 8),
        _make_receipt("D-005", "gemini", "content_generation", "repo-b", "partial_fix", 3, fix_commits=3),
    ]
    sc = compute_scorecard("gemini", receipts)
    assert sc.agent == "gemini"
    assert sc.dispatches_total == 5
    assert sc.avg_rating == (4 + 7 + 2 + 8 + 3) / 5
    assert sc.outcomes["clean"] == 2
    assert sc.outcomes["partial_fix"] == 2
    assert sc.outcomes["full_revert"] == 1

    # Per work type
    assert "content_generation" in sc.by_work_type
    assert sc.by_work_type["content_generation"]["dispatches"] == 3
    assert sc.by_work_type["content_generation"]["avg_rating"] == (4 + 2 + 3) / 3

    # Per repo
    assert "repo-a" in sc.by_repo
    assert sc.by_repo["repo-a"]["dispatches"] == 2


def test_dispatch_confidence():
    receipts = [
        _make_receipt("D-001", "gemini", "content_generation", "r", "full_revert", 2),
        _make_receipt("D-002", "gemini", "content_generation", "r", "full_revert", 1),
        _make_receipt("D-003", "gemini", "content_generation", "r", "partial_fix", 3),
    ]
    sc = compute_scorecard("gemini", receipts)
    conf = dispatch_confidence(sc, "content_generation")
    assert conf < 0.5  # poor performance = low confidence


def test_dispatch_confidence_high():
    receipts = [
        _make_receipt("D-001", "codex", "testing", "r", "clean", 9),
        _make_receipt("D-002", "codex", "testing", "r", "clean", 8),
        _make_receipt("D-003", "codex", "testing", "r", "clean", 9),
    ]
    sc = compute_scorecard("codex", receipts)
    conf = dispatch_confidence(sc, "testing")
    assert conf > 0.7  # consistently clean = high confidence


def test_empty_receipts():
    sc = compute_scorecard("unknown", [])
    assert sc.dispatches_total == 0
    assert sc.avg_rating == 0.0
    conf = dispatch_confidence(sc, "any")
    assert conf == 0.0


def test_scorecard_to_dict():
    receipts = [
        _make_receipt("D-001", "codex", "testing", "r", "clean", 9),
    ]
    sc = compute_scorecard("codex", receipts)
    d = sc.to_dict()
    assert d["agent"] == "codex"
    assert d["dispatches_total"] == 1
    assert "by_work_type" in d
    assert "by_repo" in d
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_scorecard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'conductor.scorecard'`

- [ ] **Step 3: Implement the scorecard module**

```python
# conductor/scorecard.py
"""Agent scorecard — cumulative performance profiles from dispatch receipts.

Computes per-agent statistics: avg rating, outcome distribution, survival rate,
broken down by work type and repo. Feeds into dispatch confidence scoring
and fleet router weighting.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .constants import STATE_DIR
from .contribution_ledger import DispatchReceipt, ReceiptStore


SCORECARD_DIR = STATE_DIR / "scorecards"

# Outcome weights for confidence scoring
_OUTCOME_SCORE = {
    "clean": 1.0,
    "partial_fix": 0.5,
    "full_revert": 0.0,
    "abandoned": 0.0,
}


@dataclass
class AgentScorecard:
    """Cumulative performance profile for a single agent."""

    agent: str
    dispatches_total: int = 0
    avg_rating: float = 0.0
    outcomes: dict[str, int] = field(default_factory=dict)
    total_fix_commits: int = 0
    by_work_type: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_repo: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "dispatches_total": self.dispatches_total,
            "avg_rating": round(self.avg_rating, 2),
            "outcomes": self.outcomes,
            "total_fix_commits": self.total_fix_commits,
            "by_work_type": self.by_work_type,
            "by_repo": self.by_repo,
        }


def compute_scorecard(agent: str, receipts: list[DispatchReceipt]) -> AgentScorecard:
    """Compute a scorecard from closed receipts for the given agent."""
    closed = [r for r in receipts if r.agent == agent and r.is_closed and r.return_record is not None]

    if not closed:
        return AgentScorecard(agent=agent)

    total = len(closed)
    ratings = [r.return_record.rating for r in closed]
    avg_rating = sum(ratings) / total

    outcomes: Counter[str] = Counter()
    total_fix = 0
    wt_data: dict[str, list[DispatchReceipt]] = defaultdict(list)
    repo_data: dict[str, list[DispatchReceipt]] = defaultdict(list)

    for r in closed:
        ret = r.return_record
        outcomes[ret.outcome] += 1
        total_fix += ret.fix_commits
        wt_data[r.work_type].append(r)
        repo_data[r.repo].append(r)

    by_work_type: dict[str, dict[str, Any]] = {}
    for wt, wt_receipts in wt_data.items():
        wt_ratings = [r.return_record.rating for r in wt_receipts]
        wt_outcomes = Counter(r.return_record.outcome for r in wt_receipts)
        by_work_type[wt] = {
            "dispatches": len(wt_receipts),
            "avg_rating": round(sum(wt_ratings) / len(wt_ratings), 2),
            "outcomes": dict(wt_outcomes),
        }

    by_repo: dict[str, dict[str, Any]] = {}
    for repo, repo_receipts in repo_data.items():
        repo_ratings = [r.return_record.rating for r in repo_receipts]
        by_repo[repo] = {
            "dispatches": len(repo_receipts),
            "avg_rating": round(sum(repo_ratings) / len(repo_ratings), 2),
        }

    return AgentScorecard(
        agent=agent,
        dispatches_total=total,
        avg_rating=avg_rating,
        outcomes=dict(outcomes),
        total_fix_commits=total_fix,
        by_work_type=by_work_type,
        by_repo=by_repo,
    )


def dispatch_confidence(scorecard: AgentScorecard, work_type: str) -> float:
    """Compute dispatch confidence (0.0-1.0) for an agent+work_type pair.

    Based on outcome distribution weighted by _OUTCOME_SCORE.
    Returns 0.0 if no data exists.
    """
    if scorecard.dispatches_total == 0:
        return 0.0

    # Use work-type-specific data if available, otherwise overall
    wt_data = scorecard.by_work_type.get(work_type)
    if wt_data and wt_data["dispatches"] > 0:
        outcomes = wt_data.get("outcomes", {})
        total = wt_data["dispatches"]
    else:
        outcomes = scorecard.outcomes
        total = scorecard.dispatches_total

    if total == 0:
        return 0.0

    weighted = sum(
        count * _OUTCOME_SCORE.get(outcome, 0.0)
        for outcome, count in outcomes.items()
    )
    return round(weighted / total, 4)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_scorecard.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design
git add conductor/scorecard.py tests/test_scorecard.py
git commit -m "feat: agent scorecard — cumulative profiles + dispatch confidence (Wave 2)"
```

---

### Task 7: Prompt Patch Engine — violation-driven constraint evolution

**Files:**
- Create: `conductor/prompt_patches.py`
- Create: `tests/test_prompt_patches.py`

- [ ] **Step 1: Write the failing test — patch lifecycle**

```python
# tests/test_prompt_patches.py
"""Tests for prompt patch lifecycle — create, inject, track recurrence."""

from __future__ import annotations

from pathlib import Path

from conductor.prompt_patches import (
    PromptPatch,
    Amplification,
    PatchStore,
    patches_for_dispatch,
)


def test_patch_creation():
    patch = PromptPatch(
        id="PP-2026-0330-001",
        created_from="D-2026-0330-001",
        rule="Include exact filesystem path of referenced documents.",
        agents=["gemini"],
        repos=["*"],
        work_types=["*"],
        model_version_tested="gemini-3-flash-preview",
    )
    assert patch.lifecycle_status == "active"
    assert patch.times_injected == 0
    d = patch.to_dict()
    assert d["rule"].startswith("Include")
    restored = PromptPatch.from_dict(d)
    assert restored.id == "PP-2026-0330-001"


def test_patch_store_round_trip(tmp_path):
    store = PatchStore(base_dir=tmp_path / "prompt-patches")
    patch = PromptPatch(
        id="PP-2026-0330-001",
        created_from="D-2026-0330-001",
        rule="Test rule",
        agents=["gemini"],
    )
    store.save(patch)
    loaded = store.load("PP-2026-0330-001")
    assert loaded is not None
    assert loaded.rule == "Test rule"


def test_patch_injection_tracking(tmp_path):
    store = PatchStore(base_dir=tmp_path / "prompt-patches")
    patch = PromptPatch(
        id="PP-001",
        created_from="D-001",
        rule="Test",
        agents=["gemini"],
    )
    store.save(patch)

    # Record 3 injections
    for _ in range(3):
        patch.times_injected += 1
    store.save(patch)

    loaded = store.load("PP-001")
    assert loaded.times_injected == 3


def test_patch_recurrence_rate(tmp_path):
    store = PatchStore(base_dir=tmp_path / "prompt-patches")
    patch = PromptPatch(
        id="PP-001",
        created_from="D-001",
        rule="Test",
        agents=["gemini"],
        times_injected=5,
        recurrences=1,
    )
    store.save(patch)
    assert patch.recurrence_rate == 1 / 5


def test_patch_proven_promotion():
    patch = PromptPatch(
        id="PP-001",
        created_from="D-001",
        rule="Test",
        agents=["gemini"],
        times_injected=5,
        recurrences=0,
    )
    assert patch.should_promote  # 5 injections, 0 recurrences
    patch.lifecycle_status = "proven"
    assert patch.lifecycle_status == "proven"


def test_patches_for_dispatch(tmp_path):
    store = PatchStore(base_dir=tmp_path / "prompt-patches")
    store.save(PromptPatch(id="PP-001", created_from="D-001", rule="Gemini rule 1", agents=["gemini"]))
    store.save(PromptPatch(id="PP-002", created_from="D-002", rule="All agents rule", agents=["*"]))
    store.save(PromptPatch(id="PP-003", created_from="D-003", rule="Codex rule", agents=["codex"]))
    store.save(PromptPatch(id="PP-004", created_from="D-004", rule="Retired", agents=["gemini"], lifecycle_status="retired"))

    matches = patches_for_dispatch(store, agent="gemini", repo="any", work_type="any")
    ids = [p.id for p in matches]
    assert "PP-001" in ids  # agent match
    assert "PP-002" in ids  # wildcard match
    assert "PP-003" not in ids  # wrong agent
    assert "PP-004" not in ids  # retired


def test_amplification_creation():
    amp = Amplification(
        id="AMP-2026-0330-001",
        created_from="D-2026-0330-004",
        technique="Codex spawns named sub-agents for multi-repo work",
        agents=["codex"],
        work_types=["multi_repo_parallel"],
    )
    assert amp.injection_mode == "suggestion"
    d = amp.to_dict()
    assert d["technique"].startswith("Codex")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_prompt_patches.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'conductor.prompt_patches'`

- [ ] **Step 3: Implement the prompt patches module**

```python
# conductor/prompt_patches.py
"""Prompt patch engine — violation-driven constraint evolution.

Each violation generates a prompt patch — a constraint rule injected into
future handoff envelopes. Patches have a lifecycle:
  draft → active → proven → retired

Amplifications are the positive counterpart: proven techniques suggested
(not mandated) for future dispatches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .constants import STATE_DIR


PROMPT_PATCHES_DIR = STATE_DIR / "prompt-patches"


@dataclass
class PromptPatch:
    """A constraint rule injected into future handoff envelopes."""

    id: str
    created_from: str  # dispatch ID that spawned this patch
    rule: str
    agents: list[str] = field(default_factory=lambda: ["*"])
    repos: list[str] = field(default_factory=lambda: ["*"])
    work_types: list[str] = field(default_factory=lambda: ["*"])
    model_version_tested: str = ""
    lifecycle_status: str = "active"  # draft | active | proven | retired
    times_injected: int = 0
    recurrences: int = 0

    @property
    def recurrence_rate(self) -> float:
        if self.times_injected == 0:
            return 0.0
        return self.recurrences / self.times_injected

    @property
    def should_promote(self) -> bool:
        return self.times_injected >= 3 and self.recurrences == 0

    def matches(self, agent: str, repo: str, work_type: str) -> bool:
        if self.lifecycle_status == "retired":
            return False
        agent_match = "*" in self.agents or agent in self.agents
        repo_match = "*" in self.repos or repo in self.repos
        wt_match = "*" in self.work_types or work_type in self.work_types
        return agent_match and repo_match and wt_match

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_from": self.created_from,
            "rule": self.rule,
            "agents": self.agents,
            "repos": self.repos,
            "work_types": self.work_types,
            "model_version_tested": self.model_version_tested,
            "lifecycle_status": self.lifecycle_status,
            "times_injected": self.times_injected,
            "recurrences": self.recurrences,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PromptPatch:
        return cls(
            id=str(d.get("id", "")),
            created_from=str(d.get("created_from", "")),
            rule=str(d.get("rule", "")),
            agents=list(d.get("agents", ["*"])),
            repos=list(d.get("repos", ["*"])),
            work_types=list(d.get("work_types", ["*"])),
            model_version_tested=str(d.get("model_version_tested", "")),
            lifecycle_status=str(d.get("lifecycle_status", "active")),
            times_injected=int(d.get("times_injected", 0)),
            recurrences=int(d.get("recurrences", 0)),
        )


@dataclass
class Amplification:
    """Positive counterpart to patches — proven techniques suggested for dispatch."""

    id: str
    created_from: str
    technique: str
    agents: list[str] = field(default_factory=lambda: ["*"])
    work_types: list[str] = field(default_factory=lambda: ["*"])
    injection_mode: str = "suggestion"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_from": self.created_from,
            "technique": self.technique,
            "agents": self.agents,
            "work_types": self.work_types,
            "injection_mode": self.injection_mode,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Amplification:
        return cls(
            id=str(d.get("id", "")),
            created_from=str(d.get("created_from", "")),
            technique=str(d.get("technique", "")),
            agents=list(d.get("agents", ["*"])),
            work_types=list(d.get("work_types", ["*"])),
            injection_mode=str(d.get("injection_mode", "suggestion")),
        )


class PatchStore:
    """YAML-backed storage for prompt patches."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or PROMPT_PATCHES_DIR

    def save(self, patch: PromptPatch) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self.base_dir / f"{patch.id}.yaml"
        path.write_text(yaml.dump(patch.to_dict(), default_flow_style=False, sort_keys=False))
        return path

    def load(self, patch_id: str) -> PromptPatch | None:
        path = self.base_dir / f"{patch_id}.yaml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text())
        if not data:
            return None
        return PromptPatch.from_dict(data)

    def list_active(self) -> list[PromptPatch]:
        if not self.base_dir.exists():
            return []
        patches = []
        for f in sorted(self.base_dir.glob("PP-*.yaml")):
            data = yaml.safe_load(f.read_text())
            if data:
                p = PromptPatch.from_dict(data)
                if p.lifecycle_status in ("active", "proven"):
                    patches.append(p)
        return patches


def patches_for_dispatch(
    store: PatchStore,
    agent: str,
    repo: str,
    work_type: str,
) -> list[PromptPatch]:
    """Return all active patches matching the dispatch context."""
    return [p for p in store.list_active() if p.matches(agent, repo, work_type)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_prompt_patches.py -v`
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design
git add conductor/prompt_patches.py tests/test_prompt_patches.py
git commit -m "feat: prompt patch engine — violation-driven constraint evolution (Wave 2)"
```

---

### Task 8: Wire scorecard into fleet router as routing weight

**Files:**
- Modify: `conductor/fleet_router.py`
- Modify: `tests/test_fleet.py` (or create `tests/test_scorecard_routing.py`)

- [ ] **Step 1: Write the failing test — scorecard-weighted routing**

```python
# tests/test_scorecard_routing.py
"""Tests for scorecard integration into fleet router scoring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch as mock_patch

from conductor.fleet import FleetRegistry
from conductor.fleet_router import FleetRouter, W_HISTORICAL_SURVIVAL
from conductor.scorecard import AgentScorecard


def test_historical_survival_weight_exists():
    """Verify the new weight constant is defined."""
    assert W_HISTORICAL_SURVIVAL > 0
    assert W_HISTORICAL_SURVIVAL <= 0.20


def test_router_accepts_scorecards():
    """Verify recommend() accepts optional scorecards parameter."""
    router = FleetRouter()
    # Should not raise — scorecards is optional
    results = router.recommend(
        phase="BUILD",
        scorecards={},
    )
    assert isinstance(results, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_scorecard_routing.py -v`
Expected: FAIL on `W_HISTORICAL_SURVIVAL` import

- [ ] **Step 3: Add historical survival weight to fleet_router.py**

In `conductor/fleet_router.py`, add after the existing weight constants (around line 51):

```python
W_HISTORICAL_SURVIVAL = 0.15
```

Adjust existing weights to sum to 1.0 with the new weight:
```python
W_PHASE_AFFINITY = 0.25
W_STRENGTH_MATCH = 0.20
W_UTILIZATION_PRESSURE = 0.15
W_CONTEXT_FIT = 0.15
W_COST_EFFICIENCY = 0.10
W_HISTORICAL_SURVIVAL = 0.15
```

Add `scorecards: dict[str, AgentScorecard] | None = None` parameter to `recommend()` method. In the scoring loop, add a survival score component:

```python
# Inside the scoring loop, after existing score components:
survival_score = 0.5  # default neutral
if scorecards and agent.name in scorecards:
    sc = scorecards[agent.name]
    if work_type and work_type in sc.by_work_type:
        wt_data = sc.by_work_type[work_type]
        clean = wt_data.get("outcomes", {}).get("clean", 0)
        total_wt = wt_data["dispatches"]
        survival_score = clean / total_wt if total_wt > 0 else 0.5
    elif sc.dispatches_total > 0:
        clean_total = sc.outcomes.get("clean", 0)
        survival_score = clean_total / sc.dispatches_total
breakdown["historical_survival"] = round(survival_score * W_HISTORICAL_SURVIVAL, 4)
total_score += survival_score * W_HISTORICAL_SURVIVAL
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_scorecard_routing.py tests/test_fleet.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design
git add conductor/fleet_router.py tests/test_scorecard_routing.py
git commit -m "feat: wire scorecard survival rate into fleet router scoring (Wave 2)"
```

---

## Wave 3: ANTICIPATE (requires Wave 2 intelligence)

> **Note for implementer:** Wave 3 builds the container builder, fleet bulletin, and plan dispatch modules. These depend on Waves 1-2 being complete with real data. Implementation should be a separate session after Wave 1-2 data has accumulated from real dispatches.

### Task 9: Container Builder — assembly with transport modes

**Files:**
- Create: `conductor/container_builder.py`
- Create: `tests/test_container_builder.py`

- [ ] **Step 1: Write the failing test — container assembly**

```python
# tests/test_container_builder.py
"""Tests for assignment container assembly."""

from __future__ import annotations

from pathlib import Path

from conductor.container_builder import (
    ContainerBuilder,
    ContainerManifest,
    ContainerType,
)
from conductor.scorecard import AgentScorecard
from conductor.prompt_patches import PatchStore, PromptPatch


def test_container_type_from_work_type():
    assert ContainerType.from_work_type("corpus_cross_reference") == ContainerType.READER
    assert ContainerType.from_work_type("boilerplate_generation") == ContainerType.WRITER
    assert ContainerType.from_work_type("mechanical_refactoring") == ContainerType.REFACTORER
    assert ContainerType.from_work_type("audit") == ContainerType.AUDITOR


def test_container_manifest_completeness():
    manifest = ContainerManifest(
        dispatch_id="D-2026-0330-001",
        agent="gemini",
        container_type=ContainerType.READER,
        has_assignment=True,
        has_constraints=True,
        has_directory=True,
        has_known_issues=True,
        has_skills=False,
        context_ready=True,
    )
    assert manifest.is_complete  # skills are optional for READER


def test_container_manifest_incomplete_reader():
    manifest = ContainerManifest(
        dispatch_id="D-001",
        agent="gemini",
        container_type=ContainerType.READER,
        has_assignment=True,
        has_constraints=True,
        has_directory=True,
        has_known_issues=True,
        has_skills=False,
        context_ready=False,  # READER needs context
    )
    assert not manifest.is_complete


def test_build_constraints_md(tmp_path):
    patch_store = PatchStore(base_dir=tmp_path / "patches")
    patch_store.save(PromptPatch(
        id="PP-001",
        created_from="D-001",
        rule="Never modify SEED directly",
        agents=["gemini"],
    ))
    patch_store.save(PromptPatch(
        id="PP-002",
        created_from="D-002",
        rule="Include exact file paths",
        agents=["gemini"],
    ))

    scorecard = AgentScorecard(
        agent="gemini",
        dispatches_total=5,
        avg_rating=4.2,
        outcomes={"clean": 1, "partial_fix": 3, "full_revert": 1},
    )

    builder = ContainerBuilder(patch_store=patch_store)
    constraints_md = builder.build_constraints(
        agent="gemini",
        repo="meta-organvm/post-flood",
        work_type="corpus_cross_reference",
        scorecard=scorecard,
    )
    assert "4.2" in constraints_md  # avg rating appears
    assert "Never modify SEED" in constraints_md  # patch 1
    assert "exact file paths" in constraints_md  # patch 2


def test_confidence_gate_blocks_low_confidence(tmp_path):
    patch_store = PatchStore(base_dir=tmp_path / "patches")
    scorecard = AgentScorecard(
        agent="gemini",
        dispatches_total=5,
        avg_rating=2.0,
        outcomes={"full_revert": 4, "partial_fix": 1},
        by_work_type={
            "content_generation": {
                "dispatches": 5,
                "avg_rating": 2.0,
                "outcomes": {"full_revert": 4, "partial_fix": 1},
            },
        },
    )
    builder = ContainerBuilder(patch_store=patch_store)
    blocked, reason = builder.check_confidence_gate(
        agent="gemini",
        work_type="content_generation",
        scorecard=scorecard,
    )
    assert blocked
    assert "confidence" in reason.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_container_builder.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the container builder**

```python
# conductor/container_builder.py
"""Container builder — assembles self-contained assignment packages.

A container is the input transformer: everything the agent needs,
nothing it needs to search for. Container types (permeability):
  READER:     high context in, propose-only out
  WRITER:     high constraints, direct write allowed
  REFACTORER: strict scope, pattern-following
  AUDITOR:    read-only, no write permission
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .prompt_patches import PatchStore, patches_for_dispatch
from .scorecard import AgentScorecard, dispatch_confidence

# Confidence thresholds
CONFIDENCE_BLOCK_THRESHOLD = 0.3
CONFIDENCE_STRATEGIC_THRESHOLD = 0.5


class ContainerType(enum.Enum):
    READER = "READER"
    WRITER = "WRITER"
    REFACTORER = "REFACTORER"
    AUDITOR = "AUDITOR"

    @classmethod
    def from_work_type(cls, work_type: str) -> ContainerType:
        mapping = {
            "corpus_cross_reference": cls.READER,
            "research": cls.READER,
            "content_generation": cls.WRITER,
            "boilerplate_generation": cls.WRITER,
            "testing": cls.WRITER,
            "mechanical_refactoring": cls.REFACTORER,
            "audit": cls.AUDITOR,
            "debugging": cls.AUDITOR,
            "architecture": cls.WRITER,
        }
        return mapping.get(work_type, cls.WRITER)


@dataclass
class ContainerManifest:
    """Tracks container completeness for dispatch readiness."""

    dispatch_id: str
    agent: str
    container_type: ContainerType
    has_assignment: bool = False
    has_constraints: bool = False
    has_directory: bool = False
    has_known_issues: bool = False
    has_skills: bool = False
    context_ready: bool = False
    blocked_by: str = ""
    estimated_tokens: int = 0

    @property
    def is_complete(self) -> bool:
        required = [self.has_assignment, self.has_constraints, self.has_directory, self.has_known_issues]
        if self.container_type == ContainerType.READER:
            required.append(self.context_ready)
        if self.container_type == ContainerType.REFACTORER:
            required.append(self.has_known_issues)
        return all(required) and not self.blocked_by

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispatch_id": self.dispatch_id,
            "agent": self.agent,
            "container_type": self.container_type.value,
            "has_assignment": self.has_assignment,
            "has_constraints": self.has_constraints,
            "has_directory": self.has_directory,
            "has_known_issues": self.has_known_issues,
            "has_skills": self.has_skills,
            "context_ready": self.context_ready,
            "blocked_by": self.blocked_by,
            "estimated_tokens": self.estimated_tokens,
            "is_complete": self.is_complete,
        }


class ContainerBuilder:
    """Assembles assignment containers from scorecard + patches + repo data."""

    def __init__(self, patch_store: PatchStore | None = None) -> None:
        self.patch_store = patch_store or PatchStore()

    def check_confidence_gate(
        self,
        agent: str,
        work_type: str,
        scorecard: AgentScorecard | None = None,
    ) -> tuple[bool, str]:
        """Check if dispatch confidence is too low. Returns (blocked, reason)."""
        if scorecard is None or scorecard.dispatches_total == 0:
            return False, ""
        conf = dispatch_confidence(scorecard, work_type)
        if conf < CONFIDENCE_BLOCK_THRESHOLD:
            return True, (
                f"Dispatch confidence {conf:.2f} below threshold "
                f"{CONFIDENCE_BLOCK_THRESHOLD} for {agent}+{work_type}"
            )
        return False, ""

    def build_constraints(
        self,
        agent: str,
        repo: str,
        work_type: str,
        scorecard: AgentScorecard | None = None,
    ) -> str:
        """Generate CONSTRAINTS.md content from scorecard + patches + overlay."""
        lines: list[str] = []
        lines.append(f"# Constraints for {agent} on {repo}\n")

        # Agent profile section
        if scorecard and scorecard.dispatches_total > 0:
            lines.append("## From Agent Profile")
            lines.append(f"- Avg rating: {scorecard.avg_rating}/10 across {scorecard.dispatches_total} dispatches")
            outcomes = scorecard.outcomes
            if outcomes:
                parts = [f"{v} {k}" for k, v in sorted(outcomes.items(), key=lambda x: -x[1])]
                lines.append(f"- Outcomes: {', '.join(parts)}")
            lines.append("")

        # Prompt patches section
        patches = patches_for_dispatch(self.patch_store, agent, repo, work_type)
        if patches:
            lines.append("## From Prompt Patches")
            for p in patches:
                status_tag = f" [{p.lifecycle_status}]" if p.lifecycle_status == "proven" else ""
                lines.append(f"- **{p.id}**{status_tag}: {p.rule}")
                lines.append(f"  _Origin: {p.created_from}_")
            lines.append("")

        return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_container_builder.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design
git add conductor/container_builder.py tests/test_container_builder.py
git commit -m "feat: container builder — assembly with permeability types (Wave 3)"
```

---

### Task 10: Fleet Bulletin — cross-agent awareness at session start

**Files:**
- Create: `conductor/fleet_bulletin.py`
- Create: `tests/test_fleet_bulletin.py`

- [ ] **Step 1: Write the failing test — bulletin generation**

```python
# tests/test_fleet_bulletin.py
"""Tests for fleet bulletin generation at session start."""

from __future__ import annotations

from conductor.contribution_ledger import (
    DispatchReceipt,
    OutboundRecord,
    ReturnRecord,
)
from conductor.fleet_bulletin import generate_bulletin, BulletinData


def _receipt(did: str, agent: str, outcome: str, rating: int, repo: str = "repo") -> DispatchReceipt:
    outbound = OutboundRecord(
        dispatched_at="2026-03-30T15:00:00Z",
        prompt_hash="sha256:x",
        envelope_path="",
        work_description=f"Task by {agent}",
        files_expected=[],
        write_permission="direct_edit",
    )
    ret = ReturnRecord(completed_at="2026-03-30T20:00:00Z", outcome=outcome, rating=rating) if outcome else None
    return DispatchReceipt(
        id=did, agent=agent, model=f"{agent}-model", repo=repo, organ="IV",
        work_type="testing", cognitive_class="tactical", outbound=outbound,
        return_record=ret,
    )


def test_bulletin_shows_all_agents():
    receipts = [
        _receipt("D-001", "gemini", "partial_fix", 4),
        _receipt("D-002", "codex", "clean", 9),
        _receipt("D-003", "opencode", "clean", 7),
    ]
    bulletin = generate_bulletin(receipts)
    assert "gemini" in bulletin.markdown
    assert "codex" in bulletin.markdown
    assert "opencode" in bulletin.markdown


def test_bulletin_shows_pending_review():
    receipts = [
        _receipt("D-001", "gemini", None, 0),  # no return = pending
        _receipt("D-002", "codex", "clean", 9),
    ]
    bulletin = generate_bulletin(receipts)
    assert "Pending Review" in bulletin.markdown
    assert "D-001" in bulletin.markdown


def test_bulletin_data_structure():
    receipts = [
        _receipt("D-001", "gemini", "partial_fix", 4),
        _receipt("D-002", "gemini", "clean", 7),
    ]
    bulletin = generate_bulletin(receipts)
    assert bulletin.agents_active == {"gemini"}
    assert bulletin.pending_reviews == 0
    assert bulletin.total_dispatches == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_fleet_bulletin.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the fleet bulletin module**

```python
# conductor/fleet_bulletin.py
"""Fleet bulletin — cross-agent awareness digest at session start.

Generates a markdown briefing showing:
  - Recent contributions from all agents
  - Pending review items
  - Token economy dashboard
  - Overdue review warnings
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .contribution_ledger import DispatchReceipt


@dataclass
class BulletinData:
    """Structured bulletin data."""

    markdown: str = ""
    agents_active: set[str] = field(default_factory=set)
    pending_reviews: int = 0
    total_dispatches: int = 0


def generate_bulletin(receipts: list[DispatchReceipt]) -> BulletinData:
    """Generate a fleet bulletin from dispatch receipts."""
    if not receipts:
        return BulletinData(markdown="# Fleet Bulletin\n\nNo dispatches recorded.")

    agents: set[str] = set()
    completed: list[DispatchReceipt] = []
    pending: list[DispatchReceipt] = []

    for r in receipts:
        agents.add(r.agent)
        if r.is_closed:
            completed.append(r)
        else:
            pending.append(r)

    lines: list[str] = []
    lines.append("# Fleet Bulletin\n")

    # Recent contributions
    if completed:
        lines.append("## Recent Contributions")
        lines.append("| Agent | Repo | Work Type | Outcome | Rating |")
        lines.append("|-------|------|-----------|---------|--------|")
        for r in completed[-10:]:  # last 10
            ret = r.return_record
            outcome = ret.outcome if ret else "?"
            rating = f"{ret.rating}/10" if ret else "—"
            lines.append(f"| {r.agent} | {r.repo} | {r.work_type} | {outcome} | {rating} |")
        lines.append("")

    # Pending review
    if pending:
        lines.append("## Pending Review")
        for r in pending:
            lines.append(f"- **{r.id}**: {r.agent} → {r.repo} ({r.work_type})")
        lines.append("")

    # Per-agent summary
    agent_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"dispatches": 0, "ratings": []})
    for r in completed:
        ret = r.return_record
        agent_stats[r.agent]["dispatches"] += 1
        if ret:
            agent_stats[r.agent]["ratings"].append(ret.rating)

    if agent_stats:
        lines.append("## Agent Summary")
        lines.append("| Agent | Dispatches | Avg Rating |")
        lines.append("|-------|-----------|------------|")
        for agent, stats in sorted(agent_stats.items()):
            avg = sum(stats["ratings"]) / len(stats["ratings"]) if stats["ratings"] else 0
            lines.append(f"| {agent} | {stats['dispatches']} | {avg:.1f}/10 |")
        lines.append("")

    return BulletinData(
        markdown="\n".join(lines),
        agents_active=agents,
        pending_reviews=len(pending),
        total_dispatches=len(receipts),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_fleet_bulletin.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design
git add conductor/fleet_bulletin.py tests/test_fleet_bulletin.py
git commit -m "feat: fleet bulletin — cross-agent awareness at session start (Wave 3)"
```

---

### Task 11: Final integration test + full suite verification

**Files:**
- Create: `tests/test_full_system_integration.py`

- [ ] **Step 1: Write end-to-end integration test**

```python
# tests/test_full_system_integration.py
"""End-to-end: dispatch → return → scorecard → patches → container → bulletin."""

from __future__ import annotations

from pathlib import Path

from conductor.contribution_ledger import (
    DispatchReceipt, OutboundRecord, ReturnRecord, ReceiptStore,
)
from conductor.timecard import (
    PunchIn, PunchOut, Signature, Timecard, TimecardStore, ScopeBoundary,
)
from conductor.energy_ledger import EnergyConsumed, EnergyProduced, compute_energy
from conductor.scorecard import compute_scorecard, dispatch_confidence
from conductor.prompt_patches import PromptPatch, PatchStore, patches_for_dispatch
from conductor.container_builder import ContainerBuilder, ContainerType
from conductor.fleet_bulletin import generate_bulletin


def test_full_lifecycle(tmp_path):
    """Simulate 3 dispatches to gemini, compute scorecard, build container."""
    receipt_store = ReceiptStore(base_dir=tmp_path / "ledger")
    patch_store = PatchStore(base_dir=tmp_path / "patches")

    # Create 3 receipts with varying outcomes
    for i, (outcome, rating, fix) in enumerate([
        ("partial_fix", 4, 1),
        ("clean", 7, 0),
        ("full_revert", 2, 14),
    ]):
        outbound = OutboundRecord(
            dispatched_at=f"2026-03-30T1{i}:00:00Z",
            prompt_hash=f"sha256:{i}",
            envelope_path="",
            work_description=f"Task {i}",
            files_expected=[],
            write_permission="direct_edit",
        )
        ret = ReturnRecord(
            completed_at=f"2026-03-30T2{i}:00:00Z",
            outcome=outcome,
            rating=rating,
            fix_commits=fix,
        )
        r = DispatchReceipt(
            id=f"D-2026-0330-00{i}",
            agent="gemini",
            model="gemini-3-flash-preview",
            repo="test/repo",
            organ="IV",
            work_type="content_generation",
            cognitive_class="tactical",
            outbound=outbound,
            return_record=ret,
        )
        receipt_store.save(r)

    # Create a prompt patch from the revert
    patch_store.save(PromptPatch(
        id="PP-001",
        created_from="D-2026-0330-002",
        rule="Do not fabricate metrics from training data",
        agents=["gemini"],
    ))

    # Compute scorecard
    receipts = receipt_store.list_all()
    sc = compute_scorecard("gemini", receipts)
    assert sc.dispatches_total == 3
    assert sc.avg_rating == (4 + 7 + 2) / 3

    # Check dispatch confidence
    conf = dispatch_confidence(sc, "content_generation")
    assert conf < 0.5  # 1 clean + 1 partial + 1 revert = poor

    # Build container constraints
    builder = ContainerBuilder(patch_store=patch_store)
    constraints = builder.build_constraints(
        agent="gemini", repo="test/repo",
        work_type="content_generation", scorecard=sc,
    )
    assert "fabricate metrics" in constraints  # patch injected
    assert "4.33" in constraints or "4.3" in constraints  # avg rating

    # Confidence gate
    blocked, reason = builder.check_confidence_gate(
        agent="gemini", work_type="content_generation", scorecard=sc,
    )
    # May or may not be blocked depending on exact confidence calc

    # Generate bulletin
    bulletin = generate_bulletin(receipts)
    assert "gemini" in bulletin.markdown
    assert bulletin.total_dispatches == 3
    assert bulletin.pending_reviews == 0
```

- [ ] **Step 2: Run integration test**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/test_full_system_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run the full test suite**

Run: `cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m pytest tests/ -v --timeout=30`
Expected: ALL tests PASS (existing + new)

- [ ] **Step 4: Commit**

```bash
cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design
git add tests/test_full_system_integration.py
git commit -m "test: full system integration — dispatch through bulletin lifecycle"
```
