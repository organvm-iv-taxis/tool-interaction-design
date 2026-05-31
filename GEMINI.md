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
- **Produces** → `cognitive-service-dispatch`
- **Produces** → `fleet-agent-registry`
- **Consumes** ← `orchestration-artifact`

### Siblings in Orchestration
`orchestration-start-here`, `petasum-super-petasum`, `universal-node-network`, `.github`, `agentic-titan`, `agent--claude-smith`, `a-i--skills`, `system-governance-framework`, `reverse-engine-recursive-run`, `collective-persona-operations`, `contrib--adenhq-hive`, `contrib--ipqwery-ipapi-py`, `contrib--primeinc-github-stars`, `contrib--temporal-sdk-python`, `contrib--dbt-mcp` ... and 6 more

### Governance
- *Standard ORGANVM governance applies*

*Last synced: 2026-05-23T00:26:31Z*

## Active Handoff Protocol

If `.conductor/active-handoff.md` exists, **READ IT FIRST** before doing any work.
It contains constraints, locked files, conventions, and completed work from the
originating agent. You MUST honor all constraints listed there.

If the handoff says "CROSS-VERIFICATION REQUIRED", your self-assessment will
NOT be trusted. A different agent will verify your output against these constraints.

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


## System Library

Plans: 269 indexed | Chains: 5 available | SOPs: 8 active
Discover: `organvm plans search <query>` | `organvm chains list` | `organvm sop lifecycle`
Library: `/Users/4jp/Code/organvm/praxis-perpetua/library`


## Active Directives

| Scope | Phase | Name | Description |
|-------|-------|------|-------------|
| system | any | atomic-clock | The Atomic Clock |
| system | any | execution-sequence | Execution Sequence |
| system | any | multi-agent-dispatch | Multi-Agent Dispatch |
| system | any | session-handoff-avalanche | Session Handoff Avalanche |
| system | any | system-loops | System Loops |
| system | any | prompting-standards | Prompting Standards |
| system | any | background-task-resilience | background-task-resilience |
| system | any | context-window-conservation | context-window-conservation |
| system | any | session-self-critique | session-self-critique |
| system | any | the-descent-protocol | the-descent-protocol |
| system | any | the-membrane-protocol | the-membrane-protocol |
| system | any | theory-to-concrete-gate | theory-to-concrete-gate |
| system | any | triangulation-protocol | triangulation-protocol |

Linked skills: SOP-TRIADIC-REVIEW-PROTOCOL, cicd-resilience-and-recovery, continuous-learning-agent, evaluation-to-growth, genesis-dna, multi-agent-workforce-planner, promotion-and-state-transitions, quality-gate-baseline-calibration, repo-onboarding-and-habitat-creation, session-self-critique, structural-integrity-audit, the-membrane-protocol, triple-reference


**Prompting (Google)**: context 1M tokens (Gemini 1.5 Pro), format: markdown, thinking: thinking mode (thinkingConfig)


## Atomization Pipeline

Run `organvm atoms pipeline --write && organvm atoms fanout --write` to generate task queue.


## System Density (auto-generated)

AMMOI: 25% | Edges: 0 | Tensions: 0 | Clusters: 0 | Adv: 27 | Events(24h): 37975
Structure: 8 organs / 148 repos / 1654 components (depth 17) | Inference: 0% | Organs: META-ORGANVM:63%, ORGAN-I:53%, ORGAN-II:48%, ORGAN-III:54% +5 more
Last pulse: 2026-05-23T00:26:28 | Δ24h: n/a | Δ7d: n/a


## Dialect Identity (Trivium)

**Dialect:** GOVERNANCE_LOGIC | **Classical Parallel:** Rhetoric | **Translation Role:** The Meta-Logic — governance rules ARE propositions

Strongest translations: I (formal), V (structural), META (structural)

Scan: `organvm trivium scan IV <OTHER>` | Matrix: `organvm trivium matrix` | Synthesize: `organvm trivium synthesize`


## Logos Documentation Layer

**Status:** ACTIVE | **Symmetry:** 0.5 (DREAM)

Nature demands a documentation counterpart. This formation maintains its narrative record in `docs/logos/`.

### The Tetradic Counterpart
- **[Telos (Idealized Form)](../docs/logos/telos.md)** — The dream and theoretical grounding.
- **[Pragma (Concrete State)](../docs/logos/pragma.md)** — The honest account of what exists.
- **[Praxis (Remediation Plan)](../docs/logos/praxis.md)** — The attack vectors for evolution.
- **[Receptio (Reception)](../docs/logos/receptio.md)** — The account of the constructed polis.

### Alchemical I/O
- **[Source & Transmutation](../docs/logos/alchemical-io.md)** — Narrative of inputs, process, and returns.

- **[Public Essay](https://organvm-v-logos.github.io/public-process/)** — System-wide narrative entry.

*Compliance: Record exists without implementation.*

<!-- ORGANVM:AUTO:END -->
