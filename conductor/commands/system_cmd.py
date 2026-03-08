"""System commands: patch, graph, doctor, plugins, policy, observability,
handoff, edge, migrate, retro, wiring, version."""

from __future__ import annotations

import json
import sys
import time

import yaml

from ..constants import ConductorError, resolve_organ_key


def handle(args, *, ontology, engine) -> None:
    cmd = args.command
    if cmd == "patch":
        _handle_patch(args, ontology=ontology)
    elif cmd == "graph":
        _handle_graph(args)
    elif cmd == "doctor":
        _handle_doctor(args)
    elif cmd == "plugins":
        _handle_plugins(args)
    elif cmd == "policy":
        _handle_policy(args)
    elif cmd == "observability":
        _handle_observability(args)
    elif cmd == "handoff":
        _handle_handoff(args)
    elif cmd == "edge":
        _handle_edge(args)
    elif cmd == "migrate":
        _handle_migrate(args)
    elif cmd == "retro":
        _handle_retro(args)
    elif cmd == "wiring":
        _handle_wiring(args)
    elif cmd == "version":
        _handle_version()
    elif cmd == "dora":
        _handle_dora(args)
    elif cmd == "prompt":
        _handle_prompt(args)


def _handle_patch(args, *, ontology) -> None:
    from ..patchbay import Patchbay
    from ..session import SessionEngine

    organ_filter = resolve_organ_key(args.organ) if args.organ else None
    try:
        pb = Patchbay(ontology=ontology, engine=SessionEngine(ontology))
    except Exception as e:
        print(f"  ERROR: Patchbay initialization failed: {e}", file=sys.stderr)
        sys.exit(1)

    def _do_briefing():
        data = pb.briefing(organ_filter=organ_filter)
        if args.section:
            data = {
                "timestamp": data["timestamp"],
                args.section: data.get(args.section, {}),
            }
        if args.json_output:
            return pb.format_json(data)
        elif args.section:
            return pb.format_section_text(data)
        else:
            return pb.format_text(data)

    if getattr(args, "watch", False):
        try:
            while True:
                sys.stdout.write("\033[2J\033[H")
                print(_do_briefing())
                print("\n  [Watching... Press Ctrl+C to exit]")
                time.sleep(5)
        except KeyboardInterrupt:
            print("\n  Watch mode exited.")
    else:
        print(_do_briefing())


def _handle_graph(args) -> None:
    from ..governance import GovernanceRuntime
    from ..graph import RegistryGraph

    gov = GovernanceRuntime()
    rg = RegistryGraph(gov)

    def _do_graph():
        gov._load()
        return rg.generate_mermaid()

    if args.output:
        args.output.write_text(_do_graph())
        print(f"  Graph written to: {args.output}")
    elif args.live:
        try:
            while True:
                sys.stdout.write("\033[2J\033[H")
                print(_do_graph())
                print("\n  [Watching... Press Ctrl+C to exit]")
                time.sleep(5)
        except KeyboardInterrupt:
            print("\n  Live graph mode exited.")
    else:
        print(_do_graph())


def _handle_doctor(args) -> None:
    from ..doctor import assert_doctor_ok, render_doctor_text, run_doctor

    report = run_doctor(
        workflow_path=args.workflow,
        format_name=args.format,
        apply=args.apply,
        tools=args.tools,
        mas_health=getattr(args, "mas_health", False),
    )
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(render_doctor_text(report))
    if args.strict:
        assert_doctor_ok(report)


def _handle_plugins(args) -> None:
    from ..plugins import plugin_doctor_report, render_plugin_doctor_text

    if args.plugins_command == "doctor":
        report = plugin_doctor_report()
        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            print(render_plugin_doctor_text(report))
        summary = report.get("summary", {})
        errors = int(summary.get("errors", 0))
        warnings = int(summary.get("warnings", 0))
        if errors > 0 or (args.strict and warnings > 0):
            raise ConductorError("Plugin doctor found issues.")


