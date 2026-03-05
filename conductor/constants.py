"""Shared constants, paths, and organ mapping."""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE = Path(__file__).parent.parent  # tool-interaction-design/
ONTOLOGY_PATH = BASE / "ontology.yaml"
ROUTING_PATH = BASE / "routing-matrix.yaml"
WORKFLOW_DSL_PATH = BASE / "workflow-dsl.yaml"
SESSIONS_DIR = BASE / "sessions"
TEMPLATES_DIR = BASE / "templates"
GENERATED_DIR = BASE / "generated"
EXPORTS_DIR = BASE / "exports"
SESSION_STATE_FILE = BASE / ".conductor-session.json"
STATS_FILE = BASE / ".conductor-stats.json"
CONFIG_FILE = BASE / ".conductor.yaml"

# Workspace paths (mirror organvm-engine conventions)
WORKSPACE = Path(os.environ.get("ORGANVM_WORKSPACE_DIR", str(Path.home() / "Workspace")))
CORPUS_DIR = Path(os.environ.get(
    "ORGANVM_CORPUS_DIR",
    str(WORKSPACE / "meta-organvm" / "organvm-corpvs-testamentvm"),
))
REGISTRY_PATH = CORPUS_DIR / "registry-v2.json"
GOVERNANCE_PATH = CORPUS_DIR / "governance-rules.json"

# ---------------------------------------------------------------------------
# Organ mapping (inline to avoid hard dependency on organvm-engine)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Phase configuration (defaults — overridable via .conductor.yaml)
# ---------------------------------------------------------------------------

PHASES = ["FRAME", "SHAPE", "BUILD", "PROVE"]

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

PHASE_INSTRUMENTS: dict[str, str] = {
    "FRAME": "Viola (Depth/Research)",
    "SHAPE": "First Violin (Lead/Architecture)",
    "BUILD": "Second Violin (Implementation)",
    "PROVE": "Cello (Verification)",
}

ROLE_ACTIONS: dict[str, dict[str, list[str]]] = {
    "FRAME": {
        "allowed": ["Analyze requirements", "Find prior art", "Fetch documentation"],
        "forbidden": ["Write implementation code", "Modify governance rules"],
    },
    "SHAPE": {
        "allowed": ["Design architecture", "Create plan.md", "Diagram systems"],
        "forbidden": ["Implement business logic", "Skip architectural review"],
    },
    "BUILD": {
        "allowed": ["Write code bounded by plan.md", "Generate unit tests", "Refactor within scope"],
        "forbidden": ["Add new dependencies without approval", "Change architecture"],
    },
    "PROVE": {
        "allowed": ["Run test suites", "Security scanning", "E2E verification"],
        "forbidden": ["Fix code directly (report only)", "Modify specs"],
    },
}

VALID_TRANSITIONS: dict[str, list[str]] = {
    "FRAME": ["SHAPE"],
    "SHAPE": ["BUILD", "FRAME"],
    "BUILD": ["PROVE", "SHAPE"],
    "PROVE": ["DONE", "BUILD"],
}

PROMOTION_TRANSITIONS: dict[str, list[str]] = {
    "LOCAL": ["CANDIDATE", "ARCHIVED"],
    "CANDIDATE": ["PUBLIC_PROCESS", "LOCAL", "ARCHIVED"],
    "PUBLIC_PROCESS": ["GRADUATED", "CANDIDATE", "ARCHIVED"],
    "GRADUATED": ["ARCHIVED"],
    "ARCHIVED": [],
}

PROMOTION_STATES = {"LOCAL", "CANDIDATE", "PUBLIC_PROCESS", "GRADUATED", "ARCHIVED"}

# WIP limits
MAX_CANDIDATE_PER_ORGAN = 3
MAX_PUBLIC_PROCESS_PER_ORGAN = 1


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConductorError(Exception):
    """Base exception for conductor errors."""


class SessionError(ConductorError):
    """Session lifecycle errors (no active session, invalid transition, etc.)."""


class GovernanceError(ConductorError):
    """Governance/registry errors (WIP blocked, repo not found, etc.)."""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_organ_key(organ: str) -> str:
    """Resolve shorthand (III, META) to registry key (ORGAN-III, META-ORGANVM)."""
    organ = organ.upper().strip()
    if organ in ORGANS:
        return ORGANS[organ]["registry_key"]
    for v in ORGANS.values():
        if v["registry_key"] == organ:
            return organ
    return organ


def organ_short(registry_key: str) -> str:
    """ORGAN-III -> III, META-ORGANVM -> META."""
    for k, v in ORGANS.items():
        if v["registry_key"] == registry_key:
            return k
    return registry_key


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


def load_config() -> dict:
    """Load .conductor.yaml if it exists, returning phase overrides."""
    if CONFIG_FILE.exists():
        import yaml
        return yaml.safe_load(CONFIG_FILE.read_text()) or {}
    return {}


def get_phase_clusters() -> dict[str, list[str]]:
    """Return phase-cluster mapping, with .conductor.yaml overrides applied."""
    config = load_config()
    custom = config.get("phases", {})
    if custom:
        merged = dict(PHASE_CLUSTERS)
        for phase, clusters in custom.items():
            phase_upper = phase.upper()
            if phase_upper in merged and isinstance(clusters, list):
                merged[phase_upper] = clusters
        return merged
    return PHASE_CLUSTERS
