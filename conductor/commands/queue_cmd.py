"""Queue and auto (autonomous worker) commands."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone


def handle(args, *, ontology, engine) -> None:
    if args.command == "queue":
        _handle_queue(args)
    elif args.command == "auto":
        _handle_auto(args, ontology=ontology)


def _handle_queue(args) -> None:
    from ..work_item import WorkRegistry

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
    elif args.queue_command == "push":
        from ..governance import GovernanceRuntime
        gov = GovernanceRuntime()
        dry_run = not getattr(args, "apply", False)
        max_items = getattr(args, "max_items", 5)
        results = gov.push_queue_to_github(max_items=max_items, dry_run=dry_run)
        label = "Would create" if dry_run else "Created"
        print(f"\n  Queue Push {'(DRY RUN)' if dry_run else ''}")
        print("  " + "=" * 50)
        for r in results:
            status = "created" if r.get("created") else ("dry-run" if dry_run else "FAILED")
            print(f"  [{status}] {r['title'][:60]}")
            if r.get("url"):
                print(f"    -> {r['url']}")
            if r.get("error"):
                print(f"    ERROR: {r['error']}")
        print(f"\n  {label}: {len(results)} issues")
        print()


def _handle_auto(args, *, ontology) -> None:
    from ..compiler import WorkflowCompiler
    from ..patchbay import Patchbay
    from ..session import SessionEngine

    def _run_once():
        pb = Patchbay(ontology=ontology, engine=SessionEngine(ontology))
        data = pb.briefing()
        items = data.get("queue", {}).get("items", [])
        open_items = [i for i in items if i["status"] == "OPEN"]

        if not open_items:
            print("  No open tasks found.")
            return False

        top = open_items[0]
        print(f"  [SINGULARITY] Autonomous worker picking top task: {top['id']} - {top['description']}")

        # 1. Claim
        wr = pb.wr
        if not wr.claim(top["id"], owner="conductor-auto"):
            print(f"  FAILED to claim task {top['id']}")
            return False

        # 2. JIT Compile the mission for this task
        compiler = WorkflowCompiler(engine, ontology)
        from_cluster = "code_analysis_mcp"
        to_cluster = "github_platform"
        if top["category"] == "stale":
            from_cluster = "git_core"

        try:
            state = compiler.compile_mission(
                goal=top["description"],
                start_cluster=from_cluster,
                end_cluster=to_cluster,
                session_id=f"auto-{top['id']}",
            )
            objective = compiler.get_swarm_objective(top["description"], state)
            print(f"  Mission Compiled: {state.workflow_name}")
            print(f"  [HARDENED: {state.metadata.get('hardened')}] Health: {state.metadata.get('shadow_trace_health'):.2f}")
        except Exception as e:
            print(f"  FAILED to compile mission: {e}")
            wr.yield_item(top["id"])
            return False

        # 3. SWARM EXECUTION TRIGGER
        print(f"  [EXECUTION] Spawning autonomous swarm for mission: {state.workflow_name}...")

        gemini_cmd = ["gemini", "--non-interactive", objective]

        try:
            result = subprocess.run(gemini_cmd, capture_output=True, text=True, timeout=600)

            if result.returncode == 0:
                print("  Swarm completed successfully.")
                wr.resolve(top["id"])
                print(f"  Task {top['id']} marked as RESOLVED.")
                return True
            else:
                print(f"  Swarm execution FAILED (RC={result.returncode})")
                print(f"  Error: {result.stderr.strip()[:200]}...")
                wr.yield_item(top["id"])
                return False
        except Exception as e:
            print(f"  Execution exception: {e}")
            wr.yield_item(top["id"])
            return False

    if getattr(args, "daemon", False):
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
