"""The Patchbay — Conductor's Command Center.

Composes all layers into a structured briefing: session state, system pulse,
work queue, lifetime stats, and suggested next action. Read-only, no mutations.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from .constants import (
    PHASE_INSTRUMENTS,
    PHASE_ROLES,
    ROLE_ACTIONS,
    WORKFLOW_DSL_PATH,
    organ_short,
    get_phase_clusters,
    WORKSPACE,
)
from .contracts import assert_contract
from .executor import WorkflowExecutor
from .governance import GovernanceRuntime
from .observability import get_metrics, log_event
from .guardian import GuardianAngel
from .oracle import Oracle, OracleContext
from .session import Session, SessionEngine, _load_stats
from .work_item import WorkRegistry
from .workqueue import WorkItem, WorkQueue


class Patchbay:
    """The command center. One read, all strings visible."""

    def __init__(self, ontology=None, engine: SessionEngine | None = None) -> None:
        self.ontology = ontology
        self.engine = engine or SessionEngine(ontology)
        self.gov = GovernanceRuntime()
        self.wq = WorkQueue(self.gov)
        self.wr = WorkRegistry()
        self.executor = WorkflowExecutor(WORKFLOW_DSL_PATH)

    def briefing(self, organ_filter: str | None = None) -> dict:
        """Full system briefing. Returns structured data.

        Each section degrades gracefully — a single section failure
        does not prevent other sections from rendering.
        """
        # Sync persistent registry with dynamic queue before briefing
        try:
            computed = self.wq.compute(organ_filter)
            self.wr.sync(computed)
        except Exception as exc:
            from .observability import log_event
            log_event("patchbay.sync_error", {"error": str(exc)})

        result: dict = {"timestamp": datetime.now(timezone.utc).isoformat()}

        for key, fn in [
            ("session", lambda: self._session_section()),
            ("orchestra", lambda: self._orchestra_section()),
            ("score", lambda: self.executor.get_briefing()),
            ("pulse", lambda: self._pulse_section(organ_filter)),
            ("corpus", lambda: self._corpus_section()),
            ("queue", lambda: self._queue_section(organ_filter)),
            ("stats", lambda: self._stats_section()),
            ("oracle", lambda: self._oracle_section()),
        ]:
            try:
                result[key] = fn()
            except Exception as e:
                result[key] = {"error": str(e)}

        try:
            result["suggested_action"] = self._suggest_next(organ_filter)
        except Exception as exc:
            from .observability import log_event
            log_event("patchbay.suggest_next_error", {"error": str(exc)})
            result["suggested_action"] = ""

        assert_contract("patchbay_briefing", result)
        return result

    # ----- Sections -----

    def _session_section(self) -> dict:
        """Active session or last closed."""
        try:
            session = self.engine._load_session()
        except Exception as exc:
            from .observability import log_event
            log_event("patchbay.session_load_error", {"error": str(exc)})
            session = None
        if session:
            phase_clusters = get_phase_clusters()
            phase_history = []
            for pl in session.phase_logs:
                dur = int(((pl.get("end_time") or time.time()) - pl["start_time"]) / 60)
                phase_history.append({
                    "phase": pl["name"],
                    "duration_minutes": dur,
                    "active": pl.get("end_time", 0) == 0,
                })

            return {
                "active": True,
                "session_id": session.session_id,
                "organ": session.organ,
                "repo": session.repo,
                "scope": session.scope,
                "current_phase": session.current_phase,
                "duration_minutes": session.duration_minutes,
                "ai_role": PHASE_ROLES.get(session.current_phase, "N/A"),
                "clusters": phase_clusters.get(session.current_phase, []),
                "phase_history": phase_history,
                "warnings": session.warnings,
            }

        # No active session — show last closed from stats
        stats = _load_stats()
        last = stats.get("last_session_id")
        recent = stats.get("recent_sessions", [])
        last_info = recent[-1] if recent else None

        return {
            "active": False,
            "last_session_id": last,
            "last_result": last_info.get("result") if last_info else None,
            "last_duration": last_info.get("duration_minutes") if last_info else None,
            "last_organ": last_info.get("organ") if last_info else None,
        }

    def _orchestra_section(self) -> dict:
        """AI orchestra briefing for the current session phase."""
        try:
            session = self.engine._load_session()
        except Exception as exc:
            from .observability import log_event
            log_event("patchbay.session_load_error", {"error": str(exc)})
            session = None

        if not session:
            return {"active": False}

        phase = session.current_phase
        return {
            "active": True,
            "phase": phase,
            "role": PHASE_ROLES.get(phase, "N/A"),
            "instrument": PHASE_INSTRUMENTS.get(phase, "N/A"),
            "allowed": ROLE_ACTIONS.get(phase, {}).get("allowed", []),
            "forbidden": ROLE_ACTIONS.get(phase, {}).get("forbidden", []),
            "clusters": get_phase_clusters().get(phase, []),
        }

    def _pulse_section(self, organ_filter: str | None = None) -> dict:
        """System pulse — repo counts and promotion status per organ."""
        organs_data = {}
        total_repos = 0
        total_candidate = 0
        violations = []

        for organ_key, organ_data in self.gov.registry.get("organs", {}).items():
            if organ_filter and organ_key != organ_filter:
                continue

            repos = organ_data.get("repositories", [])
            counts = Counter(r.get("promotion_status", "UNKNOWN") for r in repos)

            cand = counts.get("CANDIDATE", 0)
            pub = counts.get("PUBLIC_PROCESS", 0)
            total_repos += len(repos)
            total_candidate += cand

            flags = []
            if cand > self.gov.max_candidate_per_organ:
                flags.append(f"CAND>{self.gov.max_candidate_per_organ}")
                violations.append(organ_key)
            if pub > self.gov.max_public_process_per_organ:
                flags.append(f"PUB>{self.gov.max_public_process_per_organ}")
                if organ_key not in violations:
                    violations.append(organ_key)

            short = organ_short(organ_key)
            organs_data[organ_key] = {
                "short": short,
                "total": len(repos),
                "local": counts.get("LOCAL", 0),
                "candidate": cand,
                "public_process": pub,
                "graduated": counts.get("GRADUATED", 0),
                "archived": counts.get("ARCHIVED", 0),
                "flags": flags,
            }

        return {
            "organs": organs_data,
            "total_repos": total_repos,
            "total_candidate": total_candidate,
            "violations_count": len(violations),
        }

    def _queue_section(self, organ_filter: str | None = None) -> dict:
        """Work queue — showing persistent state and ownership."""
        # Note: sync was already called in briefing()
        items = sorted(self.wr.items.values(), key=lambda x: -x.score)
        
        if organ_filter:
            items = [i for i in items if i.organ == organ_filter]

        return {
            "total": len(items),
            "open_count": sum(1 for i in items if i.status == "OPEN"),
            "claimed_count": sum(1 for i in items if i.status == "CLAIMED"),
            "items": [
                {
                    "id": item.id,
                    "status": item.status,
                    "owner": item.owner,
                    "priority": item.priority,
                    "category": item.category,
                    "organ": item.organ,
                    "repo": item.repo,
                    "description": item.description,
                    "suggested_command": item.suggested_command,
                    "score": item.score,
                    "rationale": item.metadata.get("rationale", {}),
                }
                for item in items[:10]
            ],
        }

    def _stats_section(self) -> dict:
        """Lifetime stats from cumulative stats file."""
        stats = _load_stats()
        obs_metrics = get_metrics()
        total = stats.get("total_sessions", 0)
        shipped = stats.get("shipped", 0)
        total_minutes = stats.get("total_minutes", 0)
        streak = stats.get("streak", 0)

        return {
            "total_sessions": total,
            "total_hours": round(total_minutes / 60, 1) if total_minutes else 0,
            "shipped": shipped,
            "closed": stats.get("closed", 0),
            "ship_rate": round(shipped / total * 100) if total else 0,
            "streak": streak,
            "recent_sessions": stats.get("recent_sessions", [])[-5:],
            "top_failure_reasons": obs_metrics.get("failure_buckets", {}),
        }

    def _oracle_section(self) -> dict:
        """Advisory wisdom from the Guardian Angel (Oracle + Wisdom Corpus)."""
        guardian = GuardianAngel()

        # Build context from session state
        try:
            session = self.engine._load_session()
        except Exception as exc:
            from .observability import log_event
            log_event("patchbay.session_load_error", {"error": str(exc)})
            session = None

        ctx = OracleContext(
            trigger="patchbay",
            session_id=session.session_id if session else "",
            current_phase=session.current_phase if session else "",
            organ=session.organ if session else "",
        )
        advisories = guardian.counsel(ctx)

        # Include mastery summary
        mastery = guardian.growth_report()

        return {
            "count": len(advisories),
            "advisories": [
                {
                    "category": a.category,
                    "severity": a.severity,
                    "message": a.message,
                    "recommendation": a.recommendation,
                    "narrative": a.narrative,
                    "tools_suggested": a.tools_suggested,
                    "confidence": a.confidence,
                    "detector": a.detector,
                    "wisdom_id": a.wisdom_id,
                    "teaching": a.teaching,
                }
                for a in advisories
            ],
            "mastery": {
                "score": mastery.get("mastery_score", 0.0),
                "velocity": mastery.get("learning_velocity", "starting"),
                "encountered": mastery.get("principles_encountered", 0),
                "internalized": mastery.get("principles_internalized", 0),
            },
        }

    def _corpus_section(self) -> dict:
        """Research corpus → implementation coverage dashboard."""
        intake_dir = WORKSPACE / "alchemia-ingestvm" / "intake" / "ai-transcripts"
        if not intake_dir.is_dir():
            return {"available": False, "reason": "intake directory not found"}

        total = 0
        by_status: Counter = Counter()
        activated_docs: list[dict] = []
        total_tasks = 0
        completed_tasks = 0

        for fpath in sorted(intake_dir.glob("*.json")):
            try:
                data = json.loads(fpath.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            total += 1
            status = data.get("status", "unknown")
            by_status[status] += 1

            impl = data.get("implementation_status")
            if impl:
                extracted = len(impl.get("tasks_extracted", []))
                completed = len(impl.get("tasks_completed", []))
                total_tasks += extracted
                completed_tasks += completed
                activated_docs.append({
                    "slug": fpath.stem,
                    "tasks_extracted": extracted,
                    "tasks_completed": completed,
                    "completion_rate": impl.get("completion_rate", 0),
                })

        return {
            "available": True,
            "total_documents": total,
            "by_status": dict(by_status),
            "activated_count": len(activated_docs),
            "total_tasks_extracted": total_tasks,
            "total_tasks_completed": completed_tasks,
            "task_completion_rate": round(completed_tasks / total_tasks, 2) if total_tasks else 0,
            "activated_docs": activated_docs,
        }

    def _suggest_next(self, organ_filter: str | None = None) -> str:
        """Suggest the single most impactful next action."""
        session = self.engine._load_session()
        if session:
            # Active session — suggest next phase
            phase = session.current_phase
            if phase == "FRAME":
                return f"Continue FRAME research, then: conductor session phase shape"
            elif phase == "SHAPE":
                return f"Finalize plan, then: conductor session phase build"
            elif phase == "BUILD":
                return f"Complete implementation, then: conductor session phase prove"
            elif phase == "PROVE":
                return f"Verify quality, then: conductor session phase done"
            elif phase == "DONE":
                return f"Session complete. Run: conductor session close"
            return f"Current phase: {phase}"

        # No session — suggest from work queue
        items = self.wq.compute(organ_filter)
        if not items:
            return "System is clean. Start a new session."

        top = items[0]
        log_event(
            "patchbay.suggest_next",
            {
                "category": top.category,
                "organ": top.organ,
                "repo": top.repo,
            },
        )
        if top.category == "wip_violation":
            short = organ_short(top.organ)
            return (
                f"Triage {short} CANDIDATE backlog ({top.description}).\n"
                f"  -> {top.suggested_command}"
            )
        elif top.category == "stale":
            return (
                f"{top.repo}: {top.description}.\n"
                f"  -> {top.suggested_command}"
            )
        else:
            return (
                f"{top.repo or top.organ}: {top.description}.\n"
                f"  -> {top.suggested_command}"
            )

    # ----- Formatters -----

    def format_section_text(self, data: dict) -> str:
        """Human-readable text for a single-section view.

        Falls back to JSON for unrecognized section keys.
        """
        lines: list[str] = []
        now_str = data.get("timestamp", "")[:19].replace("T", " ") + " UTC"
        lines.append(f"  PATCHBAY{' ' * 50}{now_str}")
        lines.append("  " + "=" * 70)

        if "pulse" in data:
            pulse = data["pulse"]
            organs = pulse.get("organs", {})
            lines.append("")
            lines.append("  PULSE")
            lines.append("  " + "-" * 68)
            if organs:
                lines.append(f"  {'ORGAN':<14} {'REPOS':>5} {'CAND':>5} {'PUB':>5} {'GRAD':>5} {'ARCH':>5}   FLAGS")
                for organ_key in sorted(organs.keys()):
                    o = organs[organ_key]
                    short = o.get("short", organ_key)
                    organ_names = {
                        "I": "Theoria", "II": "Poiesis", "III": "Ergon",
                        "IV": "Taxis", "V": "Logos", "VI": "Koinonia",
                        "VII": "Kerygma", "META": "Meta",
                    }
                    label = f"{short} {organ_names.get(short, '')}"
                    flags = ", ".join(o.get("flags", []))
                    lines.append(
                        f"  {label:<14} {o['total']:>5} {o['candidate']:>5} "
                        f"{o['public_process']:>5} {o['graduated']:>5} "
                        f"{o['archived']:>5}   {flags}"
                    )
            viols = pulse.get("violations_count", 0)
            total_cand = pulse.get("total_candidate", 0)
            lines.append("  " + "-" * 68)
            if viols:
                lines.append(f"  {viols} organs over WIP limit | {total_cand} CANDIDATE system-wide")
            else:
                lines.append(f"  No WIP violations | {total_cand} CANDIDATE system-wide")

        elif "queue" in data:
            queue = data["queue"]
            queue_items = queue.get("items", [])
            total_q = queue.get("total", 0)
            lines.append("")
            lines.append(f"  QUEUE ({total_q} items)")
            lines.append("  " + "-" * 68)
            for item in queue_items:
                icon = "!!" if item["priority"] == "CRITICAL" else "!" if item["priority"] == "HIGH" else "."
                status_tag = f" [{item['status']}]" if item["status"] != "OPEN" else ""
                owner_tag = f" ({item['owner']})" if item["owner"] else ""
                if item.get("repo"):
                    lines.append(f"  {icon:<3} {item['id']} | {item['repo']}: {item['description']}{status_tag}{owner_tag}")
                else:
                    lines.append(f"  {icon:<3} {item['id']} | {organ_short(item['organ'])}: {item['description']}{status_tag}{owner_tag}")
                lines.append(f"      -> {item['suggested_command']}")
            lines.append("  " + "-" * 68)

        elif "stats" in data:
            stats = data["stats"]
            lines.append("")
            lines.append("  STATS")
            lines.append("  " + "-" * 68)
            lines.append(
                f"  Sessions: {stats.get('total_sessions', 0)} | "
                f"Hours: {stats.get('total_hours', 0)} | "
                f"Ship rate: {stats.get('ship_rate', 0)}% | "
                f"Streak: {stats.get('streak', 0)}"
            )
            recent = stats.get("recent_sessions", [])
            if recent:
                lines.append("")
                lines.append("  Recent sessions:")
                for s in recent:
                    lines.append(f"    {s.get('session_id', '?')} ({s.get('result', '?')}, {s.get('duration_minutes', 0)}m)")

        elif "corpus" in data:
            corpus = data["corpus"]
            if corpus.get("available"):
                lines.append("")
                lines.append("  RESEARCH CORPUS")
                lines.append("  " + "-" * 68)
                total_docs = corpus.get("total_documents", 0)
                by_status = corpus.get("by_status", {})
                status_parts = [f"{v} {k}" for k, v in sorted(by_status.items(), key=lambda x: -x[1])]
                lines.append(f"  Documents: {total_docs} ({', '.join(status_parts)})")
                activated = corpus.get("activated_count", 0)
                task_rate = corpus.get("task_completion_rate", 0)
                total_t = corpus.get("total_tasks_extracted", 0)
                done_t = corpus.get("total_tasks_completed", 0)
                lines.append(f"  Activated: {activated}/{total_docs} docs | Tasks: {done_t}/{total_t} ({task_rate:.0%})")
                lines.append("")
                for doc in corpus.get("activated_docs", []):
                    slug = doc["slug"]
                    rate = doc.get("completion_rate", 0)
                    extracted = doc.get("tasks_extracted", 0)
                    lines.append(f"    {slug}: {extracted} tasks ({rate:.0%})")
            else:
                lines.append("")
                lines.append(f"  CORPUS: {corpus.get('reason', 'unavailable')}")

        else:
            return json.dumps(data, indent=2)

        lines.append("")
        return "\n".join(lines)

    def format_json(self, data: dict) -> str:
        """Machine-readable JSON output."""
        return json.dumps(data, indent=2)

    def format_text(self, data: dict) -> str:
        """Human-readable plain text briefing."""
        lines: list[str] = []
        now_str = data.get("timestamp", "")[:19].replace("T", " ") + " UTC"

        lines.append(f"  PATCHBAY{' ' * 50}{now_str}")
        lines.append("  " + "=" * 70)

        # Session
        sess = data.get("session", {})
        if sess.get("active"):
            lines.append("")
            lines.append("  SESSION: ACTIVE")
            lines.append("  " + "-" * 68)
            lines.append(f"  {sess['session_id']}")
            lines.append(f"  {organ_short(sess['organ'])} | {sess['repo']} | \"{sess['scope']}\"")
            phase = sess["current_phase"]
            lines.append(f"  Phase: {phase} ({sess['duration_minutes']}m)")
            # Phase history
            history_parts = []
            for ph in sess.get("phase_history", []):
                marker = "*" if ph["active"] else ""
                history_parts.append(f"{ph['phase']}({ph['duration_minutes']}m{marker})")
            if history_parts:
                lines.append(f"  {' -> '.join(history_parts)}")
            lines.append(f"  -> Next: {self._next_command(phase)}")
        else:
            lines.append("")
            lines.append("  SESSION: none active")
            last_id = sess.get("last_session_id")
            if last_id:
                result = sess.get("last_result", "?")
                dur = sess.get("last_duration", "?")
                lines.append(f"  Last closed: {last_id} ({result}, {dur}m)")

        # Orchestra (AI-centric role briefing)
        orch = data.get("orchestra", {})
        if orch.get("active"):
            lines.append("")
            lines.append("  AI ORCHESTRA BRIEFING")
            lines.append("  " + "-" * 68)
            lines.append(f"  Role:       {orch['role']}")
            lines.append(f"  Instrument: {orch['instrument']}")
            lines.append(f"  Clusters:   {', '.join(orch['clusters'])}")
            if orch.get("allowed"):
                lines.append("  Allowed:    " + ", ".join(orch["allowed"]))
            if orch.get("forbidden"):
                lines.append("  Forbidden:  " + ", ".join(orch["forbidden"]))

        # Score (Active Workflow)
        score = data.get("score", {})
        if score.get("active"):
            lines.append("")
            lines.append("  WORKFLOW SCORE")
            lines.append("  " + "-" * 68)
            lines.append(f"  Workflow:     {score['workflow']}")
            lines.append(f"  Current Step: {score['current_step']}")
            lines.append(f"  Progress:     {score['progress']} ({score['status']})")

        # Pulse
        pulse = data.get("pulse", {})
        organs = pulse.get("organs", {})
        if organs:
            lines.append("")
            if sess.get("active"):
                lines.append("  PULSE (abbreviated)")
                lines.append("  " + "-" * 68)
                total = pulse.get("total_repos", 0)
                viols = pulse.get("violations_count", 0)
                lines.append(f"  System: {total} repos | {viols} organs over WIP")
            else:
                lines.append("  PULSE")
                lines.append("  " + "-" * 68)
                lines.append(f"  {'ORGAN':<14} {'REPOS':>5} {'CAND':>5} {'PUB':>5} {'GRAD':>5} {'ARCH':>5}   FLAGS")
                for organ_key in sorted(organs.keys()):
                    o = organs[organ_key]
                    short = o.get("short", organ_key)
                    # Build organ label
                    organ_names = {
                        "I": "Theoria", "II": "Poiesis", "III": "Ergon",
                        "IV": "Taxis", "V": "Logos", "VI": "Koinonia",
                        "VII": "Kerygma", "META": "Meta",
                    }
                    label = f"{short} {organ_names.get(short, '')}"
                    flags = ", ".join(o.get("flags", []))
                    lines.append(
                        f"  {label:<14} {o['total']:>5} {o['candidate']:>5} "
                        f"{o['public_process']:>5} {o['graduated']:>5} "
                        f"{o['archived']:>5}   {flags}"
                    )
                lines.append("  " + "-" * 68)
                viols = pulse.get("violations_count", 0)
                total_cand = pulse.get("total_candidate", 0)
                if viols:
                    lines.append(f"  {viols} organs over WIP limit | {total_cand} CANDIDATE system-wide")
                else:
                    lines.append(f"  No WIP violations | {total_cand} CANDIDATE system-wide")

        # Corpus
        corpus = data.get("corpus", {})
        if corpus.get("available") and not sess.get("active"):
            lines.append("")
            lines.append("  RESEARCH CORPUS")
            lines.append("  " + "-" * 68)
            total_docs = corpus.get("total_documents", 0)
            by_status = corpus.get("by_status", {})
            status_parts = [f"{v} {k}" for k, v in sorted(by_status.items(), key=lambda x: -x[1])]
            lines.append(f"  Documents: {total_docs} ({', '.join(status_parts)})")
            activated = corpus.get("activated_count", 0)
            task_rate = corpus.get("task_completion_rate", 0)
            total_t = corpus.get("total_tasks_extracted", 0)
            done_t = corpus.get("total_tasks_completed", 0)
            lines.append(f"  Activated: {activated}/{total_docs} docs | Tasks: {done_t}/{total_t} ({task_rate:.0%})")

        # Queue
        queue = data.get("queue", {})
        queue_items = queue.get("items", [])
        if queue_items and not sess.get("active"):
            total_q = queue.get("total", 0)
            shown = min(len(queue_items), 5)
            lines.append("")
            lines.append(f"  QUEUE (top {shown} of {total_q})")
            lines.append("  " + "-" * 68)
            for item in queue_items[:5]:
                icon = "!!" if item["priority"] == "CRITICAL" else "!" if item["priority"] == "HIGH" else "."
                organ_short_name = organ_short(item["organ"])
                status_tag = f" [{item['status']}]" if item["status"] != "OPEN" else ""
                owner_tag = f" ({item['owner']})" if item["owner"] else ""
                if item.get("repo"):
                    lines.append(f"  {icon:<3} {item['id']} | {item['repo']}: {item['description']}{status_tag}{owner_tag}")
                else:
                    lines.append(f"  {icon:<3} {item['id']} | {organ_short_name}: {item['description']}{status_tag}{owner_tag}")
                lines.append(f"      -> {item['suggested_command']}")
            lines.append("  " + "-" * 68)

        # Stats
        stats = data.get("stats", {})
        total_sessions = stats.get("total_sessions", 0)
        if total_sessions > 0:
            lines.append("")
            lines.append("  STATS")
            lines.append("  " + "-" * 68)
            lines.append(
                f"  Sessions: {total_sessions} | "
                f"Hours: {stats.get('total_hours', 0)} | "
                f"Ship rate: {stats.get('ship_rate', 0)}% | "
                f"Streak: {stats.get('streak', 0)}"
            )

        # Guardian Angel advisories
        oracle_data = data.get("oracle", {})
        oracle_items = oracle_data.get("advisories", [])
        if oracle_items:
            lines.append("")
            # Keep "ORACLE" in the header for backward-compatible text parsers.
            lines.append("  ORACLE / GUARDIAN ANGEL")
            lines.append("  " + "-" * 68)
            severity_icons = {"critical": "XX", "warning": "!!", "caution": "! ", "info": "  "}
            for adv in oracle_items[:5]:
                icon = severity_icons.get(adv["severity"], "  ")
                lines.append(f"  {icon} [{adv['category'].upper()}] {adv['message']}")
                if adv.get("teaching"):
                    lines.append(f"     * {adv['teaching'][:120]}")
                elif adv.get("narrative"):
                    lines.append(f"     ~ {adv['narrative']}")
                if adv.get("recommendation"):
                    lines.append(f"     -> {adv['recommendation']}")
                if adv.get("tools_suggested"):
                    lines.append(f"     tools: {', '.join(adv['tools_suggested'][:4])}")
            mastery = oracle_data.get("mastery", {})
            if mastery.get("encountered", 0) > 0:
                lines.append(f"  Mastery: {mastery.get('score', 0):.0%} | "
                             f"{mastery.get('encountered', 0)} encountered, "
                             f"{mastery.get('internalized', 0)} internalized | "
                             f"velocity: {mastery.get('velocity', 'starting')}")

        # Suggested action (shown for both active and inactive sessions)
        suggested = data.get("suggested_action", "")
        if suggested:
            lines.append("")
            lines.append("  NEXT ACTION")
            lines.append("  " + "-" * 68)
            for line in suggested.split("\n"):
                lines.append(f"  {line}")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _next_command(current: str) -> str:
        """Suggest the next conductor command for the session context."""
        command_map = {
            "FRAME": "conductor session phase shape",
            "SHAPE": "conductor session phase build",
            "BUILD": "conductor session phase prove",
            "PROVE": "conductor session phase done",
            "DONE": "conductor session close",
        }
        return command_map.get(current, "conductor session close")
