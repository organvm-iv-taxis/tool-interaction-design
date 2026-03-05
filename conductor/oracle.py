"""The Oracle — contextual advisory engine for the Conductor OS.

Consumes session stats, observability trends, pattern data, and governance
state to produce actionable advisories. Read-only — never mutates state.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import SESSIONS_DIR, STATS_FILE, WORKSPACE


@dataclass
class Advisory:
    """A single piece of contextual guidance."""

    category: str  # e.g., "process", "risk", "growth", "history"
    severity: str  # "info", "caution", "warning"
    message: str  # Human-readable guidance
    context: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""  # Actionable next step

    SEVERITY_ORDER = {"warning": 0, "caution": 1, "info": 2}

    def sort_key(self) -> tuple[int, str]:
        return (self.SEVERITY_ORDER.get(self.severity, 99), self.category)


class Oracle:
    """Read-only advisory engine that whispers wisdom based on system state."""

    def __init__(self) -> None:
        self._stats: dict[str, Any] | None = None
        self._trends: dict[str, Any] | None = None
        self._patterns: list[tuple[str, str]] | None = None
        self._pattern_history: list[dict[str, Any]] | None = None

    def _load_stats(self) -> dict[str, Any]:
        if self._stats is not None:
            return self._stats
        if STATS_FILE.exists():
            import json
            try:
                self._stats = json.loads(STATS_FILE.read_text())
                return self._stats
            except (OSError, json.JSONDecodeError):
                pass
        self._stats = {}
        return self._stats

    def _load_trends(self) -> dict[str, Any]:
        if self._trends is not None:
            return self._trends
        try:
            from .observability import compute_trend_report
            self._trends = compute_trend_report()
        except Exception:
            self._trends = {}
        return self._trends

    def _load_patterns(self) -> list[tuple[str, str]]:
        """Mine patterns from session logs (lightweight version)."""
        if self._patterns is not None:
            return self._patterns

        import yaml
        from collections import defaultdict

        patterns: list[tuple[str, str]] = []
        session_logs = list(SESSIONS_DIR.glob("*/session-log.yaml"))
        if not session_logs:
            self._patterns = patterns
            return patterns

        total = len(session_logs)
        phase_durations: dict[str, list[int]] = defaultdict(list)
        warning_types: Counter = Counter()

        for log_path in session_logs:
            try:
                log = yaml.safe_load(log_path.read_text())
            except Exception:
                continue
            for phase_name, phase_data in (log or {}).get("phases", {}).items():
                if isinstance(phase_data, dict):
                    phase_durations[phase_name].append(phase_data.get("duration", 0))
            for w in (log or {}).get("warnings", []):
                if "during FRAME" in w:
                    warning_types["phase_violation_FRAME"] += 1

        frame_durs = phase_durations.get("FRAME", [])
        build_durs = phase_durations.get("BUILD", [])
        avg_frame = sum(frame_durs) / len(frame_durs) if frame_durs else 0
        avg_build = sum(build_durs) / len(build_durs) if build_durs else 0

        if avg_frame < 5 and total > 3:
            patterns.append(("QUICK_FRAME", f"FRAME phase averages {avg_frame:.0f}m"))
        if avg_build > 60:
            patterns.append(("MARATHON_BUILD", f"BUILD phase averages {avg_build:.0f}m"))
        if warning_types.get("phase_violation_FRAME", 0) > total * 0.3:
            patterns.append(("EAGER_CODER", "Frequent code tool use during FRAME"))

        self._patterns = patterns
        return patterns

    def _load_pattern_history(self) -> list[dict[str, Any]]:
        if self._pattern_history is not None:
            return self._pattern_history
        try:
            from .constants import BASE
            history_file = BASE / ".conductor-pattern-history.jsonl"
            if not history_file.exists():
                self._pattern_history = []
                return self._pattern_history
            import json
            entries: list[dict[str, Any]] = []
            for line in history_file.read_text().splitlines():
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
            self._pattern_history = entries
        except Exception:
            self._pattern_history = []
        return self._pattern_history

    # ----- Detectors -----

    def _detect_process_drift(self) -> list[Advisory]:
        """Check for skipped phases and process violations."""
        advisories: list[Advisory] = []
        stats = self._load_stats()
        recent = stats.get("recent_sessions", [])
        if len(recent) < 3:
            return advisories

        # Check if sessions complete without going through all phases
        import yaml
        frame_skips = 0
        for session_info in recent[-5:]:
            sid = session_info.get("session_id", "")
            log_path = SESSIONS_DIR / sid / "session-log.yaml"
            if log_path.exists():
                try:
                    log = yaml.safe_load(log_path.read_text())
                    phases = (log or {}).get("phases", {})
                    if "FRAME" not in phases:
                        frame_skips += 1
                except Exception:
                    pass

        if frame_skips >= 2:
            advisories.append(Advisory(
                category="process",
                severity="caution",
                message=f"You've skipped FRAME in {frame_skips} of your last {min(5, len(recent))} sessions. Framing prevents scope creep.",
                context={"frame_skips": frame_skips},
                recommendation="Spend at least 5 minutes in FRAME before transitioning to SHAPE.",
            ))
        return advisories

    def _detect_scope_risk(self) -> list[Advisory]:
        """Detect sessions that are running unusually long."""
        advisories: list[Advisory] = []
        stats = self._load_stats()
        total_sessions = stats.get("total_sessions", 0)
        total_minutes = stats.get("total_minutes", 0)
        if total_sessions < 3:
            return advisories

        avg_duration = total_minutes / total_sessions

        # Check if there's an active session running long
        from .constants import SESSION_STATE_FILE
        if SESSION_STATE_FILE.exists():
            import json
            try:
                session = json.loads(SESSION_STATE_FILE.read_text())
                start_time = session.get("start_time", 0)
                duration_min = (time.time() - start_time) / 60 if start_time else 0
                if duration_min > avg_duration * 2 and duration_min > 30:
                    advisories.append(Advisory(
                        category="risk",
                        severity="caution",
                        message=f"This session is {duration_min:.0f}m — {duration_min / avg_duration:.1f}x your average ({avg_duration:.0f}m). Consider checkpointing.",
                        context={"current_duration": duration_min, "average_duration": avg_duration},
                        recommendation="Run `conductor session phase prove` or checkpoint your progress.",
                    ))
            except (OSError, json.JSONDecodeError):
                pass

        return advisories

    def _detect_momentum(self) -> list[Advisory]:
        """Check streak and ship rate trends."""
        advisories: list[Advisory] = []
        stats = self._load_stats()
        streak = stats.get("streak", 0)
        total = stats.get("total_sessions", 0)
        shipped = stats.get("shipped", 0)

        if streak >= 3:
            advisories.append(Advisory(
                category="growth",
                severity="info",
                message=f"You're on a {streak}-session shipping streak! Momentum is building.",
                context={"streak": streak},
                recommendation="Keep the streak alive — consider a smaller scope for your next session.",
            ))

        if total >= 5:
            ship_rate = shipped / total * 100
            if ship_rate >= 70:
                advisories.append(Advisory(
                    category="growth",
                    severity="info",
                    message=f"Your ship rate is {ship_rate:.0f}% — strong execution.",
                    context={"ship_rate": ship_rate, "shipped": shipped, "total": total},
                    recommendation="Maintain quality. Consider increasing scope complexity.",
                ))
            elif ship_rate < 40 and total >= 5:
                advisories.append(Advisory(
                    category="risk",
                    severity="warning",
                    message=f"Ship rate is {ship_rate:.0f}% ({shipped}/{total}). Many sessions close without shipping.",
                    context={"ship_rate": ship_rate},
                    recommendation="Reduce session scope. Aim for shippable increments.",
                ))

        return advisories

    def _detect_governance_gaps(self) -> list[Advisory]:
        """Check for repos stuck in promotion pipeline."""
        advisories: list[Advisory] = []
        try:
            from .governance import GovernanceRuntime
            gov = GovernanceRuntime()
            all_repos = gov._all_repos()

            candidate_count = sum(
                1 for _, r in all_repos
                if r.get("promotion_status") == "CANDIDATE"
            )
            if candidate_count > 10:
                advisories.append(Advisory(
                    category="process",
                    severity="warning",
                    message=f"{candidate_count} repos are stuck in CANDIDATE state. Pipeline is congested.",
                    context={"candidate_count": candidate_count},
                    recommendation="Run `conductor wip auto-promote --apply` or archive stale repos.",
                ))

            # Check for repos without CI
            no_ci = sum(1 for _, r in all_repos if not r.get("ci_workflow"))
            if no_ci > 15:
                advisories.append(Advisory(
                    category="process",
                    severity="caution",
                    message=f"{no_ci} repos lack CI workflows.",
                    context={"no_ci_count": no_ci},
                    recommendation="Run `conductor audit` to identify which repos need CI.",
                ))
        except Exception:
            pass

        return advisories

    def _detect_pattern_antipatterns(self) -> list[Advisory]:
        """Flag known risky behavioral patterns."""
        advisories: list[Advisory] = []
        patterns = self._load_patterns()
        pattern_history = self._load_pattern_history()

        pattern_names = {name for name, _ in patterns}

        if "MARATHON_BUILD" in pattern_names:
            desc = next((d for n, d in patterns if n == "MARATHON_BUILD"), "")
            # Check correlation with outcomes
            marathon_outcomes = [
                e for e in pattern_history
                if e.get("pattern") == "MARATHON_BUILD"
            ]
            fail_rate = ""
            if marathon_outcomes:
                fails = sum(1 for e in marathon_outcomes if e.get("outcome") != "SHIPPED")
                fail_rate = f" — {fails}/{len(marathon_outcomes)} sessions with this pattern didn't ship."

            advisories.append(Advisory(
                category="risk",
                severity="warning",
                message=f"MARATHON_BUILD detected: {desc}. Long builds without checkpoints correlate with higher failure rates{fail_rate}",
                context={"pattern": "MARATHON_BUILD"},
                recommendation="Break BUILD into smaller, shippable increments.",
            ))

        if "EAGER_CODER" in pattern_names:
            advisories.append(Advisory(
                category="process",
                severity="caution",
                message="EAGER_CODER detected: code tools used during FRAME phase. Research before building.",
                context={"pattern": "EAGER_CODER"},
                recommendation="During FRAME, use only research and documentation tools.",
            ))

        return advisories

    def _detect_knowledge_gaps(self) -> list[Advisory]:
        """Check for repeated failures in specific domains."""
        advisories: list[Advisory] = []
        trends = self._load_trends()
        if not trends:
            return advisories

        recent = trends.get("recent", {})
        if recent.get("failures", 0) >= 3 and recent.get("failure_rate", 0) > 0.3:
            advisories.append(Advisory(
                category="risk",
                severity="warning",
                message=f"Recent failure rate is {recent['failure_rate']*100:.0f}% ({recent['failures']}/{recent['events']} events).",
                context={"failure_rate": recent["failure_rate"]},
                recommendation="Review recent failures with `conductor observability report`.",
            ))

        return advisories

    def _detect_growth_opportunities(self) -> list[Advisory]:
        """Identify unexplored capabilities and domains."""
        advisories: list[Advisory] = []
        stats = self._load_stats()
        total = stats.get("total_sessions", 0)
        by_organ = stats.get("by_organ", {})

        if total >= 5 and len(by_organ) <= 2:
            explored = list(by_organ.keys())
            advisories.append(Advisory(
                category="growth",
                severity="info",
                message=f"You've only worked in {len(by_organ)} organ(s) ({', '.join(explored)}). Consider exploring others.",
                context={"explored_organs": explored},
                recommendation="Start a session in a different organ to broaden experience.",
            ))

        return advisories

    def _detect_seasonal_wisdom(self) -> list[Advisory]:
        """Time-based patterns and contextual observations."""
        advisories: list[Advisory] = []
        now = datetime.now(timezone.utc)

        if now.weekday() == 4 and now.hour >= 17:  # Friday evening
            advisories.append(Advisory(
                category="history",
                severity="info",
                message="Friday evening sessions tend to have lower completion rates. Consider a lighter scope.",
                context={"day": "Friday", "hour": now.hour},
                recommendation="Pick a small, self-contained task or focus on FRAME/SHAPE for Monday.",
            ))

        if now.hour >= 23 or now.hour < 5:
            advisories.append(Advisory(
                category="history",
                severity="caution",
                message="Late-night sessions produce more warnings and lower ship rates.",
                context={"hour": now.hour},
                recommendation="Consider saving complex work for daytime. Focus on documentation or planning.",
            ))

        return advisories

    def _generate_growth_plan(self) -> list[Advisory]:
        """Analyze pattern history for growth recommendations."""
        advisories: list[Advisory] = []
        pattern_history = self._load_pattern_history()
        stats = self._load_stats()
        total = stats.get("total_sessions", 0)

        if not pattern_history or total < 5:
            return advisories

        # Correlate patterns with outcomes
        pattern_outcomes: dict[str, dict[str, int]] = {}
        for entry in pattern_history:
            pat = entry.get("pattern", "")
            outcome = entry.get("outcome", "UNKNOWN")
            if pat not in pattern_outcomes:
                pattern_outcomes[pat] = {"SHIPPED": 0, "CLOSED": 0, "total": 0}
            pattern_outcomes[pat]["total"] += 1
            if outcome in pattern_outcomes[pat]:
                pattern_outcomes[pat][outcome] += 1

        for pat, outcomes in pattern_outcomes.items():
            if outcomes["total"] >= 3:
                ship_rate = outcomes["SHIPPED"] / outcomes["total"] * 100
                if ship_rate < 40:
                    advisories.append(Advisory(
                        category="growth",
                        severity="caution",
                        message=f"Pattern '{pat}' has a {ship_rate:.0f}% ship rate ({outcomes['SHIPPED']}/{outcomes['total']}). Consider changing behavior.",
                        context={"pattern": pat, "ship_rate": ship_rate, "outcomes": outcomes},
                        recommendation=f"When '{pat}' is detected, slow down and re-scope.",
                    ))

        return advisories

    # ----- Main entry point -----

    def consult(self, context: dict[str, Any] | None = None, max_advisories: int = 8) -> list[Advisory]:
        """Run all detectors and return top-N sorted advisories."""
        all_advisories: list[Advisory] = []

        detectors = [
            self._detect_process_drift,
            self._detect_scope_risk,
            self._detect_momentum,
            self._detect_governance_gaps,
            self._detect_pattern_antipatterns,
            self._detect_knowledge_gaps,
            self._detect_growth_opportunities,
            self._detect_seasonal_wisdom,
            self._generate_growth_plan,
        ]

        for detector in detectors:
            try:
                all_advisories.extend(detector())
            except Exception:
                pass

        # Deduplicate by message
        seen: set[str] = set()
        unique: list[Advisory] = []
        for adv in all_advisories:
            if adv.message not in seen:
                seen.add(adv.message)
                unique.append(adv)

        # Sort by severity (warnings first)
        unique.sort(key=lambda a: a.sort_key())

        return unique[:max_advisories]
