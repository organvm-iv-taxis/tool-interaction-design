"""Work Queue — computes prioritized action items from registry state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .constants import (
    MAX_CANDIDATE_PER_ORGAN,
    MAX_PUBLIC_PROCESS_PER_ORGAN,
    ORGANS,
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

    def _wip_violations(self, organ_filter: str | None) -> list[WorkItem]:
        """Score 100: organs exceeding CANDIDATE or PUBLIC_PROCESS limits."""
        items: list[WorkItem] = []
        organs = self.gov.registry.get("organs", {})

        for organ_key, organ_data in organs.items():
            if organ_filter and organ_key != organ_filter:
                continue

            repos = organ_data.get("repositories", [])
            cand_count = sum(1 for r in repos if r.get("promotion_status") == "CANDIDATE")
            pub_count = sum(1 for r in repos if r.get("promotion_status") == "PUBLIC_PROCESS")
            short = organ_short(organ_key)

            if cand_count > MAX_CANDIDATE_PER_ORGAN:
                items.append(WorkItem(
                    priority="CRITICAL",
                    category="wip_violation",
                    organ=organ_key,
                    repo=None,
                    description=f"{cand_count} CANDIDATE (limit {MAX_CANDIDATE_PER_ORGAN}) — triage required",
                    suggested_command=f"conductor audit --organ {short}",
                    score=100 + cand_count,
                ))

            if pub_count > MAX_PUBLIC_PROCESS_PER_ORGAN:
                items.append(WorkItem(
                    priority="CRITICAL",
                    category="wip_violation",
                    organ=organ_key,
                    repo=None,
                    description=f"{pub_count} PUBLIC_PROCESS (limit {MAX_PUBLIC_PROCESS_PER_ORGAN}) — graduate or archive",
                    suggested_command=f"conductor audit --organ {short}",
                    score=100 + pub_count,
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

            last_validated = repo.get("last_validated", "")
            if not last_validated:
                items.append(WorkItem(
                    priority="HIGH",
                    category="stale",
                    organ=organ_key,
                    repo=repo["name"],
                    description="CANDIDATE with no validation date",
                    suggested_command=f"conductor wip promote {repo['name']} PUBLIC_PROCESS",
                    score=75,
                ))
                continue

            try:
                validated_date = datetime.strptime(last_validated, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                age_days = (now - validated_date).days
                if age_days > 30:
                    items.append(WorkItem(
                        priority="HIGH",
                        category="stale",
                        organ=organ_key,
                        repo=repo["name"],
                        description=f"stale CANDIDATE (last validated {age_days}d ago)",
                        suggested_command=f"conductor wip promote {repo['name']} PUBLIC_PROCESS",
                        score=70 + min(age_days // 10, 20),
                    ))
            except ValueError:
                pass

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

            name = repo["name"]

            if not repo.get("ci_workflow"):
                items.append(WorkItem(
                    priority="MEDIUM",
                    category="missing_ci",
                    organ=organ_key,
                    repo=name,
                    description="missing CI workflow",
                    suggested_command=f"add ci workflow to {name}",
                    score=40,
                ))

            if repo.get("documentation_status", "").upper() == "EMPTY":
                items.append(WorkItem(
                    priority="MEDIUM",
                    category="missing_docs",
                    organ=organ_key,
                    repo=name,
                    description="missing README/documentation",
                    suggested_command=f"add README to {name}",
                    score=45,
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
                items.append(WorkItem(
                    priority="LOW",
                    category="promotion_ready",
                    organ=organ_key,
                    repo=repo["name"],
                    description="LOCAL with docs + CI — ready for CANDIDATE",
                    suggested_command=f"conductor wip promote {repo['name']} CANDIDATE",
                    score=25,
                ))
            elif doc_status == "DEPLOYED":
                items.append(WorkItem(
                    priority="LOW",
                    category="promotion_ready",
                    organ=organ_key,
                    repo=repo["name"],
                    description="LOCAL with docs deployed — add CI then promote",
                    suggested_command=f"conductor wip promote {repo['name']} CANDIDATE",
                    score=20,
                ))

        return items
