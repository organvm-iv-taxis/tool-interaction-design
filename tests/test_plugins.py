"""Tests for cluster provider plugin loading."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

import conductor.constants
from conductor.plugins import load_cluster_plugins, load_plugin_clusters


def test_file_cluster_provider_from_config(tmp_path) -> None:
    cluster_file = tmp_path / "clusters.yaml"
    cluster_file.write_text(yaml.dump({"clusters": [{"id": "plugin_cluster", "domain": "CODE", "label": "Plugin", "tools": [], "capabilities": [], "protocols": ["MCP"], "input_types": [], "output_types": []}]}))

    config_file = tmp_path / ".conductor.yaml"
    config_file.write_text(yaml.dump({"plugins": {"cluster_file": str(cluster_file)}}))

    with patch.object(conductor.constants, "CONFIG_FILE", config_file):
        providers = load_cluster_plugins()
        clusters = load_plugin_clusters()

    assert len(providers) == 1
    assert any(c.get("id") == "plugin_cluster" for c in clusters)
