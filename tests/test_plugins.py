"""Tests for cluster provider plugin loading."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
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


def test_provider_cluster_failure_logs_and_continues() -> None:
    class FailingProvider:
        def clusters(self):
            raise RuntimeError("plugin failure")

    with patch.dict("os.environ", {"CONDUCTOR_POLICY_BUNDLE": "default"}), \
         patch("conductor.plugins.load_cluster_plugins", return_value=[FailingProvider()]), \
         patch("conductor.plugins.log_event") as mock_log:
        clusters = load_plugin_clusters()

    assert clusters == []
    mock_log.assert_called_once()


def test_provider_cluster_failure_raises_in_strict_mode() -> None:
    class FailingProvider:
        def clusters(self):
            raise RuntimeError("plugin failure")

    with patch.dict("os.environ", {"CONDUCTOR_POLICY_BUNDLE": "strict"}), \
         patch("conductor.plugins.load_cluster_plugins", return_value=[FailingProvider()]):
        with pytest.raises(RuntimeError, match="plugin failure"):
            load_plugin_clusters()


def test_provider_spec_failure_logs_when_not_strict(tmp_path) -> None:
    config_file = tmp_path / ".conductor.yaml"
    config_file.write_text(yaml.dump({"plugins": {"cluster_providers": ["nonexistent.module:factory"]}}))

    with patch.dict("os.environ", {"CONDUCTOR_POLICY_BUNDLE": "default"}), \
         patch.object(conductor.constants, "CONFIG_FILE", config_file), \
         patch("conductor.plugins.log_event") as mock_log:
        providers = load_cluster_plugins()

    assert providers == []
    mock_log.assert_called_once()


def test_provider_spec_failure_raises_in_strict_mode(tmp_path) -> None:
    config_file = tmp_path / ".conductor.yaml"
    config_file.write_text(yaml.dump({"plugins": {"cluster_providers": ["nonexistent.module:factory"]}}))

    with patch.dict("os.environ", {"CONDUCTOR_POLICY_BUNDLE": "strict"}), \
         patch.object(conductor.constants, "CONFIG_FILE", config_file):
        with pytest.raises(ModuleNotFoundError):
            load_cluster_plugins()
