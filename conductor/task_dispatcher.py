"""Task Dispatcher — classifies cognitive work and routes to constrained agents.

Sits between the user's work description and the FleetRouter, adding:
1. Work type classification (keyword matching against taxonomy examples)
2. Restriction-aware routing (hard-filters agents that can't do this work type)
3. Dispatch plans with per-agent scope boundaries
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .fleet import FleetRegistry
from .fleet_router import FleetRouter, RouteScore, load_work_types
from .fleet_usage import FleetUsageTracker


@dataclass
class DispatchPlan:
    """Ranked agent assignments for a classified work type."""

    work_type: str
    cognitive_class: str
    verification_policy: str
    ranked_agents: list[RouteScore] = field(default_factory=list)
    excluded_agents: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_type": self.work_type,
            "cognitive_class": self.cognitive_class,
            "verification_policy": self.verification_policy,
            "ranked_agents": [
                {"agent": s.agent, "display_name": s.display_name,
                 "score": s.score, "breakdown": s.breakdown}
                for s in self.ranked_agents
            ],
            "excluded_agents": self.excluded_agents,
        }

    @property
    def recommended(self) -> str | None:
        """Return the top-ranked agent name, or None if no agents qualify."""
        return self.ranked_agents[0].agent if self.ranked_agents else None


class TaskDispatcher:
    """Classifies work and dispatches to the best-fit agent."""

    def __init__(
        self,
        fleet_router: FleetRouter | None = None,
        work_types: dict[str, Any] | None = None,
    ) -> None:
        self.router = fleet_router or FleetRouter()
        self.work_types = work_types if work_types is not None else load_work_types()

    def classify(self, description: str) -> str:
        """Classify a work description into a work type ID.

        Uses keyword matching against each work type's examples list.
        Returns the best-matching work type ID, or "unclassified" if
        no match exceeds the threshold.
        """
        description_lower = description.lower()
        best_type = "unclassified"
        best_score = 0

        for wt_id, wt_spec in self.work_types.items():
            examples = wt_spec.get("examples", [])
            score = 0
            for example in examples:
                example_lower = example.lower()
                # Check for substring match
                if example_lower in description_lower:
                    score += 2
                else:
                    # Check for word overlap
                    example_words = set(example_lower.split())
                    desc_words = set(description_lower.split())
                    overlap = len(example_words & desc_words)
                    if overlap >= 1:
                        score += overlap

            if score > best_score:
                best_score = score
                best_type = wt_id

        return best_type if best_score > 0 else "unclassified"

    def plan(
        self,
        description: str,
        phase: str,
        work_type: str | None = None,
        context_size: int = 0,
        sensitivity: dict[str, bool] | None = None,
        task_tags: list[str] | None = None,
    ) -> DispatchPlan:
        """Create a dispatch plan for the given work.

        Args:
            description: Natural language description of the work.
            phase: Current conductor phase.
            work_type: Explicit work type override. If None, auto-classified.
            context_size: Estimated context size in tokens.
            sensitivity: Additional sensitivity requirements.
            task_tags: Additional task tags for strength matching.

        Returns:
            DispatchPlan with ranked agents and exclusion reasons.
        """
        # Classify if not explicit
        resolved_type = work_type or self.classify(description)
        wt_spec = self.work_types.get(resolved_type, {})
        cognitive_class = wt_spec.get("cognitive_class", "mechanical")
        verification = wt_spec.get("verification", "self_sufficient")

        # Get all active agents for exclusion tracking
        all_active = self.router.registry.active_agents()

        # Get scored recommendations (with work type filtering)
        scored = self.router.recommend(
            phase=phase,
            task_tags=task_tags or [],
            sensitivity_required=sensitivity or {},
            context_size=context_size,
            work_type=resolved_type if resolved_type != "unclassified" else None,
        )

        # Track which agents were excluded and why
        scored_names = {s.agent for s in scored}
        excluded = []
        for agent in all_active:
            if agent.name not in scored_names:
                reason = self._exclusion_reason(agent, resolved_type, wt_spec, phase)
                excluded.append({"agent": agent.name, "reason": reason})

        return DispatchPlan(
            work_type=resolved_type,
            cognitive_class=cognitive_class,
            verification_policy=verification,
            ranked_agents=scored,
            excluded_agents=excluded,
        )

    def _exclusion_reason(
        self,
        agent: Any,
        work_type: str,
        wt_spec: dict[str, Any],
        phase: str,
    ) -> str:
        """Determine why an agent was excluded from routing."""
        from .fleet_router import COGNITIVE_CLASS_RANK

        wt_class = wt_spec.get("cognitive_class", "mechanical")
        agent_max = agent.restrictions.max_cognitive_class
        wt_rank = COGNITIVE_CLASS_RANK.get(wt_class, 1)
        agent_rank = COGNITIVE_CLASS_RANK.get(agent_max, 1)
        if wt_rank > agent_rank:
            return f"cognitive_class {wt_class} exceeds agent max {agent_max}"

        if work_type in agent.restrictions.never_decide:
            return f"work type '{work_type}' in agent's never_decide list"

        required_affinity = wt_spec.get("required_phase_affinity", {})
        for req_phase, min_score in required_affinity.items():
            actual = agent.phase_affinity.get(req_phase, 0.0)
            if actual < min_score:
                return f"phase affinity {req_phase}={actual} below required {min_score}"

        # Check sensitivity
        for key, needed in wt_spec.get("required_sensitivity", {}).items():
            if needed and not getattr(agent.sensitivity, key, False):
                return f"missing sensitivity: {key}"

        return "unknown"
