"""Preflight — auto-start sessions, infer context, and build runway briefings."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .constants import (
    ACTIVE_SESSIONS_DIR,
    WORKSPACE,
    SessionError,
    infer_organ_repo,
    organ_short,
    resolve_organ_key,
)
from .session import SessionEngine


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ActiveAgent:
    """Summary of an active agent session."""

    agent: str
    organ: str
    repo: str
    phase: str
    duration_minutes: int
    session_id: str


@dataclass
class WorkItemSummary:
    """Condensed work queue item for the runway briefing."""

    priority: str
    organ: str
    description: str


@dataclass
class PreflightResult:
    """Full preflight result — runway briefing + session auto-start outcome."""

    # Context inference
    inferred_organ: str | None = None
    inferred_repo: str | None = None

    # Active sessions
    active_agents: list[ActiveAgent] = field(default_factory=list)
    collisions: list[str] = field(default_factory=list)

    # Runway items
    work_items: list[WorkItemSummary] = field(default_factory=list)
    oracle_message: str | None = None
    fleet_recommendation: str | None = None
    fleet_score: float = 0.0

    # Auto-start result
    session_started: bool = False
    session_id: str | None = None
    session_phase: str | None = None
    error: str | None = None

    # Dispatch guidance
    dispatch_work_type: str | None = None
    dispatch_recommended_agent: str | None = None
    dispatch_guidance: str | None = None

    # Pending verification
    pending_verification: bool = False
    pending_handoff_from: str | None = None
    pending_handoff_to: str | None = None
    pending_handoff_work_type: str | None = None

    # Gate warnings
    gate_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Core preflight logic
# ---------------------------------------------------------------------------


def _collect_active_sessions(engine: SessionEngine) -> list[ActiveAgent]:
    """Gather all active Conductor sessions."""
    agents: list[ActiveAgent] = []
    for s in engine.active_sessions():
        agents.append(ActiveAgent(
            agent=s.agent,
            organ=organ_short(s.organ),
            repo=s.repo,
            phase=s.current_phase,
            duration_minutes=s.duration_minutes,
            session_id=s.session_id,
        ))
    return agents


def _collect_claims() -> list[ActiveAgent]:
    """Read organvm-engine coordination claims (if available)."""
    claims_path = Path.home() / ".organvm" / "claims.jsonl"
    if not claims_path.exists():
        return []

    agents: list[ActiveAgent] = []
    now = time.time()
    try:
        lines = claims_path.read_text().strip().splitlines()
        active_claims: dict[str, dict] = {}
        for line in lines[-50:]:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            handle = entry.get("agent_handle", "")
            action = entry.get("action", "")
            ts = entry.get("timestamp", 0)
            if isinstance(ts, str):
                continue
            if now - ts > 7200:
                continue
            if action == "punch_in":
                active_claims[handle] = entry
            elif action == "punch_out" and handle in active_claims:
                del active_claims[handle]

        for handle, claim in active_claims.items():
            agents.append(ActiveAgent(
                agent=handle,
                organ=claim.get("organ", "?"),
                repo=claim.get("repo", "?"),
                phase="CLAIMED",
                duration_minutes=int((now - claim.get("timestamp", now)) / 60),
                session_id=claim.get("session_id", ""),
            ))
    except OSError:
        pass
    return agents


def _detect_collisions(
    active: list[ActiveAgent],
    organ: str | None,
    repo: str | None,
) -> list[str]:
    """Identify agents working in the same repo."""
    if not organ or not repo:
        return []
    collisions = []
    for a in active:
        if a.organ == organ and a.repo == repo:
            collisions.append(
                f"{a.agent} is already in {a.organ}/{a.repo} ({a.phase}, {a.duration_minutes}min)"
            )
    return collisions


def _build_work_items(organ_filter: str | None, max_items: int = 5) -> list[WorkItemSummary]:
    """Top work queue items from registry state."""
    try:
        from .governance import GovernanceRuntime
        from .workqueue import WorkQueue

        gov = GovernanceRuntime()
        registry_key = resolve_organ_key(organ_filter) if organ_filter else None
        wq = WorkQueue(gov)
        items = wq.compute(organ_filter=registry_key)
        return [
            WorkItemSummary(
                priority=item.priority,
                organ=organ_short(item.organ),
                description=item.description,
            )
            for item in items[:max_items]
        ]
    except Exception:
        return []


def _get_oracle_advisory(organ: str | None, repo: str | None) -> str | None:
    """Get a single contextual advisory from Guardian Angel."""
    try:
        from .guardian import GuardianAngel

        guardian = GuardianAngel()
        advisories = guardian.counsel(max_advisories=1)
        if advisories:
            return advisories[0].message
    except Exception:
        pass
    return None


def _get_fleet_recommendation(
    phase: str = "FRAME",
    agent: str = "unknown",
) -> tuple[str | None, float]:
    """Get fleet router recommendation for best agent."""
    try:
        from .fleet_router import FleetRouter

        router = FleetRouter()
        scores = router.recommend(phase=phase)
        if scores:
            top = scores[0]
            return top.display_name, round(top.score, 2)
    except Exception:
        pass
    return None, 0.0


def _get_dispatch_guidance(
    scope: str, phase: str = "BUILD"
) -> tuple[str | None, str | None, str | None]:
    """Classify work scope and return dispatch guidance if non-Claude agent is best.

    Returns: (work_type, recommended_agent_display_name, guidance_message)
    """
    try:
        from .task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        plan = dispatcher.plan(description=scope, phase=phase)
        if plan.work_type == "unclassified":
            return None, None, None
        recommended = plan.recommended
        if recommended and recommended != "claude":
            display = plan.ranked_agents[0].display_name if plan.ranked_agents else recommended
            msg = (
                f"Work classified as {plan.work_type} ({plan.cognitive_class}). "
                f"Recommended agent: {display}. "
                f"Consider dispatching with conductor_fleet_guardrailed_handoff."
            )
            return plan.work_type, display, msg
        return plan.work_type, None, None
    except Exception:
        return None, None, None


def _check_pending_verification(cwd: Path | str) -> dict[str, str] | None:
    """Check if there's an unverified active handoff waiting for cross-verification."""
    try:
        from .fleet_handoff import read_active_handoff

        repo_path = Path(cwd) if not isinstance(cwd, Path) else cwd
        return read_active_handoff(repo_path)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_preflight(
    agent: str = "unknown",
    cwd: str | Path | None = None,
    auto_start: bool = True,
    json_output: bool = False,
) -> PreflightResult:
    """Run preflight: infer context, check collisions, build runway, optionally auto-start.

    Args:
        agent: Agent identity (claude, gemini, codex, etc.)
        cwd: Working directory to infer organ/repo from. Defaults to cwd.
        auto_start: Whether to auto-start a session.
        json_output: If True, suppresses human-readable printing.

    Returns:
        PreflightResult with all briefing data.
    """
    agent = agent or "unknown"
    cwd = cwd or Path.cwd()
    result = PreflightResult()

    # 1. Infer context from cwd
    organ, repo = infer_organ_repo(cwd)
    result.inferred_organ = organ
    result.inferred_repo = repo

    # 2. Check active sessions
    engine = SessionEngine()
    conductor_sessions = _collect_active_sessions(engine)
    claim_sessions = _collect_claims()
    all_active = conductor_sessions + claim_sessions
    result.active_agents = all_active

    # 3. Detect collisions
    result.collisions = _detect_collisions(all_active, organ, repo)

    # 4. Build runway briefing
    result.work_items = _build_work_items(organ)
    result.oracle_message = _get_oracle_advisory(organ, repo)
    rec_name, rec_score = _get_fleet_recommendation(phase="FRAME", agent=agent)
    result.fleet_recommendation = rec_name
    result.fleet_score = rec_score

    # 5. Auto-start session
    if auto_start and organ:
        try:
            session = engine.start(
                organ=organ,
                repo=repo or organ,
                scope="interactive",
                git_branch=False,
                agent=agent,
            )
            result.session_started = True
            result.session_id = session.session_id
            result.session_phase = session.current_phase
        except SessionError as e:
            result.error = str(e)
    elif auto_start and not organ:
        result.error = "Cannot auto-start: working directory is outside workspace"

    # 6. Check pending verification (unverified handoff from a previous dispatch)
    pending = _check_pending_verification(cwd)
    if pending:
        result.pending_verification = True
        result.pending_handoff_from = pending.get("from_agent")
        result.pending_handoff_to = pending.get("to_agent")
        result.pending_handoff_work_type = pending.get("work_type")
        result.gate_warnings.append(
            f"VERIFY: Pending handoff {pending.get('from_agent', '?')} → "
            f"{pending.get('to_agent', '?')} ({pending.get('work_type', 'unknown')}). "
            f"Cross-verify before proceeding."
        )

    # 7. Dispatch guidance (only when no pending verification — verify first)
    if not result.pending_verification:
        session = engine._load_session()
        scope = session.scope if session else ""
        phase = session.current_phase if session else "BUILD"
        if scope and scope != "interactive":
            wt, rec_agent, guidance = _get_dispatch_guidance(scope, phase)
            result.dispatch_work_type = wt
            result.dispatch_recommended_agent = rec_agent
            result.dispatch_guidance = guidance

    # 8. Gate warnings
    if result.collisions:
        result.gate_warnings.append(
            f"COLLISION: {len(result.collisions)} agent(s) already in this repo"
        )

    # 9. Output
    if not json_output:
        _print_briefing(result, agent)

    return result