def _handle_policy(args) -> None:
    from ..governance import GovernanceRuntime
    from ..policy import render_policy_simulation_text, simulate_policy

    if args.policy_command == "simulate":
        gov = GovernanceRuntime()
        report = simulate_policy(args.bundle, gov.registry)
        if args.organ:
            key = resolve_organ_key(args.organ)
            organs = report.get("organs", {})
            filtered = {key: organs[key]} if key in organs else {}
            report["organs"] = filtered
            report["summary"] = {
                "organs_checked": len(filtered),
                "organs_with_violations": sum(
                    1 for row in filtered.values() if row.get("violations", 0) > 0
                ),
                "violations_total": sum(
                    int(row.get("violations", 0)) for row in filtered.values()
                ),
            }
        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            print(render_policy_simulation_text(report))


def _handle_observability(args) -> None:
    from ..observability import OBS_REPORT_FILE, export_metrics_report

    if args.observability_command == "report":
        report = export_metrics_report(output_path=args.output)
        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            trend = report.get("trends", {})
            overall = trend.get("overall", {})
            recent = trend.get("recent", {})
            print("Observability report")
            print(
                f"  status={trend.get('status')} "
                f"overall_failure_rate={overall.get('failure_rate')} "
                f"recent_failure_rate={recent.get('failure_rate')}"
            )
            output_path = args.output or OBS_REPORT_FILE
            print(f"  report_path={output_path}")
        if args.check and report.get("trends", {}).get("status") in {"warn", "critical"}:
            raise ConductorError("Observability trend check failed threshold.")


def _handle_handoff(args) -> None:
    from ..handoff import validate_handoff_payload

    if args.handoff_command == "validate":
        if not args.input.exists():
            raise ConductorError(f"Handoff input file not found: {args.input}")
        if args.input.suffix.lower() == ".json":
            payload = json.loads(args.input.read_text())
        else:
            payload = yaml.safe_load(args.input.read_text()) or {}
        if not isinstance(payload, dict):
            raise ConductorError("Handoff payload must be a JSON/YAML object.")
        report = validate_handoff_payload(payload)
        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            print(f"valid={report.get('valid')}")
            for issue in report.get("issues", []):
                print(f"  {issue['code']} {issue['path']}: {issue['message']}")
        if not report.get("valid"):
            raise ConductorError("Handoff contract validation failed.")


def _handle_edge(args) -> None:
    from ..handoff import edge_health_report, get_trace_bundle

    if args.edge_command == "health":
        payload = edge_health_report(window=args.window)
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print("Edge health")
            print(
                f"  traces={payload.get('total_traces')} "
                f"success_rate={payload.get('handoff_success_rate')} "
                f"schema_pass_rate={payload.get('schema_pass_rate')} "
                f"fallback_rate={payload.get('fallback_rate')} "
                f"p95_latency_ms={payload.get('p95_edge_latency_ms')} "
                f"context_loss_rate={payload.get('context_loss_rate')}"
            )
    elif args.edge_command == "trace":
        payload = get_trace_bundle(args.trace_id)
        if not any(payload.get(key) for key in ("handoff", "trace", "route_decision")):
            raise ConductorError(f"Trace not found: {args.trace_id}")
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            trace = payload.get("trace") or {}
            decision = payload.get("route_decision") or {}
            print(f"trace_id={payload.get('trace_id')}")
            print(
                f"  status={trace.get('status')} "
                f"latency_ms={trace.get('latency_ms')} "
                f"decision={decision.get('decision')}"
            )


def _handle_migrate(args) -> None:
    from ..migrate import migrate_governance, migrate_registry, write_migration_output

    if args.migrate_command == "registry":
        from ..constants import REGISTRY_PATH

        input_path = args.input or REGISTRY_PATH
        output_path = input_path if args.in_place or args.output is None else args.output
        payload = migrate_registry(input_path)
        write_migration_output(payload, output_path)
        print(f"  Migrated registry -> {output_path}")
    elif args.migrate_command == "governance":
        from ..constants import GOVERNANCE_PATH

        input_path = args.input or GOVERNANCE_PATH
        output_path = input_path if args.in_place or args.output is None else args.output
        payload = migrate_governance(input_path)
        write_migration_output(payload, output_path)
        print(f"  Migrated governance -> {output_path}")


