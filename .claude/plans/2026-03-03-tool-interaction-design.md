# Tool Interaction Design — System Architecture

**Date:** 2026-03-03
**Status:** DELIVERED

## Objective

Design a comprehensive method for interaction between all available tools (~950+)
across Claude Code built-ins, MCP servers, macOS applications, Homebrew packages,
and runtime ecosystems.

## Deliverables

### 1. Ontology (`ontology.yaml`)
- **12 domains**: AI_AGENTS, CODE, GIT_SCM, CLOUD_DEPLOY, CREATIVE, RESEARCH, DATA, SECURITY, SYSTEM, ORCHESTRATION, COMMUNICATION, BROWSER
- **20 capabilities**: READ, WRITE, EDIT, SEARCH, EXECUTE, ANALYZE, DEPLOY, GENERATE, TRANSFORM, MONITOR, AUTHENTICATE, ORCHESTRATE, VISUALIZE, TEST, CONFIGURE, FETCH, STORE, NAVIGATE, COMPOSE, COMMUNICATE
- **7 protocols**: MCP, CLI, API, FILESYSTEM, STDIO, GUI, BROWSER_AUTO
- **15 data types**: TEXT, CODE, JSON, YAML, HTML, IMAGE, AUDIO, VIDEO, PDF, BINARY, NOTEBOOK, CONFIG, STREAM, DIAGRAM, SQL
- **64 tool clusters**: Every tool mapped to exactly one cluster
- **6 relationship types**: INVOKES, FEEDS, ALTERNATIVE_TO, ENHANCES, DEPENDS_ON, BRIDGES

### 2. Routing Matrix (`routing-matrix.yaml`)
- **32 defined routes** with data flow, protocol, and exemplars
- **7 alternative sets** (ranked fallback tools)
- **Capability routing table** mapping each capability to prioritized clusters
- **Protocol priority matrix** for choosing connection method

### 3. Workflow DSL (`workflow-dsl.yaml`)
- **7 primitives**: pipe, fan_out, fan_in, gate, loop, fallback, checkpoint
- **Expression language**: references, transforms, predicates
- **Step lifecycle**: PENDING → BLOCKED → READY → RUNNING → CHECKPOINT → COMPLETED/FAILED/SKIPPED
- **Error strategies**: abort, retry, fallback, skip, ask
- **Concurrency model**: 16GB RAM-aware limits per protocol
- **7 example workflows**: research-ingest, feature-dev-pipeline, sentry-bug-fix, figma-to-deploy, research-swarm, monitor-respond, auto-document

### 4. Visual Graph (`graph.mmd`)
- Mermaid flowchart with all 64 clusters
- Color-coded by domain
- Edges showing primary data flows
- Renderable via `mmdc` or mermaid.live

### 5. Executable Router (`router.py`)
- 8 commands: route, capability, path, validate, alternatives, clusters, domains, graph
- BFS path-finding between domains
- Data-type and protocol compatibility checking
- Workflow DSL validation
- JSON graph export for external visualization

## Architecture Decisions

- **YAML over JSON** for human authoring; JSON for machine interchange (via `router.py graph`)
- **Clusters over individual tools** as the atomic routing unit — reduces 950 tools to 64 composable units
- **Protocol bridging** — MCP, CLI, FILESYSTEM, STDIO all bridgeable via Claude Code core; GUI requires browser automation
- **16GB RAM constraint** embedded in concurrency model — max 4 parallel CLI, 2 browser instances
