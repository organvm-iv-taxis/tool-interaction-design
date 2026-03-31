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
