# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

The operational heart of ORGANVM's orchestration layer — a system that makes individual-to-enterprise amplification executable. Where `meta-organvm/VISION.md` declares that one person should be able to operate at institutional scale, the Conductor is **how** that actually works: routing 578 tools across 64 clusters so that a single practitioner can compose agent workflows, enforce governance, and ship across 8 organs without institutional headcount.

Concretely: a queryable taxonomy and routing system for 578 tools across Claude Code built-ins, MCP servers, macOS applications, Homebrew packages, and runtime ecosystems. The system maps tools into 64 clusters across 12 domains, defines data-flow routes between clusters, and provides a workflow DSL for composing multi-tool pipelines.

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

## Dispatch Protocol

Before starting BUILD-phase work, call `conductor_fleet_dispatch` with a description
of the task. If the recommended agent is NOT Claude:
1. Call `conductor_fleet_guardrailed_handoff` to generate an envelope
2. Present the envelope markdown to the user
3. Tell the user which agent to hand it to and what repo to run it in
4. Do NOT do the work yourself — reserve your tokens for strategic work

This is not optional. The system is designed for force multiplication: Claude handles
architecture, audit, governance, and cross-verification. Mechanical and tactical work
goes to the bench (Codex for scaffolding, Gemini for content/research velocity,
OpenCode for well-scoped infrastructure).

### Verification on Return

When preflight shows a pending verification (`[VERIFY]` in the runway briefing):
1. Run `git diff` to see what the dispatched agent changed
2. Call `conductor_fleet_cross_verify` with the changed files
3. If violations found, fix them before continuing
4. If passed, the active handoff is cleared automatically and you proceed

### Work Type Quick Reference

| Work Type | Cognitive Class | Claude? | Dispatch to? |
|-----------|----------------|---------|-------------|
| architecture | strategic | YES | — |
| debugging | strategic | YES | — |
| audit | strategic | YES | — |
| research | strategic | YES | Perplexity for web research |
| testing | tactical | YES | Codex for test stubs |
| content_generation | tactical | Consider | Gemini for drafting |
| boilerplate_generation | mechanical | NO | Codex or Gemini |
| mechanical_refactoring | mechanical | NO | Codex or OpenCode |

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

<!-- ORGANVM:AUTO:START -->
## System Context (auto-generated — do not edit)

**Organ:** ORGAN-IV (Orchestration) | **Tier:** flagship | **Status:** GRADUATED
**Org:** `organvm-iv-taxis` | **Repo:** `tool-interaction-design`

### Edges
- **Produces** → `conductor-session-lifecycle`
- **Produces** → `tool-interaction-ontology`
- **Produces** → `agent-coordination-protocol`
- **Consumes** ← `orchestration-artifact`

### Siblings in Orchestration
`orchestration-start-here`, `petasum-super-petasum`, `universal-node-network`, `.github`, `agentic-titan`, `agent--claude-smith`, `a-i--skills`, `system-governance-framework`, `reverse-engine-recursive-run`, `collective-persona-operations`, `contrib--adenhq-hive`, `contrib--ipqwery-ipapi-py`, `contrib--primeinc-github-stars`, `contrib--temporal-sdk-python`, `contrib--dbt-mcp` ... and 2 more

### Governance
- *Standard ORGANVM governance applies*

*Last synced: 2026-03-26T19:39:27Z*

## Session Review Protocol

At the end of each session that produces or modifies files:
1. Run `organvm session review --latest` to get a session summary
2. Check for unimplemented plans: `organvm session plans --project .`
3. Export significant sessions: `organvm session export <id> --slug <slug>`
4. Run `organvm prompts distill --dry-run` to detect uncovered operational patterns

Transcripts are on-demand (never committed):
- `organvm session transcript <id>` — conversation summary
- `organvm session transcript <id> --unabridged` — full audit trail
- `organvm session prompts <id>` — human prompts only


