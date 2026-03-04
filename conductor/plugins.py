"""Cluster-provider plugin interface for extensible ontology loading."""

from __future__ import annotations

import importlib
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

import yaml

from .constants import BASE, ConductorError, load_config
from .observability import log_event
from .policy import load_policy
from .schemas import validate_document

PLUGIN_REQUIRED_CAPABILITY = "cluster_provider"
PLUGIN_ALLOWED_CAPABILITIES = {PLUGIN_REQUIRED_CAPABILITY, "healthcheck", "metadata"}
PLUGIN_DEFAULT_TIMEOUT_SECONDS = 2.0
PLUGIN_MAX_TIMEOUT_SECONDS = 30.0

PLUGIN_FAILURE_BUCKETS = {
    "manifest_invalid": "plugin_manifest_invalid",
    "provider_load_error": "plugin_provider_load_error",
    "provider_timeout": "plugin_provider_timeout",
    "provider_clusters_error": "plugin_provider_clusters_error",
    "provider_contract_error": "plugin_provider_contract_error",
}


class ClusterProvider(Protocol):
    """Plugin contract for dynamic cluster sources."""

    def clusters(self) -> list[dict[str, Any]]:
        ...


@dataclass
class ProviderDefinition:
    """Resolved plugin provider definition after config + manifest merge."""

    name: str
    source: str
    timeout_seconds: float = PLUGIN_DEFAULT_TIMEOUT_SECONDS
    capabilities: list[str] = field(default_factory=lambda: [PLUGIN_REQUIRED_CAPABILITY])
    provider_spec: str | None = None
    cluster_file: Path | None = None
    manifest_path: str | None = None
    manifest_version: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class FileClusterProvider:
    path: Path

    def clusters(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        raw = self.path.read_text()
        if self.path.suffix.lower() in {".json"}:
            parsed = json.loads(raw)
        else:
            parsed = yaml.safe_load(raw)
        if isinstance(parsed, dict):
            parsed = parsed.get("clusters", [])
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, dict)]


def _coerce_timeout_seconds(value: Any, fallback: float = PLUGIN_DEFAULT_TIMEOUT_SECONDS) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        timeout = fallback
    timeout = max(0.1, min(timeout, PLUGIN_MAX_TIMEOUT_SECONDS))
    return timeout


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _strict_plugin_failures() -> bool:
    try:
        return bool(load_policy().fail_on_warnings)
    except Exception:
        return False


def _load_provider_from_spec(spec: str) -> ClusterProvider:
    module_name, sep, attr_name = spec.partition(":")
    if not sep:
        raise ValueError(f"Invalid provider spec '{spec}'. Use module:factory_or_object format.")
    module = importlib.import_module(module_name)
    obj = getattr(module, attr_name)
    provider = obj() if callable(obj) else obj
    if not hasattr(provider, "clusters"):
        raise ValueError(f"Provider '{spec}' does not implement clusters()")
    return cast(ClusterProvider, provider)


def _resolve_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = (BASE / path).resolve()
    return path


def _load_manifest_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConductorError(f"Plugin manifest not found: {path}")
    raw = path.read_text()
    if path.suffix.lower() == ".json":
        payload = json.loads(raw)
    else:
        payload = yaml.safe_load(raw)
    if not isinstance(payload, dict):
        raise ConductorError(f"Plugin manifest must be an object: {path}")
    return cast(dict[str, Any], payload)


def _validate_manifest(payload: dict[str, Any], *, source: str) -> list[str]:
    errors = [
        f"{issue.code} {issue.path}: {issue.message}"
        for issue in validate_document("plugin_manifest", payload)
    ]

    capabilities = payload.get("capabilities", [])
    if isinstance(capabilities, list):
        invalid_caps = sorted({str(c) for c in capabilities if str(c) not in PLUGIN_ALLOWED_CAPABILITIES})
        if invalid_caps:
            errors.append(
                f"Unsupported plugin capabilities in {source}: {', '.join(invalid_caps)} "
                f"(allowed: {', '.join(sorted(PLUGIN_ALLOWED_CAPABILITIES))})"
            )
        if PLUGIN_REQUIRED_CAPABILITY not in {str(c) for c in capabilities}:
            errors.append(
                f"Plugin manifest {source} must include capability '{PLUGIN_REQUIRED_CAPABILITY}'."
            )
    return errors


