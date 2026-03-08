"""Command dispatch modules for the conductor CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

from . import (
    export_cmd,
    fleet_cmd,
    governance_cmd,
    oracle_cmd,
    queue_cmd,
    risk_cmd,
    routing_cmd,
    session_cmd,
    system_cmd,
    workflow_cmd,
)

COMMAND_HANDLERS: dict[str, object] = {
    "session": session_cmd,
    "registry": governance_cmd,
    "wip": governance_cmd,
    "enforce": governance_cmd,
    "stale": governance_cmd,
    "audit": governance_cmd,
    "queue": queue_cmd,
    "auto": queue_cmd,
    "workflow": workflow_cmd,
    "compose": workflow_cmd,
    "route": routing_cmd,
    "capability": routing_cmd,
    "validate": routing_cmd,
    "clusters": routing_cmd,
    "domains": routing_cmd,
    "search": routing_cmd,
    "export": export_cmd,
    "patterns": export_cmd,
    "patch": system_cmd,
    "graph": system_cmd,
    "doctor": system_cmd,
    "plugins": system_cmd,
    "policy": system_cmd,
    "observability": system_cmd,
    "handoff": system_cmd,
    "edge": system_cmd,
    "migrate": system_cmd,
    "retro": system_cmd,
    "wiring": system_cmd,
    "version": system_cmd,
    "oracle": oracle_cmd,
    "risk": risk_cmd,
    "dora": system_cmd,
    "prompt": system_cmd,
    "fleet": fleet_cmd,
}


def dispatch(args: argparse.Namespace, ontology, engine) -> None:
    """Route a parsed CLI namespace to its command handler."""
    module = COMMAND_HANDLERS.get(args.command)
    if module is None:
        raise ValueError(f"Unknown command: {args.command}")
    module.handle(args, ontology=ontology, engine=engine)  # type: ignore[attr-defined]
