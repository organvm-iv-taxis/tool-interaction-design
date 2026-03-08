"""Structured observability for governance and patchbay decisions."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import STATE_DIR
from .policy import load_policy

OBS_LOG_FILE = STATE_DIR / "observability" / "events.jsonl"
OBS_METRICS_FILE = STATE_DIR / "observability" / "metrics.json"
OBS_REPORT_FILE = STATE_DIR / "observability" / "report.json"

# Log rotation constants
_MAX_LOG_LINES = 5000
_ROTATE_KEEP_LINES = 3000


def _safe_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _load_metrics() -> dict[str, Any]:
    if OBS_METRICS_FILE.exists():
        try:
            return json.loads(OBS_METRICS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "event_counts": {},
        "failure_buckets": {},
        "updated_at": "",
    }


def get_metrics() -> dict[str, Any]:
    """Return current observability aggregate metrics."""
    return _load_metrics()


def _load_log_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not OBS_LOG_FILE.exists():
        return events
    try:
        for raw_line in OBS_LOG_FILE.read_text().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                events.append(payload)
    except (OSError, json.JSONDecodeError):
        return []
    return events


def compute_trend_report(events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Compute failure-rate trends from observability events."""
    policy = load_policy()
    sample = events if events is not None else _load_log_events()
    total = len(sample)
    failures = sum(1 for event in sample if bool(event.get("failed")))
    overall_rate = (failures / total) if total else 0.0

    window = max(1, policy.trend_min_events)
    recent = sample[-window:]
    previous = sample[-2 * window:-window] if len(sample) >= window * 2 else []
    recent_total = len(recent)
    recent_failures = sum(1 for event in recent if bool(event.get("failed")))
    previous_total = len(previous)
    previous_failures = sum(1 for event in previous if bool(event.get("failed")))
    recent_rate = (recent_failures / recent_total) if recent_total else 0.0
    previous_rate = (previous_failures / previous_total) if previous_total else 0.0

    status = "ok"
    if recent_total < window:
        status = "insufficient_data"
    elif recent_rate >= policy.trend_critical_rate:
        status = "critical"
    elif recent_rate >= policy.trend_warn_rate:
        status = "warn"

    return {
        "status": status,
        "window": window,
        "overall": {
            "events": total,
            "failures": failures,
            "failure_rate": round(overall_rate, 4),
        },
        "recent": {
            "events": recent_total,
            "failures": recent_failures,
            "failure_rate": round(recent_rate, 4),
        },
        "previous": {
            "events": previous_total,
            "failures": previous_failures,
            "failure_rate": round(previous_rate, 4),
        },
        "delta_failure_rate": round(recent_rate - previous_rate, 4),
        "thresholds": {
            "warn_rate": policy.trend_warn_rate,
            "critical_rate": policy.trend_critical_rate,
        },
    }


def export_metrics_report(output_path: Path | None = None) -> dict[str, Any]:
    """Export merged observability metrics + trend checks."""
    metrics = _load_metrics()
    trends = compute_trend_report()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "trends": trends,
    }
    path = output_path or OBS_REPORT_FILE
    _safe_write_json(path, payload)
    return payload


def _record_failure_bucket(metrics: dict[str, Any], bucket: str) -> None:
    failure_buckets = Counter(metrics.get("failure_buckets", {}))
    failure_buckets[bucket] += 1
    top_n = load_policy().top_failure_buckets
    metrics["failure_buckets"] = dict(failure_buckets.most_common(top_n))


def rotate_log(log_path: Path, max_lines: int = _MAX_LOG_LINES, keep_lines: int = _ROTATE_KEEP_LINES) -> bool:
    """Rotate a JSONL log file when it exceeds max_lines.

    Keeps the most recent `keep_lines` entries and archives the rest
    into a timestamped file in the same directory.
    Returns True if rotation occurred.
    """
    if not log_path.exists():
        return False
    try:
        lines = log_path.read_text().splitlines()
        if len(lines) <= max_lines:
            return False

        # Archive the old entries
        archive_name = log_path.stem + f"-archive-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}" + log_path.suffix
        archive_path = log_path.parent / archive_name
        archive_lines = lines[:-keep_lines]
        archive_path.write_text("\n".join(archive_lines) + "\n")

        # Keep only recent entries
        recent_lines = lines[-keep_lines:]
        log_path.write_text("\n".join(recent_lines) + "\n")
        return True
    except OSError:
        return False


def log_cluster_activation(cluster_id: str, phase: str, session_id: str) -> None:
    """Track which clusters are activated during sessions."""
    log_event("cluster.activation", {
        "cluster_id": cluster_id,
        "phase": phase,
        "session_id": session_id,
    })


def log_event(event_type: str, details: dict[str, Any] | None = None, *, failed: bool = False, failure_bucket: str | None = None) -> None:
    """Append JSONL event and maintain aggregate failure counters."""
    policy = load_policy()
    if not policy.observability_enabled:
        return

    now = datetime.now(timezone.utc).isoformat()
    event = {
        "timestamp": now,
        "event_type": event_type,
        "failed": failed,
        "details": details or {},
    }

    try:
        OBS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with OBS_LOG_FILE.open("a") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")

        # Rotate if log is too large
        rotate_log(OBS_LOG_FILE)

        metrics = _load_metrics()
        counts = Counter(metrics.get("event_counts", {}))
        counts[event_type] += 1
        metrics["event_counts"] = dict(counts)
        if failed:
            bucket = failure_bucket or event_type
            _record_failure_bucket(metrics, bucket)
        metrics["updated_at"] = now
        _safe_write_json(OBS_METRICS_FILE, metrics)
    except OSError:
        # Observability is best-effort and must never break command flow.
        return
