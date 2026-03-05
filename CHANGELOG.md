# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- DSL primitive maturity annotations (`stable`/`alpha`/`planned`) with runtime warnings.
- Log rotation for observability and handoff JSONL files (5000-line threshold).
- Stale workflow pointer auto-cleanup in executor.
- CI workflow (`.github/workflows/test.yml`) — Python 3.11/3.12/3.13 matrix.
- WIP limit precedence chain: policy bundle > governance-rules.json > constants.py.
- `conductor doctor --tools` — checks which ontology tools are actually available.
- Shared test fixtures via `tests/conftest.py` (eliminates fixture duplication).
- Corpus offline fallback — governance degrades gracefully when registry path missing.
- `conductor retro` — mines session/observability logs for retrospective insights.
- `conductor workflow resume --from <step>` — crash recovery for workflow execution.
- Cost/latency metadata on ontology clusters with cheapest-path routing.
- Adaptive health feedback — session outcomes feed back into cluster health scores.
- Standalone `conductor-ontology/` package for ontology + router.
- Expanded E2E test suite (15+ tests covering full session-workflow-briefing pipeline).

## [0.5.1] - 2026-03-05

### Added
- Versioned schema validation (registry, governance, workflow DSL).
- Doctor diagnostics with `--strict` mode, `--apply` autofix.
- Migration commands (`conductor migrate registry|governance`).
- Policy bundles (`default.yaml`, `relaxed.yaml`, `strict.yaml`) with simulation.
- Plugin-driven clusters loaded from external manifests.
- Structured observability with trend analysis and failure bucketing.
- Strict workflow warning codes (`[WF-E001]` through `[WF-E009]`).
- JSON output mode (`--format json`) on all commands.
- Oracle advisory engine with process-drift and scope-risk detection.
- Work queue with computed rationale and ownership tracking.
- Route simulation with fallback repair behavior.
- Handoff envelope format with JSON Schema contracts.
- Edge health reporting (success rate, p95 latency, failure buckets).
- Workflow compiler (JIT mission synthesis from routing paths).
- `conductor auto` autonomous worker daemon.
- `conductor wiring inject|mcp` workspace-wide integration.
- `conductor graph` Mermaid registry visualization.
- Galactic Fleet Dashboard export (static HTML).
- Gemini CLI extension export.
- Process kit extraction (playbooks, contracts, scorecards).

## [0.5.0] - 2026-03-04

### Added
- Four-layer architecture: ontology (taxonomy) → routing matrix → workflow DSL → conductor OS.
- Ontology with 12 domains, 64+ clusters, 578+ tools, 20 capabilities, 7 protocols.
- Routing matrix with 118+ directed routes and BFS pathfinding.
- Workflow DSL specification with 7 primitives (pipe, fan_out, fan_in, gate, loop, fallback, checkpoint).
- Router CLI (`router.py`) — standalone with route, capability, path, validate, alternatives, clusters, domains, graph commands.
- Conductor session lifecycle engine (FRAME → SHAPE → BUILD → PROVE → DONE).
- Governance runtime with registry sync, WIP enforcement, promotion state machine (LOCAL → CANDIDATE → PUBLIC_PROCESS → GRADUATED → ARCHIVED).
- Patchbay command center with graceful per-section degradation.
- Workflow executor prototype supporting pipe, gate, checkpoint, fan_out, loop, and error strategies.
- MCP server (`mcp_server.py`) exposing conductor capabilities as live tools.
- Session template scaffolding (spec.md, plan.md, status.md).
- Git integration (feature branch creation, session breadcrumb commits).
- Cumulative session statistics with streak tracking.
- Atomic file writes (POSIX-safe tmp-rename pattern).
- 271 tests with 100% pass rate.
- 12 JSON Schema contracts for all output types.
- `pyproject.toml` packaging with `conductor` console script entry point.
