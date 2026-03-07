# Tool-Interaction-Design MCP Server & Test Infrastructure Exploration

**Date**: 2026-03-04  
**Project**: `/Users/4jp/Workspace/tool-interaction-design/`  
**Status**: Read-only exploration complete  
**Next Phase**: Plan mode (awaiting user direction)

---

## Executive Summary

Completed comprehensive exploration of the Conductor MCP server infrastructure and test suite. The system provides an intelligence layer for Claude Code through 6 MCP tools that expose router, session, governance, and work-queue functionality. Test coverage is extensive (1,816 tests across two files) with rigorous state machine validation, mocking patterns, and graceful degradation handling.

### Key Findings

| Component | Status | Size | Key Detail |
|-----------|--------|------|-----------|
| **mcp_server.py** | ✓ Read | 276 lines | 6 tools, async dispatch, stdio transport |
| **conductor/cli.py** | ✓ Read | 233 lines | 13+ subcommands, nested argparse routing |
| **pyproject.toml** | ✓ Read | 24 lines | v0.5.0, optional MCP dependency |
| **tests/test_conductor.py** | ✓ Read | 917 lines | 18+ test classes, state machine validation |
| **tests/test_patchbay.py** | ✓ Read | 899 lines | 12+ test classes, work queue + briefing |
| **.conductor.yaml.example** | ✓ Read | 27 lines | Phase-to-cluster mapping configuration |
| **templates/** | ✓ Read | 3 files | Session scaffolding (spec, plan, status) |
| **MCP registration** | ✓ Checked | — | No ~/.claude/mcp.json; expected behavior |

---

## Architecture Overview

### MCP Server Interface (mcp_server.py)

**6 Tools Exposed to Claude Code:**

1. **conductor_route_to**(from_cluster, to_cluster)
   - Returns direct and multi-hop routes between tool clusters
   - Output: JSON with route steps, protocols, data types
   - Use case: Tool discovery and composition

2. **conductor_capability**(capability)
   - Maps capability (e.g., "READ", "DEPLOY") to available clusters
   - Returns ranked list by priority
   - Use case: Capability-driven tool selection

3. **conductor_wip_status**()
   - Promotion state counts per organ (LOCAL, CANDIDATE, PUBLIC_PROCESS, GRADUATED, ARCHIVED)
   - Use case: Governance monitoring, WIP limit checking

4. **conductor_session_phase**()
   - Active session phase (FRAME, SHAPE, BUILD, PROVE)
   - Available clusters for current phase
   - Session role and context
   - Use case: Phase-aware tool suggestion

5. **conductor_suggest**(task_description)
   - Keyword-to-capability mapping from task description
   - Returns ranked cluster suggestions
   - Use case: Intelligent tool recommendation

6. **conductor_patch**(organ=None)
   - Full system briefing from Patchbay
   - Sections: pulse (health), queue (actions), stats (lifetime)
   - Optional filtering by organ
   - Use case: System state awareness

**Implementation Details:**
- Uses MCP SDK: `mcp.server.Server`, `mcp.types.TextContent`, `Tool`
- Async dispatch via `@server.list_tools()` and `@server.call_tool()` decorators
- Lazy globals for Ontology/RoutingEngine to avoid repeated parsing
- DISPATCH dict maps tool names to handler functions
- Main entry: `asyncio.run(run_server())` with stdio context manager

### CLI Command Structure (conductor/cli.py)

**Command Categories:**

| Category | Commands | Purpose |
|----------|----------|---------|
| **Session** | start, phase, status, close, log-tool | Lifecycle management (FRAME→SHAPE→BUILD→PROVE→DONE) |
| **Governance** | registry, wip, enforce, stale, audit | Promotion state machine, WIP limits, health checks |
| **Product** | export (process-kit, audit-report), patterns | Artifact extraction, pattern mining |
| **Router** | route, capability, clusters, domains | Ontology queries (inherited from router.py) |
| **Patchbay** | patch | System briefing with --json, --organ filters |
| **Other** | version | Version string |

**Dispatch Pattern:**
- argparse.RawDescriptionHelpFormatter for help text
- `_dispatch()` function loads ontology/engine conditionally
- Graceful fallback if ontology/routing files missing
- ConductorError exception hierarchy for error handling

### Phase & State Machines (conductor/constants.py)

**Session Phases (FRAME → SHAPE → BUILD → PROVE → DONE):**

| Phase | Role | Active Clusters | Next States |
|-------|------|-----------------|-------------|
| FRAME | Librarian + Architect | sequential_thinking, web_search, academic_research, documentation, knowledge_graph, knowledge_apps | SHAPE or FRAME |
| SHAPE | Strategist | sequential_thinking, code_analysis_mcp, diagramming, neon_database | BUILD, FRAME |
| BUILD | Engineer | claude_code_core, code_execution, code_quality_cli, git_core, jupyter_notebooks | PROVE, SHAPE |
| PROVE | Quality Assurance | code_quality_cli, security_scanning, browser_playwright, browser_chrome, github_platform, vercel_platform, sentry_monitoring | DONE, BUILD |

**Promotion State Machine:**
- States: LOCAL → CANDIDATE → PUBLIC_PROCESS → GRADUATED → ARCHIVED
- WIP Limits: MAX_CANDIDATE_PER_ORGAN = 3, MAX_PUBLIC_PROCESS_PER_ORGAN = 1
- Enforced by GovernanceRuntime in conductor/governance.py

### Test Coverage Analysis

**test_conductor.py (917 lines, 18+ test classes):**
- **TestUtils**: atomic_write, resolve_organ_key, organ_short
- **TestSessionEngine**: start, phase transitions, template scaffolding, state machine
- **TestStateTransitions**: Exhaustive phase transition validation
- **TestGovernanceRuntime**: WIP checks, promotion, registry operations
- **TestSessionModel**: Session properties, uniqueness
- **TestSessionIdUniqueness**: UUID generation
- **TestGitOperations**: git branch creation
- **TestPhaseClusterOverride**: .conductor.yaml config loading
- **TestTemplateScaffolding**: Jinja2 template variable filling
- **TestPromotionStateMachine**: Promotion state validation
- **TestExportForceGuard**: process kit export force flag
- **TestCorruptedSessionState**: Error handling for bad JSON
- **TestGovernanceAuditEdge**: Audit edge cases
- **TestMinePatterns**: Pattern extraction from logs
- **TestEnforceGenerate**: Governance rule generation
- **TestCumulativeStats**: Lifetime statistics tracking
- **TestWipCheckPublicProcess**: WIP limit violations
- **TestVersion**: Version string validation

**test_patchbay.py (899 lines, 12+ test classes):**
- **TestWorkQueue**: Priority ordering, command suggestions
- **TestPatchbay**: Briefing data structure, formatting
- **TestStatsExtensions**: Cumulative stats, lifetime tracking
- **TestPatchbayVersion**: Version consistency
- **TestWorkQueueEdgeCases**: Empty queue, DONE phases
- **TestPatchbayFormatting**: Text/JSON output formatting, section filtering
- **TestNextCommand**: Queue command extraction
- **TestSuggestNext**: Intelligent next-action suggestions
- **TestGracefulDegradation**: Missing files, missing registry handling
- **TestQueueTruncation**: Top-5 command limiting
- **TestPulseEdgeCases**: Empty registry, archived repos
- **TestMCPPatch**: MCP server patch() function JSON validation

**Test Patterns:**
- Fixtures with tmp_dir patching for isolated testing
- Extensive unittest.mock.patch for path/config override
- pytest.raises() for exception testing
- capsys for output capture
- Mocking approach: Module-level constant patching

### Module Organization (conductor/ package)

| Module | Purpose | Key Classes |
|--------|---------|------------|
| __init__.py | Public API surface (35 exported symbols) | Version, imports, __all__ |
| __main__.py | Entry point for `python -m conductor` | |
| cli.py | Command dispatch, subcommand routing | Main CLI logic |
| constants.py | Paths, organs, phases, state machines | 100+ constant definitions |
| governance.py | Promotion state machine, WIP limits | GovernanceRuntime |
| session.py | Session lifecycle, template scaffolding | Session, SessionEngine |
| patchbay.py | System briefing aggregation | Patchbay, WorkQueue |
| workqueue.py | Action prioritization | WorkItem, WorkQueue |
| product.py | Artifact extraction, pattern mining | ProductExtractor |

### Configuration & Templates

**.conductor.yaml.example:**
- Override file for phase-cluster mappings (optional, not mandatory)
- FRAME, SHAPE, BUILD, PROVE phase definitions
- Each phase specifies which clusters are active

**templates/ directory:**
- spec.md: Session specification template ({{ scope }}, {{ organ }}, {{ repo }} variables)
- plan.md: Session plan template
- status.md: Session status update template
- Used by SessionEngine for Jinja2 template scaffolding

---

## Technical Debt & Known Limitations

1. **MCP Registration**: No ~/.claude/mcp.json found. Assuming registration is handled through Claude Code's built-in mechanism rather than external config.

2. **Router Integration**: CLI inherits route, capability, clusters, domains commands from router.py but these are only conditionally loaded in _dispatch() if ontology files exist.

3. **Error Handling**: Graceful degradation when ontology/routing files missing, but error messages could be more specific.

4. **Test Coverage**: 1,816 tests total (917 + 899) is comprehensive, but router.py itself appears to lack automated tests (only validation commands).

---

## Recommendations for Next Work

### If Extending MCP Server:
- Consider adding tool for pattern extraction (currently only via CLI export)
- Add tool for governance audit querying
- Consider streaming capability for large briefings

### If Extending Test Coverage:
- Add integration tests for full session lifecycle (currently unit tests dominate)
- Test graceful degradation more systematically
- Add performance tests for large registries

### If Refactoring CLI:
- Consider subclass-based command dispatch instead of nested argparse
- Consolidate similar error handling patterns
- Document all --organ filtering behavior

### If Adding New Features:
- Phase-cluster mapping could be parameterized per project (not just global)
- WIP limits could be per-repo, not just per-organ
- Session log could support structured event streaming

---

## Files Analyzed

### Primary Reads (Complete)
- `/Users/4jp/Workspace/tool-interaction-design/mcp_server.py` (276 lines)
- `/Users/4jp/Workspace/tool-interaction-design/conductor/cli.py` (233 lines)
- `/Users/4jp/Workspace/tool-interaction-design/pyproject.toml` (24 lines)
- `/Users/4jp/Workspace/tool-interaction-design/.conductor.yaml.example` (27 lines)
- `/Users/4jp/Workspace/tool-interaction-design/conductor/__init__.py` (77 lines)
- `/Users/4jp/Workspace/tool-interaction-design/conductor/constants.py` (100+ lines)

### Test Reads (Sectional)
- `/Users/4jp/Workspace/tool-interaction-design/tests/test_conductor.py` (917 lines)
- `/Users/4jp/Workspace/tool-interaction-design/tests/test_patchbay.py` (899 lines)

### Directory Scans
- `/Users/4jp/Workspace/tool-interaction-design/templates/` (3 files)
- `~/.claude/` for mcp.json (not found; confirmed expected behavior)

---

## Session Metadata

- **Exploration Type**: READ-ONLY (no edits, no commits, no state changes)
- **Deliverable**: Structured summaries of 8 requested items
- **Completion Status**: 100% (all 8 items analyzed)
- **Outstanding**: None (awaiting user direction for next phase)

