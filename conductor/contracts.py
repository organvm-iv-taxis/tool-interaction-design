"""JSON output contract helpers for CLI/MCP response surfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .constants import ConductorError
from .schemas import DEFAULT_SCHEMA_VERSION, SCHEMAS_DIR

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional dependency fallback
    jsonschema = None


@dataclass(frozen=True)
class ContractIssue:
    code: str
    message: str
    path: str


def contract_path(contract_name: str, version: str = DEFAULT_SCHEMA_VERSION) -> Path:
    return cast(Path, SCHEMAS_DIR / version / "contracts" / f"{contract_name}.schema.json")


def load_contract(contract_name: str, version: str = DEFAULT_SCHEMA_VERSION) -> dict[str, Any]:
    path = contract_path(contract_name, version=version)
    if not path.exists():
        raise ConductorError(f"Output contract not found for '{contract_name}' at {path}")
    return cast(dict[str, Any], json.loads(path.read_text()))


def validate_contract(contract_name: str, payload: Any, version: str = DEFAULT_SCHEMA_VERSION) -> list[ContractIssue]:
    schema = load_contract(contract_name, version=version)
    if jsonschema is None:
        return [ContractIssue(code="CONTRACT-E000", message="jsonschema dependency not available", path="$")]

    validator = jsonschema.Draft202012Validator(schema)
    issues: list[ContractIssue] = []
    for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path)):
        path_str = "$"
        if err.absolute_path:
            path_str += "." + ".".join(str(part) for part in err.absolute_path)
        issues.append(
            ContractIssue(
                code="CONTRACT-E001",
                message=err.message,
                path=path_str,
            )
        )
    return issues


def assert_contract(contract_name: str, payload: Any, version: str = DEFAULT_SCHEMA_VERSION) -> None:
    issues = validate_contract(contract_name, payload, version=version)
    if issues:
        rendered = "; ".join(f"{issue.code} {issue.path}: {issue.message}" for issue in issues[:5])
        if len(issues) > 5:
            rendered += f"; ... ({len(issues)} total)"
        raise ConductorError(f"Output contract validation failed for {contract_name}: {rendered}")
