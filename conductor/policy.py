"""Policy bundle loading for environment-specific behavior."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .constants import BASE, organ_short, load_config

POLICIES_DIR = BASE / "policies"
DEFAULT_POLICY_BUNDLE = "default"


@dataclass(frozen=True)
class Policy:
    """Typed policy contract used by runtime components."""

    name: str
    max_candidate_per_organ: int
    max_public_process_per_organ: int
    strict_validation_default: bool
    fail_on_warnings: bool
    max_path_depth: int
    max_paths_returned: int
    observability_enabled: bool
    top_failure_buckets: int
    trend_warn_rate: float
    trend_critical_rate: float
    trend_min_events: int
    staleness_flagship_days: int
    staleness_standard_days: int
    staleness_stub_days: int
    staleness_infrastructure_days: int


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return fallback


def _coerce_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _load_policy_payload(bundle: str) -> dict[str, Any]:
    policy_file = POLICIES_DIR / f"{bundle}.yaml"
    if not policy_file.exists():
        policy_file = POLICIES_DIR / f"{DEFAULT_POLICY_BUNDLE}.yaml"
    return yaml.safe_load(policy_file.read_text()) or {}


def load_policy(bundle: str | None = None) -> Policy:
    """Load policy from bundle name, env, and .conductor.yaml overrides."""
    config = load_config()
    cfg_bundle = config.get("policy_bundle")
    selected_bundle = bundle or os.environ.get("CONDUCTOR_POLICY_BUNDLE") or cfg_bundle or DEFAULT_POLICY_BUNDLE
    payload = _load_policy_payload(selected_bundle)

    wip = payload.get("wip", {})
    validation = payload.get("validation", {})
    routing = payload.get("routing", {})
    observability = payload.get("observability", {})
    staleness = payload.get("staleness", {})

    return Policy(
        name=str(payload.get("name", selected_bundle)),
        max_candidate_per_organ=_coerce_int(wip.get("max_candidate_per_organ"), 3),
        max_public_process_per_organ=_coerce_int(wip.get("max_public_process_per_organ"), 1),
        strict_validation_default=_coerce_bool(validation.get("strict_default"), False),
        fail_on_warnings=_coerce_bool(validation.get("fail_on_warnings"), False),
        max_path_depth=_coerce_int(routing.get("max_path_depth"), 5),
        max_paths_returned=_coerce_int(routing.get("max_paths_returned"), 5),
        observability_enabled=_coerce_bool(observability.get("enabled"), True),
        top_failure_buckets=_coerce_int(observability.get("top_failure_buckets"), 10),
        trend_warn_rate=_coerce_float(observability.get("trend_warn_rate"), 0.2),
        trend_critical_rate=_coerce_float(observability.get("trend_critical_rate"), 0.4),
        trend_min_events=_coerce_int(observability.get("trend_min_events"), 25),
        staleness_flagship_days=_coerce_int(staleness.get("flagship_days"), 14),
        staleness_standard_days=_coerce_int(staleness.get("standard_days"), 30),
        staleness_stub_days=_coerce_int(staleness.get("stub_days"), 90),
        staleness_infrastructure_days=_coerce_int(staleness.get("infrastructure_days"), 60),
    )


def get_staleness_days(tier: str, policy: Policy | None = None) -> int:
    """Look up the staleness threshold in days for a given repo tier."""
    if policy is None:
        policy = load_policy()
    tier_lower = tier.strip().lower()
    mapping = {
        "flagship": policy.staleness_flagship_days,
        "standard": policy.staleness_standard_days,
        "stub": policy.staleness_stub_days,
        "infrastructure": policy.staleness_infrastructure_days,
    }
    return mapping.get(tier_lower, policy.staleness_standard_days)


def simulate_policy(bundle: str | None, registry: dict[str, Any]) -> dict[str, Any]:
    """Project policy bundle limits onto current registry state."""
    policy = load_policy(bundle)
    organs_report: dict[str, dict[str, Any]] = {}
    total_violations = 0

    for organ_key, organ_data in registry.get("organs", {}).items():
        repos = organ_data.get("repositories", [])
        candidate = sum(1 for repo in repos if repo.get("promotion_status") == "CANDIDATE")
        public_process = sum(1 for repo in repos if repo.get("promotion_status") == "PUBLIC_PROCESS")
        candidate_over = max(0, candidate - policy.max_candidate_per_organ)
        public_over = max(0, public_process - policy.max_public_process_per_organ)
        violations = int(candidate_over > 0) + int(public_over > 0)
        total_violations += violations
        organs_report[organ_key] = {
            "organ_short": organ_short(organ_key),
            "candidate": candidate,
            "public_process": public_process,
            "candidate_limit": policy.max_candidate_per_organ,
            "public_process_limit": policy.max_public_process_per_organ,
            "candidate_over_by": candidate_over,
            "public_process_over_by": public_over,
            "violations": violations,
        }

    return {
        "bundle": policy.name,
        "limits": {
            "max_candidate_per_organ": policy.max_candidate_per_organ,
            "max_public_process_per_organ": policy.max_public_process_per_organ,
        },
        "organs": organs_report,
        "summary": {
            "organs_checked": len(organs_report),
            "organs_with_violations": sum(1 for row in organs_report.values() if row["violations"] > 0),
            "violations_total": total_violations,
        },
    }


def render_policy_simulation_text(report: dict[str, Any]) -> str:
    lines = []
    bundle = report.get("bundle", "unknown")
    limits = report.get("limits", {})
    lines.append(f"Policy simulation: {bundle}")
    lines.append(
        "Limits: "
        f"CANDIDATE <= {limits.get('max_candidate_per_organ', '?')} per organ, "
        f"PUBLIC_PROCESS <= {limits.get('max_public_process_per_organ', '?')} per organ"
    )
    lines.append("")
    lines.append(f"{'ORGAN':<10} {'CAND':>5} {'PUB':>5} {'STATUS':<18}")

    organs = report.get("organs", {})
    for organ_key in sorted(organs.keys()):
        row = organs[organ_key]
        status = "OK"
        if row.get("candidate_over_by", 0) > 0 or row.get("public_process_over_by", 0) > 0:
            status = (
                f"C+{row.get('candidate_over_by', 0)} "
                f"P+{row.get('public_process_over_by', 0)}"
            )
        lines.append(
            f"{row.get('organ_short', organ_key):<10} "
            f"{row.get('candidate', 0):>5} "
            f"{row.get('public_process', 0):>5} "
            f"{status:<18}"
        )

    summary = report.get("summary", {})
    lines.append("")
    lines.append(
        "Summary: "
        f"{summary.get('organs_with_violations', 0)}/{summary.get('organs_checked', 0)} organs violating, "
        f"{summary.get('violations_total', 0)} total violations"
    )
    return "\n".join(lines)
