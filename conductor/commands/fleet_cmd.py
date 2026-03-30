"""Fleet orchestration CLI commands."""

from __future__ import annotations

import json
from datetime import date

from ..constants import SessionError


def handle(args, *, ontology, engine) -> None:
    cmd = args.fleet_command
    if cmd == "status":
        _handle_status(args)
    elif cmd == "usage":
        _handle_usage(args)
    elif cmd == "recommend":
        _handle_recommend(args)
    elif cmd == "handoff":
        _handle_handoff(args)
    elif cmd == "dispatch":
        _handle_dispatch(args)
    elif cmd == "verify":
        _handle_verify(args)


def _handle_status(args) -> None:
    from ..fleet import FleetRegistry
    from ..fleet_usage import FleetUsageTracker

    registry = FleetRegistry()
    tracker = FleetUsageTracker()
    today = date.today()
    daily = tracker.daily_snapshot(today)

    print(f"\n  FLEET STATUS ({today.isoformat()})")
    print("  " + "-" * 60)
    print(f"  {'AGENT':<12} {'DISPLAY':<28} {'PROVIDER':<12} {'STATUS'}")

    for agent in registry.all_agents():
        status = "ACTIVE" if agent.active else "inactive"
        print(f"  {agent.name:<12} {agent.display_name:<28} {agent.provider:<12} {status}")

    if daily:
        print()
        print("  TODAY'S USAGE")
        print("  " + "-" * 60)
        print(f"  {'AGENT':<12} {'SESSIONS':>8} {'TOKENS':>10} {'COST':>10} {'MINUTES':>8}")
        for agent_name, data in sorted(daily.items()):
            print(
                f"  {agent_name:<12} {data['sessions']:>8} "
                f"{data['total_tokens']:>10} "
                f"${data['total_cost_usd']:>8.4f} "
                f"{data['total_minutes']:>8}"
            )

    print()


def _handle_usage(args) -> None:
    from ..fleet import FleetRegistry
    from ..fleet_usage import FleetUsageTracker

    registry = FleetRegistry()
    tracker = FleetUsageTracker()

    if hasattr(args, "month") and args.month:
        parts = args.month.split("-")
        year, month = int(parts[0]), int(parts[1])
    else:
        today = date.today()
        year, month = today.year, today.month

    report = tracker.utilization_report(year, month, registry.active_agents())

    print(f"\n  FLEET UTILIZATION ({year}-{month:02d})")
    print("  " + "-" * 60)
    print(f"  {'AGENT':<12} {'SESSIONS':>8} {'TOKENS':>10} {'COST':>10} {'UTIL':>8}")

    for agent_name, data in sorted(report.items()):
        util = f"{data.get('utilization_pct', 0):.1f}%" if "utilization_pct" in data else "N/A"
        print(
            f"  {agent_name:<12} {data['sessions']:>8} "
            f"{data['total_tokens']:>10} "
            f"${data['total_cost_usd']:>8.4f} "
            f"{util:>8}"
        )

    if not report:
        print("  No usage data for this period.")

    print()


def _handle_recommend(args) -> None:
    from ..fleet_router import FleetRouter

    router = FleetRouter()
    phase = args.phase.upper()
    tags = args.tags if hasattr(args, "tags") and args.tags else []

    sensitivity: dict[str, bool] = {}
    if hasattr(args, "secrets") and args.secrets:
        sensitivity["can_see_secrets"] = True
    if hasattr(args, "git") and args.git:
        sensitivity["can_push_git"] = True

    context_size = int(args.context_size) if hasattr(args, "context_size") and args.context_size else 0

    scores = router.recommend(
        phase=phase,
        task_tags=tags,
        sensitivity_required=sensitivity,
        context_size=context_size,
    )

    if not scores:
        print("  No suitable agents found.")
        return

    print(f"\n  FLEET RECOMMENDATION (phase={phase})")
    print("  " + "-" * 60)

    for i, score in enumerate(scores):
        marker = ">>>" if i == 0 else "   "
        print(f"  {marker} {router.explain(score)}")
        print()


