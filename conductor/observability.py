"""Structured observability for governance and patchbay decisions."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import BASE
from .policy import load_policy

OBS_LOG_FILE = BASE / ".conductor-observability.jsonl"
OBS_METRICS_FILE = BASE / ".conductor-observability-metrics.json"


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


def _record_failure_bucket(metrics: dict[str, Any], bucket: str) -> None:
    failure_buckets = Counter(metrics.get("failure_buckets", {}))
    failure_buckets[bucket] += 1
    top_n = load_policy().top_failure_buckets
    metrics["failure_buckets"] = dict(failure_buckets.most_common(top_n))


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
