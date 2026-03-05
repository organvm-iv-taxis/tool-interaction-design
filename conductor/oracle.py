"""The Oracle — contextual advisory engine for the Conductor OS.

Consumes session stats, observability trends, pattern data, and governance
state to produce actionable advisories. Writes ONLY to its own state file
(.conductor-oracle-state.json) — never mutates session/governance/workflow state.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import ORACLE_STATE_FILE, SESSIONS_DIR, STATS_FILE, WORKSPACE


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


SEVERITY_ORDER = {"critical": -1, "warning": 0, "caution": 1, "info": 2}


@dataclass
class Advisory:
    """A single piece of contextual guidance."""

    category: str  # e.g., "process", "risk", "growth", "history", "gate", "narrative"
    severity: str  # "critical", "warning", "caution", "info"
    message: str  # Human-readable guidance
    context: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""  # Actionable next step
    # --- New fields (backward-compatible defaults) ---
    detector: str = ""  # Which detector produced this
    tools_suggested: list[str] = field(default_factory=list)  # Recommended cluster IDs
    gate_action: str = ""  # "", "block", "warn", "approve"
    confidence: float = 1.0  # 0.0-1.0
    narrative: str = ""  # Rich contextual wisdom text (capped 200 chars)
    tags: list[str] = field(default_factory=list)  # For filtering/grouping

    SEVERITY_ORDER = SEVERITY_ORDER

    def sort_key(self) -> tuple[int, str]:
        return (self.SEVERITY_ORDER.get(self.severity, 99), self.category)

    def advisory_hash(self) -> str:
        """Stable hash for dedup/acknowledgment."""
        return hashlib.sha256(f"{self.detector}:{self.category}:{self.message[:80]}".encode()).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "context": self.context,
            "recommendation": self.recommendation,
            "detector": self.detector,
            "tools_suggested": self.tools_suggested,
            "gate_action": self.gate_action,
            "confidence": self.confidence,
            "narrative": self.narrative,
            "tags": self.tags,
        }


@dataclass
class OracleContext:
    """Structured input for Oracle consultations."""

    trigger: str = "manual"  # session_start, session_close, phase_transition, workflow_pre_step, workflow_post_step, patchbay, promotion, manual
    session_id: str = ""
    current_phase: str = ""
    target_phase: str = ""
    workflow_step: str = ""
    workflow_name: str = ""
    promotion_repo: str = ""
    organ: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OracleContext:
        """Backward-compatible construction from a plain dict."""
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for k, v in d.items():
            if k in known:
                kwargs[k] = v
            else:
                extra[k] = v
        if extra:
            kwargs.setdefault("extra", {}).update(extra)
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# Oracle
# ---------------------------------------------------------------------------


class Oracle:
    """Read-only advisory engine that whispers wisdom based on system state.

    Writes ONLY to ORACLE_STATE_FILE — never to session, governance, or workflow state.
    """

    def __init__(self) -> None:
        self._stats: dict[str, Any] | None = None
        self._trends: dict[str, Any] | None = None
        self._patterns: list[tuple[str, str]] | None = None
        self._pattern_history: list[dict[str, Any]] | None = None
        self._oracle_state: dict[str, Any] | None = None

    # ----- Loaders -----

    def _load_stats(self) -> dict[str, Any]:
        if self._stats is not None:
            return self._stats
        if STATS_FILE.exists():
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
            entries: list[dict[str, Any]] = []
            for line in history_file.read_text().splitlines():
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
            self._pattern_history = entries
        except Exception:
            self._pattern_history = []
        return self._pattern_history

    # ----- Oracle state persistence -----

    def _load_oracle_state(self) -> dict[str, Any]:
        if self._oracle_state is not None:
            return self._oracle_state
        if ORACLE_STATE_FILE.exists():
            try:
                self._oracle_state = json.loads(ORACLE_STATE_FILE.read_text())
                return self._oracle_state
            except (OSError, json.JSONDecodeError):
                pass
        self._oracle_state = {
            "advisory_log": [],
            "detector_scores": {},
            "suppressed_hashes": [],
        }
        return self._oracle_state

    def _save_oracle_state(self) -> None:
        state = self._load_oracle_state()
        from .constants import atomic_write
        atomic_write(ORACLE_STATE_FILE, json.dumps(state, indent=2))

    def _record_advisories(self, advisories: list[Advisory]) -> None:
        """Append advisories to the log (capped at 500 entries)."""
        state = self._load_oracle_state()
        log = state.setdefault("advisory_log", [])
        now = datetime.now(timezone.utc).isoformat()
        for adv in advisories:
            log.append({
                "timestamp": now,
                "hash": adv.advisory_hash(),
                "detector": adv.detector,
                "category": adv.category,
                "severity": adv.severity,
                "message": adv.message[:120],
                "confidence": adv.confidence,
            })
        state["advisory_log"] = log[-500:]
        self._save_oracle_state()

    def _update_effectiveness(self, session_id: str, result: str) -> None:
        """Record which advisories were active during a session and correlate with outcome."""
        state = self._load_oracle_state()
        log = state.get("advisory_log", [])
        scores = state.setdefault("detector_scores", {})

        # Find advisories from this session's time window
        recent_detectors: set[str] = set()
        for entry in log[-50:]:
            det = entry.get("detector", "")
            if det:
                recent_detectors.add(det)

        shipped = result == "SHIPPED"
        for det in recent_detectors:
            if det not in scores:
                scores[det] = {"advised": 0, "shipped": 0, "total": 0}
            scores[det]["advised"] += 1
            scores[det]["total"] += 1
            if shipped:
                scores[det]["shipped"] += 1

        self._save_oracle_state()

    def acknowledge(self, advisory_hash: str) -> bool:
        """Suppress an advisory by its hash."""
        state = self._load_oracle_state()
        suppressed = state.setdefault("suppressed_hashes", [])
        if advisory_hash not in suppressed:
            suppressed.append(advisory_hash)
            state["suppressed_hashes"] = suppressed[-200:]
            self._save_oracle_state()
            return True
        return False

    # ----- Existing detectors -----

    def _detect_process_drift(self) -> list[Advisory]:
        """Check for skipped phases and process violations."""
        advisories: list[Advisory] = []
        stats = self._load_stats()
        recent = stats.get("recent_sessions", [])
        if len(recent) < 3:
            return advisories

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
                detector="process_drift",
                confidence=0.8,
                tags=["process", "phase"],
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

        from .constants import SESSION_STATE_FILE
        if SESSION_STATE_FILE.exists():
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
                        detector="scope_risk",
                        confidence=0.7,
                        tags=["risk", "duration"],
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
                detector="momentum",
                confidence=0.9,
                tags=["growth", "streak"],
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
                    detector="momentum",
                    confidence=0.9,
                    tags=["growth", "ship_rate"],
                ))
            elif ship_rate < 40 and total >= 5:
                advisories.append(Advisory(
                    category="risk",
                    severity="warning",
                    message=f"Ship rate is {ship_rate:.0f}% ({shipped}/{total}). Many sessions close without shipping.",
                    context={"ship_rate": ship_rate},
                    recommendation="Reduce session scope. Aim for shippable increments.",
                    detector="momentum",
                    confidence=0.85,
                    tags=["risk", "ship_rate"],
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
                    detector="governance_gaps",
                    confidence=0.9,
                    tags=["governance", "pipeline"],
                ))

            no_ci = sum(1 for _, r in all_repos if not r.get("ci_workflow"))
            if no_ci > 15:
                advisories.append(Advisory(
                    category="process",
                    severity="caution",
                    message=f"{no_ci} repos lack CI workflows.",
                    context={"no_ci_count": no_ci},
                    recommendation="Run `conductor audit` to identify which repos need CI.",
                    detector="governance_gaps",
                    confidence=0.85,
                    tags=["governance", "ci"],
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
                detector="pattern_antipatterns",
                confidence=0.8,
                tags=["risk", "pattern"],
            ))

        if "EAGER_CODER" in pattern_names:
            advisories.append(Advisory(
                category="process",
                severity="caution",
                message="EAGER_CODER detected: code tools used during FRAME phase. Research before building.",
                context={"pattern": "EAGER_CODER"},
                recommendation="During FRAME, use only research and documentation tools.",
                detector="pattern_antipatterns",
                confidence=0.8,
                tags=["process", "pattern"],
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
                detector="knowledge_gaps",
                confidence=0.75,
                tags=["risk", "failures"],
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
                detector="growth_opportunities",
                confidence=0.7,
                tags=["growth", "exploration"],
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
                detector="seasonal_wisdom",
                confidence=0.6,
                tags=["history", "timing"],
            ))

        if now.hour >= 23 or now.hour < 5:
            advisories.append(Advisory(
                category="history",
                severity="caution",
                message="Late-night sessions produce more warnings and lower ship rates.",
                context={"hour": now.hour},
                recommendation="Consider saving complex work for daytime. Focus on documentation or planning.",
                detector="seasonal_wisdom",
                confidence=0.6,
                tags=["history", "timing"],
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
                        detector="growth_plan",
                        confidence=0.7,
                        tags=["growth", "pattern"],
                    ))

        return advisories

    # ----- NEW detectors (Phase 2) -----

    def _detect_tool_recommendations(self, ctx: OracleContext) -> list[Advisory]:
        """Suggest tool clusters based on current phase + ontology."""
        advisories: list[Advisory] = []
        if not ctx.current_phase:
            return advisories

        try:
            from .constants import get_phase_clusters, SESSION_STATE_FILE
            phase_clusters = get_phase_clusters()
            active_clusters = phase_clusters.get(ctx.current_phase, [])

            if not active_clusters:
                return advisories

            # Check session for tools used so far in this phase
            if SESSION_STATE_FILE.exists():
                session = json.loads(SESSION_STATE_FILE.read_text())
                phase_logs = session.get("phase_logs", [])
                current_tools: set[str] = set()
                for pl in phase_logs:
                    if pl.get("name") == ctx.current_phase and pl.get("end_time", 0) == 0:
                        current_tools = set(pl.get("tools_used", []))
                        break

                if not current_tools and ctx.trigger in ("session_start", "phase_transition", "patchbay"):
                    advisories.append(Advisory(
                        category="process",
                        severity="info",
                        message=f"Phase {ctx.current_phase} has {len(active_clusters)} active clusters. Start with: {', '.join(active_clusters[:3])}.",
                        tools_suggested=active_clusters[:5],
                        detector="tool_recommendations",
                        confidence=0.7,
                        tags=["tools", "phase"],
                    ))
        except Exception:
            pass

        return advisories

    def _detect_gate_checks(self, ctx: OracleContext) -> list[Advisory]:
        """Advisory guidance at phase transitions and promotions."""
        advisories: list[Advisory] = []

        if ctx.trigger == "phase_transition" and ctx.target_phase:
            # Phase gate checks
            if ctx.current_phase == "FRAME" and ctx.target_phase == "SHAPE":
                try:
                    from .constants import SESSION_STATE_FILE
                    if SESSION_STATE_FILE.exists():
                        session = json.loads(SESSION_STATE_FILE.read_text())
                        start = session.get("start_time", 0)
                        duration = (time.time() - start) / 60 if start else 0
                        if duration < 3:
                            advisories.append(Advisory(
                                category="gate",
                                severity="caution",
                                message=f"FRAME lasted only {duration:.0f}m. Consider spending more time on research.",
                                gate_action="warn",
                                detector="gate_checks",
                                confidence=0.75,
                                tags=["gate", "phase_transition"],
                            ))
                except Exception:
                    pass

            if ctx.current_phase == "BUILD" and ctx.target_phase == "PROVE":
                # Warn if no commits
                try:
                    from .constants import SESSION_STATE_FILE
                    if SESSION_STATE_FILE.exists():
                        session = json.loads(SESSION_STATE_FILE.read_text())
                        phase_logs = session.get("phase_logs", [])
                        build_commits = 0
                        for pl in phase_logs:
                            if pl.get("name") == "BUILD":
                                build_commits += pl.get("commits", 0)
                        if build_commits == 0:
                            advisories.append(Advisory(
                                category="gate",
                                severity="caution",
                                message="Moving to PROVE with no recorded commits in BUILD. Ensure work is saved.",
                                gate_action="warn",
                                detector="gate_checks",
                                confidence=0.7,
                                tags=["gate", "phase_transition"],
                            ))
                except Exception:
                    pass

            if ctx.target_phase == "DONE":
                # Check for active warnings
                try:
                    from .constants import SESSION_STATE_FILE
                    if SESSION_STATE_FILE.exists():
                        session = json.loads(SESSION_STATE_FILE.read_text())
                        warnings = session.get("warnings", [])
                        if len(warnings) >= 3:
                            advisories.append(Advisory(
                                category="gate",
                                severity="caution",
                                message=f"Session has {len(warnings)} warnings. Review before marking DONE.",
                                gate_action="warn",
                                detector="gate_checks",
                                confidence=0.8,
                                tags=["gate", "warnings"],
                            ))
                except Exception:
                    pass

        if ctx.trigger == "promotion" and ctx.promotion_repo:
            try:
                from .governance import GovernanceRuntime
                gov = GovernanceRuntime()
                all_repos = gov._all_repos()
                for name, repo in all_repos:
                    if name == ctx.promotion_repo:
                        if not repo.get("ci_workflow"):
                            advisories.append(Advisory(
                                category="gate",
                                severity="warning",
                                message=f"'{ctx.promotion_repo}' lacks CI. Add CI before promoting.",
                                gate_action="warn",
                                detector="gate_checks",
                                confidence=0.9,
                                tags=["gate", "promotion", "ci"],
                            ))
                        break
            except Exception:
                pass

        return advisories

    def _detect_predictive_warnings(self) -> list[Advisory]:
        """Forecast issues using cross-session historical data."""
        advisories: list[Advisory] = []
        stats = self._load_stats()
        total = stats.get("total_sessions", 0)
        total_minutes = stats.get("total_minutes", 0)
        if total < 5:
            return advisories

        avg_duration = total_minutes / total

        # Earlier marathon detection: 1.5x threshold (instead of 2x in scope_risk)
        try:
            from .constants import SESSION_STATE_FILE
            if SESSION_STATE_FILE.exists():
                session = json.loads(SESSION_STATE_FILE.read_text())
                start_time = session.get("start_time", 0)
                duration_min = (time.time() - start_time) / 60 if start_time else 0
                if avg_duration > 0 and 1.5 * avg_duration < duration_min <= 2 * avg_duration and duration_min > 20:
                    advisories.append(Advisory(
                        category="risk",
                        severity="info",
                        message=f"Session approaching {duration_min:.0f}m (avg {avg_duration:.0f}m). Consider scoping down.",
                        detector="predictive_warnings",
                        confidence=0.6,
                        tags=["risk", "prediction"],
                    ))
        except Exception:
            pass

        # Composite session health score
        recent = stats.get("recent_sessions", [])
        if len(recent) >= 3:
            recent_shipped = sum(1 for s in recent[-5:] if s.get("result") == "SHIPPED")
            recent_total = min(5, len(recent))
            health_score = recent_shipped / recent_total
            if health_score < 0.3:
                advisories.append(Advisory(
                    category="risk",
                    severity="warning",
                    message=f"Session health score: {health_score:.0%}. Only {recent_shipped}/{recent_total} recent sessions shipped.",
                    detector="predictive_warnings",
                    confidence=0.7,
                    tags=["risk", "health"],
                ))

        return advisories

    def _generate_narrative_wisdom(self, ctx: OracleContext) -> list[Advisory]:
        """Rich contextual messages — the 'wise sage whispering in your ear'."""
        advisories: list[Advisory] = []
        stats = self._load_stats()
        total = stats.get("total_sessions", 0)
        streak = stats.get("streak", 0)

        # Milestone narratives
        milestone_messages = {
            5: "Five sessions in. You're building rhythm — the conductor's baton is finding its tempo.",
            10: "Ten sessions deep. Patterns are emerging from practice. Trust the process.",
            25: "Twenty-five sessions. The system is no longer scaffolding — it's becoming your instrument.",
            50: "Fifty sessions. Half a century of disciplined creation. The forge knows your hand.",
            100: "One hundred sessions. What was once process is now instinct. The orchestra plays itself.",
        }
        if total in milestone_messages:
            advisories.append(Advisory(
                category="narrative",
                severity="info",
                message=milestone_messages[total],
                detector="narrative_wisdom",
                narrative=milestone_messages[total][:200],
                confidence=1.0,
                tags=["narrative", "milestone"],
            ))

        # Streak encouragement
        if streak >= 5:
            advisories.append(Advisory(
                category="narrative",
                severity="info",
                message=f"A {streak}-session streak. Each shipment compounds. Consistency is the real multiplier.",
                detector="narrative_wisdom",
                narrative=f"A {streak}-session streak. Consistency is the real multiplier."[:200],
                confidence=0.9,
                tags=["narrative", "streak"],
            ))

        # Phase transition wisdom
        phase_wisdom = {
            "FRAME": "FRAME: the librarian's hour. Resist the urge to build — understand first.",
            "SHAPE": "SHAPE: the architect's draft. A plan drawn now saves ten corrections later.",
            "BUILD": "BUILD: the maker's focus. Follow the plan; let the orchestra play the score.",
            "PROVE": "PROVE: the tester's eye. What ships unverified ships with hidden debt.",
        }
        if ctx.current_phase in phase_wisdom and ctx.trigger in ("phase_transition", "session_start"):
            wisdom = phase_wisdom[ctx.current_phase]
            advisories.append(Advisory(
                category="narrative",
                severity="info",
                message=wisdom,
                detector="narrative_wisdom",
                narrative=wisdom[:200],
                confidence=0.8,
                tags=["narrative", "phase"],
            ))

        # Time-of-day observation from actual data
        now = datetime.now(timezone.utc)
        if 5 <= now.hour < 9:
            advisories.append(Advisory(
                category="narrative",
                severity="info",
                message="Early morning — fresh cognition. Good time for FRAME and SHAPE work.",
                detector="narrative_wisdom",
                narrative="Early morning — fresh cognition. Ideal for research and architecture.",
                confidence=0.5,
                tags=["narrative", "timing"],
            ))

        return advisories

    def _detect_cross_session_patterns(self) -> list[Advisory]:
        """Learn which advisories were heeded vs ignored, correlate with outcomes."""
        advisories: list[Advisory] = []
        state = self._load_oracle_state()
        scores = state.get("detector_scores", {})

        for det, score_data in scores.items():
            total = score_data.get("total", 0)
            shipped = score_data.get("shipped", 0)
            if total >= 5:
                effectiveness = shipped / total
                if effectiveness < 0.3:
                    advisories.append(Advisory(
                        category="growth",
                        severity="caution",
                        message=f"Detector '{det}' active in {total} sessions but only {shipped} shipped. Consider addressing its advisories.",
                        detector="cross_session_patterns",
                        confidence=0.65,
                        tags=["growth", "effectiveness"],
                    ))

        return advisories

    def _detect_workflow_risks(self, ctx: OracleContext) -> list[Advisory]:
        """Advise during workflow step execution."""
        advisories: list[Advisory] = []

        if ctx.trigger not in ("workflow_pre_step", "workflow_post_step"):
            return advisories

        if ctx.trigger == "workflow_pre_step" and ctx.workflow_step:
            # Warn on degraded cluster health
            try:
                from .handoff import cluster_health_metrics
                health = cluster_health_metrics(window=100)
                for cluster_id, score in health.items():
                    if score < 0.7:
                        advisories.append(Advisory(
                            category="risk",
                            severity="caution",
                            message=f"Cluster '{cluster_id}' health is {score:.2f} — consider fallback tools.",
                            detector="workflow_risks",
                            confidence=0.7,
                            tags=["risk", "workflow", "health"],
                        ))
            except Exception:
                pass

        if ctx.trigger == "workflow_post_step":
            # Suggest checkpointing for long workflows
            try:
                from .constants import BASE
                wf_state_file = BASE / ".conductor-workflow-state.json"
                if wf_state_file.exists():
                    wf_state = json.loads(wf_state_file.read_text())
                    steps = wf_state.get("steps", {})
                    completed = sum(1 for s in steps.values() if isinstance(s, dict) and s.get("status") == "COMPLETED")
                    total_steps = len(steps)
                    if total_steps > 4 and completed >= total_steps // 2:
                        advisories.append(Advisory(
                            category="process",
                            severity="info",
                            message=f"Workflow {completed}/{total_steps} steps complete. Good checkpoint opportunity.",
                            detector="workflow_risks",
                            confidence=0.6,
                            tags=["process", "workflow", "checkpoint"],
                        ))
            except Exception:
                pass

        return advisories

    # ----- Main entry point -----

    def consult(
        self,
        context: dict[str, Any] | OracleContext | None = None,
        max_advisories: int = 8,
        *,
        include_narrative: bool = False,
        gate_mode: bool = False,
    ) -> list[Advisory]:
        """Run all detectors and return top-N sorted advisories.

        Args:
            context: Dict (old API) or OracleContext (new API). Backward-compatible.
            max_advisories: Maximum advisories to return.
            include_narrative: If True, run narrative enrichment detector.
            gate_mode: If True, return all gate-relevant advisories untruncated.
        """
        # Normalize context
        if context is None:
            ctx = OracleContext()
        elif isinstance(context, OracleContext):
            ctx = context
        elif isinstance(context, dict):
            ctx = OracleContext.from_dict(context)
        else:
            ctx = OracleContext()

        all_advisories: list[Advisory] = []

        # Original detectors (no context needed)
        stateless_detectors = [
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

        for detector in stateless_detectors:
            try:
                all_advisories.extend(detector())
            except Exception:
                pass

        # New context-aware detectors
        context_detectors = [
            lambda: self._detect_tool_recommendations(ctx),
            lambda: self._detect_gate_checks(ctx),
            lambda: self._detect_predictive_warnings(),
            lambda: self._detect_cross_session_patterns(),
            lambda: self._detect_workflow_risks(ctx),
        ]

        if include_narrative:
            context_detectors.append(lambda: self._generate_narrative_wisdom(ctx))

        for detector in context_detectors:
            try:
                all_advisories.extend(detector())
            except Exception:
                pass

        # Filter suppressed
        state = self._load_oracle_state()
        suppressed = set(state.get("suppressed_hashes", []))
        all_advisories = [a for a in all_advisories if a.advisory_hash() not in suppressed]

        # Deduplicate by message
        seen: set[str] = set()
        unique: list[Advisory] = []
        for adv in all_advisories:
            if adv.message not in seen:
                seen.add(adv.message)
                unique.append(adv)

        # Sort by severity (critical/warnings first)
        unique.sort(key=lambda a: a.sort_key())

        # In gate mode, return all gate advisories untruncated
        if gate_mode:
            gate_advisories = [a for a in unique if a.gate_action]
            non_gate = [a for a in unique if not a.gate_action]
            result = gate_advisories + non_gate[:max_advisories]
        else:
            result = unique[:max_advisories]

        # Record to state
        try:
            self._record_advisories(result)
        except Exception:
            pass

        return result

    # ----- Convenience methods -----

    def get_detector_scores(self) -> dict[str, Any]:
        """Return detector effectiveness scores."""
        state = self._load_oracle_state()
        return state.get("detector_scores", {})

    def get_advisory_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent advisory log entries."""
        state = self._load_oracle_state()
        log = state.get("advisory_log", [])
        return log[-limit:]