def _normalize_provider_definition(
    entry: Any,
    *,
    source: str,
    default_timeout: float,
) -> tuple[ProviderDefinition | None, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if isinstance(entry, str):
        spec = entry.strip()
        if not spec:
            return None, [f"Empty provider spec at {source}"]
        return ProviderDefinition(
            name=spec,
            source=source,
            provider_spec=spec,
            timeout_seconds=default_timeout,
            warnings=["Legacy provider entry has no manifest; add `manifest` for v1 metadata validation."],
        ), []

    if not isinstance(entry, dict):
        return None, [f"Provider entry at {source} must be a string or object."]

    manifest_path = entry.get("manifest")
    manifest: dict[str, Any] | None = None
    if isinstance(manifest_path, str) and manifest_path.strip():
        resolved_manifest = _resolve_path(manifest_path.strip())
        try:
            manifest = _load_manifest_payload(resolved_manifest)
        except Exception as exc:
            errors.append(str(exc))
        else:
            manifest_errors = _validate_manifest(manifest, source=str(resolved_manifest))
            errors.extend(manifest_errors)
            manifest_path = str(resolved_manifest)
    elif manifest_path is not None:
        errors.append(f"Manifest path at {source} must be a string when provided.")

    provider_spec: str | None = None
    cluster_file: Path | None = None
    name = entry.get("name")
    timeout_seconds = _coerce_timeout_seconds(entry.get("timeout_seconds"), default_timeout)
    capabilities: list[str] = [PLUGIN_REQUIRED_CAPABILITY]
    manifest_version: str | None = None

    if manifest is not None:
        manifest_version = str(manifest.get("api_version", ""))
        name = name or manifest.get("name")
        caps = manifest.get("capabilities", [])
        if isinstance(caps, list):
            capabilities = [str(cap) for cap in caps]
        provider_payload = manifest.get("provider", {})
        if isinstance(provider_payload, dict):
            kind = str(provider_payload.get("kind", "python")).strip().lower()
            timeout_seconds = _coerce_timeout_seconds(provider_payload.get("timeout_seconds"), timeout_seconds)
            if kind == "python":
                spec_val = provider_payload.get("spec")
                if isinstance(spec_val, str) and spec_val.strip():
                    provider_spec = spec_val.strip()
            elif kind == "file":
                file_val = provider_payload.get("path")
                if isinstance(file_val, str) and file_val.strip():
                    cluster_file = _resolve_path(file_val.strip())

    # Explicit config fields override manifest defaults.
    spec_override = entry.get("spec")
    file_override = entry.get("cluster_file")
    if isinstance(spec_override, str) and spec_override.strip():
        provider_spec = spec_override.strip()
    if isinstance(file_override, str) and file_override.strip():
        cluster_file = _resolve_path(file_override.strip())

    if cluster_file is None and provider_spec is None:
        errors.append(
            f"Provider entry at {source} must define `spec` or `cluster_file` "
            "directly, or via manifest.provider."
        )

    if not isinstance(name, str) or not name.strip():
        name = provider_spec or (str(cluster_file) if cluster_file else f"provider@{source}")

    definition = ProviderDefinition(
        name=name.strip(),
        source=source,
        timeout_seconds=timeout_seconds,
        capabilities=capabilities,
        provider_spec=provider_spec,
        cluster_file=cluster_file,
        manifest_path=str(manifest_path) if isinstance(manifest_path, str) else None,
        manifest_version=manifest_version,
        warnings=warnings,
    )
    return definition, errors


def _iter_provider_entries(plugin_cfg: dict[str, Any]) -> list[tuple[Any, str]]:
    entries: list[tuple[Any, str]] = []

    cluster_file = os.environ.get("CONDUCTOR_CLUSTER_FILE") or plugin_cfg.get("cluster_file")
    if isinstance(cluster_file, str) and cluster_file.strip():
        entries.append(
            (
                {
                    "name": "cluster_file",
                    "cluster_file": cluster_file.strip(),
                },
                "plugins.cluster_file",
            )
        )

    raw_entries = plugin_cfg.get("cluster_providers", [])
    if isinstance(raw_entries, list):
        for idx, entry in enumerate(raw_entries):
            entries.append((entry, f"plugins.cluster_providers[{idx}]"))

    return entries


def _discover_provider_definitions() -> tuple[list[ProviderDefinition], list[dict[str, Any]]]:
    config = load_config()
    plugin_cfg = config.get("plugins", {}) if isinstance(config, dict) else {}
    if not isinstance(plugin_cfg, dict):
        plugin_cfg = {}

    strict_failures = _strict_plugin_failures()
    default_timeout = _coerce_timeout_seconds(plugin_cfg.get("timeout_seconds"), PLUGIN_DEFAULT_TIMEOUT_SECONDS)

    definitions: list[ProviderDefinition] = []
    findings: list[dict[str, Any]] = []

    for entry, source in _iter_provider_entries(plugin_cfg):
        definition, errors = _normalize_provider_definition(
            entry,
            source=source,
            default_timeout=default_timeout,
        )

        if errors:
            finding = {
                "name": source,
                "source": source,
                "status": "error",
                "errors": errors,
                "warnings": [],
            }
            findings.append(finding)
            log_event(
                "plugins.manifest_validation",
                {"source": source, "errors": errors},
                failed=True,
                failure_bucket=PLUGIN_FAILURE_BUCKETS["manifest_invalid"],
            )
            if strict_failures:
                raise ConductorError("; ".join(errors))
            continue

        assert definition is not None
        findings.append(
            {
                "name": definition.name,
                "source": definition.source,
                "status": "ok" if not definition.warnings else "warning",
                "errors": [],
                "warnings": definition.warnings,
                "timeout_seconds": definition.timeout_seconds,
                "capabilities": definition.capabilities,
                "manifest_version": definition.manifest_version,
            }
        )
        definitions.append(definition)

    return definitions, findings


def _attach_provider_metadata(provider: ClusterProvider, definition: ProviderDefinition) -> ClusterProvider:
    setattr(provider, "__conductor_provider_name__", definition.name)
    setattr(provider, "__conductor_provider_source__", definition.source)
    setattr(provider, "__conductor_timeout_seconds__", definition.timeout_seconds)
    setattr(provider, "__conductor_capabilities__", definition.capabilities)
    setattr(provider, "__conductor_manifest_version__", definition.manifest_version)
    return provider


def _provider_name(provider: ClusterProvider) -> str:
    return str(getattr(provider, "__conductor_provider_name__", provider.__class__.__name__))


def _provider_timeout(provider: ClusterProvider) -> float:
    return _coerce_timeout_seconds(getattr(provider, "__conductor_timeout_seconds__", PLUGIN_DEFAULT_TIMEOUT_SECONDS))


def load_cluster_plugins() -> list[ClusterProvider]:
    """Load plugin providers from config/env in deterministic order."""
    strict_failures = _strict_plugin_failures()
    definitions, _ = _discover_provider_definitions()
    providers: list[ClusterProvider] = []

    for definition in definitions:
        try:
            provider: ClusterProvider
            if definition.cluster_file is not None:
                provider = FileClusterProvider(path=definition.cluster_file)
            elif definition.provider_spec:
                provider = _load_provider_from_spec(definition.provider_spec)
            else:
                raise ConductorError(f"Plugin provider '{definition.name}' has no loadable source.")
            providers.append(_attach_provider_metadata(provider, definition))
        except Exception as exc:
            log_event(
                "plugins.provider_load",
                {
                    "name": definition.name,
                    "source": definition.source,
                    "error": str(exc),
                },
                failed=True,
                failure_bucket=PLUGIN_FAILURE_BUCKETS["provider_load_error"],
            )
            if strict_failures:
                raise

    return providers


def _run_provider_with_timeout(provider: ClusterProvider, timeout_seconds: float) -> Any:
    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _target() -> None:
        try:
            result["value"] = provider.clusters()
        except BaseException as exc:  # pragma: no cover - defensive
            error["exc"] = exc

    thread = threading.Thread(target=_target, daemon=True, name=f"plugin-{_provider_name(provider)}")
    thread.start()
    thread.join(timeout_seconds)

    if thread.is_alive():
        raise TimeoutError(f"Provider '{_provider_name(provider)}' timed out after {timeout_seconds:.1f}s")
    if "exc" in error:
        raise error["exc"]
    return result.get("value", [])


def _normalize_cluster_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("clusters", [])
    if not isinstance(payload, list):
        raise ValueError("Provider clusters() must return list[dict] or {'clusters': [...]} payload.")
    if not all(isinstance(item, dict) for item in payload):
        raise ValueError("Provider clusters() returned non-object entries.")
    return cast(list[dict[str, Any]], payload)


def load_plugin_clusters() -> list[dict[str, Any]]:
    """Return all cluster definitions contributed by plugins."""
    clusters: list[dict[str, Any]] = []
    strict_failures = _strict_plugin_failures()
    for provider in load_cluster_plugins():
        provider_name = _provider_name(provider)
        timeout_seconds = _provider_timeout(provider)
        try:
            payload = _run_provider_with_timeout(provider, timeout_seconds)
            clusters.extend(_normalize_cluster_payload(payload))
        except TimeoutError as exc:
            log_event(
                "plugins.provider_clusters",
                {
                    "provider": provider_name,
                    "error": str(exc),
                    "timeout_seconds": timeout_seconds,
                },
                failed=True,
                failure_bucket=PLUGIN_FAILURE_BUCKETS["provider_timeout"],
            )
            if strict_failures:
                raise
        except ValueError as exc:
            log_event(
                "plugins.provider_clusters",
                {"provider": provider_name, "error": str(exc)},
                failed=True,
                failure_bucket=PLUGIN_FAILURE_BUCKETS["provider_contract_error"],
            )
            if strict_failures:
                raise
        except Exception as exc:
            log_event(
                "plugins.provider_clusters",
                {"provider": provider_name, "error": str(exc)},
                failed=True,
                failure_bucket=PLUGIN_FAILURE_BUCKETS["provider_clusters_error"],
            )
            if strict_failures:
                raise
    return clusters


def plugin_doctor_report() -> dict[str, Any]:
    """Run plugin diagnostics (manifest, loadability, timeout config)."""
    definitions, findings = _discover_provider_definitions()
    strict_failures = _strict_plugin_failures()

    loaded_rows: list[dict[str, Any]] = []
    for definition in definitions:
        row = {
            "name": definition.name,
            "source": definition.source,
            "timeout_seconds": definition.timeout_seconds,
            "capabilities": definition.capabilities,
            "manifest_version": definition.manifest_version,
            "status": "ok",
            "errors": [],
            "warnings": list(definition.warnings),
        }
        try:
            provider: ClusterProvider
            if definition.cluster_file is not None:
                provider = FileClusterProvider(path=definition.cluster_file)
            elif definition.provider_spec:
                provider = _load_provider_from_spec(definition.provider_spec)
            else:
                raise ConductorError("provider source unresolved")
            _attach_provider_metadata(provider, definition)
        except Exception as exc:
            row["status"] = "error"
            row["errors"] = [str(exc)]
        else:
            if row["warnings"]:
                row["status"] = "warning"
        loaded_rows.append(row)

    rows_map: dict[tuple[str, str], dict[str, Any]] = {}
    for row in findings:
        key = (str(row.get("name", "")), str(row.get("source", "")))
        rows_map[key] = dict(row)
    for row in loaded_rows:
        key = (str(row.get("name", "")), str(row.get("source", "")))
        existing = rows_map.get(key)
        if existing is None:
            rows_map[key] = dict(row)
            continue
        merged = dict(existing)
        merged["warnings"] = [*_as_str_list(existing.get("warnings")), *_as_str_list(row.get("warnings"))]
        merged["errors"] = [*_as_str_list(existing.get("errors")), *_as_str_list(row.get("errors"))]
        status_rank = {"ok": 0, "warning": 1, "error": 2}
        existing_rank = status_rank.get(str(existing.get("status", "ok")), 0)
        row_rank = status_rank.get(str(row.get("status", "ok")), 0)
        merged["status"] = row.get("status") if row_rank > existing_rank else existing.get("status")
        for field_name in ("timeout_seconds", "capabilities", "manifest_version"):
            if merged.get(field_name) in (None, [], "") and row.get(field_name) not in (None, [], ""):
                merged[field_name] = row.get(field_name)
        rows_map[key] = merged
    rows = list(rows_map.values())

    summary = {
        "total": len(rows),
        "ok": sum(1 for row in rows if not row.get("warnings") and not row.get("errors")),
        "warnings": sum(1 for row in rows if bool(row.get("warnings"))),
        "errors": sum(1 for row in rows if bool(row.get("errors"))),
    }
    return {
        "ok": summary["errors"] == 0 and not (strict_failures and summary["warnings"] > 0),
        "strict_mode": strict_failures,
        "summary": summary,
        "providers": rows,
    }


def render_plugin_doctor_text(report: dict[str, Any]) -> str:
    lines = []
    status = "OK" if report.get("ok") else "FAIL"
    lines.append(f"Plugin doctor status: {status}")
    lines.append("")
    summary = report.get("summary", {})
    lines.append(
        "Summary: "
        f"{summary.get('total', 0)} providers, "
        f"{summary.get('ok', 0)} ok, "
        f"{summary.get('warnings', 0)} warnings, "
        f"{summary.get('errors', 0)} errors"
    )
    lines.append(f"Strict mode: {report.get('strict_mode')}")
    lines.append("")
    for row in report.get("providers", []):
        lines.append(f"[{str(row.get('status', 'unknown')).upper()}] {row.get('name')}")
        lines.append(f"  Source: {row.get('source')}")
        if row.get("manifest_version"):
            lines.append(f"  Manifest: {row.get('manifest_version')}")
        if row.get("timeout_seconds") is not None:
            lines.append(f"  Timeout: {row.get('timeout_seconds')}s")
        caps = row.get("capabilities", [])
        if caps:
            lines.append(f"  Capabilities: {', '.join(str(c) for c in caps)}")
        for warn in row.get("warnings", []):
            lines.append(f"  WARN: {warn}")
        for err in row.get("errors", []):
            lines.append(f"  ERROR: {err}")
    return "\n".join(lines)
