"""Work Queue — computes prioritized action items from registry state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .constants import (
    organ_short,
)
from .governance import GovernanceRuntime


@dataclass
class WorkItem:
    """A single prioritized action item."""

    priority: str  # CRITICAL, HIGH, MEDIUM, LOW
    category: str  # wip_violation, stale, missing_ci, promotion_ready
    organ: str
    repo: str | None
    description: str
    suggested_command: str
    score: int  # sort key (higher = more urgent)
    rationale: dict[str, Any] = field(default_factory=dict)


class WorkQueue:
    """Computes a prioritized work queue from registry state. Read-only, no stored file."""

    def __init__(self, gov: GovernanceRuntime) -> None:
        self.gov = gov

    def compute(self, organ_filter: str | None = None) -> list[WorkItem]:
        """Build the full work queue, optionally filtered to one organ."""
        items: list[WorkItem] = []
        items.extend(self._wip_violations(organ_filter))
        items.extend(self._stale_candidates(organ_filter))
        items.extend(self._missing_infrastructure(organ_filter))
        items.extend(self._promotion_candidates(organ_filter))
        items.sort(key=lambda x: -x.score)
        return items

    @staticmethod
    def _weighted_score(base: int, factors: dict[str, int]) -> tuple[int, dict[str, Any]]:
        total = base + sum(factors.values())
        return total, {
            "base": base,
            "factors": factors,
            "total": total,
        }

    def _wip_violations(self, organ_filter: str | None) -> list[WorkItem]:
        """Score 100: organs exceeding CANDIDATE or PUBLIC_PROCESS limits."""
        items: list[WorkItem] = []
        organs = self.gov.registry.get("organs", {})
        max_candidate = self.gov.max_candidate_per_organ
        max_public = self.gov.max_public_process_per_organ

        for organ_key, organ_data in organs.items():
            if organ_filter and organ_key != organ_filter:
                continue

            repos = organ_data.get("repositories", [])
            cand_count = sum(1 for r in repos if r.get("promotion_status") == "CANDIDATE")
            pub_count = sum(1 for r in repos if r.get("promotion_status") == "PUBLIC_PROCESS")
            short = organ_short(organ_key)

            if cand_count > max_candidate:
                score, rationale = self._weighted_score(
                    base=100,
                    factors={
                        "candidate_count": cand_count,
                        "candidate_over_limit": cand_count - max_candidate,
                    },
                )
                items.append(WorkItem(
                    priority="CRITICAL",
                    category="wip_violation",
                    organ=organ_key,
                    repo=None,
                    description=f"{cand_count} CANDIDATE (limit {max_candidate}) — triage required",
                    suggested_command=f"conductor audit --organ {short}",
                    score=score,
                    rationale=rationale,
                ))

            if pub_count > max_public:
                score, rationale = self._weighted_score(
                    base=100,
                    factors={
                        "public_process_count": pub_count,
                        "public_process_over_limit": pub_count - max_public,
                    },
                )
                items.append(WorkItem(
                    priority="CRITICAL",
                    category="wip_violation",
                    organ=organ_key,
                    repo=None,
                    description=f"{pub_count} PUBLIC_PROCESS (limit {max_public}) — graduate or archive",
                    suggested_command=f"conductor audit --organ {short}",
                    score=score,
                    rationale=rationale,
                ))

        return items

    def _stale_candidates(self, organ_filter: str | None) -> list[WorkItem]:
        """Score 70: CANDIDATE repos with last_validated > 30 days old."""
        items: list[WorkItem] = []
        now = datetime.now(timezone.utc)

        for organ_key, repo in self.gov._all_repos():
            if organ_filter and organ_key != organ_filter:
                continue
            if repo.get("promotion_status") != "CANDIDATE":
                continue

            name = repo.get("name", "unknown")
            last_validated = repo.get("last_validated", "")
            if not last_validated:
                score, rationale = self._weighted_score(
                    base=72,
                    factors={"missing_validation_date": 3},
                )
                items.append(WorkItem(
                    priority="HIGH",
                    category="stale",
                    organ=organ_key,
                    repo=name,
                    description="CANDIDATE with no validation date",
                    suggested_command=f"conductor wip promote {name} PUBLIC_PROCESS",
                    score=score,
                    rationale=rationale,
                ))
                continue

            try:
                validated_date = datetime.strptime(last_validated, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                age_days = (now - validated_date).days
                if age_days > 30:
                    score, rationale = self._weighted_score(
                        base=70,
                        factors={"staleness_age_weight": min(age_days // 10, 20)},
                    )
                    items.append(WorkItem(
                        priority="HIGH",
                        category="stale",
                        organ=organ_key,
                        repo=name,
                        description=f"stale CANDIDATE (last validated {age_days}d ago)",
                        suggested_command=f"conductor wip promote {name} PUBLIC_PROCESS",
                        score=score,
                        rationale=rationale,
                    ))
            except ValueError:
                # Malformed date — treat as stale
                score, rationale = self._weighted_score(
                    base=72,
                    factors={"invalid_validation_date": 3},
                )
                items.append(WorkItem(
                    priority="HIGH",
                    category="stale",
                    organ=organ_key,
                    repo=name,
                    description="CANDIDATE with invalid validation date",
                    suggested_command=f"conductor wip promote {name} PUBLIC_PROCESS",
                    score=score,
                    rationale=rationale,
                ))

        return items

    def _missing_infrastructure(self, organ_filter: str | None) -> list[WorkItem]:
        """Score 40: repos with empty ci_workflow or documentation_status=EMPTY."""
        items: list[WorkItem] = []

        for organ_key, repo in self.gov._all_repos():
            if organ_filter and organ_key != organ_filter:
                continue
            # Skip archived repos
            if repo.get("promotion_status") == "ARCHIVED":
                continue

            name = repo.get("name", "unknown")

            if not repo.get("ci_workflow"):
                score, rationale = self._weighted_score(base=40, factors={"missing_ci": 0})
                items.append(WorkItem(
                    priority="MEDIUM",
                    category="missing_ci",
                    organ=organ_key,
                    repo=name,
                    description="missing CI workflow",
                    suggested_command=f"add ci workflow to {name}",
                    score=score,
                    rationale=rationale,
                ))

            if repo.get("documentation_status", "").upper() == "EMPTY":
                score, rationale = self._weighted_score(base=45, factors={"missing_docs": 0})
                items.append(WorkItem(
                    priority="MEDIUM",
                    category="missing_docs",
                    organ=organ_key,
                    repo=name,
                    description="missing README/documentation",
                    suggested_command=f"add README to {name}",
                    score=score,
                    rationale=rationale,
                ))

        return items

    def _promotion_candidates(self, organ_filter: str | None) -> list[WorkItem]:
        """Score 20: LOCAL repos with docs deployed (ready to promote)."""
        items: list[WorkItem] = []

        for organ_key, repo in self.gov._all_repos():
            if organ_filter and organ_key != organ_filter:
                continue
            if repo.get("promotion_status") != "LOCAL":
                continue

            doc_status = repo.get("documentation_status", "").upper()
            has_ci = bool(repo.get("ci_workflow"))

            if doc_status == "DEPLOYED" and has_ci:
                score, rationale = self._weighted_score(
                    base=20,
                    factors={
                        "docs_deployed": 2,
                        "ci_present": 3,
                    },
                )
                items.append(WorkItem(
                    priority="LOW",
                    category="promotion_ready",
                    organ=organ_key,
                    repo=repo["name"],
                    description="LOCAL with docs + CI — ready for CANDIDATE",
                    suggested_command=f"conductor wip promote {repo['name']} CANDIDATE",
                    score=score,
                    rationale=rationale,
                ))
            elif doc_status == "DEPLOYED":
                score, rationale = self._weighted_score(
                    base=18,
                    factors={"docs_deployed": 2},
                )
                items.append(WorkItem(
                    priority="LOW",
                    category="promotion_ready",
                    organ=organ_key,
                    repo=repo["name"],
                    description="LOCAL with docs deployed — add CI then promote",
                    suggested_command=f"conductor wip promote {repo['name']} CANDIDATE",
                    score=score,
                    rationale=rationale,
                ))

        return items
