#!/usr/bin/env python3
"""
conductor — The AI-Conductor's Operating System
=================================================
Three-layer CLI that forces the FRAME/SHAPE/BUILD/PROVE lifecycle
on every work session, enforces governance as runtime constraints,
and exports its own process as the sellable product.

Layer 1: SESSION ENGINE       → What you use every day     (GROW)
Layer 2: GOVERNANCE RUNTIME   → What prevents the labyrinth (EFFICIENCY)
Layer 3: PRODUCT EXTRACTOR    → What you sell              (COMMODIFY)

Usage:
  python3 conductor.py session start --organ III --repo my-repo --scope "Add feature"
  python3 conductor.py session phase shape
  python3 conductor.py session status
  python3 conductor.py session close

  python3 conductor.py registry sync
  python3 conductor.py wip check
  python3 conductor.py wip promote <repo> <state>
  python3 conductor.py enforce generate [--dry-run]
  python3 conductor.py stale [--days 30]
  python3 conductor.py audit --organ III

  python3 conductor.py export process-kit [--output ./exports/]
  python3 conductor.py patterns
  python3 conductor.py export audit-report [--organ III]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# Import router.py classes
from router import Ontology, RoutingEngine

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE = Path(__file__).parent
ONTOLOGY_PATH = BASE / "ontology.yaml"
ROUTING_PATH = BASE / "routing-matrix.yaml"
SESSIONS_DIR = BASE / "sessions"
TEMPLATES_DIR = BASE / "templates"
GENERATED_DIR = BASE / "generated"
EXPORTS_DIR = BASE / "exports"
SESSION_STATE_FILE = BASE / ".conductor-session.json"

# Workspace paths (mirror organvm-engine conventions)
WORKSPACE = Path(os.environ.get("ORGANVM_WORKSPACE_DIR", str(Path.home() / "Workspace")))
CORPUS_DIR = Path(os.environ.get(
    "ORGANVM_CORPUS_DIR",
    str(WORKSPACE / "meta-organvm" / "organvm-corpvs-testamentvm"),
))
REGISTRY_PATH = CORPUS_DIR / "registry-v2.json"
GOVERNANCE_PATH = CORPUS_DIR / "governance-rules.json"

# Organ mapping (inline to avoid hard dependency on organvm-engine)
ORGANS: dict[str, dict[str, str]] = {
    "I":    {"dir": "organvm-i-theoria",   "registry_key": "ORGAN-I",      "org": "ivviiviivvi"},
    "II":   {"dir": "organvm-ii-poiesis",  "registry_key": "ORGAN-II",     "org": "omni-dromenon-machina"},
    "III":  {"dir": "organvm-iii-ergon",    "registry_key": "ORGAN-III",    "org": "labores-profani-crux"},
    "IV":   {"dir": "organvm-iv-taxis",     "registry_key": "ORGAN-IV",     "org": "organvm-iv-taxis"},
    "V":    {"dir": "organvm-v-logos",      "registry_key": "ORGAN-V",      "org": "organvm-v-logos"},
    "VI":   {"dir": "organvm-vi-koinonia",  "registry_key": "ORGAN-VI",     "org": "organvm-vi-koinonia"},
    "VII":  {"dir": "organvm-vii-kerygma",  "registry_key": "ORGAN-VII",    "org": "organvm-vii-kerygma"},
    "META": {"dir": "meta-organvm",         "registry_key": "META-ORGANVM", "org": "meta-organvm"},
}


def resolve_organ_key(organ: str) -> str:
    """Resolve shorthand (III, META) to registry key (ORGAN-III, META-ORGANVM)."""
    organ = organ.upper().strip()
    if organ in ORGANS:
        return ORGANS[organ]["registry_key"]
    # Already a registry key?
    for v in ORGANS.values():
        if v["registry_key"] == organ:
            return organ
    return organ


def atomic_write(path: Path, content: str) -> None:
    """Write to a temp file then rename — prevents corruption on interrupt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def organ_short(registry_key: str) -> str:
    """ORGAN-III → III, META-ORGANVM → META."""
    for k, v in ORGANS.items():
        if v["registry_key"] == registry_key:
            return k
    return registry_key


# =============================================================================
# LAYER 1: SESSION ENGINE
# =============================================================================

PHASES = ["FRAME", "SHAPE", "BUILD", "PROVE"]

# Phase → tool clusters from tool-surface-integration.yaml
PHASE_CLUSTERS: dict[str, list[str]] = {
    "FRAME": [
        "sequential_thinking", "web_search", "academic_research",
        "documentation", "knowledge_graph", "knowledge_apps",
    ],
    "SHAPE": [
        "sequential_thinking", "code_analysis_mcp", "diagramming",
        "neon_database",
    ],
    "BUILD": [
        "claude_code_core", "code_execution", "code_quality_cli",
        "git_core", "jupyter_notebooks",
    ],
    "PROVE": [
        "code_quality_cli", "security_scanning", "browser_playwright",
        "browser_chrome", "github_platform", "vercel_platform",
        "sentry_monitoring",
    ],
}

PHASE_ROLES: dict[str, str] = {
    "FRAME": "Librarian + Architect",
    "SHAPE": "Architect",
    "BUILD": "Implementer + Tester",
    "PROVE": "Tester + Reviewer",
}

