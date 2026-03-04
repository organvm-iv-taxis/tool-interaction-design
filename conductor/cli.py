"""CLI parser and dispatch for conductor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .constants import ONTOLOGY_PATH, ROUTING_PATH, ConductorError, resolve_organ_key
from .governance import GovernanceRuntime
from .patchbay import Patchbay
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

    p_enforce = sub.add_parser("enforce", help="Generate enforcement artifacts")
    enforce_sub = p_enforce.add_subparsers(dest="enforce_command", required=True)
    p_gen = enforce_sub.add_parser("generate", help="Generate rulesets and workflows")
    p_gen.add_argument("--dry-run", action="store_true", help="Show what would be generated")

    p_stale = sub.add_parser("stale", help="Find stale CANDIDATE repos")
    p_stale.add_argument("--days", type=int, default=30, help="Days threshold (default: 30)")

    p_audit = sub.add_parser("audit", help="Organ health audit")
    p_audit.add_argument("--organ", help="Organ key (default: full system)")
    p_audit.add_argument("--create-issues", action="store_true", help="File GitHub issues for findings")

    # ----- Product commands -----
    p_export = sub.add_parser("export", help="Export artifacts")
    export_sub = p_export.add_subparsers(dest="export_command", required=True)
    p_kit = export_sub.add_parser("process-kit", help="Export process kit")
    p_kit.add_argument("--output", type=Path, help="Output directory")
    p_kit.add_argument("--force", action="store_true", help="Overwrite existing output")
    p_report = export_sub.add_parser("audit-report", help="Export audit report")
    p_report.add_argument("--organ", help="Organ key (default: full system)")

    p_patterns = sub.add_parser("patterns", help="Mine session logs for patterns")
    p_patterns.add_argument("--export-essay", action="store_true", help="Export pattern essay draft")

    # ----- Router commands (inherited) -----
    p_route = sub.add_parser("route", help="Find routes between clusters")
    p_route.add_argument("--from", dest="from_cluster", required=True)
    p_route.add_argument("--to", dest="to_cluster", required=True)

    p_cap = sub.add_parser("capability", help="Find clusters by capability")
    p_cap.add_argument("cap", type=str)

    # ----- Patchbay command -----
    p_patch = sub.add_parser("patch", help="Patchbay — command center briefing")
    p_patch.add_argument("section", nargs="?", choices=["pulse", "queue", "stats"],
                         help="Show only one section (default: full briefing)")
    p_patch.add_argument("--json", action="store_true", dest="json_output",
                         help="Machine-readable JSON output")
    p_patch.add_argument("--organ", help="Filter to one organ (e.g., III, META)")

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
        confirm_fn = (lambda _: True) if getattr(args, "yes", False) else None
        gov = GovernanceRuntime(confirm_fn=confirm_fn)
        if args.wip_command == "check":
            gov.wip_check()
        elif args.wip_command == "promote":
            gov.wip_promote(args.repo, args.state)

    elif args.command == "enforce":
        gov = GovernanceRuntime()
        if args.enforce_command == "generate":
            gov.enforce_generate(dry_run=args.dry_run)

    elif args.command == "stale":
        gov = GovernanceRuntime()
        gov.stale(days=args.days)

    elif args.command == "audit":
        gov = GovernanceRuntime()
        gov.audit(organ=args.organ, create_issues=args.create_issues)

    elif args.command == "export":
        gov = GovernanceRuntime()
        pe = ProductExtractor(gov)
        if args.export_command == "process-kit":
            pe.export_process_kit(output_dir=args.output, force=args.force)
        elif args.export_command == "audit-report":
            pe.export_audit_report(organ=args.organ)

    elif args.command == "patterns":
        gov = GovernanceRuntime()
        pe = ProductExtractor(gov)
        pe.mine_patterns(export_essay=args.export_essay)

    elif args.command == "patch":
        organ_filter = resolve_organ_key(args.organ) if args.organ else None
        try:
            pb = Patchbay(ontology=ontology, engine=SessionEngine(ontology))
        except Exception as e:
            print(f"  ERROR: Patchbay initialization failed: {e}", file=sys.stderr)
            sys.exit(1)
        data = pb.briefing(organ_filter=organ_filter)

        # Filter to one section if requested
        if args.section:
            data = {
                "timestamp": data["timestamp"],
                args.section: data.get(args.section, {}),
            }

        if args.json_output:
            print(pb.format_json(data))
        elif args.section:
            print(pb.format_section_text(data))
        else:
            print(pb.format_text(data))

    elif args.command == "route":
        if not engine:
            print("  ERROR: Ontology/routing files not found.", file=sys.stderr)
            sys.exit(1)
        from router import cmd_route
        cmd_route(args, ontology, engine)

    elif args.command == "capability":
        if not engine:
            print("  ERROR: Ontology/routing files not found.", file=sys.stderr)
            sys.exit(1)
        from router import cmd_capability
        args.capability = args.cap
        cmd_capability(args, ontology, engine)

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
