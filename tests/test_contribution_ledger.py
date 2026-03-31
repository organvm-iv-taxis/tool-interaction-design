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
