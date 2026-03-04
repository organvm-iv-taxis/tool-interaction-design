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


def _collect_checks(workflow_path: Path) -> list[DoctorCheck]:
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


def run_doctor(workflow_path: Path, format_name: str = "text", apply: bool = False) -> dict[str, Any]:
    applied_fixes = _apply_autofixes() if apply else []
    checks = _collect_checks(workflow_path)

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
