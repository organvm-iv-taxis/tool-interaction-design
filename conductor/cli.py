"""CLI entry point and dispatch for conductor."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .constants import ONTOLOGY_PATH, ROUTING_PATH, ConductorError
from .parser import build_parser

try:
    _router_dir = str(Path(__file__).parent.parent)
    if _router_dir not in sys.path:
        sys.path.insert(0, _router_dir)
    from router import Ontology, RoutingEngine
    from .router_extensions import install as _install_router_extensions
    _install_router_extensions()
except ImportError:
    Ontology = None  # type: ignore[assignment,misc]
    RoutingEngine = None  # type: ignore[assignment,misc]


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        _dispatch(args)
    except ConductorError as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # pragma: no cover - safety net for user-facing CLI
        if os.environ.get("CONDUCTOR_DEBUG_TRACEBACK", "").strip() == "1":
            raise
        print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def _dispatch(args):
    """Route parsed CLI args to the appropriate command module."""
    from .commands import dispatch

    # Load ontology and routing engine
    ontology = None
    engine = None
    if Ontology and ONTOLOGY_PATH.exists():
        ontology = Ontology(ONTOLOGY_PATH)
    if RoutingEngine and ontology and ROUTING_PATH.exists():
        engine = RoutingEngine(ROUTING_PATH, ontology)
        try:
            from .feedback import inject_into_routing_engine
            inject_into_routing_engine(engine)
        except Exception as exc:
            from .observability import log_event
            log_event("cli.feedback_injection_error", {"error": str(exc)})

    dispatch(args, ontology, engine)
