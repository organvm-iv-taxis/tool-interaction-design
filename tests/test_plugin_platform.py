"""Plugin platform v1 tests: manifests, doctor, and timeout isolation."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import yaml

import conductor.constants
from conductor.plugins import load_cluster_plugins, load_plugin_clusters, plugin_doctor_report


def test_manifest_driven_provider_loads(tmp_path, monkeypatch) -> None:
    module_file = tmp_path / "demo_provider.py"
    module_file.write_text(
        "class DemoProvider:\n"
        "    def clusters(self):\n"
        "        return [{'id': 'plugin_demo', 'domain': 'CODE', 'label': 'Plugin Demo', "
        "'tools': [], 'capabilities': ['SEARCH'], 'protocols': ['MCP'], "
        "'input_types': [], 'output_types': []}]\n"
        "def build_provider():\n"
        "    return DemoProvider()\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    manifest_path = tmp_path / "provider-manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "api_version": "v1",
                "name": "demo-provider",
                "capabilities": ["cluster_provider"],
                "provider": {"kind": "python", "spec": "demo_provider:build_provider", "timeout_seconds": 1.0},
            }
        )
    )
    config_file = tmp_path / ".conductor.yaml"
    config_file.write_text(
        yaml.safe_dump({"plugins": {"cluster_providers": [{"manifest": str(manifest_path)}]}})
    )

    with patch.object(conductor.constants, "CONFIG_FILE", config_file):
        providers = load_cluster_plugins()
        clusters = load_plugin_clusters()

    assert len(providers) == 1
    assert any(cluster.get("id") == "plugin_demo" for cluster in clusters)


def test_invalid_manifest_logs_and_continues(tmp_path) -> None:
    manifest_path = tmp_path / "bad-manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "api_version": "v1",
                "name": "bad-provider",
                "capabilities": ["unknown_capability"],
                "provider": {"kind": "python", "spec": "missing.module:factory"},
            }
        )
    )
    config_file = tmp_path / ".conductor.yaml"
    config_file.write_text(
        yaml.safe_dump({"plugins": {"cluster_providers": [{"manifest": str(manifest_path)}]}})
    )

    with patch.object(conductor.constants, "CONFIG_FILE", config_file), \
         patch("conductor.plugins.log_event") as mock_log:
        providers = load_cluster_plugins()

    assert providers == []
    assert mock_log.call_args.kwargs["failure_bucket"] == "plugin_manifest_invalid"


def test_plugin_timeout_isolated_and_bucketed() -> None:
    class SlowProvider:
        def clusters(self):
            time.sleep(0.2)
            return []

    provider = SlowProvider()
    setattr(provider, "__conductor_provider_name__", "slow-provider")
    setattr(provider, "__conductor_timeout_seconds__", 0.01)

    with patch.dict("os.environ", {"CONDUCTOR_POLICY_BUNDLE": "default"}), \
         patch("conductor.plugins.load_cluster_plugins", return_value=[provider]), \
         patch("conductor.plugins.log_event") as mock_log:
        clusters = load_plugin_clusters()

    assert clusters == []
    assert mock_log.call_args.kwargs["failure_bucket"] == "plugin_provider_timeout"


def test_plugin_doctor_reports_load_errors_and_warnings(tmp_path) -> None:
    config_file = tmp_path / ".conductor.yaml"
    config_file.write_text(
        yaml.safe_dump({"plugins": {"cluster_providers": ["missing.module:factory"]}})
    )

    with patch.object(conductor.constants, "CONFIG_FILE", config_file):
        report = plugin_doctor_report()

    summary = report["summary"]
    assert summary["warnings"] >= 1
    assert summary["errors"] >= 1
