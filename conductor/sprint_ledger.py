"""Sprint ledger — per-session retrospective with feedback injection.

Not just collection: the ledger detects behavioral patterns from prompt/phase data,
records them into the pattern history (consumed by Oracle detectors), logs
observability events (consumed by trend analysis), and produces actionable
insights that replace the blank "lessons" template.

Feedback loops wired:
  1. Pattern detection → product.record_pattern() → Oracle._load_patterns()
  2. Phase imbalance → observability.log_event() → trend checks
  3. Prompt anti-patterns → session warnings (visible in next session start)
  4. Fleet efficiency → fleet_usage tracking (consumed by fleet_recommend)
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .constants import SESSIONS_DIR, WORKSPACE
from .observability import log_event
from .product import record_pattern


# ---------------------------------------------------------------------------
# Prompt-sequence pattern detectors
# ---------------------------------------------------------------------------

def _detect_prompt_patterns(prompts: list[dict]) -> list[dict]:
    """Analyze the prompt sequence for behavioral anti-patterns.

    Each detected pattern is a dict with:
      name: machine-readable pattern ID (feeds into Oracle)
      severity: info | caution | warning
      insight: human-readable description
      recommendation: what to do differently
    """
    if not prompts:
        return []

    patterns: list[dict] = []
    total = len(prompts)
    types = {}
    for p in prompts:
        t = p.get("type", "unknown")
        types[t] = types.get(t, 0) + 1

    # 1. Correction ratio — too many "no, actually" prompts = unclear scope
    corrections = types.get("correction", 0)
    if total >= 5 and corrections / total > 0.2:
        patterns.append({
            "name": "high_correction_ratio",
            "severity": "caution",
            "insight": f"{corrections}/{total} prompts were corrections — scope may have been unclear at start.",
            "recommendation": "Spend more time in FRAME clarifying intent before BUILD.",
        })

    # 2. Continuation-heavy — agent needed constant hand-holding
    continuations = types.get("continuation", 0)
    if total >= 8 and continuations / total > 0.4:
        patterns.append({
            "name": "excessive_continuation",
            "severity": "info",
            "insight": f"{continuations}/{total} prompts were continuations — agent needed frequent nudging.",
            "recommendation": "Write longer initial directives with full context to reduce back-and-forth.",
        })

    # 3. No questions asked — possible over-trust in agent output
    questions = types.get("question", 0) + types.get("exploration", 0)
    if total >= 10 and questions == 0:
        patterns.append({
            "name": "no_verification_questions",
            "severity": "caution",
            "insight": "Zero questions asked across the session — output may not have been verified.",
            "recommendation": "Ask probing questions in PROVE phase to catch hidden assumptions.",
        })

    # 4. Plan invocation without subsequent review
    plan_invocations = types.get("plan_invocation", 0)
    reviews = types.get("review", 0)
    if plan_invocations > 0 and reviews == 0 and total >= 5:
        patterns.append({
            "name": "plan_without_review",
            "severity": "info",
            "insight": "Plan was invoked but no review prompts followed.",
            "recommendation": "Review delivered artifacts against the plan before closing.",
        })

    # 5. Single-prompt session — either trivial or scope was too tight
    if total == 1:
        patterns.append({
            "name": "single_prompt_session",
            "severity": "info",
            "insight": "Session had only 1 prompt — may not warrant full conductor lifecycle.",
            "recommendation": "For quick tasks, consider skipping the session ceremony.",
        })

    return patterns


def _detect_phase_patterns(phase_history: list[dict], duration_minutes: int) -> list[dict]:
    """Detect phase-balance anti-patterns."""
    patterns: list[dict] = []
    if not phase_history or duration_minutes <= 0:
        return patterns

    total_phase_time = sum(ph.get("duration_minutes", 0) for ph in phase_history) or 1
    phase_pcts: dict[str, float] = {}
    for ph in phase_history:
        name = ph.get("name", "")
        dur = ph.get("duration_minutes", 0)
        phase_pcts[name] = dur / total_phase_time * 100

    build_pct = phase_pcts.get("BUILD", 0)
    frame_pct = phase_pcts.get("FRAME", 0)
    prove_pct = phase_pcts.get("PROVE", 0)
    shape_pct = phase_pcts.get("SHAPE", 0)

    if build_pct > 70:
        patterns.append({
            "name": "build_heavy",
            "severity": "caution",
            "insight": f"BUILD consumed {build_pct:.0f}% of session — possible cowboy coding.",
            "recommendation": "Invest more in FRAME (research) and PROVE (verification).",
        })

    if prove_pct < 5 and duration_minutes > 30:
        patterns.append({
            "name": "skipped_prove",
            "severity": "warning",
            "insight": f"PROVE phase was {prove_pct:.0f}% of a {duration_minutes}m session.",
            "recommendation": "Run tests and review before closing — unverified work creates tech debt.",
        })

    if frame_pct > 60 and build_pct < 10:
        patterns.append({
            "name": "analysis_paralysis",
            "severity": "caution",
            "insight": f"FRAME was {frame_pct:.0f}% but BUILD was only {build_pct:.0f}%.",
            "recommendation": "Set a FRAME time-box to avoid over-researching before acting.",
        })

    # No SHAPE phase at all
    if shape_pct == 0 and duration_minutes > 20:
        patterns.append({
            "name": "no_shape_phase",
            "severity": "info",
            "insight": "Session skipped SHAPE entirely — went from research to code without a plan.",
            "recommendation": "Even a quick plan.md reduces rework.",
        })

    return patterns


@dataclass
class SessionLedger:
    """Assembled retrospective data for a single conductor session."""

    session_id: str
    agent: str
    organ: str
    repo: str
    scope: str
    duration_minutes: int
    result: str
    phase_history: list[dict] = field(default_factory=list)
    prompts: list[dict] = field(default_factory=list)
    prompt_stats: dict = field(default_factory=dict)
    files_changed: list[str] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    plans_referenced: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fleet_usage: dict = field(default_factory=dict)
    detected_patterns: list[dict] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    timestamp: str = ""
    feedback_applied: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent": self.agent,
            "organ": self.organ,
            "repo": self.repo,
            "scope": self.scope,
            "duration_minutes": self.duration_minutes,
            "result": self.result,
            "phase_history": self.phase_history,
            "prompts": self.prompts,
            "prompt_stats": self.prompt_stats,
            "files_changed": self.files_changed,
            "commits": self.commits,
            "plans_referenced": self.plans_referenced,
            "warnings": self.warnings,
            "fleet_usage": self.fleet_usage,
            "detected_patterns": self.detected_patterns,
            "insights": self.insights,
            "timestamp": self.timestamp,
            "feedback_applied": self.feedback_applied,
        }


def _load_session_log(session_id: str) -> dict[str, Any] | None:
    """Load session-log.yaml for a given session ID."""
    log_path = SESSIONS_DIR / session_id / "session-log.yaml"
    if not log_path.exists():
        return None
    try:
        return yaml.safe_load(log_path.read_text()) or {}
    except (yaml.YAMLError, OSError):
        return None


def _find_latest_session() -> str | None:
    """Find the most recently closed session ID by directory mtime."""
    if not SESSIONS_DIR.exists():
        return None
    candidates = []
    for d in SESSIONS_DIR.iterdir():
        log = d / "session-log.yaml"
        if log.exists():
            candidates.append((log.stat().st_mtime, d.name))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def find_session_jsonl(session_log: dict[str, Any]) -> Path | None:
    """Match a conductor session to its Claude JSONL file by timestamp heuristics.

    Searches ~/.claude/projects/-Users-4jp-Workspace-*/ directories for JSONL
    files created around the session start time.
    """
    claude_base = Path.home() / ".claude" / "projects"
    if not claude_base.exists():
        return None

    session_ts = session_log.get("timestamp", "")
    if not session_ts:
        return None

    try:
        session_end = datetime.fromisoformat(session_ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

    duration = session_log.get("duration_minutes", 60)
    session_start_epoch = session_end.timestamp() - (duration * 60)
    # Allow 5-min window before start and after end
    window_start = session_start_epoch - 300
    window_end = session_end.timestamp() + 300

    best: tuple[float, Path] | None = None

    for project_dir in claude_base.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            try:
                mtime = jsonl.stat().st_mtime
                # JSONL file modified during the session window
                if window_start <= mtime <= window_end:
                    # Prefer the closest match to session end
                    delta = abs(mtime - session_end.timestamp())
                    if best is None or delta < best[0]:
                        best = (delta, jsonl)
            except OSError:
                continue

    return best[1] if best else None


def _extract_prompts_from_jsonl(jsonl_path: Path) -> list[dict]:
    """Extract prompts from a Claude JSONL session file."""
    try:
        from organvm_engine.session.agents import AgentSession
        from organvm_engine.prompts.extractor import extract_prompts

        size = jsonl_path.stat().st_size if jsonl_path.exists() else 0
        session = AgentSession(
            agent="claude",
            file_path=jsonl_path,
            session_id=jsonl_path.stem,
            project_dir=str(jsonl_path.parent),
            started=None,
            ended=None,
            size_bytes=size,
        )
        raw_prompts = extract_prompts(session)
        if raw_prompts is None:
            return []
        return [
            {"text": p.text, "timestamp": p.timestamp, "index": p.index}
            for p in raw_prompts
        ]
    except ImportError:
        # Fallback: minimal extraction without organvm_engine
        return _extract_prompts_fallback(jsonl_path)


def _extract_prompts_fallback(jsonl_path: Path) -> list[dict]:
    """Minimal Claude JSONL prompt extraction without organvm_engine."""
    prompts: list[dict] = []
    index = 0
    try:
        for raw_line in jsonl_path.open(encoding="utf-8"):
            line = raw_line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") != "user":
                continue
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, list):
                text = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"
                )
            elif isinstance(content, str):
                text = content
            else:
                continue
            if len(text.strip()) <= 5:
                continue
            prompts.append({
                "text": text.strip(),
                "timestamp": msg.get("timestamp"),
                "index": index,
            })
            index += 1
    except OSError:
        pass
    return prompts


def _classify_prompt(text: str, index: int) -> str:
    """Classify a prompt into a type category."""
    try:
        from organvm_engine.prompts.classifier import classify_prompt_type
        return classify_prompt_type(text, index)
    except ImportError:
        # Minimal fallback
        lower = text.lower().strip()
        if lower.startswith(("what", "how", "why", "where", "is ", "are ", "can ", "does ")):
            return "question"
        if lower.startswith(("implement", "create", "add", "build", "write")):
            return "directive"
        if lower.startswith(("ok", "yes", "go ahead", "looks good", "perfect")):
            return "continuation"
        return "command"


def _compute_prompt_stats(prompts: list[dict]) -> dict:
    """Compute aggregate stats from classified prompts."""
    if not prompts:
        return {"total": 0, "avg_chars": 0, "type_distribution": {}}

    total_chars = sum(len(p.get("text", "")) for p in prompts)
    types: dict[str, int] = {}
    for p in prompts:
        t = p.get("type", "unknown")
        types[t] = types.get(t, 0) + 1

    return {
        "total": len(prompts),
        "avg_chars": round(total_chars / len(prompts)),
        "type_distribution": types,
    }


def _collect_git_activity(
    session_log: dict[str, Any],
) -> tuple[list[dict], list[str]]:
    """Collect git commits and files changed during the session window."""
    commits: list[dict] = []
    files: list[str] = []

    session_ts = session_log.get("timestamp", "")
    duration = session_log.get("duration_minutes", 60)
    if not session_ts:
        return commits, files

    try:
        end_dt = datetime.fromisoformat(session_ts.replace("Z", "+00:00"))
        start_epoch = end_dt.timestamp() - (duration * 60)
        start_dt = datetime.fromtimestamp(start_epoch, tz=timezone.utc)
    except (ValueError, OSError):
        return commits, files

    since = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
    until = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        result = subprocess.run(
            ["git", "log", f"--since={since}", f"--until={until}",
             "--pretty=format:%H|%s|%ai", "--no-merges"],
            capture_output=True, text=True, timeout=10,
            cwd=str(WORKSPACE),
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split("|", 2)
                if len(parts) >= 2:
                    commits.append({
                        "sha": parts[0][:8],
                        "message": parts[1],
                        "date": parts[2] if len(parts) > 2 else "",
                    })

        # Files changed
        result = subprocess.run(
            ["git", "log", f"--since={since}", f"--until={until}",
             "--name-only", "--pretty=format:", "--no-merges"],
            capture_output=True, text=True, timeout=10,
            cwd=str(WORKSPACE),
        )
        if result.returncode == 0:
            seen: set[str] = set()
            for line in result.stdout.strip().splitlines():
                f = line.strip()
                if f and f not in seen:
                    seen.add(f)
                    files.append(f)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return commits, files


def _collect_fleet_usage(session_log: dict[str, Any]) -> dict:
    """Pull fleet usage data for this session."""
    return {
        "agent": session_log.get("agent", "unknown"),
        "tokens_consumed": session_log.get("tokens_consumed", 0),
        "estimated_cost_usd": session_log.get("estimated_cost_usd", 0.0),
    }


def _discover_related_plans(session_log: dict[str, Any]) -> list[dict]:
    """Find plan files in the session directory itself (fast, no workspace scan)."""
    session_id = session_log.get("session_id", "")
    if not session_id:
        return []

    session_dir = SESSIONS_DIR / session_id
    if not session_dir.exists():
        return []

    plans: list[dict] = []
    for f in session_dir.glob("*.md"):
        if f.name == "session-log.yaml" or f.name == "retro.md":
            continue
        plans.append({"path": str(f), "name": f.stem})
    return plans


def build_ledger(
    session_id: str | None = None,
    jsonl_path: Path | None = None,
) -> SessionLedger:
    """Build a complete session ledger from conductor + JSONL data.

    Args:
        session_id: Specific session ID, or None for latest.
        jsonl_path: Override JSONL path (otherwise auto-discovered).
    """
    if session_id is None:
        session_id = _find_latest_session()
        if session_id is None:
            raise ValueError("No closed sessions found.")

    session_log = _load_session_log(session_id)
    if session_log is None:
        raise ValueError(f"Session log not found: {session_id}")

    # Phase history from session log
    phases = session_log.get("phases", {})
    phase_history = []
    for name, data in phases.items():
        if isinstance(data, dict):
            phase_history.append({
                "name": name,
                "duration_minutes": round(data.get("duration", 0) / 60, 1)
                if data.get("duration", 0) > 60
                else data.get("duration", 0),
                "visits": data.get("visits", 1),
                "tools_used": data.get("tools_used", []),
                "agents": data.get("agents", []),
            })

    # Prompts from JSONL
    if jsonl_path is None:
        jsonl_path = find_session_jsonl(session_log)

    prompts: list[dict] = []
    if jsonl_path and jsonl_path.exists():
        raw_prompts = _extract_prompts_from_jsonl(jsonl_path)
        for p in raw_prompts:
            p["type"] = _classify_prompt(p.get("text", ""), p.get("index", 0))
            prompts.append(p)

    prompt_stats = _compute_prompt_stats(prompts)
    commits, files_changed = _collect_git_activity(session_log)
    fleet_usage = _collect_fleet_usage(session_log)
    plans = _discover_related_plans(session_log)

    duration = session_log.get("duration_minutes", 0)

    # Detect patterns — this is where data becomes intelligence
    prompt_patterns = _detect_prompt_patterns(prompts)
    phase_patterns = _detect_phase_patterns(phase_history, duration)
    all_patterns = prompt_patterns + phase_patterns

    # Synthesize insights from patterns (not a blank template)
    insights = [p["insight"] for p in all_patterns]
    if not insights:
        if session_log.get("result") == "SHIPPED":
            insights.append("Clean session — shipped without detected anti-patterns.")
        else:
            insights.append("Session closed without shipping — review scope and phase balance.")

    return SessionLedger(
        session_id=session_id,
        agent=session_log.get("agent", "unknown"),
        organ=session_log.get("organ", ""),
        repo=session_log.get("repo", ""),
        scope=session_log.get("scope", ""),
        duration_minutes=duration,
        result=session_log.get("result", "UNKNOWN"),
        phase_history=phase_history,
        prompts=prompts,
        prompt_stats=prompt_stats,
        files_changed=files_changed,
        commits=commits,
        plans_referenced=plans,
        warnings=session_log.get("warnings", []),
        fleet_usage=fleet_usage,
        detected_patterns=all_patterns,
        insights=insights,
        timestamp=session_log.get("timestamp", datetime.now(timezone.utc).isoformat()),
    )


def render_ledger_markdown(ledger: SessionLedger) -> str:
    """Render a session ledger as a markdown retrospective."""
    lines: list[str] = []

    lines.append(f"# Session Retrospective: {ledger.session_id}")
    lines.append("")
    lines.append(
        f"**Agent:** {ledger.agent} | **Organ:** {ledger.organ} | **Repo:** {ledger.repo}"
    )
    lines.append(
        f"**Duration:** {ledger.duration_minutes} min | **Result:** {ledger.result}"
    )
    tokens = ledger.fleet_usage.get("tokens_consumed", 0)
    cost = ledger.fleet_usage.get("estimated_cost_usd", 0.0)
    if tokens:
        lines.append(f"**Tokens:** {tokens:,} | **Est. Cost:** ${cost:.4f}")
    lines.append("")

    # Phase path
    lines.append("## Phase Path")
    if ledger.phase_history:
        parts = []
        for ph in ledger.phase_history:
            dur = ph.get("duration_minutes", 0)
            parts.append(f"{ph['name']} ({dur}m)")
        lines.append(" -> ".join(parts))
    else:
        lines.append("No phase data available.")
    lines.append("")

    # Prompt ledger
    lines.append(f"## Prompt Ledger ({len(ledger.prompts)} prompts)")
    lines.append("")
    if ledger.prompts:
        lines.append("| # | Time | Type | Text |")
        lines.append("|---|------|------|------|")
        for p in ledger.prompts:
            idx = p.get("index", 0) + 1
            ts = p.get("timestamp", "")
            if ts:
                # Show just time portion
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    ts = dt.strftime("%H:%M")
                except ValueError:
                    ts = ts[:5]
            ptype = p.get("type", "?")
            text = p.get("text", "")[:120].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {idx} | {ts} | {ptype} | {text} |")
        lines.append("")

        # Prompt stats
        stats = ledger.prompt_stats
        lines.append("### Prompt Stats")
        lines.append(
            f"- {stats.get('total', 0)} prompts, avg {stats.get('avg_chars', 0)} chars"
        )
        type_dist = stats.get("type_distribution", {})
        if type_dist:
            parts = [f"{count} {t}" for t, count in sorted(type_dist.items(), key=lambda x: -x[1])]
            lines.append(f"- Types: {', '.join(parts)}")
        lines.append("")

    # What was built
    lines.append("## What Was Built")
    if ledger.commits:
        for c in ledger.commits:
            lines.append(f"- `{c['sha']}` — {c['message']}")
    else:
        lines.append("No commits detected in session window.")
    lines.append("")

    if ledger.files_changed:
        lines.append(f"### Files Changed ({len(ledger.files_changed)})")
        for f in ledger.files_changed[:30]:
            lines.append(f"- {f}")
        if len(ledger.files_changed) > 30:
            lines.append(f"- ... and {len(ledger.files_changed) - 30} more")
        lines.append("")

    # Plans referenced
    if ledger.plans_referenced:
        lines.append("## Plans Referenced")
        for plan in ledger.plans_referenced:
            lines.append(f"- {plan.get('name', 'unknown')}")
        lines.append("")

    # Warnings
    if ledger.warnings:
        lines.append("## Warnings")
        for w in ledger.warnings:
            lines.append(f"- {w}")
        lines.append("")

    # Detected patterns — synthesized intelligence, not a blank template
    if ledger.detected_patterns:
        lines.append("## Detected Patterns")
        for pat in ledger.detected_patterns:
            sev = pat.get("severity", "info").upper()
            lines.append(f"- **[{sev}] {pat['name']}**: {pat['insight']}")
            rec = pat.get("recommendation", "")
            if rec:
                lines.append(f"  - *Action:* {rec}")
        lines.append("")

    # Synthesized insights
    lines.append("## Insights")
    for insight in ledger.insights:
        lines.append(f"- {insight}")
    lines.append("")

    # Feedback status
    if ledger.feedback_applied:
        lines.append("## Feedback Injected")
        for fb in ledger.feedback_applied:
            lines.append(f"- {fb}")
    else:
        lines.append("## Feedback")
        lines.append("Run `conductor retro session --latest --write` to inject patterns into Oracle and observability.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Alchemize — inject learnings back into the system
# ---------------------------------------------------------------------------


def alchemize_ledger(ledger: SessionLedger) -> list[str]:
    """Feed ledger intelligence back into the system's feedback loops.

    Returns a list of actions taken (for audit trail).

    Feedback targets:
      1. product.record_pattern() → Oracle pattern history (JSONL)
      2. observability.log_event() → trend analysis + alerting
      3. Session warnings → visible at next session start via Guardian Angel
    """
    actions: list[str] = []

    # 1. Record detected patterns into pattern history
    #    Oracle._load_patterns() reads this to detect recurring anti-patterns
    for pat in ledger.detected_patterns:
        try:
            record_pattern(pat["name"], ledger.session_id, ledger.result)
            actions.append(f"pattern:{pat['name']} -> pattern-history.jsonl")
        except Exception:
            pass  # Never crash feedback for logging failures

    # 2. Log phase/prompt events into observability
    #    Consumed by: observability report, trend checks, DORA metrics
    try:
        if ledger.phase_history:
            phase_data = {
                ph["name"]: ph.get("duration_minutes", 0) for ph in ledger.phase_history
            }
            log_event("retro.phase_balance", {
                "session_id": ledger.session_id,
                "phases": phase_data,
                "duration_minutes": ledger.duration_minutes,
                "result": ledger.result,
            })
            actions.append("phase_balance -> observability events")

        if ledger.prompt_stats.get("total", 0) > 0:
            log_event("retro.prompt_stats", {
                "session_id": ledger.session_id,
                "total_prompts": ledger.prompt_stats["total"],
                "avg_chars": ledger.prompt_stats.get("avg_chars", 0),
                "type_distribution": ledger.prompt_stats.get("type_distribution", {}),
                "pattern_count": len(ledger.detected_patterns),
            })
            actions.append("prompt_stats -> observability events")

        for pat in ledger.detected_patterns:
            if pat.get("severity") in ("warning", "caution"):
                log_event("retro.pattern_detected", {
                    "session_id": ledger.session_id,
                    "pattern": pat["name"],
                    "severity": pat["severity"],
                })
    except Exception:
        pass

    # 3. Cost efficiency tracking
    #    Tokens per commit — are we getting denser output over time?
    tokens = ledger.fleet_usage.get("tokens_consumed", 0)
    commit_count = len(ledger.commits)
    if tokens > 0 and commit_count > 0:
        try:
            log_event("retro.efficiency", {
                "session_id": ledger.session_id,
                "tokens_per_commit": round(tokens / commit_count),
                "cost_per_commit": round(
                    ledger.fleet_usage.get("estimated_cost_usd", 0) / commit_count, 4
                ),
                "agent": ledger.agent,
            })
            actions.append("efficiency metrics -> observability events")
        except Exception:
            pass

    ledger.feedback_applied = actions
    return actions
