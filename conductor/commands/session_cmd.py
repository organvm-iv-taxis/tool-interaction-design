"""Session lifecycle commands."""

from __future__ import annotations

from ..session import SessionEngine


def handle(args, *, ontology, engine) -> None:
    se = SessionEngine(ontology)
    if args.session_command == "start":
        se.start(args.organ, args.repo, args.scope, git_branch=not args.no_branch)
    elif args.session_command == "phase":
        se.phase(args.target)
    elif args.session_command == "status":
        se.status()
    elif args.session_command == "close":
        se.close()
    elif args.session_command == "log-tool":
        se.log_tool(args.tool_name)