def _handle_retro(args) -> None:
    retro_cmd = getattr(args, "retro_command", None)
    if retro_cmd == "session":
        from .retro_cmd import handle_retro_session
        handle_retro_session(args)
        return

    # Default: summary retro (existing behavior)
    from ..retro import render_retro_text, run_retro

    report = run_retro(last_n=args.last, format_name=args.format)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(render_retro_text(report))


def _handle_wiring(args) -> None:
    from ..governance import GovernanceRuntime
    from ..wiring import WiringEngine

    gov = GovernanceRuntime()
    we = WiringEngine(gov)
    if args.wiring_command == "inject":
        print("\n  Injecting Conductor hooks...")
        results = we.inject_all(dry_run=not args.apply)
        print(
            f"  Done. Injected: {len(results['injected'])}, "
            f"Skipped: {len(results['skipped'])}, "
            f"Errors: {len(results['errors'])}"
        )
        if not args.apply:
            print("  (Run with --apply to actually write files)")
    elif args.wiring_command == "mcp":
        print("\n  Setting up global MCP...")
        msg = we.global_mcp_setup(dry_run=not args.apply)
        print(f"  {msg}")
        if not args.apply:
            print("  (Run with --apply to actually update settings)")


def _handle_version() -> None:
    from conductor import __version__

    print(f"  conductor {__version__}")


def _handle_dora(args) -> None:
    from ..dora import compute_dora, render_dora_text

    metrics = compute_dora(days=args.days)
    if args.format == "json":
        print(json.dumps(metrics.to_dict(), indent=2))
    else:
        print(render_dora_text(metrics))


def _handle_prompt(args) -> None:
    from ..prompt_registry import PromptRegistry

    registry = PromptRegistry()

    if args.prompt_command == "register":
        if not args.file.exists():
            from ..constants import ConductorError
            raise ConductorError(f"Prompt file not found: {args.file}")
        content = args.file.read_text()
        template = registry.register(
            name=args.name,
            content=content,
            model_compat=args.models,
            tags=args.tags or [],
            performance_notes=args.notes,
        )
        print(f"  Registered: {template.id}")
        print(f"  Version: {template.version}")
        print(f"  Models: {', '.join(template.model_compatibility)}")

    elif args.prompt_command == "list":
        fmt = getattr(args, "format", "text")
        tag = getattr(args, "tag", None)
        model = getattr(args, "model", None)
        if tag or model:
            prompts = registry.search(tag=tag, model=model)
        else:
            prompts = registry.list_prompts()
        if fmt == "json":
            print(json.dumps([p.to_dict() for p in prompts], indent=2))
        else:
            if not prompts:
                print("  No prompt templates registered.")
            else:
                print(f"  {'Name':<30} {'Version':<10} {'Models':<30} {'Tags'}")
                print("  " + "-" * 80)
                for p in prompts:
                    models = ", ".join(p.model_compatibility[:3])
                    tags = ", ".join(p.tags[:3])
                    print(f"  {p.name:<30} {p.version:<10} {models:<30} {tags}")

    elif args.prompt_command == "get":
        fmt = getattr(args, "format", "text")
        version = getattr(args, "version", None)
        template = registry.get(args.name, version=version)
        if fmt == "json":
            print(json.dumps(template.to_dict(), indent=2))
        else:
            print(f"  Name: {template.name}")
            print(f"  Version: {template.version}")
            print(f"  Models: {', '.join(template.model_compatibility)}")
            print(f"  Tags: {', '.join(template.tags)}")
            if template.performance_notes:
                print(f"  Notes: {template.performance_notes}")
            print(f"\n{template.content}")
