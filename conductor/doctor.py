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
            tool_name = tool if isinstance(tool, str) else str(list(tool.values())[0]) if isinstance(tool, dict) and tool else str(tool)

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


def _collect_checks(workflow_path: Path, *, include_tools: bool = False) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = [
        _schema_check(REGISTRY_PATH, "registry"),
        _schema_check(GOVERNANCE_PATH, "governance"),
        _workflow_schema_check(workflow_path),
        _phase_config_check(ONTOLOGY_PATH),
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

    return checks


def _apply_autofixes() -> list[str]:
    fixes: list[str] = []
    for name, path, migrator in [
        ("registry", REGISTRY_PATH, migrate_registry),
        ("governance", GOVERNANCE_PATH, migrate_governance),
    ]:
        if not path.exists():
            continue
        try:
            before = json.loads(path.read_text())
            migrated = migrator(path)
        except Exception:
            continue
        if migrated != before:
            write_migration_output(migrated, path)
            fixes.append(f"migrated {name} schema in-place ({path})")
    return fixes


def run_doctor(workflow_path: Path, format_name: str = "text", apply: bool = False, tools: bool = False) -> dict[str, Any]:
    applied_fixes = _apply_autofixes() if apply else []
    checks = _collect_checks(workflow_path, include_tools=tools)

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