## Active Directives

| Scope | Phase | Name | Description |
|-------|-------|------|-------------|
| system | any | prompting-standards | Prompting Standards |
| system | any | research-standards-bibliography | APPENDIX: Research Standards Bibliography |
| system | any | phase-closing-and-forward-plan | METADOC: Phase-Closing Commemoration & Forward Attack Plan |
| system | any | research-standards | METADOC: Architectural Typology & Research Standards |
| system | any | sop-ecosystem | METADOC: SOP Ecosystem — Taxonomy, Inventory & Coverage |
| system | any | autonomous-content-syndication | SOP: Autonomous Content Syndication (The Broadcast Protocol) |
| system | any | autopoietic-systems-diagnostics | SOP: Autopoietic Systems Diagnostics (The Mirror of Eternity) |
| system | any | background-task-resilience | background-task-resilience |
| system | any | cicd-resilience-and-recovery | SOP: CI/CD Pipeline Resilience & Recovery |
| system | any | community-event-facilitation | SOP: Community Event Facilitation (The Dialectic Crucible) |
| system | any | context-window-conservation | context-window-conservation |
| system | any | conversation-to-content-pipeline | SOP — Conversation-to-Content Pipeline |
| system | any | cross-agent-handoff | SOP: Cross-Agent Session Handoff |
| system | any | cross-channel-publishing-metrics | SOP: Cross-Channel Publishing Metrics (The Echo Protocol) |
| system | any | data-migration-and-backup | SOP: Data Migration and Backup Protocol (The Memory Vault) |
| system | any | document-audit-feature-extraction | SOP: Document Audit & Feature Extraction |
| system | any | dynamic-lens-assembly | SOP: Dynamic Lens Assembly |
| system | any | essay-publishing-and-distribution | SOP: Essay Publishing & Distribution |
| system | any | formal-methods-applied-protocols | SOP: Formal Methods Applied Protocols |
| system | any | formal-methods-master-taxonomy | SOP: Formal Methods Master Taxonomy (The Blueprint of Proof) |
| system | any | formal-methods-tla-pluscal | SOP: Formal Methods — TLA+ and PlusCal Verification (The Blueprint Verifier) |
| system | any | generative-art-deployment | SOP: Generative Art Deployment (The Gallery Protocol) |
| system | any | market-gap-analysis | SOP: Full-Breath Market-Gap Analysis & Defensive Parrying |
| system | any | mcp-server-fleet-management | SOP: MCP Server Fleet Management (The Server Protocol) |
| system | any | multi-agent-swarm-orchestration | SOP: Multi-Agent Swarm Orchestration (The Polymorphic Swarm) |
| system | any | network-testament-protocol | SOP: Network Testament Protocol (The Mirror Protocol) |
| system | any | open-source-licensing-and-ip | SOP: Open Source Licensing and IP (The Commons Protocol) |
| system | any | performance-interface-design | SOP: Performance Interface Design (The Stage Protocol) |
| system | any | pitch-deck-rollout | SOP: Pitch Deck Generation & Rollout |
| system | any | polymorphic-agent-testing | SOP: Polymorphic Agent Testing (The Adversarial Protocol) |
| system | any | promotion-and-state-transitions | SOP: Promotion & State Transitions |
| system | any | recursive-study-feedback | SOP: Recursive Study & Feedback Loop (The Ouroboros) |
| system | any | repo-onboarding-and-habitat-creation | SOP: Repo Onboarding & Habitat Creation |
| system | any | research-to-implementation-pipeline | SOP: Research-to-Implementation Pipeline (The Gold Path) |
| system | any | security-and-accessibility-audit | SOP: Security & Accessibility Audit |
| system | any | session-self-critique | session-self-critique |
| system | any | smart-contract-audit-and-legal-wrap | SOP: Smart Contract Audit and Legal Wrap (The Ledger Protocol) |
| system | any | source-evaluation-and-bibliography | SOP: Source Evaluation & Annotated Bibliography (The Refinery) |
| system | any | stranger-test-protocol | SOP: Stranger Test Protocol |
| system | any | strategic-foresight-and-futures | SOP: Strategic Foresight & Futures (The Telescope) |
| system | any | styx-pipeline-traversal | SOP: Styx Pipeline Traversal (The 7-Organ Transmutation) |
| system | any | system-dashboard-telemetry | SOP: System Dashboard Telemetry (The Panopticon Protocol) |
| system | any | the-descent-protocol | the-descent-protocol |
| system | any | the-membrane-protocol | the-membrane-protocol |
| system | any | theoretical-concept-versioning | SOP: Theoretical Concept Versioning (The Epistemic Protocol) |
| system | any | theory-to-concrete-gate | theory-to-concrete-gate |
| system | any | typological-hermeneutic-analysis | SOP: Typological & Hermeneutic Analysis (The Archaeology) |

