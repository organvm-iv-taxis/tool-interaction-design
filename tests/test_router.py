"""Tests for router — ontology, routing engine, workflow validator, CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Add parent to path so we can import router
sys.path.insert(0, str(Path(__file__).parent.parent))

from router import (
    Alternative,
    Cluster,
    Ontology,
    Route,
    RoutingEngine,
    WorkflowValidator,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE = Path(__file__).parent.parent
ONTOLOGY_PATH = BASE / "ontology.yaml"
ROUTING_PATH = BASE / "routing-matrix.yaml"
WORKFLOW_PATH = BASE / "workflow-dsl.yaml"
ROUTER_SCRIPT = BASE / "router.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ontology():
    """Load the real ontology."""
    return Ontology(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def engine(ontology):
    """Load routing engine with real data."""
    return RoutingEngine(ROUTING_PATH, ontology)


@pytest.fixture(scope="module")
def validator(ontology, engine):
    """Create workflow validator."""
    return WorkflowValidator(ontology, engine)


# ===========================================================================
# TestClusterDataclass
# ===========================================================================


class TestClusterDataclass:
    def test_instantiation(self):
        c = Cluster(
            id="test_cluster",
            domain="CODE",
            label="Test Cluster",
            tools=["tool_a", "tool_b"],
            capabilities=["READ", "WRITE"],
            protocols=["MCP"],
            input_types=["TEXT"],
            output_types=["JSON"],
        )
        assert c.id == "test_cluster"
        assert c.domain == "CODE"
        assert len(c.tools) == 2
        assert "READ" in c.capabilities

    def test_field_access(self):
        c = Cluster(
            id="x", domain="D", label="L",
            tools=[], capabilities=[], protocols=[],
            input_types=[], output_types=[],
        )
        assert c.label == "L"
        assert c.tools == []


# ===========================================================================
# TestRouteDataclass
# ===========================================================================


class TestRouteDataclass:
    def test_instantiation(self):
        r = Route(
            id="test_route",
            from_cluster="a",
            to_cluster="b",
            data_flow="TEXT → JSON",
            protocol="MCP → MCP",
            automatable=True,
            description="test",
            exemplars=[{"source": "x", "target": "y"}],
        )
        assert r.id == "test_route"
        assert r.from_cluster == "a"
        assert r.to_cluster == "b"
        assert r.automatable is True

    def test_defaults(self):
        r = Route(
            id="r", from_cluster="a", to_cluster="b",
            data_flow="", protocol="", automatable=False,
        )
        assert r.description == ""
        assert r.exemplars == []


# ===========================================================================
# TestOntologyLoader
# ===========================================================================


class TestOntologyLoader:
    def test_loads_real_file(self, ontology):
        assert len(ontology.clusters) >= 64

    def test_twelve_domains(self, ontology):
        domain_ids = {d["id"] for d in ontology.domains()}
        assert len(domain_ids) == 12
        assert "CODE" in domain_ids
        assert "RESEARCH" in domain_ids
        assert "BROWSER" in domain_ids

    def test_indices_built(self, ontology):
        assert len(ontology._cap_index) > 0
        assert len(ontology._domain_index) > 0
        assert len(ontology._protocol_index) > 0

    def test_known_cluster_exists(self, ontology):
        assert "claude_code_core" in ontology.clusters
        assert "web_search" in ontology.clusters
        assert "git_core" in ontology.clusters

    def test_cluster_has_tools(self, ontology):
        cc = ontology.clusters["claude_code_core"]
        assert len(cc.tools) > 0
        assert cc.domain == "AI_AGENTS"


# ===========================================================================
# TestOntologyByCapability
# ===========================================================================


class TestOntologyByCapability:
    def test_search_returns_clusters(self, ontology):
        clusters = ontology.by_capability("SEARCH")
        assert len(clusters) > 0
        ids = {c.id for c in clusters}
        assert "claude_code_core" in ids or "web_search" in ids

    def test_unknown_capability_returns_empty(self, ontology):
        assert ontology.by_capability("NONEXISTENT_CAP") == []

    def test_case_insensitive(self, ontology):
        upper = ontology.by_capability("READ")
        lower = ontology.by_capability("read")
        assert len(upper) == len(lower)


# ===========================================================================
# TestOntologyByDomain
# ===========================================================================


class TestOntologyByDomain:
    def test_research_domain(self, ontology):
        clusters = ontology.by_domain("RESEARCH")
        assert len(clusters) >= 7  # web_search, wikipedia, etc.

    def test_unknown_domain_returns_empty(self, ontology):
        assert ontology.by_domain("NONEXISTENT_DOMAIN") == []

    def test_code_domain_has_clusters(self, ontology):
        clusters = ontology.by_domain("CODE")
        ids = {c.id for c in clusters}
        assert "code_analysis_mcp" in ids


# ===========================================================================
# TestOntologyByProtocol
# ===========================================================================


class TestOntologyByProtocol:
    def test_mcp_returns_many(self, ontology):
        clusters = ontology.by_protocol("MCP")
        assert len(clusters) >= 10

    def test_gui_returns_few(self, ontology):
        gui = ontology.by_protocol("GUI")
        mcp = ontology.by_protocol("MCP")
        assert len(gui) < len(mcp)

    def test_unknown_protocol_returns_empty(self, ontology):
        assert ontology.by_protocol("QUANTUM") == []


# ===========================================================================
# TestOntologyCompatibleTargets
# ===========================================================================


class TestOntologyCompatibleTargets:
    def test_web_search_has_targets(self, ontology):
        targets = ontology.compatible_targets("web_search")
        assert len(targets) > 0
        target_ids = {t for t, _ in targets}
        # web_search outputs TEXT, many clusters accept TEXT
        assert len(target_ids) > 3

    def test_unknown_cluster_returns_empty(self, ontology):
        assert ontology.compatible_targets("nonexistent_cluster") == []

    def test_returns_tuples(self, ontology):
        targets = ontology.compatible_targets("claude_code_core")
        for item in targets:
            assert isinstance(item, tuple)
            assert len(item) == 2  # (target_id, data_type)


# ===========================================================================
# TestRoutingEngineLoader
# ===========================================================================


class TestRoutingEngineLoader:
    def test_loads_routes(self, engine):
        assert len(engine.routes) >= 32

    def test_adjacency_graph_built(self, engine):
        assert len(engine._adj) > 0

    def test_alternatives_loaded(self, engine):
        assert len(engine.alternatives) > 0

    def test_capability_routing_loaded(self, engine):
        assert len(engine.capability_routing) > 0
        assert "SEARCH" in engine.capability_routing


# ===========================================================================
# TestRoutingEngineFindRoutes
# ===========================================================================


class TestRoutingEngineFindRoutes:
    def test_direct_route_exists(self, engine):
        routes = engine.find_routes("web_search", "knowledge_graph")
        assert len(routes) >= 1
        assert routes[0].from_cluster == "web_search"
        assert routes[0].to_cluster == "knowledge_graph"

    def test_nonexistent_pair_returns_empty(self, engine):
        routes = engine.find_routes("nonexistent_a", "nonexistent_b")
        assert routes == []

    def test_route_has_fields(self, engine):
        routes = engine.find_routes("web_search", "knowledge_graph")
        r = routes[0]
        assert r.id
        assert r.data_flow
        assert isinstance(r.automatable, bool)


# ===========================================================================
# TestRoutingEngineFindPath
# ===========================================================================


class TestRoutingEngineFindPath:
    def test_same_domain_path(self, engine):
        # Within a domain there should be some paths
        paths = engine.find_path("CODE", "CODE")
        # May or may not find paths depending on routes — just check no crash
        assert isinstance(paths, list)

    def test_cluster_level_paths(self, engine):
        paths = engine.find_cluster_paths("web_search", "knowledge_graph")
        assert paths
        assert paths[0][0] == "web_search"
        assert paths[0][-1] == "knowledge_graph"

    def test_disconnected_returns_empty(self, engine):
        paths = engine.find_path("NONEXISTENT", "ALSO_NONEXISTENT")
        assert paths == []

    def test_path_format(self, engine):
        # Try a well-connected pair
        paths = engine.find_path("RESEARCH", "GIT_SCM")
        if paths:
            assert isinstance(paths[0], list)
            assert len(paths[0]) >= 2  # At least from + to

    def test_max_five_paths(self, engine):
        paths = engine.find_path("RESEARCH", "CODE")
        assert len(paths) <= 5


# ===========================================================================
# TestRoutingEngineAlternatives
# ===========================================================================


class TestRoutingEngineAlternatives:
    def test_web_search_has_alternatives(self, engine):
        alt = engine.get_alternatives("web_search")
        assert alt is not None
        assert len(alt.tools_ranked) > 0

    def test_unknown_has_none(self, engine):
        assert engine.get_alternatives("totally_unknown_cluster") is None


# ===========================================================================
# TestRoutingEngineCapabilityTools
# ===========================================================================


class TestRoutingEngineCapabilityTools:
    def test_search_returns_ordered_list(self, engine):
        tools = engine.capability_tools("SEARCH")
        assert len(tools) > 0
        assert isinstance(tools, list)

    def test_unknown_capability_returns_empty(self, engine):
        assert engine.capability_tools("NONEXISTENT") == []


# ===========================================================================
# TestWorkflowValidator
# ===========================================================================


class TestWorkflowValidator:
    def test_validates_real_workflow_dsl(self, validator):
        issues = validator.validate(WORKFLOW_PATH)
        assert isinstance(issues, list)
        # Real file should be valid (or have known, acceptable issues)

    def test_catches_bad_cluster_ref(self, validator, tmp_path):
        bad_wf = {
            "name": "bad-workflow",
            "steps": [
                {"name": "step1", "cluster": "totally_fake_cluster_xyz"},
            ],
        }
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.dump(bad_wf))
        issues = validator.validate(path)
        assert any("totally_fake_cluster_xyz" in i for i in issues)

    def test_catches_duplicate_step_names(self, validator, tmp_path):
        dup_wf = {
            "name": "dup-workflow",
            "steps": [
                {"name": "step1", "cluster": "claude_code_core"},
                {"name": "step1", "cluster": "web_search"},
            ],
        }
        path = tmp_path / "dup.yaml"
        path.write_text(yaml.dump(dup_wf))
        issues = validator.validate(path)
        assert any("Duplicate" in i for i in issues)

    def test_empty_steps_flagged(self, validator, tmp_path):
        empty_wf = {"name": "empty", "steps": []}
        path = tmp_path / "empty.yaml"
        path.write_text(yaml.dump(empty_wf))
        issues = validator.validate(path)
        assert any("No steps" in i for i in issues)

    def test_catches_unknown_dependency(self, validator, tmp_path):
        bad_dep_wf = {
            "name": "bad-dep",
            "steps": [
                {"name": "step1", "cluster": "claude_code_core", "depends_on": ["missing_step"]},
            ],
        }
        path = tmp_path / "bad_dep.yaml"
        path.write_text(yaml.dump(bad_dep_wf))
        issues = validator.validate(path)
        assert any("Unknown dependency: missing_step" in i for i in issues)

    def test_catches_unknown_parallel_dependency(self, validator, tmp_path):
        bad_parallel_dep_wf = {
            "name": "bad-parallel-dep",
            "steps": [
                {
                    "name": "parent",
                    "cluster": "claude_code_core",
                    "parallel": [
                        {"name": "child", "cluster": "web_search", "depends_on": ["missing_parallel_dep"]},
                    ],
                },
            ],
        }
        path = tmp_path / "bad_parallel_dep.yaml"
        path.write_text(yaml.dump(bad_parallel_dep_wf))
        issues = validator.validate(path)
        assert any("Unknown dependency: missing_parallel_dep" in i for i in issues)

    def test_forward_dependency_is_warning(self, validator, tmp_path):
        forward_dep_wf = {
            "name": "forward-dep",
            "steps": [
                {"name": "build", "cluster": "claude_code_core", "depends_on": ["plan"]},
                {"name": "plan", "cluster": "sequential_thinking"},
            ],
        }
        path = tmp_path / "forward_dep.yaml"
        path.write_text(yaml.dump(forward_dep_wf))

        report = validator.validate_report(path)
        assert report.errors == []
        assert any("Forward dependency" in warning for warning in report.warnings)

        non_strict = validator.validate(path)
        strict = validator.validate(path, strict=True)
        assert non_strict == []
        assert any("Forward dependency" in issue for issue in strict)

    def test_empty_file_returns_structured_error(self, validator, tmp_path):
        path = tmp_path / "empty_file.yaml"
        path.write_text("")

        report = validator.validate_report(path)
        assert report.is_valid is False
        assert any("[WF-E008]" in issue for issue in report.errors)

    def test_scalar_top_level_returns_structured_error(self, validator, tmp_path):
        path = tmp_path / "scalar_top_level.yaml"
        path.write_text("42")

        report = validator.validate_report(path)
        assert report.is_valid is False
        assert any("[WF-E009]" in issue for issue in report.errors)

    def test_malformed_yaml_returns_structured_error(self, validator, tmp_path):
        path = tmp_path / "malformed.yaml"
        path.write_text("steps: [")

        report = validator.validate_report(path)
        assert report.is_valid is False
        assert any("[WF-E007]" in issue for issue in report.errors)


# ===========================================================================
# TestCLICommands
# ===========================================================================


class TestCLICommands:
    """Smoke tests — verify each command runs without crashing."""

    def _run(self, *args):
        result = subprocess.run(
            [sys.executable, str(ROUTER_SCRIPT)] + list(args),
            capture_output=True, text=True, timeout=15,
        )
        return result

    def test_route_command(self):
        r = self._run("route", "--from", "web_search", "--to", "knowledge_graph")
        assert r.returncode == 0
        assert "web_search" in r.stdout

    def test_route_no_route(self):
        r = self._run("route", "--from", "music_playback", "--to", "neon_database")
        assert r.returncode == 0
        assert "No direct route" in r.stdout

    def test_capability_command(self):
        r = self._run("capability", "SEARCH")
        assert r.returncode == 0
        assert "SEARCH" in r.stdout

    def test_path_command(self):
        r = self._run("path", "RESEARCH", "CODE")
        assert r.returncode == 0

    def test_validate_command(self):
        r = self._run("validate", str(WORKFLOW_PATH))
        assert r.returncode == 0

    def test_validate_strict_fails_on_warnings(self, tmp_path):
        wf = {
            "name": "strict-warning",
            "steps": [
                {"name": "build", "cluster": "claude_code_core", "depends_on": ["plan"]},
                {"name": "plan", "cluster": "sequential_thinking"},
            ],
        }
        path = tmp_path / "strict_warning.yaml"
        path.write_text(yaml.dump(wf))

        r = self._run("validate", str(path), "--strict")
        assert r.returncode == 1
        assert "STRICT-WARNING" in r.stdout

    def test_validate_malformed_yaml_json_contract(self, tmp_path):
        path = tmp_path / "malformed_cli.yaml"
        path.write_text("steps: [")

        r = self._run("validate", str(path), "--format", "json")
        assert r.returncode == 1
        payload = json.loads(r.stdout)
        assert payload["ok"] is False
        assert payload["errors"]

    def test_alternatives_command(self):
        r = self._run("alternatives", "web_search")
        assert r.returncode == 0
        assert "web_search" in r.stdout

    def test_clusters_command(self):
        r = self._run("clusters")
        assert r.returncode == 0
        assert "claude_code_core" in r.stdout

    def test_domains_command(self):
        r = self._run("domains")
        assert r.returncode == 0
        assert "CODE" in r.stdout

    def test_graph_command(self):
        r = self._run("graph")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) >= 64
