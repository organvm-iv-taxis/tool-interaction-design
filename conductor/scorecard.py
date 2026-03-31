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