VALID_TRANSITIONS: dict[str, list[str]] = {
    "FRAME": ["SHAPE"],
    "SHAPE": ["BUILD", "FRAME"],  # reshape allowed
    "BUILD": ["PROVE", "SHAPE"],  # back to shape if architecture changes
    "PROVE": ["DONE", "BUILD"],   # fail → back to build
}


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

    def current_phase_log(self) -> dict:
        for pl in self.phase_logs:
            if pl["name"] == self.current_phase and pl["end_time"] == 0:
                return pl
        return {}

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


class SessionEngine:
    """Layer 1: FRAME/SHAPE/BUILD/PROVE lifecycle engine."""

    def __init__(self, ontology: Ontology):
        self.ontology = ontology
        SESSIONS_DIR.mkdir(exist_ok=True)

    def _load_session(self) -> Optional[Session]:
        if SESSION_STATE_FILE.exists():
            try:
                data = json.loads(SESSION_STATE_FILE.read_text())
                return Session.from_dict(data)
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                print(f"  WARNING: Session state corrupted ({e}).")
                answer = input("  Reset session state? [y/N] ")
                if answer.lower() in ("y", "yes"):
                    self._clear_session()
                    print("  Session state cleared.")
                else:
                    print("  Aborting. Fix or delete .conductor-session.json manually.")
                    sys.exit(1)
        return None

    def _save_session(self, session: Session) -> None:
        atomic_write(SESSION_STATE_FILE, json.dumps(session.to_dict(), indent=2))

    def _clear_session(self) -> None:
        if SESSION_STATE_FILE.exists():
            SESSION_STATE_FILE.unlink()

    def start(self, organ: str, repo: str, scope: str) -> Session:
        """Start a new session."""
        if self._load_session():
            print("  ERROR: Session already active. Close it first with `conductor session close`.")
            sys.exit(1)

        organ_key = resolve_organ_key(organ)
        now = time.time()
        date_str = datetime.now().strftime("%Y-%m-%d")
        slug = scope.lower().replace(" ", "-")[:40]
        session_id = f"{date_str}-{organ_short(organ_key)}-{slug}"

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

        # Scaffold templates
        self._scaffold_templates(session)

        print(f"\n  Session started: {session_id}")
        print(f"  Organ: {organ_key} | Repo: {repo}")
        print(f"  Scope: {scope}")
        print(f"  Phase: FRAME")
        print(f"  AI Role: {PHASE_ROLES['FRAME']}")
        print(f"  Active clusters: {', '.join(PHASE_CLUSTERS['FRAME'])}")
        print(f"\n  Templates scaffolded in: {SESSIONS_DIR / session_id}/")
        print()

        return session

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
            print("  ERROR: No active session. Start one with `conductor session start`.")
            sys.exit(1)

        target = target_phase.upper()
        current = session.current_phase

        if target not in VALID_TRANSITIONS.get(current, []):
            valid = VALID_TRANSITIONS.get(current, [])
            print(f"  ERROR: Cannot transition {current} → {target}.")
            print(f"  Valid transitions from {current}: {', '.join(valid)}")
            sys.exit(1)

        # Close current phase log
        now = time.time()
        for pl in session.phase_logs:
            if pl["name"] == current and pl["end_time"] == 0:
                pl["end_time"] = now
                break

        if target == "DONE":
            session.current_phase = "DONE"
            session.result = "SHIPPED"
            self._save_session(session)
            print(f"\n  Phase: {current} → DONE")
            print(f"  Session marked SHIPPED. Run `conductor session close` to save log.")
            print()
            return

        # Open new phase log
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

        print(f"\n  Phase: {current} → {target} {direction}")
        print(f"  AI Role: {PHASE_ROLES.get(target, 'N/A')}")
        print(f"  Active clusters: {', '.join(PHASE_CLUSTERS.get(target, []))}")
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
            print(f"  Active clusters: {', '.join(PHASE_CLUSTERS.get(session.current_phase, []))}")

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

        # Check if tool's cluster belongs to current phase
        current_clusters = set(PHASE_CLUSTERS.get(session.current_phase, []))
        tool_cluster = self._find_tool_cluster(tool_name)

        if tool_cluster and tool_cluster not in current_clusters:
            warning = f"Tool '{tool_name}' (cluster: {tool_cluster}) used during {session.current_phase} — belongs to different phase"
            session.warnings.append(warning)
            print(f"  WARNING: {warning}")

        # Record in current phase log
        for pl in session.phase_logs:
            if pl["name"] == session.current_phase and pl.get("end_time", 0) == 0:
                if tool_name not in pl["tools_used"]:
                    pl["tools_used"].append(tool_name)
                break

        self._save_session(session)

    def _find_tool_cluster(self, tool_name: str) -> Optional[str]:
        """Find which cluster a tool belongs to (exact match, case-insensitive)."""
        tool_lower = tool_name.lower()
        for cid, cluster in self.ontology.clusters.items():
            for t in cluster.tools:
                # Normalize: handle bare strings, dicts like {mcp: name}, etc.
                if isinstance(t, str):
                    name = t
                elif isinstance(t, dict):
                    name = str(list(t.values())[0]) if t else ""
                else:
                    name = str(t)
                # Exact match on the tool name portion
                if tool_lower == name.lower():
                    return cid
        return None

    def close(self) -> None:
        """Close the session and generate the session log."""
        session = self._load_session()
        if not session:
            print("  ERROR: No active session to close.")
            sys.exit(1)

        now = time.time()

        # Close any open phase log
        for pl in session.phase_logs:
            if pl.get("end_time", 0) == 0:
                pl["end_time"] = now

        if session.result == "IN_PROGRESS":
            session.result = "CLOSED"

        # Build YAML log — merge duplicate phases (e.g., FRAME→SHAPE→FRAME reshape)
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

        # Write log
        session_dir = SESSIONS_DIR / session.session_id
        session_dir.mkdir(exist_ok=True)
        log_path = session_dir / "session-log.yaml"
        log_path.write_text(yaml.dump(log, default_flow_style=False, sort_keys=False))

        self._clear_session()

        print(f"\n  Session closed: {session.session_id}")
        print(f"  Duration: {log['duration_minutes']} minutes")
        print(f"  Result: {session.result}")
        print(f"  Log saved: {log_path}")
        if session.warnings:
            print(f"  Warnings: {len(session.warnings)}")
        print()


