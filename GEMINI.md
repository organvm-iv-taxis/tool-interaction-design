# Conductor: The AI-Conductor's Operating System

Conductor is a high-level orchestration system for managing tool interaction design, session lifecycles, and governance across a multi-organ creative-institutional framework. It provides a queryable taxonomy, a routing engine for tool data-flow, and a workflow DSL for pipeline composition.

## 🏛 Architecture

The system is built on a 4-layer data-and-logic stack:

1.  **Taxonomy (Layer 1):** `ontology.yaml` defines 64 tool clusters across 12 functional domains.
2.  **Routing (Layer 2):** `routing-matrix.yaml` defines directed data-flow routes and capability-based priorities.
3.  **Composition (Layer 3):** `workflow-dsl.yaml` provides a pipeline DSL with 7 primitives (`pipe`, `fan_out`, etc.).
4.  **Execution & Validation (Layer 4):** `router.py` provides BFS pathfinding and DSL validation.

The `conductor/` package manages the higher-level "Operating System" functions: session state, WIP enforcement, and organ health audits.

## 🛠 Core Tooling

### Conductor CLI (`python3 -m conductor`)
The primary interface for system state and workflow orchestration.

-   **`patch`**: Command center briefing. Shows session status, system pulse, and work queue.
-   **`session start`**: Initialize a new work session with organ, repo, and scope.
-   **`session phase <target>`**: Transition through lifecycle: `FRAME` → `SHAPE` → `BUILD` → `PROVE` → `DONE`.
-   **`session status`**: Show active session details and phase history.
-   **`session close`**: Finalize work, update stats, and save the session log.
-   **`wip check/promote`**: Manage repo promotion states and WIP limits across organs.
-   **`doctor`**: Run integrity diagnostics on the system and workflows.

### Router CLI (`python3 router.py`)
Focused on tool-level logic and routing discovery.

-   **`route --from <a> --to <b>`**: Find direct or multi-hop routes between tool clusters.
-   **`capability <CAP>`**: Find all clusters supporting a specific capability (SEARCH, READ, etc.).
-   **`path <DOMAIN_A> <DOMAIN_B>`**: BFS shortest path between functional domains.
-   **`validate <workflow.yaml>`**: Validate a workflow DSL file against the ontology and schema.

### MCP Server (`python3 mcp_server.py`)
Exposes Conductor's tool intelligence and system state to AI agents via the Model Context Protocol.

## 🚀 Development Workflow

### Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

### Quality Gate
```bash
./tools/run_quality_gate.sh  # Tests, Mypy, Schemas, Process Assets, Doctor
```

### Key Files
- `ontology.yaml`: Source of truth for domains, clusters, and tools.
- `routing-matrix.yaml`: Source of truth for data-flow compatibility.
- `conductor/`: Core runtime logic.
- `process/`: Delivery SOPs, playbooks, and templates.
- `research/`: Three-stage pipeline (`inbox/` → `digested/` → `implemented/`).

## ⚖️ Governance & Organs
The system manages repositories across 8 organs: **I: Theoria**, **II: Poiesis**, **III: Ergon**, **IV: Taxis**, **V: Logos**, **VI: Koinonia**, **VII: Kerygma**, and **META**. Repositories are promoted through states: `LOCAL` → `CANDIDATE` → `PUBLIC_PROCESS` → `GRADUATED`.

## 📝 Coding Standards
- **Python**: 3.11+, 4-space indent, PEP 8, Ruff (line-length 99), explicit type hints.
- **Testing**: `pytest` with `tests/test_*.py` naming.
- **Commits**: Conventional Commits preferred (`feat(schema):`, `fix(runtime):`).

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
`orchestration-start-here`, `petasum-super-petasum`, `universal-node-network`, `.github`, `agentic-titan`, `agent--claude-smith`, `a-i--skills`, `system-governance-framework`, `reverse-engine-recursive-run`, `collective-persona-operations`

### Governance
- *Standard ORGANVM governance applies*

*Last synced: 2026-03-20T10:58:30Z*

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


**Prompting (Google)**: context 1M tokens (Gemini 1.5 Pro), format: markdown, thinking: thinking mode (thinkingConfig)


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


## Entity Identity (Ontologia)

**UID:** `ent_repo_01KKKX3RVP4WSRWJA1A4D59R73` | **Matched by:** primary_name

Resolve: `organvm ontologia resolve tool-interaction-design` | History: `organvm ontologia history ent_repo_01KKKX3RVP4WSRWJA1A4D59R73`


## Live System Variables (Ontologia)

| Variable | Value | Scope | Updated |
|----------|-------|-------|---------|
| `active_repos` | 1 | global | 2026-03-20 |
| `archived_repos` | 0 | global | 2026-03-20 |
| `ci_workflows` | 1 | global | 2026-03-20 |
| `code_files` | 0 | global | 2026-03-20 |
| `dependency_edges` | 0 | global | 2026-03-20 |
| `operational_organs` | 1 | global | 2026-03-20 |
| `published_essays` | 0 | global | 2026-03-20 |
| `repos_with_tests` | 0 | global | 2026-03-20 |
| `sprints_completed` | 0 | global | 2026-03-20 |
| `test_files` | 0 | global | 2026-03-20 |
| `total_organs` | 1 | global | 2026-03-20 |
| `total_repos` | 1 | global | 2026-03-20 |
| `total_words_formatted` | 0 | global | 2026-03-20 |
| `total_words_numeric` | 0 | global | 2026-03-20 |
| `total_words_short` | 0K+ | global | 2026-03-20 |

Metrics: 9 registered | Observations: 7184 recorded
Resolve: `organvm ontologia status` | Refresh: `organvm refresh`


## System Density (auto-generated)

AMMOI: 54% | Edges: 28 | Tensions: 33 | Clusters: 5 | Adv: 3 | Events(24h): 12929
Structure: 8 organs / 117 repos / 1654 components (depth 17) | Inference: 98% | Organs: META-ORGANVM:66%, ORGAN-I:55%, ORGAN-II:47%, ORGAN-III:56% +4 more
Last pulse: 2026-03-20T10:58:23 | Δ24h: -3.7% | Δ7d: n/a

<!-- ORGANVM:AUTO:END -->
