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
    elif args.session_command == "record-output":
        se.record_output(args.category, args.description)
    elif args.session_command == "track-tokens":
        se.track_tokens(args.count, cost_per_1k=args.cost_per_1k)
    elif args.session_command == "export":
        from ..archive import export_session
        output = export_session(args.session_id, output_dir=args.output)
        print(f"  Session exported to: {output}")
