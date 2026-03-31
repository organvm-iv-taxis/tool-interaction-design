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
