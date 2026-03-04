#!/usr/bin/env python3
"""Benchmark routing hot paths and optionally enforce SLA."""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from router import Ontology, RoutingEngine

SLA_MS = {
    "find_path": 50.0,
    "find_routes": 10.0,
    "capability_lookup": 10.0,
}


def timed(fn, repeat: int = 50):
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        samples.append((t1 - t0) * 1000.0)
    return {
        "avg_ms": statistics.mean(samples),
        "p95_ms": sorted(samples)[int(repeat * 0.95) - 1],
        "max_ms": max(samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark routing performance")
    parser.add_argument("--enforce", action="store_true", help="Fail if SLA thresholds are exceeded")
    parser.add_argument("--repeat", type=int, default=50)
    args = parser.parse_args()

    ontology = Ontology(ROOT / "ontology.yaml")
    engine = RoutingEngine(ROOT / "routing-matrix.yaml", ontology)

    results = {
        "find_path": timed(lambda: engine.find_path("RESEARCH", "CODE"), repeat=args.repeat),
        "find_routes": timed(lambda: engine.find_routes("web_search", "knowledge_graph"), repeat=args.repeat),
        "capability_lookup": timed(lambda: ontology.by_capability("SEARCH"), repeat=args.repeat),
    }

    failed = False
    for name, metrics in results.items():
        print(
            f"{name:<18} avg={metrics['avg_ms']:.2f}ms "
            f"p95={metrics['p95_ms']:.2f}ms max={metrics['max_ms']:.2f}ms "
            f"(SLA {SLA_MS[name]:.2f}ms)"
        )
        if args.enforce and metrics["p95_ms"] > SLA_MS[name]:
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
