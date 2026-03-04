# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A queryable taxonomy and routing system for 578 tools across Claude Code built-ins, MCP servers, macOS applications, Homebrew packages, and runtime ecosystems. The system maps tools into 64 clusters across 12 domains, defines data-flow routes between clusters, and provides a workflow DSL for composing multi-tool pipelines.

## Architecture

Four data files + one executable form a layered system:

```
ontology.yaml          ← Layer 1: Taxonomy (12 domains, 64 clusters, 578 tools)
    ↓ referenced by
routing-matrix.yaml    ← Layer 2: 32+ directed routes between clusters
    ↓ composed into
workflow-dsl.yaml      ← Layer 3: Pipeline DSL with 7 primitives
    ↓ validated by
router.py              ← Layer 4: Executable CLI (8 commands, BFS pathfinding)
```

**graph.mmd** is a Mermaid visualization of the cluster graph (render with `mmdc` or mermaid.live).

### Key Concepts

- **Cluster**: A stable grouping of related tools (e.g., `web_search` contains Perplexity, Tavily, WebSearch, DuckDuckGo). Clusters are the routing unit — individual tools change, clusters persist.
- **Route**: A directed data flow between two clusters with protocol and data-type constraints (e.g., `web_search → knowledge_graph` via MCP, TEXT → JSON).
- **Protocol bridging**: MCP, CLI, FILESYSTEM, and STDIO are all bridgeable and automatable. GUI is not automatable. This determines which routes can be executed without human intervention.
- **Capability routing**: Each of 20 capabilities (READ, SEARCH, DEPLOY, etc.) maps to a prioritized list of clusters.

### Ontology Schema (ontology.yaml)

Each cluster entry has: `id`, `domain`, `label`, `tools` (list), `capabilities`, `protocols`, `input_types`, `output_types`. Clusters are grouped under domains. The taxonomy section defines the valid enums for domains, capabilities, protocols, and data_types.

### Routing Matrix Schema (routing-matrix.yaml)

Top-level keys: `routes` (list of directed edges), `alternatives` (ranked fallback clusters), `capability_routing` (capability → cluster priority), `routing_rules` (compatibility predicates — currently in comments, to be structured).

### Workflow DSL (workflow-dsl.yaml)

Seven primitives: `pipe` (|>), `fan_out` (=>), `fan_in` (<=), `gate` (?>), `loop` (@>), `fallback` (!>), `checkpoint` (||). Steps reference clusters from the ontology. Expression language supports `${step.field}` references and transforms (`| json`, `| text`, `| count`, etc.).

## Session Start Protocol

Before beginning any work session, run `conductor patch` to see system state:

```bash
python3 -m conductor patch                  # Full briefing
python3 -m conductor patch --json           # Machine-readable output
python3 -m conductor patch queue --organ III # Queue for one organ
```

## Commands

```bash
# Only dependency is PyYAML
pip install pyyaml

# Patchbay — command center
python3 -m conductor patch                                 # Full system briefing
python3 -m conductor patch --json                          # JSON output
python3 -m conductor patch pulse                           # System pulse only
python3 -m conductor patch queue                           # Work queue only
python3 -m conductor patch stats                           # Lifetime stats only
python3 -m conductor patch --organ III                     # Filter to one organ

# Router CLI — all commands
python3 router.py route --from <cluster> --to <cluster>   # Find routes between clusters
python3 router.py capability <CAPABILITY> [DOMAIN]         # Find clusters by capability
python3 router.py path <FROM_DOMAIN> <TO_DOMAIN>           # BFS shortest path between domains
python3 router.py validate <workflow.yaml>                 # Validate a workflow DSL file
python3 router.py alternatives <cluster>                   # Show ranked fallback clusters
python3 router.py clusters [DOMAIN]                        # List clusters, optionally filtered
python3 router.py domains                                  # List all 12 domains
python3 router.py graph                                    # Export cluster graph as JSON

# Validate all YAML files parse correctly
python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ['ontology.yaml','routing-matrix.yaml','workflow-dsl.yaml']]"
```

## Research Pipeline

`research/` has a three-stage processing pipeline: `inbox/` (raw documents) → `digested/` (structured YAML extraction) → `implemented/` (applied to core files then moved here). See `research/PROCESSING.md` for naming conventions and processing protocol.

## Known Limitations (from E2G report)

- Tool entries use inconsistent typing (bare strings vs `- cli: name` vs `- mcp: name`) — not yet programmatically resolvable
- Routing matrix has 32 routes for 64 clusters (<1% of possible edges) — sparse
- Workflow DSL has no runtime executor — validation only via `router.py validate`
- `relationship_types` in ontology are defined but no instances are populated
- No capability weighting — clusters list capabilities without primary/secondary distinction
- No automated tests for router.py
