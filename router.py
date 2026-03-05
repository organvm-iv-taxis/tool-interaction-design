#!/usr/bin/env python3
"""
Tool Interaction Router v1.0
=============================
Executable router that loads the ontology and routing matrix,
then provides:
  1. Route discovery: given source → find compatible targets
  2. Workflow validation: validate DSL workflow files
  3. Capability lookup: find tools by capability
  4. Path finding: shortest tool chain between two domains
  5. Redundancy analysis: find alternative tool paths

Usage:
  python router.py route --from web_search --to knowledge_graph
  python router.py capability SEARCH
  python router.py path RESEARCH CODE
  python router.py validate workflow.yaml
  python router.py alternatives web_search
  python router.py clusters
  python router.py domains
  python router.py graph
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    from conductor.contracts import assert_contract
    from conductor.plugins import load_plugin_clusters
    from conductor.policy import load_policy
    from conductor.schemas import validate_document
except Exception:  # pragma: no cover - router can run standalone
    assert_contract = lambda *_args, **_kwargs: None  # type: ignore[assignment]
    load_plugin_clusters = lambda: []  # type: ignore[assignment]
    load_policy = lambda: None  # type: ignore[assignment]
    validate_document = lambda *_args, **_kwargs: []  # type: ignore[assignment]


# =============================================================================
# DATA MODELS
# =============================================================================


@dataclass
class Cluster:
    id: str
    domain: str
    label: str
    tools: list
    capabilities: list[str]
    protocols: list[str]
    input_types: list[str]
    output_types: list[str]
    capability_weights: dict[str, float] = field(default_factory=dict)


@dataclass
class Route:
    id: str
    from_cluster: str
    to_cluster: str
    data_flow: str
    protocol: str
    automatable: bool
    description: str = ""
    exemplars: list = field(default_factory=list)


@dataclass
class Alternative:
    cluster: str
    tools_ranked: list[str]


@dataclass
class ValidationMessage:
    code: str
    severity: str  # error | warning
    message: str
    hint: str = ""

    def render(self) -> str:
        text = f"[{self.code}] {self.message}"
        if self.hint:
            text += f" | Hint: {self.hint}"
        return text


@dataclass
class WorkflowValidationReport:
    messages: list[ValidationMessage] = field(default_factory=list)

    def add_error(self, code: str, message: str, hint: str = "") -> None:
        self.messages.append(ValidationMessage(code=code, severity="error", message=message, hint=hint))

    def add_warning(self, code: str, message: str, hint: str = "") -> None:
        self.messages.append(ValidationMessage(code=code, severity="warning", message=message, hint=hint))

    @property
    def errors(self) -> list[str]:
        return [msg.render() for msg in self.messages if msg.severity == "error"]

    @property
    def warnings(self) -> list[str]:
        return [msg.render() for msg in self.messages if msg.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        return not any(msg.severity == "error" for msg in self.messages)

    def to_dict(self) -> dict:
        return {
            "ok": self.is_valid,
            "errors": [msg.__dict__ for msg in self.messages if msg.severity == "error"],
            "warnings": [msg.__dict__ for msg in self.messages if msg.severity == "warning"],
        }


# =============================================================================
# ONTOLOGY LOADER
# =============================================================================


class Ontology:
    """Loads and indexes the tool ontology."""

    def __init__(self, ontology_path: Path):
        with open(ontology_path) as f:
            data = yaml.safe_load(f)

        plugin_clusters = load_plugin_clusters()
        if plugin_clusters:
            data = dict(data)
            base_clusters = data.get("clusters", [])
            if not isinstance(base_clusters, list):
                base_clusters = []
            data["clusters"] = [*base_clusters, *plugin_clusters]

        self.taxonomy = data.get("taxonomy", {})
        self.clusters: dict[str, Cluster] = {}
        self.relationship_types = data.get("relationship_types", [])
        self.relationships = data.get("relationships", [])

        for c in data.get("clusters", []):
            cluster = Cluster(
                id=c["id"],
                domain=c["domain"],
                label=c["label"],
                tools=c.get("tools", []),
                capabilities=c.get("capabilities", []),
                protocols=c.get("protocols", []),
                input_types=c.get("input_types", []),
                output_types=c.get("output_types", []),
                capability_weights=c.get("capability_weights", {}),
            )
            self.clusters[cluster.id] = cluster

        # Build indices
        self._cap_index: dict[str, list[str]] = defaultdict(list)
        self._domain_index: dict[str, list[str]] = defaultdict(list)
        self._protocol_index: dict[str, list[str]] = defaultdict(list)

        for cid, cluster in self.clusters.items():
            for cap in cluster.capabilities:
                self._cap_index[cap].append(cid)
            self._domain_index[cluster.domain].append(cid)
            for proto in cluster.protocols:
                self._protocol_index[proto].append(cid)

    def by_capability(self, cap: str) -> list[Cluster]:
        return [self.clusters[cid] for cid in self._cap_index.get(cap.upper(), [])]

    def by_domain(self, domain: str) -> list[Cluster]:
        return [self.clusters[cid] for cid in self._domain_index.get(domain.upper(), [])]

    def by_protocol(self, protocol: str) -> list[Cluster]:
        return [self.clusters[cid] for cid in self._protocol_index.get(protocol.upper(), [])]

    def compatible_targets(self, source_id: str) -> list[tuple[str, str]]:
        """Find all clusters that can receive data from source.

        Returns list of (target_id, matching_data_type) tuples.
        """
        source = self.clusters.get(source_id)
        if not source:
            return []

        results = []
        for tid, target in self.clusters.items():
            if tid == source_id:
                continue
            # Check data type compatibility
            overlap = set(source.output_types) & set(target.input_types)
            if overlap:
                # Check protocol compatibility
                proto_overlap = set(source.protocols) & set(target.protocols)
                # MCP and CLI can always bridge via Claude Code
                bridgeable = {"MCP", "CLI", "FILESYSTEM", "STDIO"}
                if proto_overlap or (set(source.protocols) & bridgeable and set(target.protocols) & bridgeable):
                    for dtype in overlap:
                        results.append((tid, dtype))

        return results

    def domains(self) -> list[dict]:
        return self.taxonomy.get("domains", [])

    def capabilities(self) -> list[str]:
        return self.taxonomy.get("capabilities", [])


# =============================================================================
# ROUTING ENGINE
# =============================================================================


class RoutingEngine:
    """Loads routes and provides path-finding between clusters."""

    def __init__(self, routing_path: Path, ontology: Ontology):
        with open(routing_path) as f:
            data = yaml.safe_load(f)

        self.ontology = ontology
        self.routes: dict[str, Route] = {}
        self.alternatives: list[Alternative] = []
        self._health_scores: dict[str, float] = {}  # cluster_id -> success_rate (0.0 to 1.0)

        for r in data.get("routes", []):
            route = Route(
                id=r["id"],
                from_cluster=r["from"],
                to_cluster=r["to"],
                data_flow=r.get("data_flow", ""),
                protocol=r.get("protocol", ""),
                automatable=r.get("automatable", True),
                description=r.get("description", ""),
                exemplars=r.get("exemplars", []),
            )
            self.routes[route.id] = route

        for a in data.get("alternatives", []):
            self.alternatives.append(
                Alternative(
                    cluster=a["cluster"],
                    tools_ranked=a["tools_ranked"],
                )
            )

        self.capability_routing = data.get("capability_routing", {})
        policy = load_policy()
        self._max_path_depth = getattr(policy, "max_path_depth", 5)
        self._max_paths_returned = getattr(policy, "max_paths_returned", 5)
        self._path_cache: dict[tuple[str, str], list[list[str]]] = {}
        self._cluster_path_cache: dict[tuple[str, str], list[list[str]]] = {}

        # Build adjacency graph
        self._adj: dict[str, list[str]] = defaultdict(list)
        for route in self.routes.values():
            self._adj[route.from_cluster].append(route.to_cluster)

    def inject_health_metrics(self, metrics: dict[str, float]) -> None:
        """Inject real-time success rates for clusters to bias pathfinding."""
        self._health_scores.update(metrics)
        # Invalidate caches when health changes
        self._path_cache.clear()
        self._cluster_path_cache.clear()

    def get_cluster_health(self, cluster_id: str) -> float:
        """Return success rate (0.0-1.0). Default to 1.0 (optimistic)."""
        return self._health_scores.get(cluster_id, 1.0)

    def find_routes(self, from_cluster: str, to_cluster: str) -> list[Route]:
        """Find direct routes between two clusters."""
        return [
            r for r in self.routes.values()
            if r.from_cluster == from_cluster and r.to_cluster == to_cluster
        ]

    def find_cluster_paths(
        self,
        from_cluster: str,
        to_cluster: str,
        *,
        max_depth: int | None = None,
        max_paths: int | None = None,
    ) -> list[list[str]]:
        """BFS to find cluster-level paths between two cluster IDs.
        
        Ranked by 'Cost' where cost = length / average_health.
        """
        cache_key = (from_cluster, to_cluster)
        if max_depth is None and max_paths is None and cache_key in self._cluster_path_cache:
            return [list(path) for path in self._cluster_path_cache[cache_key]]

        depth_limit = max_depth if max_depth is not None else self._max_path_depth
        path_limit = max_paths if max_paths is not None else self._max_paths_returned

        if from_cluster not in self.ontology.clusters or to_cluster not in self.ontology.clusters:
            return []

        queue: deque[list[str]] = deque([[from_cluster]])
        results: list[list[str]] = []
        seen_path_signatures: set[tuple[str, ...]] = set()

        while queue and len(results) < path_limit * 2:  # Over-fetch for re-ranking
            path = queue.popleft()
            current = path[-1]
            signature = tuple(path)
            if signature in seen_path_signatures:
                continue
            seen_path_signatures.add(signature)

            if current == to_cluster:
                results.append(path)
                continue

            if len(path) > depth_limit:
                continue

            # Sort neighbors by health if available
            neighbors = sorted(
                self._adj.get(current, []),
                key=lambda n: self.get_cluster_health(n),
                reverse=True
            )
            
            for neighbor in neighbors:
                if neighbor in path:
                    continue
                queue.append(path + [neighbor])

        # Rank results by aggregate health score
        def _path_score(p: list[str]) -> float:
            if not p: return 0.0
            avg_health = sum(self.get_cluster_health(c) for c in p) / len(p)
            # Preference for shorter, healthier paths
            return len(p) / (avg_health + 0.001)

        results.sort(key=_path_score)
        trimmed = results[:path_limit]
        if max_depth is None and max_paths is None:
            self._cluster_path_cache[cache_key] = [list(path) for path in trimmed]
        return trimmed

    def find_path(self, from_domain: str, to_domain: str) -> list[list[str]]:
        """BFS to find shortest paths between domains via cluster graph."""
        cache_key = (from_domain.upper(), to_domain.upper())
        if cache_key in self._path_cache:
            return [list(path) for path in self._path_cache[cache_key]]

        from_clusters = [c.id for c in self.ontology.by_domain(from_domain)]
        to_clusters = set(c.id for c in self.ontology.by_domain(to_domain))

        if not from_clusters or not to_clusters:
            return []

        paths: list[list[str]] = []
        for start in from_clusters:
            for target in to_clusters:
                found = self.find_cluster_paths(
                    start,
                    target,
                    max_depth=self._max_path_depth,
                    max_paths=self._max_paths_returned,
                )
                if found:
                    paths.extend(found)

        # Sort by length
        paths.sort(key=len)
        trimmed = paths[: self._max_paths_returned]
        self._path_cache[cache_key] = [list(path) for path in trimmed]
        return trimmed

    def get_alternatives(self, cluster_id: str) -> Optional[Alternative]:
        for alt in self.alternatives:
            if alt.cluster == cluster_id:
                return alt
        return None

    def capability_tools(self, capability: str) -> list[str]:
        return self.capability_routing.get(capability.upper(), [])


# =============================================================================
# WORKFLOW VALIDATOR
# =============================================================================


class WorkflowValidator:
    """Validates workflow DSL files against the ontology."""

    def __init__(self, ontology: Ontology, engine: RoutingEngine):
        self.ontology = ontology
        self.engine = engine

    def validate_report(self, workflow_path: Path) -> WorkflowValidationReport:
        """Validate a workflow file and return structured warnings/errors."""
        report = WorkflowValidationReport()
        try:
            with open(workflow_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            report.add_error(
                "WF-E007",
                f"Invalid YAML syntax: {exc}",
                "Fix YAML syntax so the workflow file can be parsed.",
            )
            return report

        if data is None:
            report.add_error(
                "WF-E008",
                "Workflow file is empty",
                "Define a workflow object with a `steps` array.",
            )
            return report

        if not isinstance(data, dict):
            report.add_error(
                "WF-E009",
                f"Top-level workflow document must be an object, got {type(data).__name__}",
                "Wrap workflow fields in a top-level mapping/object.",
            )
            return report

        schema_issues = validate_document("workflow", data)
        for issue in schema_issues:
            report.add_error(
                issue.code,
                f"{issue.path}: {issue.message}",
                "Fix YAML shape to satisfy workflow schema v1.",
            )

        # Handle file with examples section
        workflows = data.get("examples", [data]) if "examples" in data else [data]

        for wf_index, wf in enumerate(workflows):
            if not isinstance(wf, dict):
                report.add_error(
                    "WF-E010",
                    f"Workflow entry at index {wf_index} must be an object",
                    "Ensure every workflow entry in `examples` is a mapping/object.",
                )
                continue
            name = wf.get("name", "<unnamed>")
            steps = wf.get("steps", [])

            if not isinstance(steps, list):
                report.add_error(
                    "WF-E011",
                    f"[{name}] steps must be a list",
                    "Set `steps` to an array of step objects.",
                )
                continue

            if not steps:
                report.add_error("WF-E000", f"[{name}] No steps defined", "Add at least one step under `steps`.")
                continue

            step_names: set[str] = set()
            parallel_step_names: set[str] = set()
            top_level_index: dict[str, int] = {}
            parallel_name_counts: dict[str, int] = defaultdict(int)

            # First pass: collect names for dependency validation.
            for idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    report.add_error(
                        "WF-E012",
                        f"[{name}] Step at index {idx} must be an object",
                        "Each `steps` entry must be a mapping/object.",
                    )
                    continue
                sname = step.get("name", "<unnamed>")
                if sname in step_names:
                    report.add_error("WF-E001", f"[{name}] Duplicate step name: {sname}", "Use unique step names.")
                step_names.add(sname)
                top_level_index.setdefault(sname, idx)

                local_parallel_names: set[str] = set()
                parallel_steps = step.get("parallel", [])
                if not isinstance(parallel_steps, list):
                    report.add_error(
                        "WF-E013",
                        f"[{name}/{sname}] parallel must be a list",
                        "Set `parallel` to an array of step objects.",
                    )
                    parallel_steps = []
                for psub in parallel_steps:
                    if not isinstance(psub, dict):
                        report.add_error(
                            "WF-E014",
                            f"[{name}/{sname}] parallel step entry must be an object",
                            "Each `parallel` entry must be a mapping/object.",
                        )
                        continue
                    pname = psub.get("name", "<unnamed>")
                    if pname in local_parallel_names:
                        report.add_error(
                            "WF-E002",
                            f"[{name}/{sname}] Duplicate parallel step name: {pname}",
                            "Rename parallel steps to unique names within the branch.",
                        )
                    local_parallel_names.add(pname)
                    parallel_step_names.add(pname)
                    parallel_name_counts[pname] += 1

            known_dependencies = step_names | parallel_step_names

            # Second pass: validate references.
            for idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                sname = step.get("name", "<unnamed>")

                # Check cluster reference
                cluster = step.get("cluster")
                if cluster and cluster not in self.ontology.clusters and cluster != "*":
                    report.add_error(
                        "WF-E003",
                        f"[{name}/{sname}] Unknown cluster: {cluster}",
                        "Use `router.py clusters` to list valid cluster IDs.",
                    )
                elif cluster == "*":
                    report.add_warning(
                        "WF-W001",
                        f"[{name}/{sname}] Wildcard cluster '*' reduces routing precision",
                        "Replace '*' with explicit cluster IDs for deterministic routing.",
                    )

                # Check dependencies
                deps = step.get("depends_on", [])
                if not isinstance(deps, list):
                    report.add_error(
                        "WF-E004",
                        f"[{name}/{sname}] depends_on must be a list",
                        "Set depends_on to an array of step names.",
                    )
                    deps = []
                for dep in deps:
                    if dep not in known_dependencies:
                        report.add_error(
                            "WF-E005",
                            f"[{name}/{sname}] Unknown dependency: {dep}",
                            "Define the missing dependency step or remove it from depends_on.",
                        )
                    elif dep in top_level_index and top_level_index[dep] > idx:
                        report.add_warning(
                            "WF-W002",
                            f"[{name}/{sname}] Forward dependency on later step: {dep}",
                            "Consider reordering steps so dependencies appear earlier.",
                        )

                # Check parallel sub-steps
                parallel = step.get("parallel", [])
                if not isinstance(parallel, list):
                    report.add_error(
                        "WF-E013",
                        f"[{name}/{sname}] parallel must be a list",
                        "Set `parallel` to an array of step objects.",
                    )
                    parallel = []
                for psub in parallel:
                    if not isinstance(psub, dict):
                        report.add_error(
                            "WF-E014",
                            f"[{name}/{sname}] parallel step entry must be an object",
                            "Each `parallel` entry must be a mapping/object.",
                        )
                        continue
                    pname = psub.get("name", "<unnamed>")
                    pcluster = psub.get("cluster")
                    if pcluster and pcluster not in self.ontology.clusters and pcluster != "*":
                        report.add_error(
                            "WF-E006",
                            f"[{name}/{sname}/{pname}] Unknown cluster: {pcluster}",
                            "Use a valid cluster ID from ontology.",
                        )
                    elif pcluster == "*":
                        report.add_warning(
                            "WF-W001",
                            f"[{name}/{sname}/{pname}] Wildcard cluster '*' reduces routing precision",
                            "Replace '*' with explicit cluster IDs for deterministic routing.",
                        )

                    if pname in step_names:
                        report.add_warning(
                            "WF-W003",
                            f"[{name}/{sname}/{pname}] Name collides with top-level step; dependency resolution may be ambiguous",
                            "Rename one of the steps to avoid ambiguous dependency references.",
                        )
                    if parallel_name_counts.get(pname, 0) > 1:
                        report.add_warning(
                            "WF-W004",
                            f"[{name}/{sname}/{pname}] Parallel step name reused across branches; dependency references may be ambiguous",
                            "Use globally unique parallel step names when they are dependency targets.",
                        )

                    pdeps = psub.get("depends_on", [])
                    if not isinstance(pdeps, list):
                        report.add_error(
                            "WF-E004",
                            f"[{name}/{sname}/{pname}] depends_on must be a list",
                            "Set depends_on to an array of step names.",
                        )
                        pdeps = []
                    for dep in pdeps:
                        if dep not in known_dependencies:
                            report.add_error(
                                "WF-E005",
                                f"[{name}/{sname}/{pname}] Unknown dependency: {dep}",
                                "Define the missing dependency step or remove it from depends_on.",
                            )
                        elif dep in top_level_index and top_level_index[dep] > idx:
                            report.add_warning(
                                "WF-W002",
                                f"[{name}/{sname}/{pname}] Forward dependency on later top-level step: {dep}",
                                "Consider reordering steps so dependencies appear earlier.",
                            )

        dedup: dict[tuple[str, str, str], ValidationMessage] = {}
        for msg in report.messages:
            dedup[(msg.code, msg.severity, msg.message)] = msg
        report.messages = sorted(
            dedup.values(),
            key=lambda m: (m.severity, m.code, m.message),
        )
        return report

    def validate(self, workflow_path: Path, strict: bool = False) -> list[str]:
        """Validate a workflow file, returning errors (and warnings in strict mode)."""
        report = self.validate_report(workflow_path)
        if strict:
            return report.errors + report.warnings
        return report.errors


# =============================================================================
# CLI
# =============================================================================


def cmd_route(args, ontology: Ontology, engine: RoutingEngine):
    """Find routes between clusters."""
    routes = engine.find_routes(args.from_cluster, args.to_cluster)

    if routes:
        print(f"\n  Direct routes: {args.from_cluster} → {args.to_cluster}\n")
        for r in routes:
            print(f"  [{r.id}]")
            print(f"    Data flow : {r.data_flow}")
            print(f"    Protocol  : {r.protocol}")
            print(f"    Auto      : {'yes' if r.automatable else 'NO — human required'}")
            if r.description:
                print(f"    Desc      : {r.description}")
            if r.exemplars:
                print(f"    Exemplars :")
                for ex in r.exemplars:
                    src = ex.get("source", "?")
                    tgt = ex.get("target", "?")
                    mid = ex.get("intermediate", "")
                    chain = f"{src} → {mid} → {tgt}" if mid else f"{src} → {tgt}"
                    print(f"      {chain}")
            print()
    else:
        print(f"\n  No direct route: {args.from_cluster} → {args.to_cluster}")

        # Check data compatibility
        compatible = ontology.compatible_targets(args.from_cluster)
        matching = [(t, d) for t, d in compatible if t == args.to_cluster]
        if matching:
            print(f"  But data-type compatible via: {', '.join(d for _, d in matching)}")
            print(f"  Route could be created.\n")
        else:
            print(f"  Not directly data-compatible either.\n")

            # Try to find multi-hop path
            src_cluster = ontology.clusters.get(args.from_cluster)
            tgt_cluster = ontology.clusters.get(args.to_cluster)
            if src_cluster and tgt_cluster:
                paths = engine.find_path(src_cluster.domain, tgt_cluster.domain)
                if paths:
                    print(f"  Multi-hop paths via domain graph:")
                    for p in paths:
                        print(f"    {'  →  '.join(p)}")
                    print()


def cmd_capability(args, ontology: Ontology, engine: RoutingEngine):
    """Find tools by capability."""
    cap = args.capability.upper()
    clusters = ontology.by_capability(cap)

    if not clusters:
        print(f"\n  No clusters with capability: {cap}\n")
        return

    print(f"\n  Clusters with capability [{cap}]:\n")
    for c in clusters:
        tool_count = len(c.tools)
        print(f"  [{c.id}] {c.label}")
        print(f"    Domain    : {c.domain}")
        print(f"    Protocols : {', '.join(c.protocols)}")
        print(f"    Tools     : {tool_count}")
        print(f"    I/O       : {', '.join(c.input_types)} → {', '.join(c.output_types)}")
        print()

    # Show routing-matrix preferred order
    preferred = engine.capability_tools(cap)
    if preferred:
        print(f"  Routing priority for [{cap}]:")
        for i, cluster_id in enumerate(preferred, 1):
            label = ontology.clusters[cluster_id].label if cluster_id in ontology.clusters else cluster_id
            print(f"    {i}. {cluster_id} ({label})")
        print()


def cmd_path(args, ontology: Ontology, engine: RoutingEngine):
    """Find paths between domains."""
    paths = engine.find_path(args.from_domain.upper(), args.to_domain.upper())

    if not paths:
        print(f"\n  No paths found: {args.from_domain} → {args.to_domain}\n")
        return

    print(f"\n  Paths: {args.from_domain} → {args.to_domain}\n")
    for i, path in enumerate(paths, 1):
        labels = []
        for cid in path:
            c = ontology.clusters.get(cid)
            labels.append(f"{cid} ({c.label})" if c else cid)
        print(f"  Path {i} ({len(path)} hops):")
        print(f"    {'  →  '.join(labels)}")
        print()


def cmd_validate(args, ontology: Ontology, engine: RoutingEngine):
    """Validate workflow DSL file."""
    validator = WorkflowValidator(ontology, engine)
    path = Path(args.file)
    policy = load_policy()
    strict_mode = bool(args.strict or getattr(policy, "strict_validation_default", False))

    if not path.exists():
        print(f"  File not found: {path}", file=sys.stderr)
        sys.exit(1)

    report = validator.validate_report(path)
    should_fail = bool(report.errors or (strict_mode and report.warnings))

    if args.format == "json":
        payload = {
            "file": str(path),
            "strict": strict_mode,
            "ok": not should_fail,
            **report.to_dict(),
        }
        assert_contract("router_validate_output", payload)
        print(json.dumps(payload, indent=2))
        if should_fail:
            sys.exit(1)
        return

    if report.errors or report.warnings:
        print(f"\n  Validation issues in {path}:\n")
        for issue in report.errors:
            print(f"    ERROR   {issue}")
        for warning in report.warnings:
            marker = "WARNING" if not strict_mode else "STRICT-WARNING"
            print(f"    {marker:<7} {warning}")

        total = len(report.errors) + len(report.warnings)
        strict_note = " (strict mode)" if strict_mode else ""
        print(f"\n  {total} issue(s) found{strict_note}.")
        if report.warnings and not strict_mode:
            print("  Note: warnings do not fail validation unless --strict is enabled.")
        print()

    if should_fail:
        sys.exit(1)

    print(f"\n  ✓ {path} is valid.\n")


def cmd_alternatives(args, ontology: Ontology, engine: RoutingEngine):
    """Show alternative tools for a cluster."""
    alt = engine.get_alternatives(args.cluster)

    if alt:
        print(f"\n  Alternatives for [{args.cluster}]:\n")
        for i, tool in enumerate(alt.tools_ranked, 1):
            print(f"    {i}. {tool}")
        print()
    else:
        print(f"\n  No defined alternatives for [{args.cluster}]")

        # Show compatible clusters
        cluster = ontology.clusters.get(args.cluster)
        if cluster:
            same_cap = set()
            for cap in cluster.capabilities:
                for c in ontology.by_capability(cap):
                    if c.id != args.cluster:
                        same_cap.add(c.id)
            if same_cap:
                print(f"  Clusters with overlapping capabilities:")
                for cid in sorted(same_cap):
                    c = ontology.clusters[cid]
                    print(f"    - {cid} ({c.label})")
        print()


def cmd_clusters(args, ontology: Ontology, engine: RoutingEngine):
    """List all clusters."""
    print(f"\n  {'ID':<30} {'DOMAIN':<20} {'LABEL':<35} {'TOOLS':>5}")
    print(f"  {'─'*30} {'─'*20} {'─'*35} {'─'*5}")
    for cid, c in sorted(ontology.clusters.items()):
        print(f"  {cid:<30} {c.domain:<20} {c.label:<35} {len(c.tools):>5}")
    print(f"\n  Total: {len(ontology.clusters)} clusters\n")


def cmd_domains(args, ontology: Ontology, engine: RoutingEngine):
    """List all domains with cluster counts."""
    print(f"\n  {'DOMAIN':<20} {'CLUSTERS':>8}  DESCRIPTION")
    print(f"  {'─'*20} {'─'*8}  {'─'*40}")
    for d in ontology.domains():
        count = len(ontology.by_domain(d["id"]))
        print(f"  {d['id']:<20} {count:>8}  {d['description']}")
    print()


def cmd_graph(args, ontology: Ontology, engine: RoutingEngine):
    """Output adjacency list as JSON for external visualization."""
    graph = {
        "nodes": [],
        "edges": [],
    }

    for cid, c in ontology.clusters.items():
        graph["nodes"].append({
            "id": cid,
            "domain": c.domain,
            "label": c.label,
            "capabilities": c.capabilities,
            "protocols": c.protocols,
            "tool_count": len(c.tools),
        })

    for route in engine.routes.values():
        graph["edges"].append({
            "id": route.id,
            "source": route.from_cluster,
            "target": route.to_cluster,
            "data_flow": route.data_flow,
            "automatable": route.automatable,
        })

    print(json.dumps(graph, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Tool Interaction Router",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    base = Path(__file__).parent
    parser.add_argument(
        "--ontology",
        type=Path,
        default=base / "ontology.yaml",
        help="Path to ontology.yaml",
    )
    parser.add_argument(
        "--routing",
        type=Path,
        default=base / "routing-matrix.yaml",
        help="Path to routing-matrix.yaml",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # route
    p_route = sub.add_parser("route", help="Find routes between clusters")
    p_route.add_argument("--from", dest="from_cluster", required=True)
    p_route.add_argument("--to", dest="to_cluster", required=True)

    # capability
    p_cap = sub.add_parser("capability", help="Find clusters by capability")
    p_cap.add_argument("capability", type=str)

    # path
    p_path = sub.add_parser("path", help="Find paths between domains")
    p_path.add_argument("from_domain", type=str)
    p_path.add_argument("to_domain", type=str)

    # validate
    p_val = sub.add_parser("validate", help="Validate a workflow DSL file")
    p_val.add_argument("file", type=str)
    p_val.add_argument("--strict", action="store_true", help="Treat warnings as validation failures")
    p_val.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    # alternatives
    p_alt = sub.add_parser("alternatives", help="Show alternative tools")
    p_alt.add_argument("cluster", type=str)

    # clusters
    sub.add_parser("clusters", help="List all clusters")

    # domains
    sub.add_parser("domains", help="List all domains")

    # graph
    sub.add_parser("graph", help="Output graph as JSON")

    args = parser.parse_args()

    # Load data
    ontology = Ontology(args.ontology)
    engine = RoutingEngine(args.routing, ontology)

    # Dispatch
    commands = {
        "route": cmd_route,
        "capability": cmd_capability,
        "path": cmd_path,
        "validate": cmd_validate,
        "alternatives": cmd_alternatives,
        "clusters": cmd_clusters,
        "domains": cmd_domains,
        "graph": cmd_graph,
    }

    commands[args.command](args, ontology, engine)


if __name__ == "__main__":
    main()
