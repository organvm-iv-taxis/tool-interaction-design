"""Fleet routing — score agents for task assignment based on phase, capabilities,
utilization pressure, context fit, and cost efficiency."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .fleet import FleetAgent, FleetRegistry
from .fleet_usage import FleetUsageTracker


@dataclass
class RouteScore:
    """Scored recommendation for an agent."""

    agent: str
    display_name: str
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)


# Scoring weights
W_PHASE_AFFINITY = 0.30
W_STRENGTH_MATCH = 0.20
W_UTILIZATION_PRESSURE = 0.20
W_CONTEXT_FIT = 0.15
W_COST_EFFICIENCY = 0.15


class FleetRouter:
    """Routes tasks to the best-fit agent in the fleet."""

    def __init__(
        self,
        registry: FleetRegistry | None = None,
        tracker: FleetUsageTracker | None = None,
    ) -> None:
        self.registry = registry or FleetRegistry()
        self.tracker = tracker or FleetUsageTracker()

    def recommend(
        self,
        phase: str,
        task_tags: list[str] | None = None,
        sensitivity_required: dict[str, bool] | None = None,
        context_size: int = 0,
    ) -> list[RouteScore]:
        """Return agents scored and ranked for the given task context.

        Args:
            phase: Current conductor phase (FRAME, SHAPE, BUILD, PROVE).
            task_tags: Optional tags describing the task (matched against strengths).
            sensitivity_required: Dict of sensitivity requirements, e.g.
                {"can_see_secrets": True, "can_push_git": True}.
            context_size: Estimated context size in tokens (for context fit scoring).

        Returns:
            Sorted list of RouteScore (highest score first), excluding
            inactive agents and those failing sensitivity hard filters.
        """
        task_tags = task_tags or []
        sensitivity_required = sensitivity_required or {}
        phase_upper = phase.upper()

        # Get current utilization snapshot
        today = date.today()
        daily = self.tracker.daily_snapshot(today)

        # Get monthly utilization for pressure scoring
        monthly_report = self.tracker.utilization_report(
            today.year, today.month, self.registry.active_agents()
        )

        scores: list[RouteScore] = []

        for agent in self.registry.active_agents():
            # Hard filter: sensitivity requirements
            if not self._passes_sensitivity(agent, sensitivity_required):
                continue

            breakdown: dict[str, float] = {}

            # 1. Phase affinity (0.0-1.0)
            affinity = agent.phase_affinity.get(phase_upper, 0.5)
            breakdown["phase_affinity"] = affinity

            # 2. Strength match (0.0-1.0)
            strength_score = self._strength_match(agent, task_tags)
            breakdown["strength_match"] = strength_score

            # 3. Utilization pressure (higher = more underused = should use more)
            util_pct = monthly_report.get(agent.name, {}).get("utilization_pct", 0)
            pressure = max(0.0, min(1.0, 1.0 - (util_pct / 100.0)))
            breakdown["utilization_pressure"] = pressure

            # 4. Context fit (1.0 if context fits, degrades if too large)
            context_fit = self._context_fit(agent, context_size)
            breakdown["context_fit"] = context_fit

            # 5. Cost efficiency (free tiers score higher)
            cost_score = self._cost_efficiency(agent)
            breakdown["cost_efficiency"] = cost_score

            total = (
                W_PHASE_AFFINITY * affinity
                + W_STRENGTH_MATCH * strength_score
                + W_UTILIZATION_PRESSURE * pressure
                + W_CONTEXT_FIT * context_fit
                + W_COST_EFFICIENCY * cost_score
            )
            breakdown["total"] = round(total, 3)

            scores.append(RouteScore(
                agent=agent.name,
                display_name=agent.display_name,
                score=round(total, 3),
                breakdown=breakdown,
            ))

        scores.sort(key=lambda s: s.score, reverse=True)
        return scores

    def explain(self, route_score: RouteScore) -> str:
        """Human-readable explanation of a routing score."""
        lines = [f"{route_score.display_name} (score: {route_score.score:.3f})"]
        for factor, value in route_score.breakdown.items():
            if factor == "total":
                continue
            bar = "█" * int(value * 10) + "░" * (10 - int(value * 10))
            lines.append(f"  {factor:<24} {bar} {value:.2f}")
        return "\n".join(lines)

    @staticmethod
    def _passes_sensitivity(
        agent: FleetAgent, required: dict[str, bool]
    ) -> bool:
        """Check that agent meets all sensitivity requirements."""
        for key, needed in required.items():
            if not needed:
                continue
            agent_val = getattr(agent.sensitivity, key, False)
            if not agent_val:
                return False
        return True

    @staticmethod
    def _strength_match(agent: FleetAgent, task_tags: list[str]) -> float:
        """Score how well agent strengths match task tags (0.0-1.0)."""
        if not task_tags:
            return 0.5  # Neutral when no tags provided
        strengths = set(agent.capabilities.strengths)
        weaknesses = set(agent.capabilities.weaknesses)
        tags = set(task_tags)

        matches = len(tags & strengths)
        anti_matches = len(tags & weaknesses)
        total = len(tags)

        if total == 0:
            return 0.5

        # Positive for matches, penalty for anti-matches
        raw = (matches - anti_matches * 0.5) / total
        return max(0.0, min(1.0, 0.5 + raw * 0.5))

    @staticmethod
    def _context_fit(agent: FleetAgent, context_size: int) -> float:
        """Score context size fit (1.0 if fits comfortably, degrades if tight)."""
        if context_size <= 0:
            return 0.8  # Neutral when unknown
        window = agent.subscription.allotment.context_window
        if window <= 0:
            return 0.5
        ratio = context_size / window
        if ratio <= 0.5:
            return 1.0
        if ratio <= 0.8:
            return 0.8
        if ratio <= 1.0:
            return 0.5
        return 0.1  # Exceeds context window

    @staticmethod
    def _cost_efficiency(agent: FleetAgent) -> float:
        """Score cost efficiency (free tiers get higher scores)."""
        tier = agent.subscription.tier.lower()
        tier_scores = {
            "free": 1.0,
            "plus": 0.6,
            "pro": 0.5,
            "max": 0.3,
        }
        return tier_scores.get(tier, 0.5)
