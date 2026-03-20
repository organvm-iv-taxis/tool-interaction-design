"""The Oracle — contextual advisory engine for the Conductor OS.

Consumes session stats, observability trends, pattern data, and governance
state to produce actionable advisories. Writes ONLY to its own state file
(.conductor/oracle/state.json) — never mutates session/governance/workflow state.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .constants import ORACLE_STATE_FILE, SESSION_STATE_FILE, SESSIONS_DIR, STATS_FILE, WORKSPACE
from .observability import log_event


def _log_detector_error(detector: str, error: Exception) -> None:
    """Log a detector failure to observability — keeps Oracle non-fatal but visible."""
    log_event("oracle.detector_error", {
        "detector": detector,
        "error_type": type(error).__name__,
        "error": str(error)[:200],
    })


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
    # --- Guardian Angel fields ---
    wisdom_id: str = ""  # Reference to WisdomEntry
    teaching: str = ""  # Pedagogical explanation from wisdom corpus
    mastery_note: str = ""  # "You've encountered this 5 times..."

    SEVERITY_ORDER = SEVERITY_ORDER

    def sort_key(self) -> tuple[int, str]:
        return (self.SEVERITY_ORDER.get(self.severity, 99), self.category)

    def advisory_hash(self) -> str:
        """Stable hash for dedup/acknowledgment."""
        return hashlib.sha256(f"{self.detector}:{self.category}:{self.message[:80]}".encode()).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        d = {
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
        if self.wisdom_id:
            d["wisdom_id"] = self.wisdom_id
        if self.teaching:
            d["teaching"] = self.teaching
        if self.mastery_note:
            d["mastery_note"] = self.mastery_note
        return d


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


# Re-export for backwards compatibility
from .profiler import OracleProfile  # noqa: F401


# ---------------------------------------------------------------------------
# Oracle configuration
# ---------------------------------------------------------------------------


def _load_oracle_config() -> dict[str, Any]:
    """Load oracle-specific config from .conductor.yaml."""
    from .constants import load_config
    config = load_config()
    return config.get("oracle", {})


DETECTOR_REGISTRY: dict[str, dict[str, Any]] = {
    # Original detectors
    "process_drift": {"category": "process", "default_enabled": True, "phase": "stateless"},
    "scope_risk": {"category": "risk", "default_enabled": True, "phase": "stateless"},
    "momentum": {"category": "growth", "default_enabled": True, "phase": "stateless"},
    "governance_gaps": {"category": "governance", "default_enabled": True, "phase": "stateless"},
    "pattern_antipatterns": {"category": "risk", "default_enabled": True, "phase": "stateless"},
    "knowledge_gaps": {"category": "risk", "default_enabled": True, "phase": "stateless"},
    "growth_opportunities": {"category": "growth", "default_enabled": True, "phase": "stateless"},
    "seasonal_wisdom": {"category": "history", "default_enabled": True, "phase": "stateless"},
    "growth_plan": {"category": "growth", "default_enabled": True, "phase": "stateless", "method": "_generate_growth_plan"},
    # Phase 2 detectors
    "tool_recommendations": {"category": "tools", "default_enabled": True, "phase": "context"},
    "gate_checks": {"category": "gate", "default_enabled": True, "phase": "context"},
    "predictive_warnings": {"category": "risk", "default_enabled": True, "phase": "context"},
    "narrative_wisdom": {"category": "narrative", "default_enabled": True, "phase": "narrative", "method": "_generate_narrative_wisdom"},
    "cross_session_patterns": {"category": "growth", "default_enabled": True, "phase": "context"},
    "workflow_risks": {"category": "risk", "default_enabled": True, "phase": "context"},
    # Phase 3 detectors (expansion)
    "dependency_risks": {"category": "governance", "default_enabled": True, "phase": "stateless"},
    "cost_awareness": {"category": "cost", "default_enabled": True, "phase": "context"},
    "session_cadence": {"category": "process", "default_enabled": True, "phase": "stateless"},
    "technical_debt": {"category": "governance", "default_enabled": True, "phase": "stateless"},
    "scope_complexity": {"category": "risk", "default_enabled": True, "phase": "context"},
    "collaboration_patterns": {"category": "process", "default_enabled": True, "phase": "stateless"},
    "stale_repos": {"category": "governance", "default_enabled": True, "phase": "stateless"},
    "burnout_risk": {"category": "risk", "default_enabled": True, "phase": "stateless"},
    # Guardian Angel detectors (wisdom-powered)
    "canonical_practice": {"category": "wisdom", "default_enabled": True, "phase": "context"},
    "business_insight": {"category": "business", "default_enabled": True, "phase": "context"},
    "mastery_progress": {"category": "growth", "default_enabled": True, "phase": "stateless"},
    # Conductor activation detectors (process anti-patterns)
    "no_session": {"category": "gate", "default_enabled": True, "phase": "stateless"},
    "phase_skip": {"category": "gate", "default_enabled": True, "phase": "context"},
    "context_switching": {"category": "process", "default_enabled": True, "phase": "stateless"},
    "infrastructure_gravity": {"category": "process", "default_enabled": True, "phase": "stateless"},
    "session_fragmentation": {"category": "process", "default_enabled": True, "phase": "stateless"},
    # Phase impasse detection
    "phase_impasse": {"category": "process", "default_enabled": True, "phase": "stateless"},
}


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
        except (OSError, json.JSONDecodeError, ImportError) as e:
            _log_detector_error("_load_trends", e)
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
            except (OSError, yaml.YAMLError):
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
            from .constants import PATTERN_HISTORY_FILE
            history_file = PATTERN_HISTORY_FILE
            if not history_file.exists():
                self._pattern_history = []
                return self._pattern_history
            entries: list[dict[str, Any]] = []
            for line in history_file.read_text().splitlines():
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
            self._pattern_history = entries
        except (OSError, json.JSONDecodeError) as e:
            _log_detector_error("_load_pattern_history", e)
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

    # ----- Mastery ledger -----

    def _load_mastery(self) -> dict[str, Any]:
        """Load the mastery section from oracle state."""
        state = self._load_oracle_state()
        return state.setdefault("mastery", {
            "encountered": {},
            "internalized": {},
            "growth_areas": [],
            "mastery_score": 0.0,
        })

    def _save_mastery(self, mastery: dict[str, Any]) -> None:
        """Write mastery section back to oracle state."""
        state = self._load_oracle_state()
        state["mastery"] = mastery
        self._save_oracle_state()

    def _current_session_id(self) -> str:
        """Read the active session ID from the session state file."""
        try:
            if SESSION_STATE_FILE.exists():
                data = json.loads(SESSION_STATE_FILE.read_text())
                return data.get("session_id", "")
        except (json.JSONDecodeError, OSError):
            pass
        return ""

    def _record_wisdom_shown(self, wisdom_id: str) -> None:
        """Increment encounter counter for a wisdom entry (once per session)."""
        mastery = self._load_mastery()
        encountered = mastery.setdefault("encountered", {})
        now = datetime.now(timezone.utc).isoformat()
        current_session = self._current_session_id()

        if wisdom_id in encountered:
            # Per-session dedup: skip if already recorded for this session
            if current_session and encountered[wisdom_id].get("last_session") == current_session:
                return
            encountered[wisdom_id]["times_shown"] += 1
            encountered[wisdom_id]["last_shown"] = now
            if current_session:
                encountered[wisdom_id]["last_session"] = current_session
        else:
            entry: dict[str, Any] = {
                "first_seen": now,
                "times_shown": 1,
                "last_shown": now,
            }
            if current_session:
                entry["last_session"] = current_session
            encountered[wisdom_id] = entry
        self._save_mastery(mastery)

    def _check_internalization(self, wisdom_id: str) -> bool:
        """Check if a wisdom entry has been internalized (behavioral change detected)."""
        mastery = self._load_mastery()
        return wisdom_id in mastery.get("internalized", {})

    def _mark_internalized(self, wisdom_id: str, evidence: str = "") -> None:
        """Mark a wisdom entry as internalized."""
        mastery = self._load_mastery()
        internalized = mastery.setdefault("internalized", {})
        internalized[wisdom_id] = {
            "at": datetime.now(timezone.utc).isoformat(),
            "evidence": evidence,
        }
        # Update mastery score
        total_encountered = len(mastery.get("encountered", {}))
        total_internalized = len(internalized)
        mastery["mastery_score"] = total_internalized / total_encountered if total_encountered > 0 else 0.0
        # Remove from growth areas if present
        growth = mastery.get("growth_areas", [])
        if wisdom_id in growth:
            growth.remove(wisdom_id)
            mastery["growth_areas"] = growth
        self._save_mastery(mastery)

    def get_mastery_report(self) -> dict[str, Any]:
        """Public API returning growth state."""
        mastery = self._load_mastery()
        encountered = mastery.get("encountered", {})
        internalized = mastery.get("internalized", {})
        total_encountered = len(encountered)
        total_internalized = len(internalized)

        # Determine learning velocity
        velocity = "starting"
        if total_encountered == 0:
            velocity = "starting"
        elif total_internalized >= total_encountered * 0.7 and total_encountered >= 10:
            velocity = "mastering"
        elif total_internalized >= total_encountered * 0.4:
            velocity = "growing"
        elif total_encountered >= 10:
            velocity = "plateau"

        # Top growth areas: most shown but not internalized
        practicing = []
        for wid, data in encountered.items():
            if wid not in internalized:
                practicing.append((wid, data.get("times_shown", 0)))
        practicing.sort(key=lambda x: -x[1])

        return {
            "mastery_score": mastery.get("mastery_score", 0.0),
            "principles_encountered": total_encountered,
            "principles_internalized": total_internalized,
            "learning_velocity": velocity,
            "top_growth_areas": [wid for wid, _ in practicing[:5]],
            "recently_internalized": [
                {"id": wid, "at": data.get("at", "")}
                for wid, data in sorted(
                    internalized.items(),
                    key=lambda x: x[1].get("at", ""),
                    reverse=True,
                )[:5]
            ],
            "most_encountered": [
                {"id": wid, "times": data.get("times_shown", 0)}
                for wid, data in sorted(
                    encountered.items(),
                    key=lambda x: x[1].get("times_shown", 0),
                    reverse=True,
                )[:5]
            ],
        }

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
                except (OSError, yaml.YAMLError):
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
        except (OSError, json.JSONDecodeError) as e:
            _log_detector_error("governance_gaps", e)

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
        except (OSError, json.JSONDecodeError) as e:
            _log_detector_error("tool_recommendations", e)

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
                except (OSError, json.JSONDecodeError) as e:
                    _log_detector_error("gate_checks.frame_shape", e)

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
                except (OSError, json.JSONDecodeError) as e:
                    _log_detector_error("gate_checks.build_prove", e)

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
                except (OSError, json.JSONDecodeError) as e:
                    _log_detector_error("gate_checks.done", e)

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
            except (OSError, json.JSONDecodeError) as e:
                _log_detector_error("gate_checks.promotion", e)

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
        except (OSError, json.JSONDecodeError) as e:
            _log_detector_error("predictive_warnings", e)

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
        from .profiler import detect_cross_session_patterns
        state = self._load_oracle_state()
        return [Advisory(**d) for d in detect_cross_session_patterns(state)]

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
            except (OSError, json.JSONDecodeError) as e:
                _log_detector_error("workflow_risks.health", e)

        if ctx.trigger == "workflow_post_step":
            # Suggest checkpointing for long workflows.
            # Prefer explicit workflow_name, then active pointer, then legacy default.
            try:
                from .constants import STATE_DIR

                wf_dir = STATE_DIR / "workflows"
                candidates: list[Path] = []
                if ctx.workflow_name:
                    candidates.append(wf_dir / f"{ctx.workflow_name}.json")

                active_pointer = wf_dir / "_active"
                if active_pointer.exists():
                    try:
                        active_name = active_pointer.read_text().strip()
                        if active_name:
                            candidates.append(wf_dir / f"{active_name}.json")
                    except OSError as e:
                        _log_detector_error("workflow_risks.checkpoint.active_pointer", e)

                # Backward compatibility for old single-file state.
                candidates.append(wf_dir / "_default.json")

                wf_state_file = next((path for path in candidates if path.exists()), None)
                if wf_state_file is not None:
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
            except (OSError, json.JSONDecodeError) as e:
                _log_detector_error("workflow_risks.checkpoint", e)

        return advisories

    # ----- Phase 3 detectors (expansion) -----

    def _detect_dependency_risks(self) -> list[Advisory]:
        """Cross-organ dependency violations and unhealthy coupling."""
        advisories: list[Advisory] = []
        try:
            from .governance import GovernanceRuntime
            gov = GovernanceRuntime()
            all_repos = gov._all_repos()

            # Check for repos depending on lower-tier organs (back-edges)
            organ_order = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "META": 0}
            dep_violations = 0
            for name, repo in all_repos:
                deps = repo.get("dependencies", [])
                repo_organ = repo.get("organ", "")
                repo_rank = organ_order.get(repo_organ.replace("ORGAN-", "").replace("META-ORGANVM", "META"), 99)
                for dep in deps:
                    if not isinstance(dep, dict):
                        continue
                    dep_organ = dep.get("organ", "")
                    dep_rank = organ_order.get(dep_organ.replace("ORGAN-", "").replace("META-ORGANVM", "META"), 99)
                    if dep_rank > repo_rank and repo_rank < 4:  # back-edge in I->II->III
                        dep_violations += 1

            if dep_violations > 0:
                advisories.append(Advisory(
                    category="governance",
                    severity="warning",
                    message=f"{dep_violations} cross-organ dependency violation(s) detected. Check unidirectional flow.",
                    recommendation="Run `conductor audit` to identify dependency back-edges.",
                    detector="dependency_risks",
                    confidence=0.85,
                    tags=["governance", "dependencies"],
                ))

            # Concentration risk: too many repos depending on one
            dep_targets: Counter = Counter()
            for name, repo in all_repos:
                for dep in repo.get("dependencies", []):
                    dep_name = dep.get("repo", "") if isinstance(dep, dict) else str(dep)
                    dep_targets[dep_name] += 1
            for target, count in dep_targets.most_common(3):
                if count >= 5 and target:
                    advisories.append(Advisory(
                        category="governance",
                        severity="caution",
                        message=f"'{target}' is a dependency for {count} repos — high concentration risk.",
                        detector="dependency_risks",
                        confidence=0.7,
                        tags=["governance", "dependencies", "concentration"],
                    ))

        except (OSError, json.JSONDecodeError) as e:
            _log_detector_error("dependency_risks", e)
        return advisories

    def _detect_cost_awareness(self, ctx: OracleContext) -> list[Advisory]:
        """Warn about expensive tool cluster usage and suggest cheaper alternatives."""
        advisories: list[Advisory] = []
        try:
            import yaml
            from .constants import ONTOLOGY_PATH
            if not ONTOLOGY_PATH.exists():
                return advisories
            data = yaml.safe_load(ONTOLOGY_PATH.read_text())
            clusters = {c["id"]: c for c in data.get("clusters", [])}

            # Identify high-cost clusters being used in current session
            from .constants import SESSION_STATE_FILE
            if not SESSION_STATE_FILE.exists():
                return advisories
            session = json.loads(SESSION_STATE_FILE.read_text())
            tools_used: set[str] = set()
            for pl in session.get("phase_logs", []):
                tools_used.update(pl.get("tools_used", []))

            high_cost_used = []
            for tool_id in tools_used:
                for cid, cluster in clusters.items():
                    if cluster.get("cost_tier") == "high":
                        tool_ids = []
                        for t in cluster.get("tools", []):
                            if isinstance(t, str):
                                tool_ids.append(t)
                            elif isinstance(t, dict):
                                tool_ids.extend(t.values())
                        if tool_id in tool_ids or tool_id == cid:
                            high_cost_used.append(cid)
                            break

            if high_cost_used:
                unique_clusters = list(set(high_cost_used))
                # Find cheaper alternatives in same domain
                alternatives = []
                for hc in unique_clusters[:2]:
                    hc_domain = clusters.get(hc, {}).get("domain", "")
                    for cid, cluster in clusters.items():
                        if (cluster.get("domain") == hc_domain and
                                cluster.get("cost_tier") in ("free", "low") and
                                cid != hc):
                            alternatives.append(cid)
                            break

                advisories.append(Advisory(
                    category="cost",
                    severity="info",
                    message=f"Using {len(unique_clusters)} high-cost cluster(s): {', '.join(unique_clusters[:3])}.",
                    tools_suggested=alternatives[:3],
                    recommendation=f"Consider alternatives: {', '.join(alternatives[:3])}" if alternatives else "Monitor usage costs.",
                    detector="cost_awareness",
                    confidence=0.65,
                    tags=["cost", "optimization"],
                ))
        except (OSError, json.JSONDecodeError, ValueError) as e:
            _log_detector_error("cost_awareness", e)
        return advisories

    def _detect_session_cadence(self) -> list[Advisory]:
        """Analyze daily/weekly rhythm and suggest optimal scheduling."""
        from .profiler import detect_session_cadence
        stats = self._load_stats()
        return [Advisory(**d) for d in detect_session_cadence(stats)]

    def _detect_technical_debt(self) -> list[Advisory]:
        """Identify repos lacking tests, CI, or documentation — correlating with failures."""
        advisories: list[Advisory] = []
        try:
            from .governance import GovernanceRuntime
            gov = GovernanceRuntime()
            all_repos = gov._all_repos()

            no_ci_candidates = []
            no_tests_candidates = []
            for name, repo in all_repos:
                status = repo.get("promotion_status", "LOCAL")
                if status in ("CANDIDATE", "PUBLIC_PROCESS"):
                    if not repo.get("ci_workflow"):
                        no_ci_candidates.append(name)
                    if not repo.get("has_tests", True):  # assume True if not tracked
                        no_tests_candidates.append(name)

            if len(no_ci_candidates) >= 3:
                advisories.append(Advisory(
                    category="governance",
                    severity="warning",
                    message=f"{len(no_ci_candidates)} promoted repos lack CI: {', '.join(no_ci_candidates[:3])}{'...' if len(no_ci_candidates) > 3 else ''}",
                    recommendation="Add CI workflows before further promotion. Run `conductor enforce generate`.",
                    detector="technical_debt",
                    confidence=0.85,
                    tags=["governance", "ci", "debt"],
                ))

            if no_tests_candidates:
                advisories.append(Advisory(
                    category="governance",
                    severity="caution",
                    message=f"{len(no_tests_candidates)} promoted repo(s) lack test coverage.",
                    recommendation="Add test suites to repos approaching PUBLIC_PROCESS.",
                    detector="technical_debt",
                    confidence=0.75,
                    tags=["governance", "tests", "debt"],
                ))

            # Repos in CANDIDATE > 30 days
            stale_candidates = []
            now = time.time()
            for name, repo in all_repos:
                if repo.get("promotion_status") == "CANDIDATE":
                    promoted_at = repo.get("last_promoted_at", 0)
                    if promoted_at and isinstance(promoted_at, (int, float)):
                        days = (now - promoted_at) / 86400
                        if days > 30:
                            stale_candidates.append((name, int(days)))

            if stale_candidates:
                worst = sorted(stale_candidates, key=lambda x: -x[1])[:3]
                names = ", ".join(f"{n} ({d}d)" for n, d in worst)
                advisories.append(Advisory(
                    category="governance",
                    severity="caution",
                    message=f"Stale CANDIDATE repos: {names}. Either promote or archive.",
                    recommendation="Run `conductor stale --days 30` for full list.",
                    detector="technical_debt",
                    confidence=0.8,
                    tags=["governance", "stale", "debt"],
                ))

        except (OSError, json.JSONDecodeError) as e:
            _log_detector_error("technical_debt", e)
        return advisories

    def _detect_scope_complexity(self, ctx: OracleContext) -> list[Advisory]:
        """Analyze session scope text for complexity signals."""
        advisories: list[Advisory] = []
        try:
            from .constants import SESSION_STATE_FILE
            if not SESSION_STATE_FILE.exists():
                return advisories
            session = json.loads(SESSION_STATE_FILE.read_text())
            scope = session.get("scope", "")
            if not scope:
                return advisories

            # Word count heuristic
            words = scope.split()
            word_count = len(words)

            # Complexity signals
            complexity_keywords = ["and", "also", "plus", "additionally", "furthermore",
                                   "as well as", "along with", "including", "multiple"]
            conjunctions = sum(1 for w in words if w.lower() in complexity_keywords)

            # Scope too broad?
            if word_count > 30:
                advisories.append(Advisory(
                    category="risk",
                    severity="caution",
                    message=f"Scope description is {word_count} words. Complex scopes correlate with lower ship rates.",
                    recommendation="Distill scope to a single sentence. Ship the rest in follow-up sessions.",
                    detector="scope_complexity",
                    confidence=0.65,
                    tags=["risk", "scope"],
                ))
            elif conjunctions >= 3:
                advisories.append(Advisory(
                    category="risk",
                    severity="caution",
                    message=f"Scope has {conjunctions} conjunction(s) ('and', 'also', etc.) — may be multiple tasks in disguise.",
                    recommendation="Consider splitting into separate sessions for each deliverable.",
                    detector="scope_complexity",
                    confidence=0.6,
                    tags=["risk", "scope", "splitting"],
                ))

            # Check if scope mentions unfamiliar organs
            if ctx.organ:
                mentioned_organs = re.findall(r'\b(ORGAN-[IVX]+|organ[- ][IVX]+)\b', scope, re.IGNORECASE)
                other_organs = [o for o in mentioned_organs if ctx.organ not in o.upper()]
                if other_organs:
                    advisories.append(Advisory(
                        category="risk",
                        severity="info",
                        message=f"Scope references other organs ({', '.join(other_organs[:2])}). Cross-organ work needs extra coordination.",
                        detector="scope_complexity",
                        confidence=0.55,
                        tags=["risk", "scope", "cross_organ"],
                    ))

        except (OSError, json.JSONDecodeError) as e:
            _log_detector_error("scope_complexity", e)
        return advisories

    def _detect_collaboration_patterns(self) -> list[Advisory]:
        """Detect multi-session coordination patterns and repo contention."""
        from .profiler import detect_collaboration_patterns
        stats = self._load_stats()
        return [Advisory(**d) for d in detect_collaboration_patterns(stats)]

    def _detect_stale_repos(self) -> list[Advisory]:
        """Identify repos that haven't been touched in a long time."""
        advisories: list[Advisory] = []
        try:
            from .governance import GovernanceRuntime
            gov = GovernanceRuntime()
            all_repos = gov._all_repos()

            now = time.time()
            stale_by_organ: dict[str, int] = defaultdict(int)
            total_stale = 0
            threshold_days = 60

            for name, repo in all_repos:
                status = repo.get("promotion_status", "LOCAL")
                if status in ("ARCHIVED",):
                    continue
                last_activity = repo.get("last_committed_at") or repo.get("last_promoted_at") or 0
                if last_activity and isinstance(last_activity, (int, float)):
                    days_since = (now - last_activity) / 86400
                    if days_since > threshold_days:
                        organ = repo.get("organ", "UNKNOWN")
                        stale_by_organ[organ] += 1
                        total_stale += 1

            if total_stale >= 10:
                worst_organ = max(stale_by_organ.items(), key=lambda x: x[1]) if stale_by_organ else ("?", 0)
                advisories.append(Advisory(
                    category="governance",
                    severity="caution",
                    message=f"{total_stale} non-archived repos inactive for {threshold_days}+ days. Worst: {worst_organ[0]} ({worst_organ[1]}).",
                    recommendation=f"Run `conductor stale --days {threshold_days}` to review. Archive or revive.",
                    detector="stale_repos",
                    confidence=0.75,
                    tags=["governance", "stale"],
                ))

        except (OSError, json.JSONDecodeError) as e:
            _log_detector_error("stale_repos", e)
        return advisories

    def _detect_burnout_risk(self) -> list[Advisory]:
        """Detect overwork patterns: marathon sessions, late nights, declining ship rates."""
        from .profiler import detect_burnout_risk
        stats = self._load_stats()
        return [Advisory(**d) for d in detect_burnout_risk(stats)]

    def _detect_phase_impasse(self) -> list[Advisory]:
        """Detect when the current phase is running significantly longer than historical median."""
        advisories: list[Advisory] = []
        from .constants import SESSION_STATE_FILE

        if not SESSION_STATE_FILE.exists():
            return advisories

        try:
            session = json.loads(SESSION_STATE_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            return advisories

        current_phase = session.get("current_phase", "")
        if current_phase == "DONE" or not current_phase:
            return advisories

        # Find current phase start time
        phase_start = 0.0
        for pl in session.get("phase_logs", []):
            if pl.get("name") == current_phase and pl.get("end_time", 0) == 0:
                phase_start = pl.get("start_time", 0)
                break

        if not phase_start:
            return advisories

        current_duration = (time.time() - phase_start) / 60  # minutes

        # Compute median phase duration from session logs
        import yaml
        phase_durations: list[float] = []
        for log_path in SESSIONS_DIR.glob("*/session-log.yaml"):
            try:
                log = yaml.safe_load(log_path.read_text())
                phases = (log or {}).get("phases", {})
                phase_data = phases.get(current_phase)
                if isinstance(phase_data, dict):
                    dur = phase_data.get("duration", 0)
                    if dur > 0:
                        phase_durations.append(dur)
            except (OSError, yaml.YAMLError):
                continue

        if len(phase_durations) < 3:
            return advisories

        # Compute median
        sorted_durs = sorted(phase_durations)
        n = len(sorted_durs)
        median = sorted_durs[n // 2] if n % 2 else (sorted_durs[n // 2 - 1] + sorted_durs[n // 2]) / 2

        if median <= 0:
            return advisories

        ratio = current_duration / median

        if ratio > 3:
            advisories.append(Advisory(
                category="process",
                severity="warning",
                message=(
                    f"{current_phase} phase running {ratio:.0f}x longer than median "
                    f"({current_duration:.0f}m vs {median:.0f}m) — consider narrowing scope or transitioning."
                ),
                context={"phase": current_phase, "current_minutes": round(current_duration), "median_minutes": round(median), "ratio": round(ratio, 1)},
                recommendation="Break the problem down, checkpoint progress, or transition to the next phase.",
                detector="phase_impasse",
                confidence=0.8,
                tags=["process", "impasse"],
            ))
        elif ratio > 2:
            advisories.append(Advisory(
                category="process",
                severity="caution",
                message=(
                    f"{current_phase} phase running {ratio:.0f}x longer than median "
                    f"({current_duration:.0f}m vs {median:.0f}m) — consider narrowing scope."
                ),
                context={"phase": current_phase, "current_minutes": round(current_duration), "median_minutes": round(median), "ratio": round(ratio, 1)},
                recommendation="Review scope and consider whether you're blocked on something.",
                detector="phase_impasse",
                confidence=0.7,
                tags=["process", "impasse"],
            ))

        return advisories

    # ----- Guardian Angel detectors (wisdom-powered) -----

    def _detect_canonical_practice(self, ctx: OracleContext) -> list[Advisory]:
        """Surface engineering principles relevant to current phase/behavior."""
        advisories: list[Advisory] = []
        try:
            from .wisdom import WisdomCorpus
            corpus = WisdomCorpus()

            # Derive triggers from phase and behavioral signals
            triggers: list[str] = []
            phase = ctx.current_phase or ""

            if phase == "FRAME":
                triggers.extend(["research_phase", "preparation", "ambiguity"])
            elif phase == "SHAPE":
                triggers.extend(["decomposition", "system_design", "scope_complex"])
            elif phase == "BUILD":
                triggers.extend(["no_tests", "small_commits", "refactoring"])
            elif phase == "PROVE":
                triggers.extend(["testing", "monitoring", "deployment"])

            # Check session for behavioral signals
            from .constants import SESSION_STATE_FILE
            if SESSION_STATE_FILE.exists():
                try:
                    session = json.loads(SESSION_STATE_FILE.read_text())
                    scope = session.get("scope", "").lower()
                    if "and" in scope or "also" in scope:
                        triggers.append("scope_complex")
                    if "refactor" in scope:
                        triggers.append("refactoring")
                    warnings = session.get("warnings", [])
                    if len(warnings) >= 2:
                        triggers.append("multi_concern")
                except (OSError, json.JSONDecodeError):
                    pass

            if not triggers:
                return advisories

            entries = corpus.query(
                triggers=triggers,
                phase=phase,
                domain="engineering",
                limit=2,
            )

            for entry in entries:
                if self._check_internalization(entry.id):
                    continue
                mastery = self._load_mastery()
                enc = mastery.get("encountered", {}).get(entry.id, {})
                times = enc.get("times_shown", 0)
                mastery_note = f"You've encountered this {times} time(s)." if times > 0 else ""

                advisories.append(Advisory(
                    category="wisdom",
                    severity=entry.severity_hint,
                    message=f"{entry.principle}: {entry.summary}",
                    teaching=entry.teaching,
                    narrative=entry.metaphor[:200] if entry.metaphor else "",
                    wisdom_id=entry.id,
                    mastery_note=mastery_note,
                    detector="canonical_practice",
                    confidence=0.7,
                    tags=["wisdom", "engineering"] + entry.tags[:3],
                ))

        except (ImportError, OSError) as e:
            _log_detector_error("canonical_practice", e)
        return advisories

    def _detect_business_insight(self, ctx: OracleContext) -> list[Advisory]:
        """Surface business wisdom based on project state."""
        advisories: list[Advisory] = []
        try:
            from .wisdom import WisdomCorpus
            corpus = WisdomCorpus()
            stats = self._load_stats()
            total = stats.get("total_sessions", 0)

            triggers: list[str] = []

            # New repos → MVP thinking
            if total < 5:
                triggers.extend(["new_repo", "mvp", "validation"])

            # Stuck candidates → shipping urgency
            try:
                from .governance import GovernanceRuntime
                gov = GovernanceRuntime()
                all_repos = gov._all_repos()
                candidates = sum(1 for _, r in all_repos if r.get("promotion_status") == "CANDIDATE")
                if candidates > 8:
                    triggers.extend(["stuck_candidate", "perfectionism", "fear_of_shipping"])
            except Exception as exc:
                from .observability import log_event
                log_event("oracle.governance_gap_error", {"error": str(exc)})

            # Single organ focus → portfolio balancing
            by_organ = stats.get("by_organ", {})
            if total >= 5 and len(by_organ) <= 2:
                triggers.extend(["single_organ_focus", "portfolio_imbalance"])

            # Momentum
            streak = stats.get("streak", 0)
            if streak >= 3:
                triggers.append("momentum")

            if not triggers:
                return advisories

            entries = corpus.query(
                triggers=triggers,
                phase=ctx.current_phase or "",
                domain="business",
                limit=1,
            )

            for entry in entries:
                if self._check_internalization(entry.id):
                    continue
                advisories.append(Advisory(
                    category="business",
                    severity=entry.severity_hint,
                    message=f"{entry.principle}: {entry.summary}",
                    teaching=entry.teaching,
                    narrative=entry.metaphor[:200] if entry.metaphor else "",
                    wisdom_id=entry.id,
                    detector="business_insight",
                    confidence=0.65,
                    tags=["wisdom", "business"] + entry.tags[:3],
                ))

        except (ImportError, OSError) as e:
            _log_detector_error("business_insight", e)
        return advisories

    def _detect_mastery_progress(self) -> list[Advisory]:
        """Growth trajectory updates and milestone celebration."""
        advisories: list[Advisory] = []
        mastery = self._load_mastery()
        encountered = mastery.get("encountered", {})
        internalized = mastery.get("internalized", {})

        total_enc = len(encountered)
        total_int = len(internalized)

        if total_enc == 0:
            return advisories

        # Milestone celebrations
        milestone_messages = {
            5: "You've encountered 5 principles. The foundation of wisdom is exposure.",
            10: "10 principles encountered. Pattern recognition is beginning.",
            25: "25 principles encountered. You're building a comprehensive knowledge base.",
            50: "50 principles. The corpus of wisdom is becoming part of your practice.",
        }
        if total_enc in milestone_messages:
            advisories.append(Advisory(
                category="growth",
                severity="info",
                message=milestone_messages[total_enc],
                detector="mastery_progress",
                confidence=0.9,
                tags=["growth", "mastery", "milestone"],
            ))

        internalization_milestones = {
            3: "3 principles internalized! Your behavior is visibly changing.",
            5: "5 principles internalized. Wisdom is becoming instinct.",
            10: "10 principles internalized. The Guardian Angel has less to teach — you're teaching yourself.",
        }
        if total_int in internalization_milestones:
            advisories.append(Advisory(
                category="growth",
                severity="info",
                message=internalization_milestones[total_int],
                detector="mastery_progress",
                confidence=0.9,
                tags=["growth", "mastery", "internalization"],
            ))

        # Identify stalled growth
        if total_enc >= 15 and total_int < total_enc * 0.2:
            advisories.append(Advisory(
                category="growth",
                severity="caution",
                message=f"You've encountered {total_enc} principles but internalized only {total_int}. "
                        f"Consider slowing down to practice what you've learned.",
                recommendation="Run `conductor oracle mastery` to see your growth areas.",
                detector="mastery_progress",
                confidence=0.6,
                tags=["growth", "mastery", "plateau"],
            ))

        return advisories

    # ----- Conductor activation detectors -----

    def _detect_no_session(self) -> list[Advisory]:
        """Block when no active session exists."""
        from .constants import SESSION_STATE_FILE
        if SESSION_STATE_FILE.exists():
            return []
        return [Advisory(
            category="gate",
            severity="critical",
            message="No active Conductor session. Start one before working.",
            recommendation="Call conductor_session_start with organ, repo, and scope.",
            detector="no_session",
            gate_action="block",
            confidence=1.0,
            tags=["gate", "session"],
        )]

    def _detect_phase_skip(self, ctx: OracleContext) -> list[Advisory]:
        """Warn when prompt signals implementation intent but session is in FRAME."""
        from .constants import SESSION_STATE_FILE
        if not SESSION_STATE_FILE.exists():
            return []
        phase = ctx.current_phase
        if phase not in ("FRAME", "SHAPE"):
            return []
        return [Advisory(
            category="gate",
            severity="warning",
            message=f"You're in {phase} phase. Explore and design before building.",
            recommendation=f"Transition to {'SHAPE' if phase == 'FRAME' else 'BUILD'} when ready: conductor_session_transition.",
            detector="phase_skip",
            gate_action="warn",
            confidence=0.7,
            tags=["gate", "phase"],
        )]

    def _detect_context_switching(self) -> list[Advisory]:
        """Warn when recent sessions span too many different organs."""
        from .constants import CONTEXT_SWITCH_THRESHOLD, CONTEXT_SWITCH_WINDOW
        stats = self._load_stats()
        recent = stats.get("recent_sessions", [])[-CONTEXT_SWITCH_WINDOW:]
        if len(recent) < 3:
            return []
        organs = {s.get("organ", "") for s in recent if s.get("organ")}
        if len(organs) >= CONTEXT_SWITCH_THRESHOLD:
            return [Advisory(
                category="process",
                severity="warning",
                message=f"Context switching: {len(organs)} different organs in last {len(recent)} sessions ({', '.join(sorted(organs))}). Focus reduces overhead.",
                recommendation="Consider batching work within a single organ before switching.",
                detector="context_switching",
                confidence=0.75,
                tags=["process", "context_switching"],
            )]
        return []

    def _detect_infrastructure_gravity(self) -> list[Advisory]:
        """Caution when >70% of recent sessions target META/IV (infrastructure) organs."""
        from .constants import INFRASTRUCTURE_GRAVITY_THRESHOLD, INFRASTRUCTURE_GRAVITY_WINDOW
        stats = self._load_stats()
        recent = stats.get("recent_sessions", [])[-INFRASTRUCTURE_GRAVITY_WINDOW:]
        if len(recent) < 5:
            return []
        infra_organs = {"META-ORGANVM", "ORGAN-IV"}
        infra_count = sum(1 for s in recent if s.get("organ", "") in infra_organs)
        ratio = infra_count / len(recent)
        if ratio > INFRASTRUCTURE_GRAVITY_THRESHOLD:
            return [Advisory(
                category="process",
                severity="caution",
                message=f"Infrastructure gravity: {ratio:.0%} of last {len(recent)} sessions target META/IV. "
                        f"Consider shifting focus to product organs (I, II, III).",
                context={"infra_ratio": ratio, "infra_count": infra_count, "total": len(recent)},
                recommendation="Start a session in ORGAN-I, II, or III to balance the portfolio.",
                detector="infrastructure_gravity",
                confidence=0.7,
                tags=["process", "infrastructure_gravity"],
            )]
        return []

    def _detect_session_fragmentation(self) -> list[Advisory]:
        """Caution when recent sessions are all very short (< 5 min)."""
        from .constants import SESSION_FRAGMENTATION_THRESHOLD, SESSION_FRAGMENTATION_WINDOW
        stats = self._load_stats()
        recent = stats.get("recent_sessions", [])[-SESSION_FRAGMENTATION_WINDOW:]
        if len(recent) < SESSION_FRAGMENTATION_WINDOW:
            return []
        short_count = sum(1 for s in recent if s.get("duration_minutes", 999) < SESSION_FRAGMENTATION_THRESHOLD)
        if short_count == len(recent):
            return [Advisory(
                category="process",
                severity="caution",
                message=f"Session fragmentation: last {len(recent)} sessions all under {SESSION_FRAGMENTATION_THRESHOLD} minutes. "
                        f"Consider batching short tasks into focused sessions.",
                recommendation="Combine related tasks into a single session with clear scope.",
                detector="session_fragmentation",
                confidence=0.65,
                tags=["process", "fragmentation"],
            )]
        return []

    # ----- Profile + convenience -----

    def build_profile(self) -> OracleProfile:
        """Build a behavioral profile from stats and oracle state."""
        stats = self._load_stats()
        state = self._load_oracle_state()
        return OracleProfile.build(stats, state)

    def get_detector_manifest(self) -> list[dict[str, Any]]:
        """Return metadata for all registered detectors."""
        config = _load_oracle_config()
        disabled = set(config.get("disabled_detectors", []))
        thresholds = config.get("thresholds", {})
        scores = self.get_detector_scores()

        manifest = []
        for name, meta in DETECTOR_REGISTRY.items():
            entry = {
                "name": name,
                "category": meta["category"],
                "phase": meta["phase"],
                "enabled": name not in disabled and meta["default_enabled"],
                "effectiveness": None,
            }
            if name in scores:
                s = scores[name]
                t = s.get("total", 0)
                entry["effectiveness"] = s.get("shipped", 0) / t if t > 0 else None
            if name in thresholds:
                entry["threshold_override"] = thresholds[name]
            manifest.append(entry)
        return manifest

    def get_trend_summary(self) -> dict[str, Any]:
        """Aggregate trends: ship rate, duration, phase balance over recent sessions."""
        from .profiler import get_trend_summary
        stats = self._load_stats()
        return get_trend_summary(stats)

    def calibrate_detector(self, detector_name: str, action: str = "reset") -> dict[str, Any]:
        """Calibrate a detector: reset its effectiveness scores or boost/penalize."""
        state = self._load_oracle_state()
        scores = state.setdefault("detector_scores", {})

        if detector_name not in DETECTOR_REGISTRY:
            return {"error": f"Unknown detector: {detector_name}"}

        if action == "reset":
            scores.pop(detector_name, None)
            self._save_oracle_state()
            return {"calibrated": detector_name, "action": "reset"}
        elif action == "boost":
            if detector_name in scores:
                scores[detector_name]["shipped"] = min(
                    scores[detector_name].get("shipped", 0) + 2,
                    scores[detector_name].get("total", 0),
                )
            self._save_oracle_state()
            return {"calibrated": detector_name, "action": "boost"}
        elif action == "penalize":
            if detector_name in scores:
                scores[detector_name]["shipped"] = max(scores[detector_name].get("shipped", 0) - 2, 0)
            self._save_oracle_state()
            return {"calibrated": detector_name, "action": "penalize"}
        else:
            return {"error": f"Unknown action: {action}. Use reset, boost, or penalize."}

    def export_state(self) -> dict[str, Any]:
        """Full export of oracle state, profile, and detector manifest."""
        return {
            "profile": self.build_profile().to_dict(),
            "detector_manifest": self.get_detector_manifest(),
            "trend_summary": self.get_trend_summary(),
            "state": self._load_oracle_state(),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    def diagnose(self) -> dict[str, Any]:
        """Self-diagnostic: check detector health, state file integrity, data freshness."""
        issues: list[dict[str, str]] = []
        info: dict[str, Any] = {}

        # State file
        if ORACLE_STATE_FILE.exists():
            try:
                state = json.loads(ORACLE_STATE_FILE.read_text())
                info["state_file_size"] = ORACLE_STATE_FILE.stat().st_size
                info["advisory_log_entries"] = len(state.get("advisory_log", []))
                info["suppressed_count"] = len(state.get("suppressed_hashes", []))
                info["detector_scores_tracked"] = len(state.get("detector_scores", {}))
            except (OSError, json.JSONDecodeError) as e:
                issues.append({"level": "error", "message": f"Oracle state file corrupt: {e}"})
        else:
            info["state_file_size"] = 0
            issues.append({"level": "info", "message": "No oracle state file yet — will be created on first consult."})

        # Stats file freshness
        if STATS_FILE.exists():
            age_hours = (time.time() - STATS_FILE.stat().st_mtime) / 3600
            info["stats_file_age_hours"] = round(age_hours, 1)
            if age_hours > 168:  # 1 week
                issues.append({"level": "warning", "message": f"Stats file is {age_hours:.0f}h old. Run a session to refresh."})
        else:
            issues.append({"level": "info", "message": "No stats file. Complete a session to generate stats."})

        # Detector coverage
        config = _load_oracle_config()
        disabled = set(config.get("disabled_detectors", []))
        enabled_count = sum(1 for name, meta in DETECTOR_REGISTRY.items() if name not in disabled and meta["default_enabled"])
        info["detectors_total"] = len(DETECTOR_REGISTRY)
        info["detectors_enabled"] = enabled_count
        info["detectors_disabled"] = list(disabled) if disabled else []

        # Run a test consult to check for errors
        detector_errors: list[str] = []
        try:
            test_ctx = OracleContext(trigger="manual")
            # Test each stateless detector
            for name in DETECTOR_REGISTRY:
                meta = DETECTOR_REGISTRY[name]
                if meta["phase"] == "stateless":
                    method_name = meta.get("method", f"_detect_{name}")
                    method = getattr(self, method_name, None)
                    if method is None:
                        detector_errors.append(f"Missing method: {method_name}")
                    else:
                        try:
                            method()
                        except Exception as e:
                            detector_errors.append(f"{name}: {e}")
        except Exception as e:
            detector_errors.append(f"Diagnostic run failed: {e}")

        if detector_errors:
            for err in detector_errors:
                issues.append({"level": "warning", "message": f"Detector issue: {err}"})
        info["detector_errors"] = len(detector_errors)

        return {
            "ok": len([i for i in issues if i["level"] == "error"]) == 0,
            "issues": issues,
            "info": info,
        }

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

        # Load config for detector toggles
        oracle_config = _load_oracle_config()
        disabled_detectors = set(oracle_config.get("disabled_detectors", []))

        def _is_enabled(name: str) -> bool:
            if name in disabled_detectors:
                return False
            reg = DETECTOR_REGISTRY.get(name, {})
            return reg.get("default_enabled", True)

        # Original stateless detectors
        stateless_detectors: list[tuple[str, Any]] = [
            ("process_drift", self._detect_process_drift),
            ("scope_risk", self._detect_scope_risk),
            ("momentum", self._detect_momentum),
            ("governance_gaps", self._detect_governance_gaps),
            ("pattern_antipatterns", self._detect_pattern_antipatterns),
            ("knowledge_gaps", self._detect_knowledge_gaps),
            ("growth_opportunities", self._detect_growth_opportunities),
            ("seasonal_wisdom", self._detect_seasonal_wisdom),
            ("growth_plan", self._generate_growth_plan),
            # Phase 3 stateless
            ("dependency_risks", self._detect_dependency_risks),
            ("session_cadence", self._detect_session_cadence),
            ("technical_debt", self._detect_technical_debt),
            ("collaboration_patterns", self._detect_collaboration_patterns),
            ("stale_repos", self._detect_stale_repos),
            ("burnout_risk", self._detect_burnout_risk),
            # Guardian Angel stateless
            ("mastery_progress", self._detect_mastery_progress),
            # Conductor activation detectors
            ("no_session", self._detect_no_session),
            ("context_switching", self._detect_context_switching),
            ("infrastructure_gravity", self._detect_infrastructure_gravity),
            ("session_fragmentation", self._detect_session_fragmentation),
            # Phase impasse detection
            ("phase_impasse", self._detect_phase_impasse),
        ]

        for name, detector in stateless_detectors:
            if not _is_enabled(name):
                continue
            try:
                all_advisories.extend(detector())
            except Exception as e:
                _log_detector_error(name, e)

        # Context-aware detectors
        context_detectors: list[tuple[str, Any]] = [
            ("tool_recommendations", lambda: self._detect_tool_recommendations(ctx)),
            ("gate_checks", lambda: self._detect_gate_checks(ctx)),
            ("predictive_warnings", lambda: self._detect_predictive_warnings()),
            ("cross_session_patterns", lambda: self._detect_cross_session_patterns()),
            ("workflow_risks", lambda: self._detect_workflow_risks(ctx)),
            # Phase 3 context-aware
            ("cost_awareness", lambda: self._detect_cost_awareness(ctx)),
            ("scope_complexity", lambda: self._detect_scope_complexity(ctx)),
            # Guardian Angel context-aware
            ("canonical_practice", lambda: self._detect_canonical_practice(ctx)),
            ("business_insight", lambda: self._detect_business_insight(ctx)),
            # Conductor activation context-aware
            ("phase_skip", lambda: self._detect_phase_skip(ctx)),
        ]

        if include_narrative:
            context_detectors.append(("narrative_wisdom", lambda: self._generate_narrative_wisdom(ctx)))

        for name, detector in context_detectors:
            if not _is_enabled(name):
                continue
            try:
                all_advisories.extend(detector())
            except Exception as e:
                _log_detector_error(name, e)

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
        except (OSError, json.JSONDecodeError) as e:
            _log_detector_error("_record_advisories", e)

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
