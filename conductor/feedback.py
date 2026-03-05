"""Adaptive health feedback loop.

After workflow steps complete, this module feeds success/failure signals
back into the routing engine's health metrics, improving future pathfinding.
The feedback is persisted so it survives across sessions.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import STATE_DIR, atomic_write
from .observability import log_event

HEALTH_CACHE_FILE = STATE_DIR / "cluster-health.json"

# Decay factor: each feedback cycle blends new data with existing scores.
# 0.0 = ignore history, 1.0 = ignore new data. 0.3 = 30% history weight.
_DECAY_FACTOR = 0.3


def _load_health_cache() -> dict[str, float]:
    """Load persisted cluster health scores."""
    if HEALTH_CACHE_FILE.exists():
        try:
            data = json.loads(HEALTH_CACHE_FILE.read_text())
            if isinstance(data, dict):
                return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_health_cache(scores: dict[str, float]) -> None:
    """Persist cluster health scores."""
    atomic_write(HEALTH_CACHE_FILE, json.dumps(scores, indent=2, sort_keys=True))


def record_step_outcome(
    cluster_id: str | None,
    success: bool,
    *,
    workflow_name: str = "",
    step_name: str = "",
) -> None:
    """Record the outcome of a workflow step for a cluster.

    This updates the persisted health cache with exponential moving average.
    """
    if not cluster_id:
        return

    cache = _load_health_cache()
    current = cache.get(cluster_id, 1.0)
    observation = 1.0 if success else 0.0

    # Exponential moving average
    updated = _DECAY_FACTOR * current + (1 - _DECAY_FACTOR) * observation
    cache[cluster_id] = round(updated, 4)

    _save_health_cache(cache)
    log_event(
        "feedback.health_updated",
        {
            "cluster": cluster_id,
            "success": success,
            "previous_score": current,
            "new_score": cache[cluster_id],
            "workflow": workflow_name,
            "step": step_name,
        },
    )


def get_health_scores() -> dict[str, float]:
    """Return current cluster health scores (0.0-1.0)."""
    return _load_health_cache()


def inject_into_routing_engine(engine: Any) -> int:
    """Inject persisted health scores into a RoutingEngine instance.

    Returns the number of clusters injected.
    """
    scores = _load_health_cache()
    if scores and hasattr(engine, "inject_health_metrics"):
        engine.inject_health_metrics(scores)
    return len(scores)


def merge_with_trace_metrics(trace_metrics: dict[str, float]) -> dict[str, float]:
    """Merge persisted feedback scores with live trace-based metrics.

    Trace metrics are treated as more recent and get higher weight.
    """
    cached = _load_health_cache()
    merged: dict[str, float] = dict(cached)

    for cluster_id, trace_score in trace_metrics.items():
        if cluster_id in merged:
            # Blend: 40% cached, 60% trace (trace is more recent)
            merged[cluster_id] = round(0.4 * merged[cluster_id] + 0.6 * trace_score, 4)
        else:
            merged[cluster_id] = trace_score

    return merged


def reset_health_cache() -> None:
    """Clear the persisted health cache."""
    HEALTH_CACHE_FILE.unlink(missing_ok=True)
