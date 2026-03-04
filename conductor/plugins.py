"""Cluster-provider plugin interface for extensible ontology loading."""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import yaml

from .constants import load_config


class ClusterProvider(Protocol):
    """Plugin contract for dynamic cluster sources."""

    def clusters(self) -> list[dict[str, Any]]:
        ...


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


def load_cluster_plugins() -> list[ClusterProvider]:
    """Load plugin providers from config/env in deterministic order."""
    config = load_config()
    plugin_cfg = config.get("plugins", {}) if isinstance(config, dict) else {}

    providers: list[ClusterProvider] = []

    cluster_file = (
        os.environ.get("CONDUCTOR_CLUSTER_FILE")
        or plugin_cfg.get("cluster_file")
    )
    if cluster_file:
        providers.append(FileClusterProvider(path=Path(cluster_file)))

    for spec in plugin_cfg.get("cluster_providers", []) if isinstance(plugin_cfg, dict) else []:
        if isinstance(spec, str) and spec.strip():
            providers.append(_load_provider_from_spec(spec.strip()))

    return providers


def load_plugin_clusters() -> list[dict[str, Any]]:
    """Return all cluster definitions contributed by plugins."""
    clusters: list[dict[str, Any]] = []
    for provider in load_cluster_plugins():
        try:
            clusters.extend(provider.clusters())
        except Exception:
            continue
    return clusters
