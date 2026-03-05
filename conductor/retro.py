"""Conductor retro — mine session logs and observability for retrospective insights."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .constants import SESSIONS_DIR, STATS_FILE
from .observability import _load_log_events


def _load_session_logs() -> list[dict[str, Any]]:
    """Load all session-log.yaml files from the sessions directory."""
    logs: list[dict[str, Any]] = []
    if not SESSIONS_DIR.exists():
        return logs
    for session_dir in sorted(SESSIONS_DIR.iterdir()):
        log_file = session_dir / "session-log.yaml"
        if log_file.exists():
            try:
                data = yaml.safe_load(log_file.read_text())
                if isinstance(data, dict):
                    logs.append(data)
            except Exception:
                continue
    return logs


def _load_stats() -> dict[str, Any]:
    """Load cumulative session stats."""
    if STATS_FILE.exists():
        try:
            return json.loads(STATS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _analyze_phase_balance(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze time spent in each phase across all sessions."""
    phase_totals: Counter[str] = Counter()
    phase_visits: Counter[str] = Counter()
    for session in sessions:
        phases = session.get("phases", {})
        for phase_name, phase_data in phases.items():
            if isinstance(phase_data, dict):
                phase_totals[phase_name] += phase_data.get("duration", 0)
                phase_visits[phase_name] += phase_data.get("visits", 1)

    total_time = sum(phase_totals.values()) or 1
    balance = {}
    for phase in ["FRAME", "SHAPE", "BUILD", "PROVE"]:
        t = phase_totals.get(phase, 0)
        balance[phase] = {
            "total_minutes": round(t / 60, 1),
            "percentage": round(t / total_time * 100, 1),
            "visits": phase_visits.get(phase, 0),
        }
    return balance


