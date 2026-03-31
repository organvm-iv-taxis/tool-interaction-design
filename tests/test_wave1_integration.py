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
