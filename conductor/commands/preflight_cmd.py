"""Preflight command — auto-start sessions with runway briefing."""

from __future__ import annotations

import json


def handle(args, *, ontology, engine) -> None:
    from ..preflight import run_preflight

    agent = getattr(args, "agent", "unknown") or "unknown"
    cwd = getattr(args, "cwd", None)
    json_output = getattr(args, "json_output", False)
    no_start = getattr(args, "no_start", False)

    result = run_preflight(
        agent=agent,
        cwd=cwd,
        auto_start=not no_start,
        json_output=json_output,
    )

    if json_output:
        print(json.dumps(result.to_dict(), indent=2))