# =============================================================================
# LAYER 2: GOVERNANCE RUNTIME
# =============================================================================

# WIP limits
MAX_CANDIDATE_PER_ORGAN = 3
MAX_PUBLIC_PROCESS_PER_ORGAN = 1


class GovernanceRuntime:
    """Layer 2: Registry sync, WIP enforcement, staleness, audit."""

    def __init__(self) -> None:
        self.registry: dict = {}
        self.governance: dict = {}
        self._load()

    def _load(self) -> None:
        if REGISTRY_PATH.exists():
            self.registry = json.loads(REGISTRY_PATH.read_text())
        else:
            print(f"  WARNING: Registry not found at {REGISTRY_PATH}")

        if GOVERNANCE_PATH.exists():
            self.governance = json.loads(GOVERNANCE_PATH.read_text())
        else:
            print(f"  WARNING: Governance rules not found at {GOVERNANCE_PATH}")

    def _all_repos(self) -> list[tuple[str, dict]]:
        """Yield (organ_key, repo_dict) for every repo in registry."""
        results = []
        for organ_key, organ_data in self.registry.get("organs", {}).items():
            for repo in organ_data.get("repositories", []):
                results.append((organ_key, repo))
        return results

    # ----- Registry Sync -----

    def registry_sync(self) -> None:
        """Compare GitHub API repos vs registry, report delta."""
        print("\n  Registry Sync")
        print("  " + "=" * 50)

        # Get repos from GitHub orgs
        github_repos: dict[str, list[str]] = {}
        for short_key, meta in ORGANS.items():
            org = meta["org"]
            try:
                result = subprocess.run(
                    ["gh", "repo", "list", org, "--json", "name", "--limit", "200"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    repos = json.loads(result.stdout)
                    github_repos[meta["registry_key"]] = [r["name"] for r in repos]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                print(f"  WARNING: Could not fetch repos for {org} (gh CLI unavailable?)")
                github_repos[meta["registry_key"]] = []

        # Compare with registry
        registry_repos: dict[str, set[str]] = {}
        for organ_key, repo in self._all_repos():
            registry_repos.setdefault(organ_key, set()).add(repo["name"])

        total_gh = sum(len(v) for v in github_repos.values())
        total_reg = sum(len(v) for v in registry_repos.values())

        print(f"\n  GitHub API: {total_gh} repos")
        print(f"  Registry:   {total_reg} repos")

        missing_from_registry = []
        for organ_key, gh_names in github_repos.items():
            reg_names = registry_repos.get(organ_key, set())
            for name in gh_names:
                if name not in reg_names:
                    missing_from_registry.append((organ_key, name))

        missing_from_github = []
        for organ_key, reg_names in registry_repos.items():
            gh_names = set(github_repos.get(organ_key, []))
            for name in reg_names:
                if name not in gh_names:
                    missing_from_github.append((organ_key, name))

        if missing_from_registry:
            print(f"\n  Missing from registry ({len(missing_from_registry)}):")
            for organ_key, name in missing_from_registry:
                print(f"    + [{organ_key}] {name}")
        else:
            print(f"\n  Registry is complete — all GitHub repos accounted for.")

        if missing_from_github:
            print(f"\n  In registry but not on GitHub ({len(missing_from_github)}):")
            for organ_key, name in missing_from_github:
                print(f"    - [{organ_key}] {name}")

        print()

    # ----- WIP Check -----

    def wip_check(self) -> None:
        """Show WIP counts per organ, flag violations."""
        print("\n  WIP Status")
        print("  " + "=" * 50)

        counts: dict[str, Counter] = defaultdict(Counter)
        for organ_key, repo in self._all_repos():
            status = repo.get("promotion_status", "UNKNOWN")
            counts[organ_key][status] += 1

        total_candidate = 0
        violations = []

        print(f"\n  {'ORGAN':<16} {'LOCAL':>5} {'CAND':>5} {'PUB_P':>5} {'GRAD':>5} {'ARCH':>5} {'FLAGS':>6}")
        print(f"  {'─'*16} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*6}")

        for organ_key in sorted(counts.keys()):
            c = counts[organ_key]
            local = c.get("LOCAL", 0)
            cand = c.get("CANDIDATE", 0)
            pub = c.get("PUBLIC_PROCESS", 0)
            grad = c.get("GRADUATED", 0)
            arch = c.get("ARCHIVED", 0)
            total_candidate += cand

            flags = []
            if cand > MAX_CANDIDATE_PER_ORGAN:
                flags.append(f"CAND>{MAX_CANDIDATE_PER_ORGAN}")
                violations.append(f"{organ_key}: {cand} CANDIDATE (limit {MAX_CANDIDATE_PER_ORGAN})")

            flag_str = ", ".join(flags) if flags else ""
            short = organ_short(organ_key)
            print(f"  {short:<16} {local:>5} {cand:>5} {pub:>5} {grad:>5} {arch:>5}  {flag_str}")

        print(f"\n  Total CANDIDATE across system: {total_candidate}")

        if violations:
            print(f"\n  WIP VIOLATIONS ({len(violations)}):")
            for v in violations:
                print(f"    ! {v}")
        else:
            print(f"  No WIP violations.")
        print()

    # ----- WIP Promote -----

    def wip_promote(self, repo_name: str, target_state: str) -> None:
        """Promote a repo with WIP limit enforcement."""
        target_state = target_state.upper()

        valid_states = {"LOCAL", "CANDIDATE", "PUBLIC_PROCESS", "GRADUATED", "ARCHIVED"}
        if target_state not in valid_states:
            print(f"  ERROR: Invalid state '{target_state}'. Valid: {', '.join(sorted(valid_states))}")
            sys.exit(1)

        # Find repo
        found = None
        for organ_key, repo in self._all_repos():
            if repo["name"] == repo_name:
                found = (organ_key, repo)
                break

        if not found:
            print(f"  ERROR: Repo '{repo_name}' not found in registry.")
            sys.exit(1)

        organ_key, repo = found
        current = repo.get("promotion_status", "LOCAL")

        # Check state machine
        transitions = {
            "LOCAL": ["CANDIDATE", "ARCHIVED"],
            "CANDIDATE": ["PUBLIC_PROCESS", "LOCAL", "ARCHIVED"],
            "PUBLIC_PROCESS": ["GRADUATED", "CANDIDATE", "ARCHIVED"],
            "GRADUATED": ["ARCHIVED"],
            "ARCHIVED": [],
        }
        if target_state not in transitions.get(current, []):
            print(f"  ERROR: Cannot transition {current} → {target_state}.")
            print(f"  Valid transitions: {', '.join(transitions.get(current, ['none']))}")
            sys.exit(1)

        # Check WIP limits for target state
        all_repos = self._all_repos()

        if target_state == "CANDIDATE":
            cand_count = sum(
                1 for ok, r in all_repos
                if ok == organ_key and r.get("promotion_status") == "CANDIDATE"
            )
            if cand_count >= MAX_CANDIDATE_PER_ORGAN:
                print(f"  BLOCKED: {organ_key} already has {cand_count} CANDIDATE repos (limit {MAX_CANDIDATE_PER_ORGAN}).")
                print(f"  Promote or archive existing CANDIDATE repos first.")
                print(f"\n  Current CANDIDATE repos in {organ_key}:")
                for ok, r in all_repos:
                    if ok == organ_key and r.get("promotion_status") == "CANDIDATE":
                        print(f"    - {r['name']}")
                sys.exit(1)

        if target_state == "PUBLIC_PROCESS":
            pub_count = sum(
                1 for ok, r in all_repos
                if ok == organ_key and r.get("promotion_status") == "PUBLIC_PROCESS"
            )
            if pub_count >= MAX_PUBLIC_PROCESS_PER_ORGAN:
                print(f"  BLOCKED: {organ_key} already has {pub_count} PUBLIC_PROCESS repos (limit {MAX_PUBLIC_PROCESS_PER_ORGAN}).")
                print(f"  Graduate or archive existing PUBLIC_PROCESS repos first.")
                sys.exit(1)

        # Confirm
        if not getattr(self, '_skip_confirm', False):
            answer = input(f"  Promote {repo_name}: {current} → {target_state}? [y/N] ")
            if answer.lower() not in ("y", "yes"):
                print("  Aborted.")
                return

        # Apply promotion
        repo["promotion_status"] = target_state
        repo["last_validated"] = datetime.now().strftime("%Y-%m-%d")

        # Save registry with backup
        if REGISTRY_PATH.exists():
            backup = REGISTRY_PATH.with_suffix(".json.bak")
            shutil.copy2(REGISTRY_PATH, backup)
        atomic_write(REGISTRY_PATH, json.dumps(self.registry, indent=2) + "\n")

        print(f"\n  Promoted: {repo_name}")
        print(f"  {current} → {target_state}")
        print(f"  Registry updated: {REGISTRY_PATH}")
        print()

    # ----- Staleness -----

    def stale(self, days: int = 30) -> None:
        """Find CANDIDATE repos with no recent push."""
        print(f"\n  Stale CANDIDATE repos (no push in {days}+ days)")
        print("  " + "=" * 50)

        candidates = [
            (ok, r) for ok, r in self._all_repos()
            if r.get("promotion_status") == "CANDIDATE"
        ]

        if not candidates:
            print("  No CANDIDATE repos found.")
            print()
            return

        stale_repos = []
        for organ_key, repo in candidates:
            org = None
            for meta in ORGANS.values():
                if meta["registry_key"] == organ_key:
                    org = meta["org"]
                    break

            if not org:
                continue

            try:
                result = subprocess.run(
                    ["gh", "api", f"repos/{org}/{repo['name']}", "--jq", ".pushed_at"],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode == 0 and result.stdout.strip():
                    pushed = datetime.fromisoformat(result.stdout.strip().replace("Z", "+00:00"))
                    age = (datetime.now(timezone.utc) - pushed).days
                    if age >= days:
                        stale_repos.append((organ_key, repo["name"], age))
            except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
                stale_repos.append((organ_key, repo["name"], -1))

        if stale_repos:
            print(f"\n  Found {len(stale_repos)} stale CANDIDATE repos:\n")
            for organ_key, name, age in sorted(stale_repos, key=lambda x: -x[2]):
                age_str = f"{age}d" if age >= 0 else "unknown"
                print(f"    [{organ_short(organ_key)}] {name:<45} last push: {age_str} ago")
            print(f"\n  Suggestion: promote, archive, or work on these repos to unclog the pipeline.")
        else:
            print(f"  No stale CANDIDATE repos (all pushed within {days} days).")
        print()

    # ----- Enforce Generate -----

    def enforce_generate(self, dry_run: bool = False) -> None:
        """Generate GitHub rulesets and Actions from governance-rules.json."""
        print(f"\n  Generating enforcement artifacts {'(DRY RUN)' if dry_run else ''}")
        print("  " + "=" * 50)

        if not self.governance:
            print("  ERROR: No governance rules loaded.")
            sys.exit(1)

        output_dir = GENERATED_DIR
        if not dry_run:
            output_dir.mkdir(exist_ok=True)

        artifacts = []

        # 1. Generate org-level rulesets
        for short_key, meta in ORGANS.items():
            org = meta["org"]
            ruleset = {
                "name": f"{org}-branch-protection",
                "target": "branch",
                "enforcement": "active",
                "conditions": {
                    "ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []},
                },
                "rules": [
                    {"type": "pull_request", "parameters": {
                        "required_approving_review_count": 0,
                        "dismiss_stale_reviews_on_push": True,
                        "require_last_push_approval": False,
                    }},
                    {"type": "required_status_checks", "parameters": {
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": [{"context": "validate-lifecycle"}],
                    }},
                    {"type": "non_fast_forward"},
                ],
            }
            artifacts.append((f"rulesets/{org}.json", ruleset))

        # 2. Generate validate-lifecycle workflow
        lifecycle_workflow = {
            "name": "Validate Lifecycle",
            "on": {"pull_request": {"branches": ["main", "master"]}},
            "jobs": {
                "validate": {
                    "runs-on": "ubuntu-latest",
                    "steps": [
                        {"uses": "actions/checkout@v4"},
                        {"name": "Check spec.md exists", "run": "test -f spec.md || test -f docs/spec.md || echo 'WARNING: No spec.md found'"},
                        {"name": "Check plan.md exists", "run": "test -f plan.md || test -f docs/plan.md || echo 'WARNING: No plan.md found'"},
                        {"name": "Validate conventional commits", "run": "echo 'TODO: Add commitlint'"},
                    ],
                }
            },
        }
        artifacts.append(("workflows/validate-lifecycle.yml", lifecycle_workflow))

        # 3. Generate WIP validation workflow
        wip_workflow = {
            "name": "Validate WIP Limits",
            "on": {"workflow_dispatch": {}, "schedule": [{"cron": "0 6 * * 1"}]},
            "jobs": {
                "check-wip": {
                    "runs-on": "ubuntu-latest",
                    "steps": [
                        {"uses": "actions/checkout@v4"},
                        {"name": "Install conductor", "run": "pip install pyyaml"},
                        {"name": "Check WIP", "run": "python3 conductor.py wip check"},
                    ],
                }
            },
        }
        artifacts.append(("workflows/validate-wip.yml", wip_workflow))

        # 4. Generate PR template
        pr_template = """## Summary

<!-- What does this PR do? Reference the Issue. -->

## Governance Checklist

- [ ] spec.md exists and is current
- [ ] plan.md exists and steps are checked off
- [ ] All tests pass
- [ ] No WIP limit violations
- [ ] CHANGELOG updated
- [ ] Conventional commit messages used

## Phase

- [ ] FRAME complete (spec reviewed)
- [ ] SHAPE complete (plan approved)
- [ ] BUILD complete (code + tests)
- [ ] PROVE complete (lint + security + review)
"""
        artifacts.append(("PULL_REQUEST_TEMPLATE.md", pr_template))

        # 5. Generate Issue Form
        issue_form = {
            "name": "Feature Request (Conductor)",
            "description": "Propose a new feature using the FRAME/SHAPE/BUILD/PROVE lifecycle.",
            "body": [
                {"type": "dropdown", "id": "phase", "attributes": {
                    "label": "Current Phase",
                    "options": ["FRAME", "SHAPE", "BUILD", "PROVE"],
                }, "validations": {"required": True}},
                {"type": "input", "id": "organ", "attributes": {
                    "label": "Organ", "placeholder": "e.g., III",
                }, "validations": {"required": True}},
                {"type": "textarea", "id": "scope", "attributes": {
                    "label": "Scope", "placeholder": "What are you building?",
                }, "validations": {"required": True}},
                {"type": "textarea", "id": "acceptance", "attributes": {
                    "label": "Acceptance Criteria",
                }, "validations": {"required": True}},
            ],
        }
        artifacts.append(("ISSUE_TEMPLATE/feature-conductor.yml", issue_form))

        # Output
        for path, content in artifacts:
            if dry_run:
                print(f"\n  Would generate: {path}")
                if isinstance(content, str):
                    print(f"  ({len(content)} chars)")
                else:
                    print(f"  ({len(json.dumps(content))} chars)")
            else:
                full_path = output_dir / path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, str):
                    full_path.write_text(content)
                elif path.endswith(".yml") or path.endswith(".yaml"):
                    full_path.write_text(yaml.dump(content, default_flow_style=False, sort_keys=False))
                else:
                    full_path.write_text(json.dumps(content, indent=2))
                print(f"  Generated: {full_path}")

        total = len(artifacts)
        print(f"\n  {'Would generate' if dry_run else 'Generated'}: {total} artifacts")
        if not dry_run:
            print(f"  Output: {output_dir}/")
        print()

    # ----- Audit -----

    def audit(self, organ: Optional[str] = None) -> None:
        """Full organ or system health report."""
        print(f"\n  Audit Report: {organ or 'FULL SYSTEM'}")
        print("  " + "=" * 50)

        organs_to_check = {}
        if organ:
            key = resolve_organ_key(organ)
            organ_data = self.registry.get("organs", {}).get(key, {})
            if organ_data:
                organs_to_check[key] = organ_data
            else:
                print(f"  ERROR: Organ '{organ}' not found in registry.")
                sys.exit(1)
        else:
            organs_to_check = self.registry.get("organs", {})

        for organ_key, organ_data in organs_to_check.items():
            repos = organ_data.get("repositories", [])
            total = len(repos)

            # Counts
            statuses = Counter(r.get("promotion_status", "UNKNOWN") for r in repos)
            tiers = Counter(r.get("tier", "unknown") for r in repos)
            impl = Counter(r.get("implementation_status", "UNKNOWN") for r in repos)

            # Health checks
            missing_readme = [r["name"] for r in repos if r.get("documentation_status", "").upper() == "EMPTY"]
            missing_ci = [r["name"] for r in repos if not r.get("ci_workflow")]
            no_deps = [r["name"] for r in repos if not r.get("dependencies")]

            print(f"\n  [{organ_short(organ_key)}] {organ_data.get('name', organ_key)} — {total} repos")
            print(f"  {'─' * 50}")

            print(f"  Promotion: " + ", ".join(f"{s}={c}" for s, c in sorted(statuses.items())))
            print(f"  Tiers:     " + ", ".join(f"{t}={c}" for t, c in sorted(tiers.items())))
            print(f"  Impl:      " + ", ".join(f"{i}={c}" for i, c in sorted(impl.items())))

            if missing_readme:
                print(f"\n  CRITICAL: {len(missing_readme)} repos missing README:")
                for name in missing_readme[:5]:
                    print(f"    - {name}")

            if missing_ci:
                print(f"\n  WARNING: {len(missing_ci)} repos without CI:")
                for name in missing_ci[:5]:
                    print(f"    - {name}")

            # WIP check inline
            cand = statuses.get("CANDIDATE", 0)
            if cand > MAX_CANDIDATE_PER_ORGAN:
                print(f"\n  WIP VIOLATION: {cand} CANDIDATE (limit {MAX_CANDIDATE_PER_ORGAN})")

            # Recommendations
            recs = []
            if cand > MAX_CANDIDATE_PER_ORGAN:
                recs.append(f"Triage CANDIDATE repos: promote {cand - MAX_CANDIDATE_PER_ORGAN}+ to PUBLIC_PROCESS or archive")
            if missing_ci:
                recs.append(f"Add CI workflows to {len(missing_ci)} repos")
            if statuses.get("LOCAL", 0) > 0:
                recs.append(f"Evaluate {statuses['LOCAL']} LOCAL repos for CANDIDATE promotion")
            if not recs:
                recs.append("Organ is healthy — no immediate action needed")

            print(f"\n  Recommendations:")
            for r in recs:
                print(f"    → {r}")

        print()


# =============================================================================
# LAYER 3: PRODUCT EXTRACTOR
# =============================================================================


class ProductExtractor:
    """Layer 3: Export process, mine patterns, generate audit reports."""

    def __init__(self, governance: GovernanceRuntime) -> None:
        self.governance = governance

    def export_process_kit(self, output_dir: Optional[Path] = None) -> None:
        """Export templates and CI artifacts as a reusable process kit."""
        output = output_dir or EXPORTS_DIR / "process-kit"
        output.mkdir(parents=True, exist_ok=True)

        print(f"\n  Exporting Process Kit → {output}")
        print("  " + "=" * 50)

        # Copy templates
        templates_out = output / "templates"
        templates_out.mkdir(exist_ok=True)
        for f in TEMPLATES_DIR.glob("*.md"):
            shutil.copy2(f, templates_out / f.name)
            print(f"  + templates/{f.name}")

        # Copy generated CI artifacts if they exist
        if GENERATED_DIR.exists():
            for f in GENERATED_DIR.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(GENERATED_DIR)
                    dest = output / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest)
                    print(f"  + {rel}")

        # Generate a seed CLAUDE.md
        claude_md = output / "CLAUDE.md"
        claude_md.write_text("""# CLAUDE.md — Process Kit Template

## Session Workflow

This project uses the FRAME/SHAPE/BUILD/PROVE lifecycle:

1. **FRAME** — Define scope, research the problem, create spec.md
2. **SHAPE** — Design the approach, create plan.md, branch
3. **BUILD** — Implement step by step, test continuously
4. **PROVE** — Lint, security scan, create PR, review

## Templates

- `templates/spec.md` — FRAME output
- `templates/plan.md` — SHAPE output
- `templates/status.md` — Session close log

## Commands

```bash
python3 conductor.py session start --organ <ORGAN> --repo <REPO> --scope "Description"
python3 conductor.py session phase shape
python3 conductor.py session phase build
python3 conductor.py session phase prove
python3 conductor.py session close
```
""")
        print(f"  + CLAUDE.md")

        # Generate a README
        readme = output / "README.md"
        readme.write_text("""# Process Kit

A session-based development workflow built on the FRAME/SHAPE/BUILD/PROVE lifecycle.

## What's Included

- **Templates**: spec.md, plan.md, status.md — scaffolded per session
- **CI Workflows**: lifecycle validation, WIP limit checking
- **PR Template**: governance gates checklist
- **Issue Form**: lifecycle-aware feature requests
- **CLAUDE.md**: AI assistant configuration

## Quick Start

1. Copy this directory into your project
2. Install: `pip install pyyaml`
3. Run: `python3 conductor.py session start --organ III --repo my-repo --scope "My feature"`

## The Lifecycle

```
FRAME  →  SHAPE  →  BUILD  →  PROVE  →  DONE
  ↑          |                    |
  +----------+ (reshape)         +-- (fail → back to BUILD)
```

Each phase activates specific tool clusters and AI roles.
Built by the conductor operating system.
""")
        print(f"  + README.md")

        total = sum(1 for _ in output.rglob("*") if _.is_file())
        print(f"\n  Exported {total} files to {output}")
        print()

    def mine_patterns(self) -> None:
        """Mine session logs for recurring patterns."""
        print("\n  Pattern Mining")
        print("  " + "=" * 50)

        session_logs = list(SESSIONS_DIR.glob("*/session-log.yaml"))
        if not session_logs:
            print("  No session logs found. Complete some sessions first.")
            print()
            return

        # Aggregate data
        total_sessions = len(session_logs)
        phase_durations: dict[str, list[int]] = defaultdict(list)
        tool_frequency: Counter = Counter()
        warning_types: Counter = Counter()
        results: Counter = Counter()
        organs_used: Counter = Counter()

        for log_path in session_logs:
            log = yaml.safe_load(log_path.read_text())

            results[log.get("result", "UNKNOWN")] += 1
            organs_used[log.get("organ", "UNKNOWN")] += 1

            for phase_name, phase_data in log.get("phases", {}).items():
                if isinstance(phase_data, dict):
                    phase_durations[phase_name].append(phase_data.get("duration", 0))
                    for tool in phase_data.get("tools_used", []):
                        tool_frequency[tool] += 1

            for w in log.get("warnings", []):
                # Categorize warnings
                if "during FRAME" in w:
                    warning_types["phase_violation_FRAME"] += 1
                elif "during SHAPE" in w:
                    warning_types["phase_violation_SHAPE"] += 1
                elif "during BUILD" in w:
                    warning_types["phase_violation_BUILD"] += 1
                else:
                    warning_types["other"] += 1

        print(f"\n  Sessions analyzed: {total_sessions}")
        print(f"  Results: {dict(results)}")
        print(f"  Organs: {dict(organs_used)}")

        print(f"\n  Phase Duration Averages:")
        for phase in PHASES:
            durs = phase_durations.get(phase, [])
            if durs:
                avg = sum(durs) / len(durs)
                print(f"    {phase:<8} avg={avg:.0f}m  min={min(durs)}m  max={max(durs)}m  n={len(durs)}")

        if tool_frequency:
            print(f"\n  Top 10 Tools:")
            for tool, count in tool_frequency.most_common(10):
                print(f"    {tool:<35} {count}x")

        if warning_types:
            print(f"\n  Warning Patterns:")
            for wtype, count in warning_types.most_common():
                print(f"    {wtype:<35} {count}x")

        # Named patterns
        print(f"\n  Detected Patterns:")
        avg_frame = sum(phase_durations.get("FRAME", [0])) / max(len(phase_durations.get("FRAME", [1])), 1)
        avg_build = sum(phase_durations.get("BUILD", [0])) / max(len(phase_durations.get("BUILD", [1])), 1)

        if avg_frame > 20:
            print(f"    [DEEP_RESEARCH] FRAME phase averages {avg_frame:.0f}m — research-heavy workflow")
        elif avg_frame < 5:
            print(f"    [QUICK_FRAME] FRAME phase averages {avg_frame:.0f}m — consider more upfront research")

        if avg_build > 60:
            print(f"    [MARATHON_BUILD] BUILD phase averages {avg_build:.0f}m — consider smaller scopes")

        if warning_types.get("phase_violation_FRAME", 0) > total_sessions * 0.3:
            print(f"    [EAGER_CODER] Frequent code tool use during FRAME — slow down, research first")

        shipped = results.get("SHIPPED", 0)
        if total_sessions > 0:
            ship_rate = shipped / total_sessions * 100
            print(f"\n  Ship rate: {shipped}/{total_sessions} ({ship_rate:.0f}%)")

        print()

    def export_audit_report(self, organ: Optional[str] = None) -> None:
        """Generate a structured audit report."""
        print(f"\n  Generating Audit Report: {organ or 'FULL SYSTEM'}")
        print("  " + "=" * 50)

        # Delegate to governance audit for the data
        self.governance.audit(organ)

        # Also include session metrics if available
        session_logs = list(SESSIONS_DIR.glob("*/session-log.yaml"))
        if session_logs:
            print(f"\n  Session Metrics ({len(session_logs)} sessions):")
            total_minutes = 0
            for log_path in session_logs:
                log = yaml.safe_load(log_path.read_text())
                total_minutes += log.get("duration_minutes", 0)
            print(f"    Total session time: {total_minutes} minutes ({total_minutes / 60:.1f} hours)")
            print(f"    Average session: {total_minutes / len(session_logs):.0f} minutes")
        print()


# =============================================================================
# CLI
# =============================================================================


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

    p_phase = session_sub.add_parser("phase", help="Transition to next phase")
    p_phase.add_argument("target", help="Target phase (shape, build, prove, done)")

    session_sub.add_parser("status", help="Show current session status")
    session_sub.add_parser("close", help="Close session and generate log")

    p_log_tool = session_sub.add_parser("log-tool", help="Record a tool use")
    p_log_tool.add_argument("tool_name", help="Name of the tool used")

    # ----- Governance commands -----
    p_registry = sub.add_parser("registry", help="Registry operations")
    registry_sub = p_registry.add_subparsers(dest="registry_command", required=True)
    registry_sub.add_parser("sync", help="Sync registry with GitHub")

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

    # ----- Product commands -----
    p_export = sub.add_parser("export", help="Export artifacts")
    export_sub = p_export.add_subparsers(dest="export_command", required=True)
    p_kit = export_sub.add_parser("process-kit", help="Export process kit")
    p_kit.add_argument("--output", type=Path, help="Output directory")
    p_report = export_sub.add_parser("audit-report", help="Export audit report")
    p_report.add_argument("--organ", help="Organ key (default: full system)")

    sub.add_parser("patterns", help="Mine session logs for patterns")

    # ----- Router commands (inherited) -----
    p_route = sub.add_parser("route", help="Find routes between clusters")
    p_route.add_argument("--from", dest="from_cluster", required=True)
    p_route.add_argument("--to", dest="to_cluster", required=True)

    p_cap = sub.add_parser("capability", help="Find clusters by capability")
    p_cap.add_argument("cap", type=str)

    p_clusters = sub.add_parser("clusters", help="List all clusters")
    p_domains = sub.add_parser("domains", help="List all domains")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Load ontology for all commands
    ontology = Ontology(ONTOLOGY_PATH)
    engine = RoutingEngine(ROUTING_PATH, ontology)

    # Dispatch
    if args.command == "session":
        se = SessionEngine(ontology)
        if args.session_command == "start":
            se.start(args.organ, args.repo, args.scope)
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
            gov.registry_sync()

    elif args.command == "wip":
        gov = GovernanceRuntime()
        if args.wip_command == "check":
            gov.wip_check()
        elif args.wip_command == "promote":
            if args.yes:
                gov._skip_confirm = True
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
        gov.audit(organ=args.organ)

    elif args.command == "export":
        gov = GovernanceRuntime()
        pe = ProductExtractor(gov)
        if args.export_command == "process-kit":
            pe.export_process_kit(output_dir=args.output)
        elif args.export_command == "audit-report":
            pe.export_audit_report(organ=args.organ)

    elif args.command == "patterns":
        gov = GovernanceRuntime()
        pe = ProductExtractor(gov)
        pe.mine_patterns()

    elif args.command == "route":
        from router import cmd_route
        cmd_route(args, ontology, engine)

    elif args.command == "capability":
        # Reuse router capability logic
        from router import cmd_capability
        args.capability = args.cap
        cmd_capability(args, ontology, engine)

    elif args.command == "clusters":
        from router import cmd_clusters
        cmd_clusters(args, ontology, engine)

    elif args.command == "domains":
        from router import cmd_domains
        cmd_domains(args, ontology, engine)


if __name__ == "__main__":
    main()