def _handle_dispatch(args) -> None:
    from ..task_dispatcher import TaskDispatcher

    dispatcher = TaskDispatcher()
    phase = args.phase.upper() if hasattr(args, "phase") and args.phase else "BUILD"
    work_type = args.work_type if hasattr(args, "work_type") and args.work_type else None
    description = args.description if hasattr(args, "description") and args.description else ""

    plan = dispatcher.plan(
        description=description,
        phase=phase,
        work_type=work_type,
    )

    print(f"\n  DISPATCH PLAN")
    print("  " + "-" * 60)
    print(f"  Work type:     {plan.work_type}")
    print(f"  Cognitive:     {plan.cognitive_class}")
    print(f"  Verification:  {plan.verification_policy}")
    print()

    if plan.ranked_agents:
        print(f"  QUALIFIED AGENTS (ranked)")
        for i, score in enumerate(plan.ranked_agents):
            marker = ">>>" if i == 0 else "   "
            trust = ""
            # Show guardrail info
            from ..fleet import FleetRegistry
            reg = FleetRegistry()
            agent = reg.get(score.agent)
            if agent and not agent.guardrails.self_audit_trusted:
                trust = " [CROSS-VERIFY REQUIRED]"
            print(f"  {marker} {score.display_name} (score: {score.score:.3f}){trust}")
    else:
        print("  No agents qualify for this work type.")

    if plan.excluded_agents:
        print()
        print(f"  EXCLUDED AGENTS")
        for excl in plan.excluded_agents:
            print(f"      {excl['agent']}: {excl['reason']}")

    print()


def _handle_verify(args) -> None:
    from ..cross_verify import CrossVerifier
    from ..fleet_handoff import GuardrailedHandoffBrief

    changed_files = args.changed_files if hasattr(args, "changed_files") and args.changed_files else []
    diff = args.diff if hasattr(args, "diff") and args.diff else ""

    # Load the most recent handoff if available
    from ..constants import STATE_DIR
    import json as _json

    handoff_log = STATE_DIR / "handoff-log.jsonl"
    if not handoff_log.exists():
        print("  No handoff log found. Run 'fleet handoff' first.")
        return

    lines = handoff_log.read_text().strip().splitlines()
    if not lines:
        print("  Handoff log is empty.")
        return

    last = _json.loads(lines[-1])

    # Try to load as guardrailed, fall back to basic
    if "constraints_locked" in last:
        brief = GuardrailedHandoffBrief.from_dict(last)
    else:
        print("  Last handoff is not guardrailed. Nothing to verify.")
        return

    verifier = CrossVerifier()
    report = verifier.verify(
        handoff=brief,
        changed_files=changed_files,
        diff_content=diff,
    )

    print(f"\n  VERIFICATION REPORT")
    print("  " + "-" * 60)
    print(f"  Status: {'PASSED' if report.passed else 'FAILED'}")
    print(f"  {report.summary}")

    if report.violations:
        print()
        for v in report.violations:
            icon = "ERROR" if v.severity == "error" else "WARN"
            print(f"  [{icon}] {v.rule}: {v.detail}")

    print()


def _handle_handoff(args) -> None:
    from ..fleet_handoff import format_markdown, generate_handoff, log_handoff, write_handoff
    from ..session import SessionEngine

    engine = SessionEngine()
    session = engine._load_session()
    if not session:
        raise SessionError("No active session. Start one before generating a handoff.")

    to_agent = args.to_agent
    summary = args.summary if hasattr(args, "summary") and args.summary else f"Handoff from {session.agent} to {to_agent}"

    brief = generate_handoff(
        session=session,
        from_agent=session.agent,
        to_agent=to_agent,
        summary=summary,
    )

    # Log it
    log_handoff(brief)

    # Print the markdown
    md = format_markdown(brief)
    print(md)
