"""Policy bundle loading for environment-specific behavior."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .constants import BASE, load_config

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
    )