def _analyze_tool_usage(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Identify most-used tools and underused tools."""
    tool_counter: Counter[str] = Counter()
    for session in sessions:
        phases = session.get("phases", {})
        for phase_data in phases.values():
            if isinstance(phase_data, dict):
                for tool in phase_data.get("tools_used", []):
                    tool_counter[str(tool)] += 1
    return {
        "top_tools": dict(tool_counter.most_common(15)),
        "unique_tools": len(tool_counter),
        "total_uses": sum(tool_counter.values()),
    }


def _analyze_outcomes(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze session outcomes (ship rate, failure modes)."""
    results: Counter[str] = Counter()
    durations: list[int] = []
    for session in sessions:
        result = session.get("result", "UNKNOWN")
        results[result] += 1
        dur = session.get("duration_minutes", 0)
        if isinstance(dur, (int, float)) and dur > 0:
            durations.append(int(dur))

    total = sum(results.values()) or 1
    shipped = results.get("SHIPPED", 0)
    return {
        "total_sessions": sum(results.values()),
        "outcomes": dict(results),
        "ship_rate": round(shipped / total * 100, 1),
        "avg_duration_minutes": round(sum(durations) / len(durations), 1) if durations else 0,
        "median_duration_minutes": sorted(durations)[len(durations) // 2] if durations else 0,
    }


def _analyze_organ_focus(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze which organs get the most attention."""
    organ_counter: Counter[str] = Counter()
    for session in sessions:
        organ = session.get("organ", "UNKNOWN")
        organ_counter[str(organ)] += 1
    return dict(organ_counter.most_common(20))


def _extract_warnings(sessions: list[dict[str, Any]]) -> list[str]:
    """Collect recurring warnings from sessions."""
    warning_counter: Counter[str] = Counter()
    for session in sessions:
        for w in session.get("warnings", []):
            warning_counter[str(w)] += 1
    return [f"{w} (x{count})" for w, count in warning_counter.most_common(10) if count > 1]


def _derive_insights(
    phase_balance: dict[str, Any],
    tool_usage: dict[str, Any],
    outcomes: dict[str, Any],
) -> list[str]:
    """Generate actionable insights from the analysis."""
    insights: list[str] = []

    # Phase imbalance detection
    build_pct = phase_balance.get("BUILD", {}).get("percentage", 0)
    frame_pct = phase_balance.get("FRAME", {}).get("percentage", 0)
    prove_pct = phase_balance.get("PROVE", {}).get("percentage", 0)

    if build_pct > 60:
        insights.append(
            "Heavy BUILD bias — consider spending more time in FRAME/SHAPE "
            "to reduce rework cycles."
        )
    if prove_pct < 10 and outcomes.get("total_sessions", 0) > 3:
        insights.append(
            "Very little PROVE time — verification may be insufficient. "
            "Consider adding test/review steps."
        )
    if frame_pct > 40:
        insights.append(
            "High FRAME ratio — good research discipline, but ensure "
            "it translates into shipped outcomes."
        )

    # Ship rate
    ship_rate = outcomes.get("ship_rate", 0)
    if ship_rate < 50 and outcomes.get("total_sessions", 0) > 3:
        insights.append(
            f"Ship rate is {ship_rate}% — review why sessions are failing "
            f"or being abandoned."
        )

    # Tool diversity
    unique = tool_usage.get("unique_tools", 0)
    if unique < 5 and outcomes.get("total_sessions", 0) > 3:
        insights.append(
            "Low tool diversity — the taxonomy offers many clusters. "
            "Consider expanding workflow repertoire."
        )

    if not insights:
        insights.append("No significant anomalies detected. Keep building momentum.")

    return insights


def _analyze_observability_events() -> dict[str, Any]:
    """Analyze observability log events for failure patterns."""
    events = _load_log_events()
    if not events:
        return {"total_events": 0, "failure_buckets": {}, "event_types": {}}

    type_counter: Counter[str] = Counter()
    failure_counter: Counter[str] = Counter()
    for event in events:
        etype = event.get("event_type", "unknown")
        type_counter[etype] += 1
        if event.get("failed"):
            bucket = event.get("details", {}).get("failure_bucket", etype)
            failure_counter[str(bucket)] += 1

    return {
        "total_events": len(events),
        "event_types": dict(type_counter.most_common(15)),
        "failure_buckets": dict(failure_counter.most_common(10)),
        "failure_rate": round(
            sum(failure_counter.values()) / len(events) * 100, 2
        ) if events else 0,
    }


def run_retro(*, last_n: int = 0, format_name: str = "text") -> dict[str, Any]:
    """Generate a retrospective report from session and observability data.

    Args:
        last_n: If > 0, only analyze the most recent N sessions.
        format_name: Output format (text or json).
    """
    sessions = _load_session_logs()
    if last_n > 0:
        sessions = sessions[-last_n:]

    stats = _load_stats()
    phase_balance = _analyze_phase_balance(sessions)
    tool_usage = _analyze_tool_usage(sessions)
    outcomes = _analyze_outcomes(sessions)
    organ_focus = _analyze_organ_focus(sessions)
    recurring_warnings = _extract_warnings(sessions)
    obs_analysis = _analyze_observability_events()
    insights = _derive_insights(phase_balance, tool_usage, outcomes)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sessions_analyzed": len(sessions),
        "cumulative_stats": stats,
        "phase_balance": phase_balance,
        "tool_usage": tool_usage,
        "outcomes": outcomes,
        "organ_focus": organ_focus,
        "recurring_warnings": recurring_warnings,
        "observability": obs_analysis,
        "insights": insights,
    }
    return report


def render_retro_text(report: dict[str, Any]) -> str:
    """Render a retro report as human-readable text."""
    lines: list[str] = []
    lines.append("Conductor Retrospective")
    lines.append(f"  Generated: {report.get('generated_at', 'N/A')}")
    lines.append(f"  Sessions analyzed: {report.get('sessions_analyzed', 0)}")
    lines.append("")

    # Outcomes
    outcomes = report.get("outcomes", {})
    lines.append("Outcomes:")
    lines.append(f"  Total sessions: {outcomes.get('total_sessions', 0)}")
    lines.append(f"  Ship rate: {outcomes.get('ship_rate', 0)}%")
    lines.append(f"  Avg duration: {outcomes.get('avg_duration_minutes', 0)} min")
    for result, count in outcomes.get("outcomes", {}).items():
        lines.append(f"    {result}: {count}")
    lines.append("")

    # Phase balance
    lines.append("Phase Balance:")
    for phase, data in report.get("phase_balance", {}).items():
        if isinstance(data, dict):
            lines.append(
                f"  {phase}: {data.get('percentage', 0)}% "
                f"({data.get('total_minutes', 0)} min, "
                f"{data.get('visits', 0)} visits)"
            )
    lines.append("")

    # Top tools
    tool_data = report.get("tool_usage", {})
    lines.append(f"Tool Usage ({tool_data.get('unique_tools', 0)} unique tools):")
    for tool, count in list(tool_data.get("top_tools", {}).items())[:10]:
        lines.append(f"  {tool}: {count}")
    lines.append("")

    # Organ focus
    organ_focus = report.get("organ_focus", {})
    if organ_focus:
        lines.append("Organ Focus:")
        for organ, count in organ_focus.items():
            lines.append(f"  {organ}: {count} sessions")
        lines.append("")

    # Observability
    obs = report.get("observability", {})
    if obs.get("total_events", 0) > 0:
        lines.append(f"Observability ({obs['total_events']} events):")
        lines.append(f"  Failure rate: {obs.get('failure_rate', 0)}%")
        for bucket, count in list(obs.get("failure_buckets", {}).items())[:5]:
            lines.append(f"  FAIL: {bucket} (x{count})")
        lines.append("")

    # Warnings
    warnings = report.get("recurring_warnings", [])
    if warnings:
        lines.append("Recurring Warnings:")
        for w in warnings:
            lines.append(f"  - {w}")
        lines.append("")

    # Insights
    lines.append("Insights:")
    for insight in report.get("insights", []):
        lines.append(f"  * {insight}")

    return "\n".join(lines)
