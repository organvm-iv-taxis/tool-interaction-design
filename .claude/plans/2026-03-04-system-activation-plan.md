# Plan: Four-Phase System Activation

## Context

The tool-interaction-design project has a solid 578-tool taxonomy (64 clusters, 12 domains), a working conductor engine (sessions, governance, patchbay with 119 tests), and a complete MCP server definition — but three critical gaps prevent it from being a live, self-aware system:

1. **router.py has 0 tests** — the core query engine for everything is unverified
2. **32 routes for 64 clusters** — the graph is so sparse that BFS pathfinding mostly hits dead ends
3. **MCP server is dead code** — 6 tools defined but never registered in Claude Code
4. **Research digests unimplemented** — 3 new clusters and 4 new routes from `research/digested/` are structured and ready to apply

## Phase 1: Router Test Suite (`tests/test_router.py`)

**Why:** Can't trust what you can't verify. Router is the query engine for all routing, pathfinding, and MCP server responses.

**File:** `tests/test_router.py` (~300 lines)

**Test classes following existing patterns from `test_conductor.py`:**

- `TestClusterDataclass` — instantiation, field access
- `TestRouteDataclass` — instantiation, field defaults
- `TestOntologyLoader` — loads real `ontology.yaml`, verifies 64 clusters, 12 domains, indices built
- `TestOntologyByCapability` — `SEARCH` returns expected clusters, unknown cap returns empty
- `TestOntologyByDomain` — `RESEARCH` returns 10 clusters, unknown returns empty
- `TestOntologyByProtocol` — `MCP` returns many, `GUI` returns few
- `TestOntologyCompatibleTargets` — `web_search` → expected targets, protocol bridging works, unknown cluster returns `[]`
- `TestRoutingEngineLoader` — loads real `routing-matrix.yaml`, verifies 32+ routes, adjacency graph built
- `TestRoutingEngineFindRoutes` — `web_search → knowledge_graph` returns direct route, nonexistent pair returns `[]`
- `TestRoutingEngineFindPath` — `RESEARCH → CODE` finds path, same domain returns trivial path, disconnected returns `[]`
- `TestRoutingEngineAlternatives` — `web_search` has alternatives, unknown has `None`
- `TestRoutingEngineCapabilityTools` — `SEARCH` returns ordered list
- `TestWorkflowValidator` — validates `workflow-dsl.yaml`, catches bad cluster refs, catches duplicate step names
- `TestCLICommands` — smoke tests for all 8 commands (capture stdout, verify no crash)

**Pattern:** Use real YAML files (following `test_conductor.py` which loads real `ontology.yaml`). Fixtures for `ontology` and `engine` objects.

## Phase 2: Route Densification (`routing-matrix.yaml`)

**Why:** 32 routes covers ~1.6% of possible edges. BFS pathfinding fails for most domain pairs. The graph needs ~80+ routes for meaningful connectivity.

**Strategy:** Systematically add routes for every major data flow pattern. Group by pipeline archetype:

### New routes to add (~50 routes):

**Intra-domain completion** (clusters within same domain that should connect):
- `code_analysis_mcp → code_quality_cli` (analysis → fixes)
- `code_quality_cli → git_core` (lint → commit)
- `git_core → git_enhanced` (core → power tools)
- `git_enhanced → github_platform` (power tools → platform)
- `filesystem_mcp → filesystem_cli` (MCP → CLI bridge)
- `browser_chrome → browser_playwright` (chrome → headless fallback)
- `web_search → web_content` (search → extract)
- `web_content → documentation` (extract → docs)
- `wikipedia → web_content` (wiki → content pipeline)
- `npm_registry → documentation` (npm → docs)
- `academic_research → web_content` (papers → extraction)
- `knowledge_graph → knowledge_apps` (already exists: kg_to_notion)
- `cloudflare_platform → cloudflare_data` (platform → data services)
- `vercel_platform → ci_cd` (deploy → CI)
- `netlify_platform → ci_cd` (deploy → CI)
- `container_orchestration → ci_cd` (containers → CI)

