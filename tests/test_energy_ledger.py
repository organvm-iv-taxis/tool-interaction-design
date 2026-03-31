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
