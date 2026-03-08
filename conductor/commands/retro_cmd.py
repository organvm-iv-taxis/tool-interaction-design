"""Retro session subcommand — generate per-session retrospective and inject feedback."""

from __future__ import annotations

import json
from pathlib import Path


def handle_retro_session(args) -> None:
    """Generate a session retrospective and optionally inject feedback into system loops."""
    from ..sprint_ledger import alchemize_ledger, build_ledger, render_ledger_markdown

    session_id = getattr(args, "id", None)
    if not session_id and getattr(args, "latest", True):
        session_id = None  # build_ledger defaults to latest

    try:
        ledger = build_ledger(session_id=session_id)
    except ValueError as e:
        print(f"  ERROR: {e}")
        return

    output = getattr(args, "output", None)
    write_flag = getattr(args, "write", False)

    # --write triggers the feedback injection (alchemize)
    if write_flag or output:
        actions = alchemize_ledger(ledger)
        if actions:
            print(f"  Feedback injected ({len(actions)} actions):")
            for a in actions:
                print(f"    -> {a}")

    fmt = getattr(args, "format", "text")
    if fmt == "json":
        print(json.dumps(ledger.to_dict(), indent=2))
        return

    md = render_ledger_markdown(ledger)

    if output:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md)
        print(f"  Retrospective written to: {output}")
    elif write_flag:
        from ..constants import SESSIONS_DIR
        retro_path = SESSIONS_DIR / ledger.session_id / "retro.md"
        retro_path.parent.mkdir(parents=True, exist_ok=True)
        retro_path.write_text(md)
        print(f"  Retrospective written to: {retro_path}")
    else:
        print(md)
