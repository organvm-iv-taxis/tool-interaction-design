"""Tests for structured observability outputs."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import conductor.observability
from conductor.observability import log_event


def test_log_event_writes_log_and_metrics(tmp_path) -> None:
    log_file = tmp_path / "obs.jsonl"
    metrics_file = tmp_path / "metrics.json"

    with patch.object(conductor.observability, "OBS_LOG_FILE", log_file), \
         patch.object(conductor.observability, "OBS_METRICS_FILE", metrics_file):
        log_event("governance.audit", {"scope": "FULL"})
        log_event("governance.audit", {"scope": "FULL"}, failed=True, failure_bucket="audit_fail")

    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 2
    payload = json.loads(lines[0])
    assert payload["event_type"] == "governance.audit"

    metrics = json.loads(metrics_file.read_text())
    assert metrics["event_counts"]["governance.audit"] == 2
    assert metrics["failure_buckets"]["audit_fail"] == 1
