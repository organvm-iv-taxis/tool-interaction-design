"""Cross-file integrity checks for ontology, routing matrix, and workflow DSL."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class IntegrityIssue:
    code: str
    severity: str  # error | warning
    message: str
    hint: str = ""


@dataclass
class IntegrityReport:
    issues: list[IntegrityIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[IntegrityIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[IntegrityIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "errors": [issue.__dict__ for issue in self.errors],
            "warnings": [issue.__dict__ for issue in self.warnings],
            "ok": len(self.errors) == 0,
        }


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def run_integrity_checks(ontology_path: Path, routing_path: Path, workflow_path: Path) -> IntegrityReport:
    report = IntegrityReport()

    ontology = _load_yaml(ontology_path)
    routing = _load_yaml(routing_path)
    workflow = _load_yaml(workflow_path)

    clusters = ontology.get("clusters", []) if isinstance(ontology, dict) else []
    cluster_ids = {c.get("id") for c in clusters if isinstance(c, dict) and isinstance(c.get("id"), str)}

    routes = routing.get("routes", []) if isinstance(routing, dict) else []
    for idx, route in enumerate(routes):
        if not isinstance(route, dict):
            report.issues.append(IntegrityIssue(
                code="INT-E001",
                severity="error",
                message=f"Route at index {idx} must be an object",
                hint="Fix routing-matrix.yaml: routes entries must be maps.",
            ))
            continue
        from_cluster = route.get("from")
        to_cluster = route.get("to")
        if from_cluster == "*" or to_cluster == "*":
            report.issues.append(IntegrityIssue(
                code="INT-W002",
                severity="warning",
                message=f"Route uses wildcard endpoint: {from_cluster} -> {to_cluster}",
                hint="Prefer explicit cluster IDs for stronger integrity guarantees.",
            ))
            continue

        if from_cluster not in cluster_ids:
            report.issues.append(IntegrityIssue(
                code="INT-E002",
                severity="error",
                message=f"Route references unknown source cluster: {from_cluster}",
                hint="Add missing cluster to ontology.yaml or correct routing-matrix.yaml.",
            ))
        if to_cluster not in cluster_ids:
            report.issues.append(IntegrityIssue(
                code="INT-E003",
                severity="error",
                message=f"Route references unknown target cluster: {to_cluster}",
                hint="Add missing cluster to ontology.yaml or correct routing-matrix.yaml.",
            ))

    capability_routing = routing.get("capability_routing", {}) if isinstance(routing, dict) else {}
    if isinstance(capability_routing, dict):
        for capability, ordered_clusters in capability_routing.items():
            if not isinstance(ordered_clusters, list):
                report.issues.append(IntegrityIssue(
                    code="INT-E004",
                    severity="error",
                    message=f"capability_routing.{capability} must be a list",
                    hint="Update routing-matrix.yaml to list cluster IDs per capability.",
                ))
                continue
            for cluster_id in ordered_clusters:
                if cluster_id not in cluster_ids:
                    report.issues.append(IntegrityIssue(
                        code="INT-E005",
                        severity="error",
                        message=f"capability_routing.{capability} references unknown cluster: {cluster_id}",
                        hint="Align capability_routing with ontology cluster IDs.",
                    ))

    workflows: list[dict[str, Any]]
    if isinstance(workflow, dict) and "examples" in workflow:
        examples = workflow.get("examples")
        workflows = [wf for wf in examples if isinstance(wf, dict)] if isinstance(examples, list) else []
    elif isinstance(workflow, dict):
        workflows = [workflow]
    else:
        workflows = []

    for wf in workflows:
        wf_name = str(wf.get("name", "<unnamed>"))
        steps = wf.get("steps", [])
        if not isinstance(steps, list):
            report.issues.append(IntegrityIssue(
                code="INT-E006",
                severity="error",
                message=f"Workflow '{wf_name}' steps must be a list",
                hint="Update workflow-dsl.yaml steps field to be an array of step objects.",
            ))
            continue

        known_step_names = {
            step.get("name")
            for step in steps
            if isinstance(step, dict) and isinstance(step.get("name"), str)
        }
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_name = str(step.get("name", "<unnamed>"))
            cluster = step.get("cluster")
            if cluster and cluster != "*" and cluster not in cluster_ids:
                report.issues.append(IntegrityIssue(
                    code="INT-E007",
                    severity="error",
                    message=f"Workflow '{wf_name}' step '{step_name}' references unknown cluster '{cluster}'",
                    hint="Fix cluster name or add missing cluster to ontology.yaml.",
                ))
            deps = step.get("depends_on", [])
            if isinstance(deps, list):
                for dep in deps:
                    if dep not in known_step_names:
                        report.issues.append(IntegrityIssue(
                            code="INT-W001",
                            severity="warning",
                            message=f"Workflow '{wf_name}' step '{step_name}' depends on unknown step '{dep}'",
                            hint="If this is intentional, ensure dependency is defined in the same workflow.",
                        ))

    return report
