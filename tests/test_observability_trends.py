"""Trend analysis tests for observability reporting."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from conductor.observability import compute_trend_report


def test_trend_report_warn_status() -> None:
    events = [
        {"failed": False},
        {"failed": False},
        {"failed": True},
        {"failed": False},
        {"failed": True},
        {"failed": False},
        {"failed": True},
        {"failed": False},
    ]
    policy = SimpleNamespace(trend_min_events=4, trend_warn_rate=0.5, trend_critical_rate=0.75)
    with patch("conductor.observability.load_policy", return_value=policy):
        report = compute_trend_report(events)

    assert report["status"] == "warn"
    assert report["recent"]["events"] == 4


def test_trend_report_critical_status() -> None:
    events = [
        {"failed": False},
        {"failed": False},
        {"failed": False},
        {"failed": False},
        {"failed": True},
        {"failed": True},
        {"failed": True},
        {"failed": True},
    ]
    policy = SimpleNamespace(trend_min_events=4, trend_warn_rate=0.5, trend_critical_rate=0.75)
    with patch("conductor.observability.load_policy", return_value=policy):
        report = compute_trend_report(events)

    assert report["status"] == "critical"


def test_trend_report_insufficient_data() -> None:
    events = [{"failed": True}, {"failed": False}]
    policy = SimpleNamespace(trend_min_events=5, trend_warn_rate=0.5, trend_critical_rate=0.75)
    with patch("conductor.observability.load_policy", return_value=policy):
        report = compute_trend_report(events)

    assert report["status"] == "insufficient_data"
