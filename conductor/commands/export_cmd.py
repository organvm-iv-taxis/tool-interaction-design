"""Export and patterns commands."""

from __future__ import annotations

from ..governance import GovernanceRuntime
from ..product import ProductExtractor


def handle(args, *, ontology, engine) -> None:
    if args.command == "export":
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
        elif args.export_command == "literate":
            output = pe.export_literate(args.session_id, output_path=args.output)
            print(f"  Literate export written to: {output}")

    elif args.command == "patterns":
        gov = GovernanceRuntime()
        pe = ProductExtractor(gov)
        pe.mine_patterns(export_essay=args.export_essay)
