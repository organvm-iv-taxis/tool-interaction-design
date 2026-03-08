"""Route, capability, validate, clusters, and domains commands."""

from __future__ import annotations

import json
import sys

from ..constants import ConductorError
from ..handoff import simulate_route_handoff


def handle(args, *, ontology, engine) -> None:
    if args.command == "route":
        _handle_route(args, ontology=ontology, engine=engine)
    elif args.command == "capability":
        _handle_capability(args, ontology=ontology, engine=engine)
    elif args.command == "validate":
        _handle_validate(args, ontology=ontology, engine=engine)
    elif args.command == "clusters":
        _handle_clusters(args, ontology=ontology, engine=engine)
    elif args.command == "domains":
        _handle_domains(args, ontology=ontology, engine=engine)
    elif args.command == "search":
        _handle_search(args, ontology=ontology, engine=engine)


def _require_engine(engine):
    if not engine:
        print("  ERROR: Ontology/routing files not found.", file=sys.stderr)
        sys.exit(1)


def _handle_route(args, *, ontology, engine) -> None:
    _require_engine(engine)
    if args.route_command == "simulate":
        report = simulate_route_handoff(
            ontology=ontology,
            engine=engine,
            source_cluster=args.from_cluster,
            target_cluster=args.to_cluster,
            objective=args.objective,
            deadline_ms=args.deadline_ms,
            priority=args.priority,
        )
        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            decision = report.get("route_decision", {})
            trace = report.get("trace", {})
            print("Route simulation")
            print(
                f"  decision={decision.get('decision')} "
                f"status={trace.get('status')} "
                f"latency_ms={trace.get('latency_ms')}"
            )
            print(f"  selected_path={decision.get('selected_path')}")
        if not report.get("ok"):
            raise ConductorError("Route simulation failed to produce a valid path.")
    else:
        if not args.from_cluster or not args.to_cluster:
            raise ConductorError("Route requires --from and --to when not using `route simulate`.")
        from router import cmd_route
        cmd_route(args, ontology, engine)


def _handle_capability(args, *, ontology, engine) -> None:
    _require_engine(engine)
    from router import cmd_capability
    args.capability = args.cap
    cmd_capability(args, ontology, engine)


def _handle_validate(args, *, ontology, engine) -> None:
    _require_engine(engine)
    from router import cmd_validate
    cmd_validate(args, ontology, engine)


def _handle_clusters(args, *, ontology, engine) -> None:
    _require_engine(engine)
    from router import cmd_clusters
    cmd_clusters(args, ontology, engine)


def _handle_domains(args, *, ontology, engine) -> None:
    _require_engine(engine)
    from router import cmd_domains
    cmd_domains(args, ontology, engine)


def _handle_search(args, *, ontology, engine) -> None:
    _require_engine(engine)
    from router import cmd_search
    cmd_search(args, ontology, engine)
