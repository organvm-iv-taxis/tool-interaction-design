"""DORA metrics computation from session and git data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from .constants import SESSIONS_DIR, STATS_FILE


@dataclass
class DORAMetrics:
    deployment_frequency: float  # deployments per week
    lead_time_minutes: float  # average minutes from session start to SHIPPED
    change_failure_rate: float  # fraction of sessions that CLOSED (not SHIPPED)
    mttr_minutes: float  # average time to recover (re-ship after a CLOSED session)
    rating: str  # "elite", "high", "medium", "low" per DORA benchmarks

    def to_dict(self) -> dict[str, Any]:
        return {
            "deployment_frequency": round(self.deployment_frequency, 2),
            "lead_time_minutes": round(self.lead_time_minutes, 1),
            "change_failure_rate": round(self.change_failure_rate, 4),
            "mttr_minutes": round(self.mttr_minutes, 1),
            "rating": self.rating,
        }


def _load_session_logs(days: int = 30) -> list[dict]:
    """Load session logs from the sessions directory within the given window."""
    logs: list[dict] = []
    if not SESSIONS_DIR.exists():
        return logs

    now = datetime.now(timezone.utc)
    for log_path in SESSIONS_DIR.glob("*/session-log.yaml"):
        try:
            log = yaml.safe_load(log_path.read_text())
            if not isinstance(log, dict):
                continue
            # Filter by timestamp if present
            ts_str = log.get("timestamp")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age_days = (now - ts).total_seconds() / 86400
                    if age_days > days:
                        continue
                except (ValueError, TypeError):
                    pass
            logs.append(log)
        except (yaml.YAMLError, OSError):
            continue

    # Sort by timestamp
    logs.sort(key=lambda x: x.get("timestamp", ""))
    return logs


def _classify_rating(
    deploys_per_week: float,
    lead_time_min: float,
    failure_rate: float,
    mttr_min: float,
) -> str:
    """Classify DORA performance based on standard benchmarks.

    Elite: daily+ deploys (>5/wk), <60min lead, <5% failure, <60min MTTR
    High: weekly+ deploys (>1/wk), <480min lead, <15% failure, <480min MTTR
    Medium: monthly+ deploys (>0.25/wk), <1440min lead, <30% failure, <1440min MTTR
    Low: everything else
    """
    if (
        deploys_per_week >= 5
        and lead_time_min < 60
        and failure_rate < 0.05
        and mttr_min < 60
    ):
        return "elite"
    if (
        deploys_per_week >= 1
        and lead_time_min < 480
        and failure_rate < 0.15
        and mttr_min < 480
    ):
        return "high"
    if (
        deploys_per_week >= 0.25
        and lead_time_min < 1440
        and failure_rate < 0.30
        and mttr_min < 1440
    ):
        return "medium"
    return "low"


def compute_dora(stats_file: Optional[Path] = None, days: int = 30) -> DORAMetrics:
    """Compute DORA metrics from session stats and logs."""
    logs = _load_session_logs(days)

    if not logs:
        return DORAMetrics(
            deployment_frequency=0.0,
            lead_time_minutes=0.0,
            change_failure_rate=0.0,
            mttr_minutes=0.0,
            rating="low",
        )

    # Deployment frequency: SHIPPED sessions per week
    shipped = [l for l in logs if l.get("result") == "SHIPPED"]
    closed = [l for l in logs if l.get("result") == "CLOSED"]
    total = len(logs)

    weeks = max(days / 7.0, 1.0)
    deploys_per_week = len(shipped) / weeks

    # Lead time: average duration (minutes) for SHIPPED sessions
    shipped_durations = [l.get("duration_minutes", 0) for l in shipped]
    lead_time = sum(shipped_durations) / len(shipped_durations) if shipped_durations else 0.0

    # Change failure rate: CLOSED / total
    failure_rate = len(closed) / total if total else 0.0

    # MTTR: average gap between a CLOSED session and the next SHIPPED session
    # Walk through chronological logs and measure recovery time
    mttr_gaps: list[float] = []
    last_closed_ts: Optional[str] = None
    for log in logs:
        result = log.get("result", "")
        if result == "CLOSED":
            last_closed_ts = log.get("timestamp")
        elif result == "SHIPPED" and last_closed_ts is not None:
            try:
                t_closed = datetime.fromisoformat(last_closed_ts)
                t_shipped = datetime.fromisoformat(log.get("timestamp", ""))
                if hasattr(t_closed, "tzinfo") and t_closed.tzinfo is None:
                    t_closed = t_closed.replace(tzinfo=timezone.utc)
                if hasattr(t_shipped, "tzinfo") and t_shipped.tzinfo is None:
                    t_shipped = t_shipped.replace(tzinfo=timezone.utc)
                gap_minutes = (t_shipped - t_closed).total_seconds() / 60
                if gap_minutes >= 0:
                    mttr_gaps.append(gap_minutes)
            except (ValueError, TypeError):
                pass
            last_closed_ts = None

    mttr = sum(mttr_gaps) / len(mttr_gaps) if mttr_gaps else 0.0

    rating = _classify_rating(deploys_per_week, lead_time, failure_rate, mttr)

    return DORAMetrics(
        deployment_frequency=deploys_per_week,
        lead_time_minutes=lead_time,
        change_failure_rate=failure_rate,
        mttr_minutes=mttr,
        rating=rating,
    )


def render_dora_text(metrics: DORAMetrics) -> str:
    """Render DORA metrics as human-readable text."""
    lines = [
        "DORA Metrics",
        "=" * 40,
        f"  Deployment frequency: {metrics.deployment_frequency:.2f}/week",
        f"  Lead time:            {metrics.lead_time_minutes:.0f} minutes",
        f"  Change failure rate:  {metrics.change_failure_rate * 100:.1f}%",
        f"  MTTR:                 {metrics.mttr_minutes:.0f} minutes",
        f"  Rating:               {metrics.rating.upper()}",
    ]
    return "\n".join(lines)
