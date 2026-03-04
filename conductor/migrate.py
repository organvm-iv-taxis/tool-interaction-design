"""Migration helpers for registry and governance documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from .constants import ConductorError
from .governance import _parse_governance_payload, _parse_registry_payload


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise ConductorError(f"File not found: {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ConductorError(f"Invalid JSON in {path}: {e}") from e


def migrate_registry(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    normalized = cast(dict[str, Any], _parse_registry_payload(payload))
    normalized["schema_version"] = "1"
    return normalized


def migrate_governance(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    normalized = cast(dict[str, Any], _parse_governance_payload(payload))
    normalized["schema_version"] = "1"
    return normalized


def write_migration_output(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n")
