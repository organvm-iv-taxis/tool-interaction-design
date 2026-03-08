"""Risk register CLI commands."""

from __future__ import annotations

import json


def handle(args, *, ontology, engine) -> None:
    from ..risk_register import RiskRegistry

    registry = RiskRegistry()

    if args.risk_command == "add":
        risk = registry.add(
            description=args.description,
            probability=args.probability,
            impact=args.impact,
            mitigation=args.mitigation,
            owner=args.owner,
        )
        print(f"  Risk added: {risk.id}")
        print(f"  Description: {risk.description}")
        print(f"  Severity: {risk.probability} x {risk.impact} = {risk.severity_score}")

    elif args.risk_command == "list":
        risks = registry.list_risks(status=getattr(args, "status", None))
        fmt = getattr(args, "format", "text")

        if fmt == "json":
            print(json.dumps([r.to_dict() for r in risks], indent=2))
        elif fmt == "markdown":
            print(registry.to_markdown())
        else:
            if not risks:
                print("  No risks found.")
                return
            print(f"\n  Risk Register ({len(risks)} risks)")
            print("  " + "=" * 60)
            for r in risks:
                print(f"  [{r.id}] {r.description}")
                print(f"    P={r.probability} I={r.impact} Score={r.severity_score} Status={r.status} Owner={r.owner}")
                print(f"    Mitigation: {r.mitigation}")
                print()

    elif args.risk_command == "resolve":
        if registry.resolve(args.risk_id):
            print(f"  Resolved: {args.risk_id}")
        else:
            print(f"  FAILED: Risk '{args.risk_id}' not found.")
