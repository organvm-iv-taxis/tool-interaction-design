# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A queryable taxonomy and routing system for 578 tools across Claude Code built-ins, MCP servers, macOS applications, Homebrew packages, and runtime ecosystems. The system maps tools into 64 clusters across 12 domains, defines data-flow routes between clusters, and provides a workflow DSL for composing multi-tool pipelines.

On top of this taxonomy sits the **Conductor OS** — an AI-conductor operating system that adds session lifecycle management, governance/WIP enforcement, workflow compilation and execution, observability, and a Patchbay command center.

## Architecture

```
ontology.yaml          ← Layer 1: Taxonomy (12 domains, 64 clusters, 578 tools)
    ↓ referenced by
routing-matrix.yaml    ← Layer 2: 32+ directed routes between clusters
    ↓ composed into
workflow-dsl.yaml      ← Layer 3: Pipeline DSL with 7 primitives
    ↓ validated/executed by
router.py              ← Layer 4a: Standalone CLI (8 commands, BFS pathfinding)
conductor/             ← Layer 4b: Full OS — sessions, governance, workflows, exports
mcp_server.py          ← Layer 4c: MCP server exposing conductor as live tools
```

### Key Concepts

- **Cluster**: A stable grouping of related tools (e.g., `web_search` contains Perplexity, Tavily, WebSearch). Clusters are the routing unit — individual tools change, clusters persist.
- **Route**: A directed data flow between two clusters with protocol and data-type constraints.
- **Protocol bridging**: MCP, CLI, FILESYSTEM, STDIO are automatable. GUI is not.
- **Session lifecycle**: FRAME → SHAPE → BUILD → PROVE → DONE. Each phase activates specific tool clusters and AI roles.
- **WorkflowCompiler**: JIT-compiles RoutingEngine paths into stateful execution "scores" with health-aware checkpoint injection.

### Conductor Package (`conductor/`)

The `conductor/` package is the core OS. Key modules:

| Module | Purpose |
|--------|---------|
| `cli.py` | CLI parser and dispatch (`python3 -m conductor`) |
| `constants.py` | All paths, organ mapping, phase config, exceptions |
| `patchbay.py` | Read-only command center composing all layers into briefings |
| `session.py` | Session lifecycle (start/phase/close), stats tracking |
| `governance.py` | Registry operations, WIP limits, audit, promotion state machine |
| `executor.py` | Workflow DSL runtime — interprets steps, persists state |
| `compiler.py` | JIT workflow compilation from routing paths with pre-mortem hardening |
| `handoff.py` | Canonical handoff envelopes, traces, edge-health reporting |
| `schemas.py` | JSON Schema loading/validation (schemas in `schemas/v1/`) |
| `contracts.py` | Output contract assertions for CLI/MCP responses |
| `observability.py` | Event logging, metrics, trend analysis |
| `plugins.py` | Plugin cluster loading from external manifests |
| `policy.py` | Policy bundles for WIP/promotion limits |
| `wiring.py` | Workspace-wide hook injection and MCP server configuration |
| `product.py` | Export process kits, Gemini extensions, fleet dashboards |
| `graph.py` | Mermaid graph generation from registry state |

### Data Flow

`router.py` can run standalone (only needs PyYAML). The `conductor/` package imports from `router.py` for ontology/routing queries but adds sessions, governance (reads `registry-v2.json` and `governance-rules.json` from the ORGANVM corpus), workflow execution, and observability.

The MCP server (`mcp_server.py`) exposes conductor capabilities as tools for real-time AI assistant integration.

## Session Start Protocol

Before beginning any work session, run `conductor patch` to see system state:

```bash
python3 -m conductor patch                  # Full briefing
python3 -m conductor patch --json           # Machine-readable output
python3 -m conductor patch queue --organ III # Queue for one organ
```

## Commands

