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
