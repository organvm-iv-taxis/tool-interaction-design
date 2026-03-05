"""CLI parser and dispatch for conductor."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .constants import ONTOLOGY_PATH, ROUTING_PATH, WORKFLOW_DSL_PATH, ConductorError, resolve_organ_key
from .doctor import assert_doctor_ok, render_doctor_text, run_doctor
from .governance import GovernanceRuntime
from .handoff import edge_health_report, get_trace_bundle, simulate_route_handoff, validate_handoff_payload
from .migrate import migrate_governance, migrate_registry, write_migration_output
from .observability import export_metrics_report
from .patchbay import Patchbay
from .plugins import plugin_doctor_report, render_plugin_doctor_text
from .policy import render_policy_simulation_text, simulate_policy
from .product import ProductExtractor
from .session import SessionEngine

try:
    _router_dir = str(Path(__file__).parent.parent)
    if _router_dir not in sys.path:
        sys.path.insert(0, _router_dir)
    from router import Ontology, RoutingEngine
except ImportError:
    Ontology = None  # type: ignore[assignment,misc]
    RoutingEngine = None  # type: ignore[assignment,misc]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="conductor",
        description="The AI-Conductor's Operating System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # ----- Session commands -----
    p_session = sub.add_parser("session", help="Session lifecycle management")
    session_sub = p_session.add_subparsers(dest="session_command", required=True)

    p_start = session_sub.add_parser("start", help="Start a new session")
    p_start.add_argument("--organ", required=True, help="Organ key (e.g., III, META)")
    p_start.add_argument("--repo", required=True, help="Repository name")
    p_start.add_argument("--scope", required=True, help="Session scope description")
    p_start.add_argument("--no-branch", action="store_true", help="Skip git branch creation")

    p_phase = session_sub.add_parser("phase", help="Transition to next phase")
    p_phase.add_argument("target", help="Target phase (shape, build, prove, done)")

    session_sub.add_parser("status", help="Show current session status")
    session_sub.add_parser("close", help="Close session and generate log")

    p_log_tool = session_sub.add_parser("log-tool", help="Record a tool use")
    p_log_tool.add_argument("tool_name", help="Name of the tool used")

    # ----- Governance commands -----
    p_registry = sub.add_parser("registry", help="Registry operations")
    registry_sub = p_registry.add_subparsers(dest="registry_command", required=True)
    p_sync = registry_sub.add_parser("sync", help="Sync registry with GitHub")
    p_sync.add_argument("--fix", action="store_true", help="Auto-add missing repos")
    p_sync.add_argument("--dry-run", action="store_true", help="Show what --fix would do without writing")

    p_wip = sub.add_parser("wip", help="WIP limit management")
    wip_sub = p_wip.add_subparsers(dest="wip_command", required=True)
    wip_sub.add_parser("check", help="Show WIP status")
    p_promote = wip_sub.add_parser("promote", help="Promote repo with WIP enforcement")
    p_promote.add_argument("repo", help="Repository name")
    p_promote.add_argument("state", help="Target state (CANDIDATE, PUBLIC_PROCESS, etc.)")
    p_promote.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    p_auto_promote = wip_sub.add_parser("auto-promote", help="Auto-promote healthy repos while respecting WIP limits")
    p_auto_promote.add_argument(
        "--apply",
        action="store_true",
        help="Apply promotions (default is dry-run preview)",
    )
    p_auto_promote.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_enforce = sub.add_parser("enforce", help="Generate enforcement artifacts")
    enforce_sub = p_enforce.add_subparsers(dest="enforce_command", required=True)
    p_gen = enforce_sub.add_parser("generate", help="Generate rulesets and workflows")
    p_gen.add_argument("--dry-run", action="store_true", help="Show what would be generated")

    p_stale = sub.add_parser("stale", help="Find stale CANDIDATE repos")
    p_stale.add_argument("--days", type=int, default=30, help="Days threshold (default: 30)")

    p_audit = sub.add_parser("audit", help="Organ health audit")
    p_audit.add_argument("--organ", help="Organ key (default: full system)")
    p_audit.add_argument("--create-issues", action="store_true", help="File GitHub issues for findings")
    p_audit.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    # ----- Work Registry commands -----
    p_queue = sub.add_parser("queue", help="Work item registry management")
    queue_sub = p_queue.add_subparsers(dest="queue_command", required=True)
    p_q_claim = queue_sub.add_parser("claim", help="Claim a work item")
    p_q_claim.add_argument("item_id", help="Item ID to claim")
    p_q_claim.add_argument("--owner", help="Optional owner name (defaults to 'agent')")
    
    p_q_yield = queue_sub.add_parser("yield", help="Yield a claimed work item")
    p_q_yield.add_argument("item_id", help="Item ID to yield")
    
    p_q_resolve = queue_sub.add_parser("resolve", help="Mark a work item as resolved")
    p_q_resolve.add_argument("item_id", help="Item ID to resolve")

    p_auto = sub.add_parser("auto", help="Autonomous worker daemon")
    p_auto.add_argument("--daemon", action="store_true", help="Run in continuous loop")
    p_auto.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    p_auto.add_argument("--limit", type=int, default=1, help="Max tasks to perform")

    # ----- Product commands -----
    p_export = sub.add_parser("export", help="Export artifacts")
    export_sub = p_export.add_subparsers(dest="export_command", required=True)
    p_kit = export_sub.add_parser("process-kit", help="Export process kit")
    p_kit.add_argument("--output", type=Path, help="Output directory")
    p_kit.add_argument("--force", action="store_true", help="Overwrite existing output")
    p_ext = export_sub.add_parser("gemini-extension", help="Export Conductor OS as a Gemini CLI extension")
    p_ext.add_argument("--output", type=Path, help="Output directory")
    p_ext.add_argument("--force", action="store_true", help="Overwrite existing output")
    p_fleet = export_sub.add_parser("fleet-dashboard", help="Export HTML Fleet Admiral Dashboard")
    p_fleet.add_argument("--output", type=Path, help="Output directory")
    p_report = export_sub.add_parser("audit-report", help="Export audit report")
    p_report.add_argument("--organ", help="Organ key (default: full system)")

    p_patterns = sub.add_parser("patterns", help="Mine session logs for patterns")
    p_patterns.add_argument("--export-essay", action="store_true", help="Export pattern essay draft")

    # ----- Router commands (inherited) -----
    p_route = sub.add_parser("route", help="Find routes between clusters")
    route_sub = p_route.add_subparsers(dest="route_command")
    p_route.add_argument("--from", dest="from_cluster")
    p_route.add_argument("--to", dest="to_cluster")
    p_route_sim = route_sub.add_parser("simulate", help="Simulate a routed handoff with repair/fallback behavior")
    p_route_sim.add_argument("--from", dest="from_cluster", required=True)
    p_route_sim.add_argument("--to", dest="to_cluster", required=True)
    p_route_sim.add_argument("--objective", required=True, help="Objective for the simulated handoff")
    p_route_sim.add_argument("--deadline-ms", type=int, default=5000, help="Deadline budget for simulation")
    p_route_sim.add_argument("--priority", choices=["low", "medium", "high", "critical"], default="high")
    p_route_sim.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_cap = sub.add_parser("capability", help="Find clusters by capability")
    p_cap.add_argument("cap", type=str)

    p_validate = sub.add_parser("validate", help="Validate a workflow DSL file")
    p_validate.add_argument("file", type=str)
    p_validate.add_argument("--strict", action="store_true", help="Treat warnings as validation failures")
    p_validate.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_compose = sub.add_parser("compose", help="Synthesize a JIT workflow mission")
    p_compose.add_argument("--goal", required=True, help="High-level goal description")
    p_compose.add_argument("--from", dest="from_cluster", required=True, help="Starting tool cluster")
    p_compose.add_argument("--to", dest="to_cluster", required=True, help="Target tool cluster")
    p_compose.add_argument("--session-id", help="Optional session ID")
    p_compose.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_workflow = sub.add_parser("workflow", help="Workflow DSL runtime commands")
    workflow_sub = p_workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_sub.add_parser("list", help="List available workflow names")
    p_workflow_start = workflow_sub.add_parser("start", help="Start workflow execution state")
    p_workflow_start.add_argument("--name", required=True, help="Workflow name from workflow-dsl.yaml")
    p_workflow_start.add_argument("--session-id", help="Optional session id (default: active session or generated)")
    p_workflow_start.add_argument("--input-json", help="Optional JSON payload for workflow input")
    p_workflow_start.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_workflow_status = workflow_sub.add_parser("status", help="Show workflow execution status")
    p_workflow_status.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_workflow_step = workflow_sub.add_parser("step", help="Execute one workflow step")
    p_workflow_step.add_argument("--name", required=True, help="Step name to execute")
    p_workflow_step.add_argument("--output-json", help="Optional JSON payload for step output")
    p_workflow_step.add_argument(
        "--checkpoint-action",
        choices=["approve", "modify", "abort"],
        help="Checkpoint decision when the step is gated",
    )
    p_workflow_step.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    workflow_sub.add_parser("clear", help="Clear persisted workflow execution state")

    p_doctor = sub.add_parser("doctor", help="Run conductor integrity diagnostics")
    p_doctor.add_argument("--workflow", type=Path, default=Path("workflow-dsl.yaml"), help="Workflow file to validate")
    p_doctor.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_doctor.add_argument("--strict", action="store_true", help="Exit non-zero on any failing check")
    p_doctor.add_argument("--apply", action="store_true", help="Apply available schema autofixes before reporting")

    p_plugins = sub.add_parser("plugins", help="Plugin diagnostics")
    plugin_sub = p_plugins.add_subparsers(dest="plugins_command", required=True)
    p_plugins_doctor = plugin_sub.add_parser("doctor", help="Validate plugin manifests and provider loading")
    p_plugins_doctor.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_plugins_doctor.add_argument("--strict", action="store_true", help="Fail on warnings in addition to errors")

    p_policy = sub.add_parser("policy", help="Policy analysis commands")
    policy_sub = p_policy.add_subparsers(dest="policy_command", required=True)
    p_policy_simulate = policy_sub.add_parser("simulate", help="Simulate policy limits against registry state")
    p_policy_simulate.add_argument("--bundle", help="Policy bundle name to simulate (default resolves from env/config)")
    p_policy_simulate.add_argument("--organ", help="Optional organ filter (e.g., III, META)")
    p_policy_simulate.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_obs = sub.add_parser("observability", help="Observability exports and trend checks")
    obs_sub = p_obs.add_subparsers(dest="observability_command", required=True)
    p_obs_report = obs_sub.add_parser("report", help="Export observability metrics with trend checks")
    p_obs_report.add_argument("--output", type=Path, help="Optional output path for JSON report")
    p_obs_report.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_obs_report.add_argument("--check", action="store_true", help="Exit non-zero when trend status is warn/critical")

    p_handoff = sub.add_parser("handoff", help="Canonical handoff envelope commands")
    handoff_sub = p_handoff.add_subparsers(dest="handoff_command", required=True)
    p_handoff_validate = handoff_sub.add_parser("validate", help="Validate a handoff payload file")
    p_handoff_validate.add_argument("--input", type=Path, required=True, help="Path to JSON or YAML payload file")
    p_handoff_validate.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_edge = sub.add_parser("edge", help="Edge telemetry and trace inspection")
    edge_sub = p_edge.add_subparsers(dest="edge_command", required=True)
    p_edge_health = edge_sub.add_parser("health", help="Compute edge health metrics from trace logs")
    p_edge_health.add_argument("--window", type=int, default=200, help="Window size (last N traces)")
    p_edge_health.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_edge_trace = edge_sub.add_parser("trace", help="Fetch a trace bundle by trace_id")
    p_edge_trace.add_argument("--trace-id", required=True, help="Trace identifier")
    p_edge_trace.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_migrate = sub.add_parser("migrate", help="Migrate registry/governance to current schema")
    migrate_sub = p_migrate.add_subparsers(dest="migrate_command", required=True)
    p_mig_registry = migrate_sub.add_parser("registry", help="Migrate registry JSON")
    p_mig_registry.add_argument("--input", type=Path, default=None, help="Input registry path")
    p_mig_registry.add_argument("--output", type=Path, default=None, help="Output path (defaults to input path)")
    p_mig_registry.add_argument("--in-place", action="store_true", help="Write migration output over input file")
    p_mig_governance = migrate_sub.add_parser("governance", help="Migrate governance JSON")
    p_mig_governance.add_argument("--input", type=Path, default=None, help="Input governance path")
    p_mig_governance.add_argument("--output", type=Path, default=None, help="Output path (defaults to input path)")
    p_mig_governance.add_argument("--in-place", action="store_true", help="Write migration output over input file")

    # ----- Patchbay command -----
    p_patch = sub.add_parser("patch", help="Patchbay — command center briefing")
    p_patch.add_argument("section", nargs="?", choices=["pulse", "queue", "stats"],
                         help="Show only one section (default: full briefing)")
    p_patch.add_argument("--json", action="store_true", dest="json_output",
                         help="Machine-readable JSON output")
    p_patch.add_argument("--organ", help="Filter to one organ (e.g., III, META)")
    p_patch.add_argument("--watch", action="store_true", help="Real-time watch mode (updates every 5s)")

    p_graph = sub.add_parser("graph", help="Generate Galactic Registry Graph (Mermaid.js)")
    p_graph.add_argument("--live", action="store_true", help="Watch mode for live terminal updates")
    p_graph.add_argument("--output", type=Path, help="Write output to file")

    sub.add_parser("clusters", help="List all clusters")
    sub.add_parser("domains", help="List all domains")
    sub.add_parser("version", help="Show conductor version")

    return parser


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
    # Load ontology for session and router commands
    ontology = None
    engine = None
    if Ontology and ONTOLOGY_PATH.exists():
        ontology = Ontology(ONTOLOGY_PATH)
    if RoutingEngine and ontology and ROUTING_PATH.exists():
        engine = RoutingEngine(ROUTING_PATH, ontology)

    # Dispatch
    if args.command == "session":
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

    elif args.command == "registry":
        gov = GovernanceRuntime()
        if args.registry_command == "sync":
            gov.registry_sync(fix=args.fix, dry_run=args.dry_run)

    elif args.command == "wip":
        from .governance import GovernanceRuntime
        confirm_fn = (lambda _: True) if getattr(args, "yes", False) else None
        gov = GovernanceRuntime(confirm_fn=confirm_fn)
        if args.wip_command == "check":
            gov.wip_check()
        elif args.wip_command == "promote":
            gov.wip_promote(args.repo, args.state)
        elif args.wip_command == "auto-promote":
            report = gov.auto_promote(dry_run=not args.apply)
            if args.format == "json":
                print(json.dumps(report, indent=2))
            else:
                summary = report.get("summary", {})
                print("Auto-promotion report")
                print(
                    f"  dry_run={summary.get('dry_run')} "
                    f"eligible={summary.get('eligible')} "
                    f"promoted={summary.get('promoted')} "
                    f"policy_bundle={summary.get('policy_bundle')}"
                )
                rows = report.get("promoted") if args.apply else report.get("proposed")
                label = "promoted" if args.apply else "proposed"
                for row in rows or []:
                    print(
                        f"  {label}: [{row.get('organ')}] {row.get('repo')} "
                        f"{row.get('current')} -> {row.get('target')}"
                    )

    elif args.command == "enforce":
        gov = GovernanceRuntime()
        if args.enforce_command == "generate":
            gov.enforce_generate(dry_run=args.dry_run)

    elif args.command == "stale":
        gov = GovernanceRuntime()
        gov.stale(days=args.days)

    elif args.command == "audit":
        gov = GovernanceRuntime()
        if args.format == "json":
            print(json.dumps(gov.audit_report(organ=args.organ), indent=2))
        else:
            gov.audit(organ=args.organ, create_issues=args.create_issues)

    elif args.command == "queue":
        from .work_item import WorkRegistry
        wr = WorkRegistry()
        if args.queue_command == "claim":
            owner = args.owner or "agent"
            if wr.claim(args.item_id, owner):
                print(f"  Claimed: {args.item_id} by {owner}")
            else:
                print(f"  FAILED to claim: {args.item_id} (not found or already claimed)")
        elif args.queue_command == "yield":
            if wr.yield_item(args.item_id):
                print(f"  Yielded: {args.item_id}")
            else:
                print(f"  FAILED to yield: {args.item_id}")
        elif args.queue_command == "resolve":
            if wr.resolve(args.item_id):
                print(f"  Resolved: {args.item_id}")
            else:
                print(f"  FAILED to resolve: {args.item_id}")

    elif args.command == "auto":
        from .work_item import WorkRegistry
        from .patchbay import Patchbay
        
        def _run_once():
            pb = Patchbay(ontology=ontology, engine=SessionEngine(ontology))
            # briefing() calls sync() internally
            data = pb.briefing()
            items = data.get("queue", {}).get("items", [])
            open_items = [i for i in items if i["status"] == "OPEN"]
            
            if not open_items:
                print("  No open tasks found.")
                return False
            
            top = open_items[0]
            print(f"  Autonomous worker picking top task: {top['id']} - {top['description']}")
            
            # 1. Claim
            wr = pb.wr
            if not wr.claim(top["id"], owner="conductor-auto"):
                print(f"  FAILED to claim task {top['id']}")
                return False
            
            print(f"  Task claimed. Spawning session for {top['repo'] or top['organ']}...")
            
            # 2. Execution Skeleton (Epoch II.2)
            # In a real run, we'd call se.start() and then execute a workflow
            # For the first pass, we just simulate the 'intent'
            print(f"  [EXECUTION] Would run: {top['suggested_command']}")
            
            # 3. Resolve (for now, immediately auto-resolving to demonstrate the loop)
            # In the final implementation, this only happens after 'PROVE' phase
            wr.resolve(top["id"])
            print(f"  Task resolved.")
            return True

        if getattr(args, "daemon", False):
            import time
            tasks_done = 0
            try:
                while tasks_done < args.limit:
                    if _run_once():
                        tasks_done += 1
                    if tasks_done >= args.limit:
                        break
                    print(f"  Waiting {args.interval}s for next check...")
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\n  Daemon stopped.")
        else:
            _run_once()

    elif args.command == "export":
        from .governance import GovernanceRuntime
        gov = GovernanceRuntime()
        pe = ProductExtractor(gov)
        if args.export_command == "process-kit":
            pe.export_process_kit(output_dir=args.output, force=args.force)
        elif args.export_command == "gemini-extension":
            pe.export_gemini_extension(output_dir=args.output, force=args.force)
        elif args.export_command == "fleet-dashboard":
            pe.export_fleet_dashboard(output_dir=args.output)
        elif args.export_command == "audit-report":
            pe.export_audit_report(organ=args.organ)

    elif args.command == "patterns":
        gov = GovernanceRuntime()
        pe = ProductExtractor(gov)
        pe.mine_patterns(export_essay=args.export_essay)

    elif args.command == "patch":
        from .patchbay import Patchbay
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
            import time
            try:
                while True:
                    # Use escape codes to clear screen and move cursor to top-left
                    sys.stdout.write("\033[2J\033[H")
                    print(_do_briefing())
                    print("\n  [Watching... Press Ctrl+C to exit]")
                    time.sleep(5)
            except KeyboardInterrupt:
                print("\n  Watch mode exited.")
        else:
            print(_do_briefing())

    elif args.command == "graph":
        from .graph import RegistryGraph
        from .governance import GovernanceRuntime
        gov = GovernanceRuntime()
        rg = RegistryGraph(gov)
        
        def _do_graph():
            gov._load()  # Refresh data
            return rg.generate_mermaid()
            
        if args.output:
            args.output.write_text(_do_graph())
            print(f"  Graph written to: {args.output}")
        elif args.live:
            import time
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

    elif args.command == "route":
        if not engine:
            print("  ERROR: Ontology/routing files not found.", file=sys.stderr)
            sys.exit(1)
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

    elif args.command == "capability":
        if not engine:
            print("  ERROR: Ontology/routing files not found.", file=sys.stderr)
            sys.exit(1)
        from router import cmd_capability
        args.capability = args.cap
        cmd_capability(args, ontology, engine)

    elif args.command == "validate":
        if not engine:
            print("  ERROR: Ontology/routing files not found.", file=sys.stderr)
            sys.exit(1)
        from router import cmd_validate
        cmd_validate(args, ontology, engine)

    elif args.command == "compose":
        if not engine or not ontology:
            print("  ERROR: Ontology/routing files not found.", file=sys.stderr)
            sys.exit(1)
        from .compiler import WorkflowCompiler
        compiler = WorkflowCompiler(engine, ontology)
        
        session_id = args.session_id
        if not session_id:
            try:
                active = SessionEngine(ontology)._load_session()
                session_id = active.session_id if active else "adhoc-compose"
            except Exception:
                session_id = "adhoc-compose"

        state = compiler.compile_mission(
            goal=args.goal,
            start_cluster=args.from_cluster,
            end_cluster=args.to_cluster,
            session_id=session_id
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

    elif args.command == "workflow":
        from .executor import WorkflowExecutor

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
                except Exception:
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
        elif args.workflow_command == "clear":
            executor.clear_state()
            print("Cleared workflow execution state.")

    elif args.command == "doctor":
        report = run_doctor(workflow_path=args.workflow, format_name=args.format, apply=args.apply)
        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            print(render_doctor_text(report))
        if args.strict:
            assert_doctor_ok(report)

    elif args.command == "plugins":
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

    elif args.command == "policy":
        from .governance import GovernanceRuntime
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
                    "organs_with_violations": sum(1 for row in filtered.values() if row.get("violations", 0) > 0),
                    "violations_total": sum(int(row.get("violations", 0)) for row in filtered.values()),
                }
            if args.format == "json":
                print(json.dumps(report, indent=2))
            else:
                print(render_policy_simulation_text(report))

    elif args.command == "observability":
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
                output_path = args.output or Path(".conductor-observability-report.json")
                print(f"  report_path={output_path}")
            if args.check and report.get("trends", {}).get("status") in {"warn", "critical"}:
                raise ConductorError("Observability trend check failed threshold.")

    elif args.command == "handoff":
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

    elif args.command == "edge":
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

    elif args.command == "migrate":
        if args.migrate_command == "registry":
            from .constants import REGISTRY_PATH
            input_path = args.input or REGISTRY_PATH
            output_path = input_path if args.in_place or args.output is None else args.output
            payload = migrate_registry(input_path)
            write_migration_output(payload, output_path)
            print(f"  Migrated registry -> {output_path}")
        elif args.migrate_command == "governance":
            from .constants import GOVERNANCE_PATH
            input_path = args.input or GOVERNANCE_PATH
            output_path = input_path if args.in_place or args.output is None else args.output
            payload = migrate_governance(input_path)
            write_migration_output(payload, output_path)
            print(f"  Migrated governance -> {output_path}")

    elif args.command == "clusters":
        if not engine:
            print("  ERROR: Ontology/routing files not found.", file=sys.stderr)
            sys.exit(1)
        from router import cmd_clusters
        cmd_clusters(args, ontology, engine)

    elif args.command == "domains":
        if not engine:
            print("  ERROR: Ontology/routing files not found.", file=sys.stderr)
            sys.exit(1)
        from router import cmd_domains
        cmd_domains(args, ontology, engine)

    elif args.command == "version":
        from conductor import __version__
        print(f"  conductor {__version__}")