Linked skills: cicd-resilience-and-recovery, continuous-learning-agent, evaluation-to-growth, genesis-dna, multi-agent-workforce-planner, promotion-and-state-transitions, quality-gate-baseline-calibration, repo-onboarding-and-habitat-creation, structural-integrity-audit


**Prompting (Anthropic)**: context 200K tokens, format: XML tags, thinking: extended thinking (budget_tokens)


## Ecosystem Status

- **delivery**: 2/2 live, 0 planned
- **content**: 0/1 live, 1 planned

Run: `organvm ecosystem show tool-interaction-design` | `organvm ecosystem validate --organ IV`


## Task Queue (from pipeline)

**358** pending tasks | Last pipeline: unknown

- `47cc43373336` Multi-session support — Sessions stored in `active-sessions/{agent}.json`. Different agents coexist. Legacy `session
- `b717429722c9` CLI — `conductor preflight --agent claude --cwd $PWD [--json] [--no-start]`
- `b4e36ab4f1ee` MCP tools — `conductor_preflight`, `conductor_active_sessions`
- `77babaf21805` Hooks — Claude hook (`claude-prompt-gate.sh`) now calls preflight when venv available. New `codex-preflight.sh` for
- `69dad1b53c7a` 1. Shell Initialization Layer (MISSING) [bash, go, homebrew]
- `04a7fe4fd797` Status line command — Runs `statusline-command.sh` (implementation unknown, not yet explored) [bash, go, homebrew]
- `b417d8fd54aa` UserPromptSubmit hook — Runs `claude-prompt-gate.sh` with 5-second timeout [bash, go, homebrew]
- `0e3a69b85695` 2. Claude Code Settings Layer (ACTIVE) [bash, go, homebrew]
- ... and 350 more

Cross-organ links: 591 | Top tags: `mcp`, `python`, `bash`, `pytest`, `fastapi`

Run: `organvm atoms pipeline --write && organvm atoms fanout --write`


## System Density (auto-generated)

AMMOI: 56% | Edges: 41 | Tensions: 0 | Clusters: 0 | Adv: 8 | Events(24h): 24029
Structure: 8 organs / 127 repos / 1654 components (depth 17) | Inference: 0% | Organs: META-ORGANVM:64%, ORGAN-I:55%, ORGAN-II:47%, ORGAN-III:55% +4 more
Last pulse: 2026-03-26T19:39:26 | Δ24h: +3.6% | Δ7d: n/a


## Dialect Identity (Trivium)

**Dialect:** GOVERNANCE_LOGIC | **Classical Parallel:** Rhetoric | **Translation Role:** The Meta-Logic — governance rules ARE propositions

Strongest translations: I (formal), V (structural), META (structural)

Scan: `organvm trivium scan IV <OTHER>` | Matrix: `organvm trivium matrix` | Synthesize: `organvm trivium synthesize`

<!-- ORGANVM:AUTO:END -->
