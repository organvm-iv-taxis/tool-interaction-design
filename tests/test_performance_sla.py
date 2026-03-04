"""Performance SLA smoke checks for routing operations."""

from __future__ import annotations

import statistics
import time
from pathlib import Path

from router import Ontology, RoutingEngine


BASE = Path(__file__).parent.parent


def measure_ms(fn, repeat: int = 20) -> list[float]:
    samples: list[float] = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return samples


def test_routing_find_path_p95_under_sla() -> None:
    ontology = Ontology(BASE / "ontology.yaml")
    engine = RoutingEngine(BASE / "routing-matrix.yaml", ontology)
    samples = measure_ms(lambda: engine.find_path("RESEARCH", "CODE"))
    p95 = sorted(samples)[int(len(samples) * 0.95) - 1]
    assert p95 < 80.0


def test_ontology_capability_lookup_avg_under_sla() -> None:
    ontology = Ontology(BASE / "ontology.yaml")
    samples = measure_ms(lambda: ontology.by_capability("SEARCH"))
    avg = statistics.mean(samples)
    assert avg < 20.0