```bash
# Setup
pip install pyyaml                    # Required
pip install jsonschema                # Optional: enables schema validation

# Patchbay — command center
python3 -m conductor patch                                 # Full system briefing
python3 -m conductor patch --json                          # JSON output
python3 -m conductor patch pulse                           # System pulse only
python3 -m conductor patch queue                           # Work queue only
python3 -m conductor patch stats                           # Lifetime stats only
python3 -m conductor patch --organ III                     # Filter to one organ
python3 -m conductor patch --watch                         # Live updates every 5s

# Session lifecycle
python3 -m conductor session start --organ III --repo my-repo --scope "Feature X"
python3 -m conductor session phase shape                   # Transition phase
python3 -m conductor session status                        # Show current session
python3 -m conductor session close                         # Close and log

# Governance
python3 -m conductor wip check                             # Show WIP status
python3 -m conductor wip promote <repo> <STATE>            # Promote with WIP enforcement
python3 -m conductor wip auto-promote --apply              # Auto-promote healthy repos
python3 -m conductor audit --organ III                     # Organ health audit
python3 -m conductor stale --days 30                       # Find stale CANDIDATE repos
python3 -m conductor enforce generate                      # Generate rulesets/workflows

# Workflow execution
python3 -m conductor workflow list                         # List available workflows
python3 -m conductor workflow start --name <name>          # Start workflow
python3 -m conductor workflow status                       # Show execution state
python3 -m conductor workflow step --name <step>           # Execute one step

# JIT workflow compilation
python3 -m conductor compose --goal "description" --from <cluster> --to <cluster>

# Route simulation
python3 -m conductor route simulate --from <cluster> --to <cluster> --objective "..."

# Router CLI (also available standalone via router.py)
python3 -m conductor route --from <cluster> --to <cluster>
python3 -m conductor capability SEARCH
python3 -m conductor clusters
python3 -m conductor domains

# Diagnostics
python3 -m conductor doctor                                # Integrity diagnostics
python3 -m conductor doctor --strict                       # Exit non-zero on any issue
python3 -m conductor plugins doctor                        # Validate plugin manifests
python3 -m conductor policy simulate                       # Policy limit analysis
python3 -m conductor observability report                  # Metrics and trends

# Exports
python3 -m conductor export process-kit --output ./kit     # Export reusable process kit
python3 -m conductor export gemini-extension               # Export as Gemini CLI extension
python3 -m conductor export fleet-dashboard                # Static HTML dashboard
python3 -m conductor patterns --export-essay               # Mine session logs
```

## Testing

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run a single test file
python3 -m pytest tests/test_router.py -v

# Run a single test
python3 -m pytest tests/test_router.py::test_function_name -v

# Key test files
tests/test_conductor.py        # Core conductor/session/governance
tests/test_router.py           # Router CLI and pathfinding
tests/test_executor.py         # Workflow execution engine
tests/test_handoff.py          # Handoff envelopes and edge health
tests/test_mcp_server.py       # MCP server tool responses
tests/test_e2e_flow.py         # End-to-end session flow
tests/test_fuzz_validation.py  # Fuzzing workflow validator
tests/test_output_contracts.py # JSON schema contract tests
```

## Validation

```bash
# Validate all YAML files parse correctly
python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ['ontology.yaml','routing-matrix.yaml','workflow-dsl.yaml']]"

# Validate workflow DSL
python3 router.py validate workflow-dsl.yaml
python3 router.py validate workflow-dsl.yaml --strict     # Warnings fail too

# Validate process/generated assets
python3 tools/validate_process_assets.py
python3 tools/validate_schemas.py

# Full doctor check
python3 -m conductor doctor --strict
```

## File Layout

### Core Data Files (edit carefully — these define the taxonomy)
- `ontology.yaml` — 12 domains, 64 clusters, 578 tools, capabilities, protocols
- `routing-matrix.yaml` — directed routes, alternatives, capability_routing
- `workflow-dsl.yaml` — pipeline DSL examples with 7 primitives

### Persisted State (dot-files, gitignored)
- `.conductor-session.json` — active session state
- `.conductor-stats.json` — lifetime session statistics
- `.conductor-work-registry.json` — persistent work queue with ownership
- `.conductor-workflow-state.json` — active workflow execution state
- `.conductor-handoffs.jsonl` — handoff envelope log
- `.conductor-traces.jsonl` — execution trace log
- `.conductor.yaml` — optional per-project config overrides (phase clusters, etc.)

### Schemas (`schemas/v1/`)
JSON Schemas for contracts (handoffs, traces, route decisions, MCP responses) and data (registry, governance, workflows, plugin manifests). Used by `conductor.schemas.validate_document()`.

### Research Pipeline
`research/` has a three-stage pipeline: `inbox/` (raw documents) → `digested/` (structured YAML extraction) → `implemented/` (applied to core files then moved here). See `research/PROCESSING.md`.

### Generated Artifacts (`generated/`)
CI rulesets per organ, workflow validators, PR/issue templates — produced by `conductor enforce generate`.

## Known Limitations

- Tool entries in `ontology.yaml` use inconsistent typing (bare strings vs `- cli: name` vs `- mcp: name`)
- Routing matrix has 32 routes for 64 clusters (<1% of possible edges) — sparse
- `relationship_types` in ontology are defined but no instances are populated
- No capability weighting — clusters list capabilities without primary/secondary distinction
- Conductor reads `registry-v2.json` and `governance-rules.json` from `~/Workspace/meta-organvm/organvm-corpvs-testamentvm/` — ensure that path exists or set `ORGANVM_CORPUS_DIR`

## Environment Variables

- `ORGANVM_WORKSPACE_DIR` — Override workspace root (default: `~/Workspace`)
- `ORGANVM_CORPUS_DIR` — Override registry/governance location
- `CONDUCTOR_DEBUG_TRACEBACK` — Set to `1` for full stack traces on CLI errors
