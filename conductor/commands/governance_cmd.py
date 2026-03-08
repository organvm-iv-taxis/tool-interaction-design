"""Governance, WIP, enforce, stale, and audit commands."""

from __future__ import annotations

import json

from ..constants import ConductorError, resolve_organ_key
from ..governance import GovernanceRuntime


def handle(args, *, ontology, engine) -> None:
    if args.command == "registry":
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
        elif args.enforce_command == "github-rulesets":
            rulesets = gov.generate_github_rulesets()
            print(f"  Generated {len(rulesets)} GitHub rulesets.")
            for org_name in rulesets:
                print(f"    - {org_name}")
            print(f"  Output: generated/github-rulesets/")

    elif args.command == "stale":
        gov = GovernanceRuntime()
        gov.stale(days=args.days)

    elif args.command == "audit":
        gov = GovernanceRuntime()
        if args.format == "json":
            print(json.dumps(gov.audit_report(organ=args.organ), indent=2))
        else:
            gov.audit(organ=args.organ, create_issues=args.create_issues)
