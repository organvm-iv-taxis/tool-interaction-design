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