# ---------------------------------------------------------------------------
# Human-readable output
# ---------------------------------------------------------------------------


def _print_briefing(result: PreflightResult, agent: str) -> None:
    """Print the runway briefing in human-readable format."""
    location = f"{result.inferred_organ}/{result.inferred_repo}" if result.inferred_organ else "system-wide"
    print(f"\n[CONDUCTOR] Runway Briefing — {location}")
    print("━" * 52)

    # Active agents
    if result.active_agents:
        print(f"Active agents:")
        for a in result.active_agents:
            print(f"  {a.agent:<12} → {a.organ}/{a.repo} ({a.phase}, {a.duration_minutes}min)")
    else:
        print(f"Active agents:     (none)")

    # Collisions
    if result.collisions:
        print(f"⚠ Collisions:")
        for c in result.collisions:
            print(f"  {c}")

    # Work items
    if result.work_items:
        print(f"\nTop work items:")
        for i, item in enumerate(result.work_items[:5], 1):
            print(f"  {i}. [{item.priority:<8}] {item.organ}: {item.description}")

    # Oracle
    if result.oracle_message:
        print(f"\nOracle says:       \"{result.oracle_message}\"")

    # Fleet recommendation
    if result.fleet_recommendation:
        print(f"\nRecommendation:    Best agent: {result.fleet_recommendation} (score: {result.fleet_score})")

    # Pending verification (Gap 3)
    if result.pending_verification:
        print(f"\n[VERIFY] Pending handoff: {result.pending_handoff_from} → {result.pending_handoff_to}"
              f" ({result.pending_handoff_work_type or 'unknown'})")
        print(f"[VERIFY] Cross-verification required. Run: conductor_fleet_cross_verify")

    # Dispatch guidance (Gap 1)
    if result.dispatch_guidance:
        print(f"\n[DISPATCH] {result.dispatch_guidance}")

    # Session result
    if result.session_started:
        print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"Session started: {result.session_id} ({result.session_phase})")
    elif result.error:
        print(f"\n⚠ {result.error}")

    # Gate warnings
    for w in result.gate_warnings:
        print(f"⚠ {w}")

    print()
