"""Layer 1: Session Engine — FRAME/SHAPE/BUILD/PROVE lifecycle."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from .constants import (
    PHASES,
    PHASE_ROLES,
    SESSIONS_DIR,
    SESSION_STATE_FILE,
    STATS_FILE,
    TEMPLATES_DIR,
    VALID_TRANSITIONS,
    SessionError,
    atomic_write,
    get_phase_clusters,
    organ_short,
    resolve_organ_key,
)

try:
    from router import Ontology
except ImportError:
    Ontology = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Session:
    session_id: str
    organ: str
    repo: str
    scope: str
    start_time: float
    current_phase: str = "FRAME"
    phase_logs: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    result: str = "IN_PROGRESS"

    @property
    def duration_minutes(self) -> int:
        return int((time.time() - self.start_time) / 60)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "organ": self.organ,
            "repo": self.repo,
            "scope": self.scope,
            "start_time": self.start_time,
            "current_phase": self.current_phase,
            "phase_logs": self.phase_logs,
            "warnings": self.warnings,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Session:
        return cls(**d)


# ---------------------------------------------------------------------------
# Cumulative stats (P5.5)
# ---------------------------------------------------------------------------


def _load_stats() -> dict:
    if STATS_FILE.exists():
        try:
            return json.loads(STATS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "total_sessions": 0, "total_minutes": 0, "shipped": 0, "closed": 0,
        "by_organ": {}, "streak": 0, "last_session_id": "", "recent_sessions": [],
    }


def _save_stats(stats: dict) -> None:
    atomic_write(STATS_FILE, json.dumps(stats, indent=2))


def _update_stats(session_log: dict) -> dict:
    """Update cumulative stats from a completed session log. Returns updated stats."""
    stats = _load_stats()
    stats["total_sessions"] += 1
    stats["total_minutes"] += session_log.get("duration_minutes", 0)

    result = session_log.get("result", "CLOSED")
    if result == "SHIPPED":
        stats["shipped"] += 1
    elif result == "CLOSED":
        stats["closed"] += 1
    # IN_PROGRESS or other values are counted in total but not shipped/closed

    organ = session_log.get("organ", "UNKNOWN")
    organ_stats = stats.setdefault("by_organ", {}).setdefault(organ, {"sessions": 0, "minutes": 0})
    organ_stats["sessions"] += 1
    organ_stats["minutes"] += session_log.get("duration_minutes", 0)

    # Streak: consecutive SHIPPED sessions (resets on non-SHIPPED)
    if result == "SHIPPED":
        stats["streak"] = stats.get("streak", 0) + 1
    else:
        stats["streak"] = 0

    # Last session ID
    stats["last_session_id"] = session_log.get("session_id", "")

    # Recent sessions (last 10)
    recent = stats.get("recent_sessions", [])
    recent.append({
        "session_id": session_log.get("session_id", ""),
        "result": result,
        "organ": organ,
        "duration_minutes": session_log.get("duration_minutes", 0),
    })
    stats["recent_sessions"] = recent[-10:]

    _save_stats(stats)
    return stats


# ---------------------------------------------------------------------------
# Session Engine
# ---------------------------------------------------------------------------


class SessionEngine:
    """Layer 1: FRAME/SHAPE/BUILD/PROVE lifecycle engine."""

    def __init__(self, ontology=None):
        self.ontology = ontology
        self.phase_clusters = get_phase_clusters()
        SESSIONS_DIR.mkdir(exist_ok=True)

    def _load_session(self) -> Optional[Session]:
        if SESSION_STATE_FILE.exists():
            try:
                data = json.loads(SESSION_STATE_FILE.read_text())
                return Session.from_dict(data)
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                raise SessionError(
                    f"Session state corrupted ({e}). Fix or delete .conductor-session.json manually."
                ) from e
        return None

    def _save_session(self, session: Session) -> None:
        atomic_write(SESSION_STATE_FILE, json.dumps(session.to_dict(), indent=2))

    def _clear_session(self) -> None:
        if SESSION_STATE_FILE.exists():
            SESSION_STATE_FILE.unlink()

    def start(self, organ: str, repo: str, scope: str, git_branch: bool = True) -> Session:
        """Start a new session."""
        if self._load_session():
            raise SessionError("Session already active. Close it first with `conductor session close`.")

        organ_key = resolve_organ_key(organ)
        now = time.time()
        date_str = datetime.now().strftime("%Y-%m-%d")
        slug = scope.lower().replace(" ", "-")[:40]
        # Short hash for uniqueness when same scope is used twice in one day
        short_hash = hashlib.sha256(f"{now}{organ_key}{repo}{scope}".encode()).hexdigest()[:6]
        session_id = f"{date_str}-{organ_short(organ_key)}-{slug}-{short_hash}"

        session = Session(
            session_id=session_id,
            organ=organ_key,
            repo=repo,
            scope=scope,
            start_time=now,
            current_phase="FRAME",
            phase_logs=[{"name": "FRAME", "start_time": now, "end_time": 0, "tools_used": [], "commits": 0}],
        )
        self._save_session(session)
        self._scaffold_templates(session)

        # Git integration: create feature branch
        if git_branch:
            self._create_branch(organ_key, slug)

        print(f"\n  Session started: {session_id}")
        print(f"  Organ: {organ_key} | Repo: {repo}")
        print(f"  Scope: {scope}")
        print(f"  Phase: FRAME")
        print(f"  AI Role: {PHASE_ROLES['FRAME']}")
        print(f"  Active clusters: {', '.join(self.phase_clusters.get('FRAME', []))}")
        print(f"\n  Templates scaffolded in: {SESSIONS_DIR / session_id}/")

        # Show cumulative stats
        stats = _load_stats()
        if stats["total_sessions"] > 0:
            ship_rate = stats["shipped"] / stats["total_sessions"] * 100
            print(f"  Lifetime: {stats['total_sessions']} sessions, {stats['total_minutes']}m, {ship_rate:.0f}% ship rate")
        print()

        return session

    def _create_branch(self, organ_key: str, slug: str) -> None:
        """Create a feature branch if we're in a git repo."""
        branch = f"feat/{organ_short(organ_key).lower()}/{slug}"
        try:
            # Check if in a git repo
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return

            # Check if branch exists
            result = subprocess.run(
                ["git", "branch", "--list", branch],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                print(f"  Branch exists: {branch}")
                return

            result = subprocess.run(
                ["git", "checkout", "-b", branch],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                print(f"  Branch created: {branch}")
            else:
                print(f"  WARNING: Could not create branch: {result.stderr.strip()}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # No git — that's fine

    def _scaffold_templates(self, session: Session) -> None:
        """Copy and fill templates for this session."""
        session_dir = SESSIONS_DIR / session.session_id
        session_dir.mkdir(exist_ok=True)

        date_str = datetime.now().strftime("%Y-%m-%d")
        replacements = {
            "{{ scope }}": session.scope,
            "{{ organ }}": session.organ,
            "{{ repo }}": session.repo,
            "{{ session_id }}": session.session_id,
            "{{ date }}": date_str,
        }

        for template_name in ["spec.md", "plan.md", "status.md"]:
            src = TEMPLATES_DIR / template_name
            if src.exists():
                content = src.read_text()
                for old, new in replacements.items():
                    content = content.replace(old, new)
                (session_dir / template_name).write_text(content)

    def phase(self, target_phase: str) -> None:
        """Transition to a new phase."""
        session = self._load_session()
        if not session:
            raise SessionError("No active session. Start one with `conductor session start`.")

        target = target_phase.upper()
        current = session.current_phase

        if target not in VALID_TRANSITIONS.get(current, []):
            valid = VALID_TRANSITIONS.get(current, [])
            raise SessionError(
                f"Cannot transition {current} -> {target}. "
                f"Valid transitions from {current}: {', '.join(valid)}"
            )

        now = time.time()
        for pl in session.phase_logs:
            if pl["name"] == current and pl["end_time"] == 0:
                pl["end_time"] = now
                break

        if target == "DONE":
            session.current_phase = "DONE"
            session.result = "SHIPPED"
            self._save_session(session)
            print(f"\n  Phase: {current} -> DONE")
            print(f"  Session marked SHIPPED. Run `conductor session close` to save log.")
            print()
            return

        session.phase_logs.append({
            "name": target,
            "start_time": now,
            "end_time": 0,
            "tools_used": [],
            "commits": 0,
        })
        session.current_phase = target
        self._save_session(session)

        is_back = PHASES.index(target) < PHASES.index(current) if target in PHASES and current in PHASES else False
        direction = "(reshape)" if is_back else ""

        print(f"\n  Phase: {current} -> {target} {direction}")
        print(f"  AI Role: {PHASE_ROLES.get(target, 'N/A')}")
        print(f"  Active clusters: {', '.join(self.phase_clusters.get(target, []))}")
        print()

    def status(self) -> None:
        """Show current session status."""
        session = self._load_session()
        if not session:
            print("  No active session.")
            return

        print(f"\n  Session: {session.session_id}")
        print(f"  Organ: {session.organ} | Repo: {session.repo}")
        print(f"  Scope: {session.scope}")
        print(f"  Phase: {session.current_phase}")
        print(f"  Duration: {session.duration_minutes} minutes")
        print(f"  Result: {session.result}")

        if session.current_phase in PHASE_ROLES:
            print(f"  AI Role: {PHASE_ROLES[session.current_phase]}")
            print(f"  Active clusters: {', '.join(self.phase_clusters.get(session.current_phase, []))}")

        if session.warnings:
            print(f"\n  Warnings ({len(session.warnings)}):")
            for w in session.warnings:
                print(f"    - {w}")

        print(f"\n  Phase history:")
        for pl in session.phase_logs:
            dur = int((pl.get("end_time") or time.time()) - pl["start_time"]) // 60
            status_marker = "*" if pl.get("end_time", 0) == 0 else " "
            tools = ", ".join(pl.get("tools_used", [])) or "none"
            print(f"  {status_marker} {pl['name']:<8} {dur:>3}m  commits={pl.get('commits', 0)}  tools=[{tools}]")
        print()

    def log_tool(self, tool_name: str) -> None:
        """Record a tool use in the current phase. Warn if wrong phase."""
        session = self._load_session()
        if not session:
            return

        current_clusters = set(self.phase_clusters.get(session.current_phase, []))
        tool_cluster = self._find_tool_cluster(tool_name)

        if tool_cluster and tool_cluster not in current_clusters:
            warning = f"Tool '{tool_name}' (cluster: {tool_cluster}) used during {session.current_phase} -- belongs to different phase"
            session.warnings.append(warning)
            print(f"  WARNING: {warning}")

        for pl in session.phase_logs:
            if pl["name"] == session.current_phase and pl.get("end_time", 0) == 0:
                if tool_name not in pl["tools_used"]:
                    pl["tools_used"].append(tool_name)
                break

        self._save_session(session)

    def _find_tool_cluster(self, tool_name: str) -> Optional[str]:
        """Find which cluster a tool belongs to (exact match, case-insensitive)."""
        if not self.ontology:
            return None
        tool_lower = tool_name.lower()
        for cid, cluster in self.ontology.clusters.items():
            for t in cluster.tools:
                if isinstance(t, str):
                    name = t
                elif isinstance(t, dict):
                    name = str(list(t.values())[0]) if t else ""
                else:
                    name = str(t)
                if tool_lower == name.lower():
                    return cid
        return None

    def close(self) -> None:
        """Close the session and generate the session log."""
        session = self._load_session()
        if not session:
            raise SessionError("No active session to close.")

        now = time.time()
        for pl in session.phase_logs:
            if pl.get("end_time", 0) == 0:
                pl["end_time"] = now

        if session.result == "IN_PROGRESS":
            session.result = "CLOSED"

        # Build YAML log — merge duplicate phases (reshape visits tracked)
        phase_summary: dict[str, dict] = {}
        for pl in session.phase_logs:
            dur = int((pl["end_time"] - pl["start_time"]) / 60)
            name = pl["name"]
            if name in phase_summary:
                phase_summary[name]["duration"] += dur
                for t in pl.get("tools_used", []):
                    if t not in phase_summary[name]["tools_used"]:
                        phase_summary[name]["tools_used"].append(t)
                phase_summary[name]["commits"] += pl.get("commits", 0)
                phase_summary[name]["visits"] += 1
            else:
                phase_summary[name] = {
                    "duration": dur,
                    "tools_used": list(pl.get("tools_used", [])),
                    "commits": pl.get("commits", 0),
                    "visits": 1,
                }

        log = {
            "session_id": session.session_id,
            "organ": session.organ,
            "repo": session.repo,
            "scope": session.scope,
            "duration_minutes": int((now - session.start_time) / 60),
            "phases": phase_summary,
            "warnings": session.warnings,
            "result": session.result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        session_dir = SESSIONS_DIR / session.session_id
        session_dir.mkdir(exist_ok=True)
        log_path = session_dir / "session-log.yaml"
        log_path.write_text(yaml.dump(log, default_flow_style=False, sort_keys=False))

        # Git integration: commit breadcrumb
        self._commit_breadcrumb(session)

        # Update cumulative stats
        stats = _update_stats(log)

        self._clear_session()

        print(f"\n  Session closed: {session.session_id}")
        print(f"  Duration: {log['duration_minutes']} minutes")
        print(f"  Result: {session.result}")
        print(f"  Log saved: {log_path}")
        if session.warnings:
            print(f"  Warnings: {len(session.warnings)}")

        # Cumulative stats line
        ship_rate = stats["shipped"] / stats["total_sessions"] * 100 if stats["total_sessions"] else 0
        print(f"  Lifetime: session #{stats['total_sessions']} | {stats['total_minutes']}m total | {ship_rate:.0f}% ship rate")

        # Milestones
        n = stats["total_sessions"]
        if n in (1, 5, 10, 25, 50, 100):
            print(f"  MILESTONE: {n} sessions completed!")
        print()

    def _commit_breadcrumb(self, session: Session) -> None:
        """Commit session artifacts as a breadcrumb if in a git repo."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return

            session_dir = SESSIONS_DIR / session.session_id
            result = subprocess.run(
                ["git", "add", str(session_dir)],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                print(f"  WARNING: git add failed: {result.stderr.strip()}")
                return

            msg = f"session: close {session.session_id} [{session.result}]"
            result = subprocess.run(
                ["git", "commit", "-m", msg, "--allow-empty"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                print(f"  WARNING: git commit failed: {result.stderr.strip()}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