**Cross-domain pipelines:**
- `sequential_thinking → claude_code_core` (reasoning → code)
- `task_management → github_platform` (tasks → issues)
- `task_management → sequential_thinking` (tasks → reasoning)
- `knowledge_graph → sequential_thinking` (knowledge → reasoning)
- `documentation → code_analysis_mcp` (docs → analysis)
- `claude_code_core → code_analysis_mcp` (code → analysis)
- `claude_code_core → code_quality_cli` (code → lint)
- `claude_code_core → filesystem_cli` (code → fs operations)
- `code_execution → claude_code_core` (sandbox results → code fixes)
- `security_scanning → github_platform` (scans → issues/PRs)
- `github_platform → sentry_monitoring` (deploys → monitoring)
- `github_platform → task_management` (issues → tasks)
- `neon_database → code_analysis_mcp` (schema → analysis)
- `jupyter_notebooks → neon_database` (notebooks → DB)
- `jupyter_notebooks → diagramming` (notebooks → visualization)
- `claude_code_core → publishing` (code → docs)
- `diagramming → github_platform` (diagrams → PRs)
- `diagramming → publishing` (diagrams → docs)
- `visual_design → publishing` (design → docs)
- `web_search → sequential_thinking` (research → reasoning)
- `academic_research → sequential_thinking` (research → reasoning)
- `mcp_meta → claude_code_core` (meta-tools → code tools)
- `usage_meta → sequential_thinking` (usage stats → reasoning)
- `shell_environment → process_management` (shell → processes)
- `process_management → observability` (processes → monitoring)
- `system_config → filesystem_cli` (config → filesystem)
- `sentry_monitoring → sequential_thinking` (errors → reasoning)
- `bug_reporting → task_management` (bugs → tasks)
- `time_location → sequential_thinking` (time → reasoning context)
- `auth_identity → github_platform` (auth → platform)
- `learning_standards → knowledge_graph` (standards → KG)
- `media_research → knowledge_apps` (media → knowledge)
- `claude_code_core → browser_chrome` (already exists but add reverse)
- `browser_chrome → claude_code_core` (browser results → code)
- `browser_playwright → claude_code_core` (test results → code)

**Research-recommended routes (from tool-surface-integration.yaml):**
- `governance_engine → ci_cd`
- `prompt_engineering → claude_code_core`
- `knowledge_graph → governance_engine`
- `sentry_monitoring → governance_engine`

Each route gets: `id`, `from`, `to`, `data_flow`, `protocol`, `automatable`, `description`, `exemplars`.

## Phase 3: Research Implementation

### 3a. New Clusters in `ontology.yaml`

Add 3 clusters from `research/digested/2026-03-03-tool-surface-integration.yaml`:

1. **`prompt_engineering`** (AI_AGENTS domain) — CLAUDE.md files, .cursorrules, agents.yaml, spec/plan/status templates
2. **`governance_engine`** (ORCHESTRATION domain) — registry-v2.json, governance-rules.json, seed.yaml, audit scripts
3. **`knowledge_management`** (RESEARCH domain) — Obsidian, PARA structure, pattern catalog

### 3b. New Workflows in `workflow-dsl.yaml`

Add 3 canonical workflows from research:
1. **`frame-shape-build-prove`** — the lifecycle loop
2. **`research-to-spec`** — research pipeline → spec.md
3. **`session-ritual`** — D4's 6-step session protocol

### 3c. Add `CONFIGURE` and `ORGANIZE` to capabilities in `ontology.yaml`

The new clusters use `CONFIGURE` and `ORGANIZE` which aren't in the taxonomy capabilities list.

## Phase 4: MCP Server Registration

**File:** Project-scoped `/.claude/settings.json` (preferred) or user guidance

**Registration config** for the project's `.claude/settings.json`:
```json
{
  "mcpServers": {
    "conductor": {
      "command": "/Users/4jp/Workspace/tool-interaction-design/.venv/bin/python",
      "args": ["/Users/4jp/Workspace/tool-interaction-design/mcp_server.py"],
      "cwd": "/Users/4jp/Workspace/tool-interaction-design"
    }
  }
}
```

Also need to verify the MCP SDK is installed in the venv. If not, add `mcp` to the venv.

## Files Modified

| File | Action | Phase |
|------|--------|-------|
| `tests/test_router.py` | **CREATE** | 1 |
| `routing-matrix.yaml` | EDIT (add ~50 routes) | 2 |
| `ontology.yaml` | EDIT (add 3 clusters + 2 capabilities) | 3 |
| `workflow-dsl.yaml` | EDIT (add 3 workflows) | 3 |
| `.claude/settings.json` | CREATE/EDIT (MCP registration) | 4 |

## Verification

```bash
# Phase 1: Run router tests
source .venv/bin/activate && python -m pytest tests/test_router.py -v

# Phase 2: Validate routes parse and pathfinding improves
python3 router.py path RESEARCH CODE
python3 router.py path SECURITY CLOUD_DEPLOY
python3 router.py route --from sequential_thinking --to claude_code_core

# Phase 3: Validate ontology + workflow DSL
python3 router.py clusters | grep -c "^  "  # Should be 67 (64+3)
python3 router.py validate workflow-dsl.yaml

# Phase 4: Verify MCP server starts
source .venv/bin/activate && python -c "from mcp.server import Server; print('MCP SDK OK')"
# After Claude Code restart, conductor_* tools should appear in ToolSearch

# Full regression
source .venv/bin/activate && python -m pytest tests/ -v
```
