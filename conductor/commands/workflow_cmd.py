"""Workflow execution and compose commands."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from ..constants import WORKFLOW_DSL_PATH, ConductorError


def handle(args, *, ontology, engine) -> None:
    if args.command == "workflow":
        _handle_workflow(args, ontology=ontology)
    elif args.command == "compose":
        _handle_compose(args, ontology=ontology, engine=engine)


def _handle_workflow(args, *, ontology) -> None:
    from ..executor import WorkflowExecutor
    from ..session import SessionEngine

    executor = WorkflowExecutor(WORKFLOW_DSL_PATH)

    if args.workflow_command == "list":
        workflows = executor.list_workflows()
        for name in workflows:
            print(name)
        if not workflows:
            raise ConductorError("No workflows found in workflow DSL.")

    elif args.workflow_command == "start":
        input_payload = None
        if args.input_json:
            try:
                input_payload = json.loads(args.input_json)
            except json.JSONDecodeError as exc:
                raise ConductorError(f"--input-json is not valid JSON: {exc}") from exc

        session_id = args.session_id
        if not session_id:
            try:
                active = SessionEngine(ontology)._load_session()
            except Exception as exc:
                from ..observability import log_event
                log_event("workflow_cmd.active_session_load_error", {"error": str(exc)})
                active = None
            if active:
                session_id = active.session_id
            else:
                session_id = datetime.now(timezone.utc).strftime("adhoc-%Y%m%d%H%M%S")

        state = executor.start_workflow(args.name, session_id=session_id, global_input=input_payload)
        payload = {
            "workflow": state.workflow_name,
            "session_id": state.session_id,
            "status": state.status,
            "current_step": state.current_step,
            "progress": f"0/{len(state.steps)}",
        }
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(f"workflow={payload['workflow']} session_id={payload['session_id']}")
            print(
                f"  status={payload['status']} current_step={payload['current_step']} "
                f"progress={payload['progress']}"
            )

    elif args.workflow_command == "status":
        payload = executor.get_briefing()
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            if not payload.get("active"):
                print("No active workflow execution state.")
            else:
                context = payload.get("current_context", {})
                print(f"workflow={payload.get('workflow')} status={payload.get('status')}")
                print(f"  current_step={payload.get('current_step')} progress={payload.get('progress')}")
                if context.get("cluster"):
                    print(
                        f"  cluster={context.get('cluster')} "
                        f"tool={context.get('tool')} checkpoint={context.get('checkpoint')}"
                    )

    elif args.workflow_command == "step":
        output_payload = None
        if args.output_json:
            try:
                output_payload = json.loads(args.output_json)
            except json.JSONDecodeError as exc:
                raise ConductorError(f"--output-json is not valid JSON: {exc}") from exc
        payload = executor.run_step(
            step_name=args.name,
            tool_output=output_payload,
            checkpoint_action=args.checkpoint_action,
        )
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(f"status={payload.get('status')} step={args.name}")
            if payload.get("next_step"):
                print(
                    f"  next_step={payload.get('next_step')} "
                    f"checkpoint={payload.get('checkpoint')}"
                )
            if payload.get("allowed_actions"):
                print(f"  allowed_actions={','.join(payload.get('allowed_actions', []))}")

    elif args.workflow_command == "resume":
        payload = executor.resume_workflow(from_step=args.from_step)
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(f"workflow={payload['workflow']} status={payload['status']}")
            print(
                f"  current_step={payload['current_step']} "
                f"progress={payload['progress']}"
            )
            if payload.get("from_step"):
                print(f"  rewound from: {payload['from_step']}")

    elif args.workflow_command == "clear":
        executor.clear_state()
        print("Cleared workflow execution state.")


def _handle_compose(args, *, ontology, engine) -> None:
    from ..compiler import WorkflowCompiler
    from ..session import SessionEngine

    if not engine or not ontology:
        print("  ERROR: Ontology/routing files not found.", file=sys.stderr)
        sys.exit(1)

    compiler = WorkflowCompiler(engine, ontology)

    session_id = args.session_id
    if not session_id:
        try:
            active = SessionEngine(ontology)._load_session()
            session_id = active.session_id if active else "adhoc-compose"
        except Exception as exc:
            from ..observability import log_event
            log_event("workflow_cmd.compose_session_load_error", {"error": str(exc)})
            session_id = "adhoc-compose"

    state = compiler.compile_mission(
        goal=args.goal,
        start_cluster=args.from_cluster,
        end_cluster=args.to_cluster,
        session_id=session_id,
    )

    if args.format == "json":
        print(json.dumps(state.to_dict(), indent=2))
    else:
        print("\n  Mission Synthesized")
        print("  " + "=" * 50)
        print(f"  Goal: {args.goal}")
        print(f"  Path: {args.from_cluster} -> {args.to_cluster}")
        print(f"  ID:   {state.workflow_name}")
        print("\n  Compiled Score:")
        print(compiler.generate_description(state))
        print("\n  Run `conductor workflow status` to begin execution.")
        print()
