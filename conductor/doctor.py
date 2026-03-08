"""System doctor command for one-shot integrity and health diagnostics."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .constants import GOVERNANCE_PATH, ONTOLOGY_PATH, REGISTRY_PATH, ROUTING_PATH, ConductorError, get_phase_clusters
from .contracts import assert_contract
from .integrity import run_integrity_checks
from .migrate import migrate_governance, migrate_registry, write_migration_output
from .schemas import validate_document


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "hints": self.hints,
        }


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _schema_check(path: Path, document_type: str) -> DoctorCheck:
    if not path.exists():
        return DoctorCheck(
            name=f"schema:{document_type}",
            ok=False,
            errors=[f"Missing file: {path}"],
            hints=[f"Create {path} or point configuration to a valid {document_type} file."],
        )
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return DoctorCheck(
            name=f"schema:{document_type}",
            ok=False,
            errors=[f"Invalid JSON in {path}: {e}"],
            hints=["Fix JSON syntax or run migration command to normalize content."],
        )

    issues = validate_document(document_type, payload)
    if issues:
        return DoctorCheck(
            name=f"schema:{document_type}",
            ok=False,
            errors=[f"{issue.code} {issue.path}: {issue.message}" for issue in issues],
            hints=["Run `conductor migrate` to normalize file shape or edit fields to match schema."],
        )
    return DoctorCheck(name=f"schema:{document_type}", ok=True)


def _workflow_schema_check(workflow_path: Path) -> DoctorCheck:
    if not workflow_path.exists():
        return DoctorCheck(
            name="schema:workflow",
            ok=False,
            errors=[f"Missing file: {workflow_path}"],
            hints=["Create workflow-dsl.yaml or adjust path."],
        )
    payload = _load_yaml(workflow_path)
    issues = validate_document("workflow", payload)
    if issues:
        return DoctorCheck(
            name="schema:workflow",
            ok=False,
            errors=[f"{issue.code} {issue.path}: {issue.message}" for issue in issues],
            hints=["Ensure workflows include `steps` arrays with step objects."],
        )
    return DoctorCheck(name="schema:workflow", ok=True)


def _phase_config_check(ontology_path: Path) -> DoctorCheck:
    ontology = _load_yaml(ontology_path)
    clusters = ontology.get("clusters", [])
    cluster_ids = {c.get("id") for c in clusters if isinstance(c, dict)}
    errors: list[str] = []
    hints: list[str] = []
    for phase, members in get_phase_clusters().items():
        for cluster_id in members:
            if cluster_id not in cluster_ids:
                errors.append(f"Phase {phase} references unknown cluster: {cluster_id}")
    if errors:
        hints.append("Update .conductor.yaml phase overrides or ontology.yaml cluster IDs.")
    return DoctorCheck(name="phase-config", ok=not errors, errors=errors, hints=hints)


def _tool_availability_check(ontology_path: Path) -> DoctorCheck:
    """Check which ontology tools are actually available on this system."""
    import shutil

    ontology = _load_yaml(ontology_path)
    clusters = ontology.get("clusters", [])
    if not clusters:
        return DoctorCheck(name="tool-availability", ok=True, warnings=["No clusters found in ontology."])

    total_tools = 0
    available_tools = 0
    unavailable: list[str] = []
    warnings: list[str] = []

    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        cluster_id = cluster.get("id", "unknown")
        protocols = cluster.get("protocols", [])
        tools = cluster.get("tools", [])

        for tool in tools:
            total_tools += 1
            # Support both normalized {name, type} and legacy ontology formats
            if isinstance(tool, str):
                tool_name = tool
            elif isinstance(tool, dict):
                tool_name = str(tool.get("name", "")) if "name" in tool else str(list(tool.values())[0]) if tool else ""
            else:
                tool_name = str(tool)

            # CLI tools: check if binary exists on PATH
            if "CLI" in protocols:
                if shutil.which(tool_name):
                    available_tools += 1
                    continue

            # MCP tools: check if name matches known MCP pattern
            if "MCP" in protocols:
                # MCP tools are available if the server is configured; assume available
                available_tools += 1
                continue

            # Built-in tools (Read, Write, Edit, etc.): always available
            builtins = {"Read", "Write", "Edit", "Glob", "Grep", "Bash", "Agent", "WebSearch", "WebFetch"}
            if tool_name in builtins:
                available_tools += 1
                continue

            # GUI / BROWSER_AUTO: can't auto-check
            if "GUI" in protocols or "BROWSER_AUTO" in protocols:
                available_tools += 1  # assume available, can't verify
                continue

            # API / FILESYSTEM / STDIO: assume available unless explicitly a CLI binary
            if any(p in protocols for p in ("API", "FILESYSTEM", "STDIO")):
                available_tools += 1
                continue

            unavailable.append(f"{cluster_id}/{tool_name}")

    errors: list[str] = []
    if unavailable and len(unavailable) > total_tools * 0.5:
        errors.append(f"{len(unavailable)}/{total_tools} tools unavailable (>50%)")

    if unavailable:
        sample = unavailable[:10]
        suffix = f" (+{len(unavailable) - 10} more)" if len(unavailable) > 10 else ""
        warnings.append(f"Unavailable tools: {', '.join(sample)}{suffix}")

    hints: list[str] = []
    if unavailable:
        hints.append("Install missing CLI tools or configure MCP servers for unavailable tools.")

    return DoctorCheck(
        name="tool-availability",
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        hints=hints,
    )


def _legacy_artifacts_check() -> DoctorCheck:
    """Check for legacy .conductor-* files in the root that should be in .conductor/."""
    from .constants import BASE, STATE_DIR
    legacy = sorted(
        (p for p in BASE.glob(".conductor-*") if p != STATE_DIR),
        key=lambda p: p.name,
    )
    # Filter out the state directory itself if it matches the pattern (unlikely but safe)
    if not legacy:
        return DoctorCheck(name="legacy-artifacts", ok=True)

    preview = ", ".join(p.name for p in legacy[:5])
    extra = len(legacy) - 5
    suffix = f" (+{extra} more)" if extra > 0 else ""
    message = f"Found {len(legacy)} legacy artifacts in root: {preview}{suffix}"

    return DoctorCheck(
        name="legacy-artifacts",
        ok=False,
        errors=[message],
        hints=[
            "Review root-level `.conductor-*` files, move any needed data into `.conductor/`, then remove the legacy files.",
        ],
    )


def _mas_role_definition_check() -> DoctorCheck:
    """MAS: Verify ROLE_ACTIONS is populated for all phases."""
    from .constants import PHASES, ROLE_ACTIONS

    errors: list[str] = []
    for phase in PHASES:
        if phase not in ROLE_ACTIONS:
            errors.append(f"Phase {phase} missing from ROLE_ACTIONS")
        else:
            actions = ROLE_ACTIONS[phase]
            if not actions.get("allowed"):
                errors.append(f"Phase {phase} has empty 'allowed' actions in ROLE_ACTIONS")
            if not actions.get("forbidden"):
                errors.append(f"Phase {phase} has empty 'forbidden' actions in ROLE_ACTIONS")
    return DoctorCheck(
        name="mas:role-definitions",
        ok=not errors,
        errors=errors,
        hints=["Ensure ROLE_ACTIONS in constants.py defines allowed/forbidden for all phases."] if errors else [],
    )


def _mas_termination_condition_check() -> DoctorCheck:
    """MAS: Verify circuit breaker limits are configured."""
    from .constants import MAX_PHASE_MINUTES, MAX_SESSION_MINUTES, load_circuit_breaker_config

    errors: list[str] = []
    warnings: list[str] = []

    if MAX_PHASE_MINUTES <= 0:
        errors.append(f"MAX_PHASE_MINUTES is {MAX_PHASE_MINUTES} (must be > 0)")
    if MAX_SESSION_MINUTES <= 0:
        errors.append(f"MAX_SESSION_MINUTES is {MAX_SESSION_MINUTES} (must be > 0)")

    cb = load_circuit_breaker_config()
    if cb["max_phase_minutes"] <= 0:
        errors.append(f"Resolved max_phase_minutes is {cb['max_phase_minutes']} (must be > 0)")
    if cb["max_session_minutes"] <= 0:
        errors.append(f"Resolved max_session_minutes is {cb['max_session_minutes']} (must be > 0)")
    if cb["max_phase_minutes"] > cb["max_session_minutes"]:
        warnings.append(
            f"max_phase_minutes ({cb['max_phase_minutes']}) > max_session_minutes ({cb['max_session_minutes']})"
        )
    return DoctorCheck(
        name="mas:termination-conditions",
        ok=not errors,
        errors=errors,
        warnings=warnings,
        hints=["Check MAX_PHASE_MINUTES and MAX_SESSION_MINUTES in constants.py or .conductor.yaml."] if errors else [],
    )


def _mas_context_preservation_check() -> DoctorCheck:
    """MAS: Verify SESSION_EVENTS_FILE logging is active (file exists and recent)."""
    import time

    from .constants import SESSION_EVENTS_FILE

    errors: list[str] = []
    warnings: list[str] = []

    if not SESSION_EVENTS_FILE.exists():
        warnings.append(f"Session events file not found: {SESSION_EVENTS_FILE}")
        warnings.append("No session history is being preserved. Run a session to create it.")
    else:
        try:
            mtime = SESSION_EVENTS_FILE.stat().st_mtime
            age_hours = (time.time() - mtime) / 3600
            if age_hours > 168:  # 7 days
                warnings.append(
                    f"Session events file last modified {age_hours:.0f}h ago "
                    "(>168h). Context may be stale."
                )
        except OSError as exc:
            errors.append(f"Cannot stat session events file: {exc}")

    return DoctorCheck(
        name="mas:context-preservation",
        ok=not errors,
        errors=errors,
        warnings=warnings,
        hints=["Run sessions regularly to keep event context fresh."] if warnings else [],
    )


def _mas_governance_integrity_check() -> DoctorCheck:
    """MAS: Verify governance integrity in VALID_TRANSITIONS.

    Checks:
    - No direct self-loops (state -> same state)
    - Every state can eventually reach DONE (no dead-end cycles)
    Note: back-transitions (SHAPE->FRAME for reshape) are intentional
    and are not considered circular dependency errors, as long as DONE
    remains reachable from every state.
    """
    from .constants import VALID_TRANSITIONS

    errors: list[str] = []

    # Check for direct self-loops
    for state, targets in VALID_TRANSITIONS.items():
        if state in targets:
            errors.append(f"Self-loop detected: {state} -> {state}")

    # Check that every state can reach DONE via BFS
    def _can_reach_done(start: str) -> bool:
        visited: set[str] = set()
        queue = [start]
        while queue:
            current = queue.pop(0)
            if current == "DONE":
                return True
            if current in visited:
                continue
            visited.add(current)
            for neighbor in VALID_TRANSITIONS.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)
        return False

    for state in VALID_TRANSITIONS:
        if not _can_reach_done(state):
            errors.append(f"State {state} cannot reach DONE — potential dead-end cycle")

    return DoctorCheck(
        name="mas:governance-integrity",
        ok=not errors,
        errors=errors,
        hints=["Fix circular transitions in VALID_TRANSITIONS in constants.py."] if errors else [],
    )


def _collect_checks(workflow_path: Path, *, include_tools: bool = False, include_mas: bool = False) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = [
        _schema_check(REGISTRY_PATH, "registry"),
        _schema_check(GOVERNANCE_PATH, "governance"),
        _workflow_schema_check(workflow_path),
        _phase_config_check(ONTOLOGY_PATH),
        _legacy_artifacts_check(),
    ]

    integrity = run_integrity_checks(ONTOLOGY_PATH, ROUTING_PATH, workflow_path)
    checks.append(
        DoctorCheck(
            name="cross-file-integrity",
            ok=len(integrity.errors) == 0,
            errors=[f"{issue.code}: {issue.message}" for issue in integrity.errors],
            warnings=[f"{issue.code}: {issue.message}" for issue in integrity.warnings],
            hints=[issue.hint for issue in integrity.issues if issue.hint],
        )
    )

    if include_tools:
        checks.append(_tool_availability_check(ONTOLOGY_PATH))

    if include_mas:
        checks.extend([
            _mas_role_definition_check(),
            _mas_termination_condition_check(),
            _mas_context_preservation_check(),
            _mas_governance_integrity_check(),
        ])

    return checks


def _apply_autofixes() -> list[str]:
    fixes: list[str] = []
    
    # 1. Clean up legacy artifacts in root
    from .constants import BASE, STATE_DIR
    legacy = sorted(p for p in BASE.glob(".conductor-*") if p != STATE_DIR)
    for p in legacy:
        p.unlink()
        fixes.append(f"removed legacy artifact: {p.name}")

    # 2. Migrate schemas
    for name, path, migrator in [
        ("registry", REGISTRY_PATH, migrate_registry),
        ("governance", GOVERNANCE_PATH, migrate_governance),
    ]:
        if not path.exists():
            continue
        try:
            before = json.loads(path.read_text())
            migrated = migrator(path)
        except Exception as exc:
            from .observability import log_event
            log_event("doctor.migration_error", {"error": str(exc), "file": str(path)})
            continue
        if migrated != before:
            write_migration_output(migrated, path)
            fixes.append(f"migrated {name} schema in-place ({path})")
    return fixes


def run_doctor(
    workflow_path: Path,
    format_name: str = "text",
    apply: bool = False,
    tools: bool = False,
    mas_health: bool = False,
) -> dict[str, Any]:
    applied_fixes = _apply_autofixes() if apply else []
    checks = _collect_checks(workflow_path, include_tools=tools, include_mas=mas_health)

    ok = all(check.ok for check in checks)
    report = {
        "ok": ok,
        "checks": [check.to_dict() for check in checks],
        "summary": {
            "errors": sum(len(check.errors) for check in checks),
            "warnings": sum(len(check.warnings) for check in checks),
            "checks_total": len(checks),
            "checks_ok": sum(1 for check in checks if check.ok),
        },
        "autofix_hints": [
            hint
            for check in checks
            for hint in check.hints
            if hint
        ],
        "applied_fixes": applied_fixes,
    }

    assert_contract("doctor_report", report)
    if format_name == "json":
        return report
    return report


def render_doctor_text(report: dict[str, Any]) -> str:
    lines = []
    status = "OK" if report.get("ok") else "FAIL"
    lines.append(f"Doctor status: {status}")
    applied_fixes = report.get("applied_fixes", [])
    if applied_fixes:
        lines.append("Applied fixes:")
        for fix in applied_fixes:
            lines.append(f"  - {fix}")
    lines.append("")
    for check in report.get("checks", []):
        marker = "OK" if check.get("ok") else "FAIL"
        lines.append(f"[{marker}] {check.get('name')}")
        for err in check.get("errors", []):
            lines.append(f"  ERROR: {err}")
        for warn in check.get("warnings", []):
            lines.append(f"  WARN: {warn}")
        for hint in check.get("hints", []):
            lines.append(f"  Hint: {hint}")
    summary = report.get("summary", {})
    lines.append("")
    lines.append(
        "Summary: "
        f"{summary.get('checks_ok', 0)}/{summary.get('checks_total', 0)} checks ok, "
        f"{summary.get('errors', 0)} errors, {summary.get('warnings', 0)} warnings"
    )
    return "\n".join(lines)


def assert_doctor_ok(report: dict[str, Any]) -> None:
    if not report.get("ok"):
        raise ConductorError("Doctor checks failed. Run `conductor doctor --format json` for details.")
