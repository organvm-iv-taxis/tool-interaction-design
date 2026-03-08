"""Behavioral profiler — cross-session pattern analysis.

Extracted from oracle.py so that profiling logic is reusable by retro.py
and other modules without pulling in the full Oracle advisory engine.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class OracleProfile:
    """Persistent behavioral profile built from cross-session patterns."""

    total_sessions: int = 0
    total_minutes: float = 0.0
    ship_rate: float = 0.0
    avg_duration_min: float = 0.0
    preferred_organs: list[str] = field(default_factory=list)
    preferred_phases: list[str] = field(default_factory=list)
    active_hours: list[int] = field(default_factory=list)  # peak hours (0-23)
    dominant_patterns: list[str] = field(default_factory=list)  # recurring pattern names
    streak_max: int = 0
    streak_current: int = 0
    risk_appetite: str = "moderate"  # "conservative", "moderate", "aggressive"
    cadence: str = "irregular"  # "daily", "regular", "bursty", "irregular"
    detector_trust: dict[str, float] = field(default_factory=dict)  # detector -> trust score
    last_session_iso: str = ""
    phase_balance: dict[str, float] = field(default_factory=dict)  # phase -> avg % of session time
    # --- Guardian Angel fields ---
    mastery_score: float = 0.0
    principles_encountered: int = 0
    principles_internalized: int = 0
    top_growth_areas: list[str] = field(default_factory=list)
    learning_velocity: str = "starting"  # starting | growing | plateau | mastering

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_sessions": self.total_sessions,
            "total_minutes": round(self.total_minutes, 1),
            "ship_rate": round(self.ship_rate, 3),
            "avg_duration_min": round(self.avg_duration_min, 1),
            "preferred_organs": self.preferred_organs,
            "preferred_phases": self.preferred_phases,
            "active_hours": self.active_hours,
            "dominant_patterns": self.dominant_patterns,
            "streak_max": self.streak_max,
            "streak_current": self.streak_current,
            "risk_appetite": self.risk_appetite,
            "cadence": self.cadence,
            "detector_trust": {k: round(v, 3) for k, v in self.detector_trust.items()},
            "last_session_iso": self.last_session_iso,
            "phase_balance": {k: round(v, 3) for k, v in self.phase_balance.items()},
            "mastery_score": round(self.mastery_score, 3),
            "principles_encountered": self.principles_encountered,
            "principles_internalized": self.principles_internalized,
            "top_growth_areas": self.top_growth_areas,
            "learning_velocity": self.learning_velocity,
        }

    @classmethod
    def build(cls, stats: dict[str, Any], oracle_state: dict[str, Any]) -> OracleProfile:
        """Build a profile from stats + oracle state."""
        total = stats.get("total_sessions", 0)
        shipped = stats.get("shipped", 0)
        total_min = stats.get("total_minutes", 0.0)
        streak = stats.get("streak", 0)
        streak_max = stats.get("streak_max", streak)
        by_organ = stats.get("by_organ", {})
        recent = stats.get("recent_sessions", [])

        # Preferred organs (top 3 by session count)
        # by_organ values may be int counts or dicts with sub-counts
        def _organ_count(v: Any) -> int:
            if isinstance(v, (int, float)):
                return int(v)
            if isinstance(v, dict):
                return v.get("count", v.get("sessions", 0))
            return 0

        organ_counts = sorted(by_organ.items(), key=lambda x: _organ_count(x[1]), reverse=True)
        preferred_organs = [k for k, _ in organ_counts[:3]]

        # Active hours from recent sessions
        hour_counter: Counter = Counter()
        for s in recent:
            ts = s.get("start_time")
            if ts and isinstance(ts, (int, float)):
                hour_counter[datetime.fromtimestamp(ts, tz=timezone.utc).hour] += 1
        active_hours = [h for h, _ in hour_counter.most_common(4)]

        # Session cadence
        cadence = "irregular"
        if len(recent) >= 5:
            gaps = []
            for i in range(1, min(10, len(recent))):
                t1 = recent[-i].get("start_time", 0)
                t2 = recent[-i - 1].get("start_time", 0) if i < len(recent) else 0
                if t1 and t2:
                    gaps.append((t1 - t2) / 3600)  # hours
            if gaps:
                avg_gap = sum(gaps) / len(gaps)
                std_gap = (sum((g - avg_gap) ** 2 for g in gaps) / len(gaps)) ** 0.5 if len(gaps) > 1 else avg_gap
                cv = std_gap / avg_gap if avg_gap > 0 else 1.0
                if avg_gap < 30 and cv < 0.5:
                    cadence = "daily"
                elif cv < 0.6:
                    cadence = "regular"
                elif avg_gap < 72:
                    cadence = "bursty"

        # Risk appetite (derived from ship rate + scope patterns)
        ship_rate = shipped / total if total > 0 else 0.0
        risk_appetite = "moderate"
        if ship_rate > 0.75 and total >= 5:
            risk_appetite = "conservative"  # ships often = doesn't over-reach
        elif ship_rate < 0.35 and total >= 5:
            risk_appetite = "aggressive"  # frequently fails to ship

        # Detector trust scores
        det_scores = oracle_state.get("detector_scores", {})
        detector_trust: dict[str, float] = {}
        for det, data in det_scores.items():
            t = data.get("total", 0)
            s = data.get("shipped", 0)
            if t >= 3:
                detector_trust[det] = s / t

        # Last session
        last_iso = ""
        if recent:
            ts = recent[-1].get("start_time")
            if ts and isinstance(ts, (int, float)):
                last_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        # Guardian mastery snapshot
        mastery = oracle_state.get("mastery", {})
        encountered_map = mastery.get("encountered", {})
        internalized_map = mastery.get("internalized", {})
        principles_encountered = len(encountered_map) if isinstance(encountered_map, dict) else 0
        principles_internalized = len(internalized_map) if isinstance(internalized_map, dict) else 0

        mastery_score = mastery.get("mastery_score", 0.0)
        if not isinstance(mastery_score, (int, float)):
            mastery_score = 0.0
        if mastery_score == 0.0 and principles_encountered > 0:
            mastery_score = principles_internalized / principles_encountered

        top_growth_areas: list[str] = []
        raw_growth = mastery.get("growth_areas", [])
        if isinstance(raw_growth, list):
            top_growth_areas = [g for g in raw_growth if isinstance(g, str)][:5]

        if not top_growth_areas and isinstance(encountered_map, dict):
            practicing = []
            for wid, data in encountered_map.items():
                if not isinstance(wid, str):
                    continue
                if isinstance(internalized_map, dict) and wid in internalized_map:
                    continue
                shown = data.get("times_shown", 0) if isinstance(data, dict) else 0
                shown_i = shown if isinstance(shown, int) else 0
                practicing.append((wid, shown_i))
            practicing.sort(key=lambda x: -x[1])
            top_growth_areas = [wid for wid, _ in practicing[:5]]

        learning_velocity = "starting"
        if principles_encountered == 0:
            learning_velocity = "starting"
        elif principles_internalized >= principles_encountered * 0.7 and principles_encountered >= 10:
            learning_velocity = "mastering"
        elif principles_internalized >= principles_encountered * 0.4:
            learning_velocity = "growing"
        elif principles_encountered >= 10:
            learning_velocity = "plateau"

        return cls(
            total_sessions=total,
            total_minutes=total_min,
            ship_rate=ship_rate,
            avg_duration_min=total_min / total if total > 0 else 0.0,
            preferred_organs=preferred_organs,
            active_hours=active_hours,
            streak_max=streak_max,
            streak_current=streak,
            risk_appetite=risk_appetite,
            cadence=cadence,
            detector_trust=detector_trust,
            last_session_iso=last_iso,
            mastery_score=float(mastery_score),
            principles_encountered=principles_encountered,
            principles_internalized=principles_internalized,
            top_growth_areas=top_growth_areas,
            learning_velocity=learning_velocity,
        )


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------


def get_trend_summary(stats: dict[str, Any]) -> dict[str, Any]:
    """Aggregate trends: ship rate, duration over recent sessions.

    Accepts raw stats dict so callers don't need an Oracle instance.
    """
    recent = stats.get("recent_sessions", [])
    if not recent:
        return {"sessions_analyzed": 0}

    windows = {"last_5": recent[-5:], "last_10": recent[-10:], "last_20": recent[-20:]}
    summary: dict[str, Any] = {"sessions_analyzed": len(recent)}

    for label, window in windows.items():
        if not window:
            continue
        shipped = sum(1 for s in window if s.get("result") == "SHIPPED")
        durations = [s.get("duration_min", 0) for s in window if s.get("duration_min")]
        summary[label] = {
            "count": len(window),
            "shipped": shipped,
            "ship_rate": round(shipped / len(window), 3) if window else 0,
            "avg_duration_min": round(sum(durations) / len(durations), 1) if durations else 0,
        }

    return summary


# ---------------------------------------------------------------------------
# Behavioral detectors (extracted from Oracle for reuse)
# ---------------------------------------------------------------------------


def detect_session_cadence(stats: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze daily/weekly rhythm and suggest optimal scheduling.

    Returns raw advisory dicts (not Advisory instances) for loose coupling.
    """
    advisories: list[dict[str, Any]] = []
    recent = stats.get("recent_sessions", [])
    if len(recent) < 5:
        return advisories

    timestamps = []
    for s in recent[-20:]:
        ts = s.get("start_time")
        if ts and isinstance(ts, (int, float)):
            timestamps.append(ts)

    if len(timestamps) < 3:
        return advisories

    timestamps.sort()
    gaps_hours = [(timestamps[i + 1] - timestamps[i]) / 3600 for i in range(len(timestamps) - 1)]
    avg_gap = sum(gaps_hours) / len(gaps_hours)

    # Detect long absence
    now = time.time()
    if timestamps:
        since_last = (now - timestamps[-1]) / 3600
        if since_last > avg_gap * 3 and since_last > 72:
            days_away = since_last / 24
            advisories.append({
                "category": "process",
                "severity": "info",
                "message": f"It's been {days_away:.0f} days since your last session (avg gap: {avg_gap / 24:.1f}d). Welcome back.",
                "recommendation": "Start with a FRAME session to re-orient. Check `conductor patch` for context.",
                "detector": "session_cadence",
                "narrative": f"After {days_away:.0f} days away, begin with orientation. The system remembers where you left off."[:200],
                "confidence": 0.6,
                "tags": ["process", "cadence"],
            })

    # Detect burst patterns
    short_gaps = sum(1 for g in gaps_hours if g < 4)
    long_gaps = sum(1 for g in gaps_hours if g > 48)
    if short_gaps > len(gaps_hours) * 0.5 and long_gaps > len(gaps_hours) * 0.2:
        advisories.append({
            "category": "process",
            "severity": "caution",
            "message": "Bursty session pattern detected: intense clusters followed by long breaks.",
            "recommendation": "Aim for shorter, more regular sessions. Consistency compounds.",
            "detector": "session_cadence",
            "confidence": 0.6,
            "tags": ["process", "cadence", "burst"],
        })

    # Day-of-week distribution
    day_counter: Counter = Counter()
    for ts in timestamps:
        day_counter[datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%A")] += 1
    most_common_day, most_count = day_counter.most_common(1)[0] if day_counter else ("", 0)
    if most_count >= len(timestamps) * 0.4 and len(timestamps) >= 5:
        advisories.append({
            "category": "process",
            "severity": "info",
            "message": f"You tend to work most on {most_common_day}s ({most_count}/{len(timestamps)} recent sessions).",
            "detector": "session_cadence",
            "confidence": 0.5,
            "tags": ["process", "cadence", "schedule"],
        })

    return advisories


def detect_burnout_risk(stats: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect overwork patterns: marathon sessions, late nights, declining ship rates."""
    advisories: list[dict[str, Any]] = []
    recent = stats.get("recent_sessions", [])
    if len(recent) < 5:
        return advisories

    recent_5 = recent[-5:]
    durations = [s.get("duration_min", 0) for s in recent_5 if s.get("duration_min")]
    late_night_count = 0
    for s in recent_5:
        ts = s.get("start_time")
        if ts and isinstance(ts, (int, float)):
            hour = datetime.fromtimestamp(ts, tz=timezone.utc).hour
            if hour >= 23 or hour < 5:
                late_night_count += 1

    if durations and len(durations) >= 3:
        avg_dur = sum(durations) / len(durations)
        if avg_dur > 90:
            advisories.append({
                "category": "risk",
                "severity": "warning",
                "message": f"Average session length is {avg_dur:.0f}m over last 5 sessions. Marathon sessions compound fatigue.",
                "recommendation": "Cap sessions at 60-90 minutes. Use PROVE as a natural stopping point.",
                "detector": "burnout_risk",
                "confidence": 0.7,
                "tags": ["risk", "burnout", "duration"],
            })

    if late_night_count >= 3:
        advisories.append({
            "category": "risk",
            "severity": "warning",
            "message": f"{late_night_count}/5 recent sessions started late at night. Sleep-deprived coding ships bugs.",
            "recommendation": "Shift sessions earlier. Late-night sessions have lower ship rates empirically.",
            "detector": "burnout_risk",
            "confidence": 0.65,
            "tags": ["risk", "burnout", "timing"],
        })

    if len(recent) >= 10:
        first_half = recent[-10:-5]
        second_half = recent[-5:]
        first_shipped = sum(1 for s in first_half if s.get("result") == "SHIPPED")
        second_shipped = sum(1 for s in second_half if s.get("result") == "SHIPPED")
        if first_shipped >= 3 and second_shipped <= 1:
            advisories.append({
                "category": "risk",
                "severity": "caution",
                "message": f"Ship rate declining: {first_shipped}/5 → {second_shipped}/5 in recent sessions.",
                "recommendation": "Take a break or reduce scope. Declining rates often indicate fatigue.",
                "detector": "burnout_risk",
                "narrative": "When the work stops shipping, the conductor needs rest — not more effort."[:200],
                "confidence": 0.6,
                "tags": ["risk", "burnout", "decline"],
            })

    timestamps = []
    for s in recent_5:
        ts = s.get("start_time")
        if ts and isinstance(ts, (int, float)):
            timestamps.append(ts)
    timestamps.sort()
    if len(timestamps) >= 3:
        short_gaps = sum(
            1 for i in range(len(timestamps) - 1)
            if (timestamps[i + 1] - timestamps[i]) / 3600 < 2
        )
        if short_gaps >= 2:
            advisories.append({
                "category": "risk",
                "severity": "info",
                "message": "Rapid-fire sessions detected (< 2h gaps). Ensure you're taking breaks.",
                "detector": "burnout_risk",
                "confidence": 0.55,
                "tags": ["risk", "burnout", "pacing"],
            })

    return advisories


def detect_collaboration_patterns(stats: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect multi-session coordination patterns and repo contention."""
    advisories: list[dict[str, Any]] = []
    recent = stats.get("recent_sessions", [])
    if len(recent) < 5:
        return advisories

    # Check for repo re-entry patterns
    repo_sessions: dict[str, int] = defaultdict(int)
    for s in recent[-10:]:
        repo = s.get("repo", "")
        if repo:
            repo_sessions[repo] += 1

    for repo, count in repo_sessions.items():
        if count >= 4:
            advisories.append({
                "category": "process",
                "severity": "info",
                "message": f"Repo '{repo}' visited {count} times in last 10 sessions. Consider a larger restructuring session.",
                "recommendation": f"Batch remaining '{repo}' work into a single scoped session.",
                "detector": "collaboration_patterns",
                "confidence": 0.6,
                "tags": ["process", "collaboration", "revisit"],
            })

    # Phase cycling detection
    phase_transitions: list[str] = []
    for s in recent[-5:]:
        phases = s.get("phases_visited", [])
        if isinstance(phases, list):
            phase_transitions.extend(phases)

    if len(phase_transitions) >= 6:
        reversals = 0
        for i in range(2, len(phase_transitions)):
            if phase_transitions[i] == phase_transitions[i - 2] and phase_transitions[i] != phase_transitions[i - 1]:
                reversals += 1
        if reversals >= 2:
            advisories.append({
                "category": "process",
                "severity": "caution",
                "message": f"Phase ping-pong detected ({reversals} reversals). Architecture may need more SHAPE time upfront.",
                "recommendation": "Invest more in SHAPE before entering BUILD to reduce rework.",
                "detector": "collaboration_patterns",
                "confidence": 0.65,
                "tags": ["process", "collaboration", "ping_pong"],
            })

    return advisories


def detect_cross_session_patterns(oracle_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Learn which advisories were heeded vs ignored, correlate with outcomes."""
    advisories: list[dict[str, Any]] = []
    scores = oracle_state.get("detector_scores", {})

    for det, score_data in scores.items():
        total = score_data.get("total", 0)
        shipped = score_data.get("shipped", 0)
        if total >= 5:
            effectiveness = shipped / total
            if effectiveness < 0.3:
                advisories.append({
                    "category": "growth",
                    "severity": "caution",
                    "message": f"Detector '{det}' active in {total} sessions but only {shipped} shipped. Consider addressing its advisories.",
                    "detector": "cross_session_patterns",
                    "confidence": 0.65,
                    "tags": ["growth", "effectiveness"],
                })

    return advisories
