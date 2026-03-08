"""Versioned schema loading and validation helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .constants import BASE, ConductorError

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional dependency fallback
    jsonschema = None

SCHEMAS_DIR = BASE / "schemas"
DEFAULT_SCHEMA_VERSION = "v1"


@dataclass(frozen=True)
class SchemaIssue:
    code: str
    message: str
    path: str


def schema_path(document_type: str, version: str = DEFAULT_SCHEMA_VERSION) -> Path:
    return cast(Path, SCHEMAS_DIR / version / f"{document_type}.schema.json")


def load_schema(document_type: str, version: str = DEFAULT_SCHEMA_VERSION) -> dict[str, Any]:
    path = schema_path(document_type, version=version)
    if not path.exists():
        raise ConductorError(f"Schema not found for '{document_type}' at {path}")
    return cast(dict[str, Any], json.loads(path.read_text()))


def validate_document(document_type: str, payload: Any, version: str = DEFAULT_SCHEMA_VERSION) -> list[SchemaIssue]:
    schema = load_schema(document_type, version=version)
    if jsonschema is None:
        # Degrade gracefully — skip validation when jsonschema is not installed
        return []

    validator = jsonschema.Draft202012Validator(schema)
    issues: list[SchemaIssue] = []
    for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path)):
        path_str = "$"
        if err.absolute_path:
            path_str += "." + ".".join(str(part) for part in err.absolute_path)
        issues.append(
            SchemaIssue(
                code="SCHEMA-E001",
                message=err.message,
                path=path_str,
            )
        )
    return issues


def assert_valid_document(document_type: str, payload: Any, version: str = DEFAULT_SCHEMA_VERSION) -> None:
    issues = validate_document(document_type, payload, version=version)
    if issues:
        rendered = "; ".join(f"{issue.code} {issue.path}: {issue.message}" for issue in issues[:5])
        if len(issues) > 5:
            rendered += f"; ... ({len(issues)} total)"
        raise ConductorError(f"Schema validation failed for {document_type}: {rendered}")
