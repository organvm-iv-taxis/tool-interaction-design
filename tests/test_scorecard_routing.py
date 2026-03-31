"""Tests for scorecard integration into fleet router scoring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch as mock_patch

from conductor.fleet import FleetRegistry
from conductor.fleet_router import FleetRouter, W_HISTORICAL_SURVIVAL
from conductor.scorecard import AgentScorecard


def test_historical_survival_weight_exists():
    """Verify the new weight constant is defined."""
    assert W_HISTORICAL_SURVIVAL > 0
    assert W_HISTORICAL_SURVIVAL <= 0.20


def test_router_accepts_scorecards():
    """Verify recommend() accepts optional scorecards parameter."""
    router = FleetRouter()
    # Should not raise — scorecards is optional
    results = router.recommend(
        phase="BUILD",
        scorecards={},
    )
    assert isinstance(results, list)
