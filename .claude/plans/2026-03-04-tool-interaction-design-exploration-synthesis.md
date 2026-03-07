# Tool Interaction Design — Complete YAML Exploration & Research Synthesis
**Date**: 2026-03-04  
**Status**: Complete exploration, ready for planning  
**Session**: Continuation of thorough YAML file analysis + research digest integration  

---

## Executive Summary

The tool-interaction-design system is a **queryable taxonomy and routing engine** for 578 tools across 12 domains, 64 clusters, organized as a four-layer stack:

```
Layer 1: ontology.yaml       (Taxonomy: tools → clusters → domains)
    ↓ referenced by
Layer 2: routing-matrix.yaml (Data flows: cluster → cluster routes + fallbacks)
    ↓ composed into
Layer 3: workflow-dsl.yaml   (7 primitives for multi-tool pipelines)
    ↓ validated by
Layer 4: router.py           (BFS pathfinding, validation, CLI)
```

**Critical findings from research digests**: Five documents (D1-D5) achieved 10 unanimous consensus points and identified 7 contentions. The system is **ready for canonicalization** — the AI-conductor approach is a strength (not a deficiency), the FRAME/SHAPE/BUILD/PROVE lifecycle is the right abstraction, and WIP limits are the critical enforcement mechanism.

---

## PART 1: ONTOLOGY.YAML ARCHITECTURE

### Scope & Scale
- **578 tools** enumerated across **64 clusters** in **12 domains**
- Each cluster is stable (tools change, clusters persist)
- Clusters are the routing unit; capability routing uses clusters as targets
- Note: Tool entries use **inconsistent typing** (bare strings vs. `- cli: name` vs. `- mcp: name`) — not yet programmatically resolvable

### 12 Domains (taxonomy.domains in ontology.yaml)
1. **AI_AGENTS** — Claude models, reasoning, orchestration
2. **CODE** — Editors, IDEs, static analysis, refactoring, formatting
3. **GIT_SCM** — Git core, GitHub, GitLab, Gitea
4. **CLOUD_DEPLOY** — Vercel, Cloudflare, GCP, AWS, Netlify, Docker
5. **CREATIVE** — Figma, Mermaid, audio/video editing, generative art
6. **RESEARCH** — Web search, academic databases, Wikipedia, Perplexity, Tavily
7. **DATA** — Neon, PostgreSQL, DuckDB, Jupyter, DataFrames, visualization
8. **SECURITY** — SAST, DAST, dependency scanning, secret detection, STRIDE
9. **SYSTEM** — Shells, package managers, system monitoring, logs
10. **ORCHESTRATION** — MCP, Zapier, Make, workflow runners, task queues
11. **PUBLISHING** — Notion, Obsidian, GitHub Pages, document generation
12. **TEAM_COLLAB** — Slack, email, GitHub Discussions, project management

### Cluster Entry Schema (canonical structure)
```yaml
- id: <cluster_id>
  domain: <DOMAIN_NAME>
  label: "<Human-readable label>"
  tools:
    - "<tool_name>"        # OR
    - mcp: "<tool_name>"   # OR
    - cli: "<tool_name>"   # (inconsistent typing — TBD)
  capabilities:
    - READ
    - WRITE
    - SEARCH
    # ... (any of the 14 canonical capabilities)
  protocols:
    - MCP              # Model Context Protocol
    - CLI              # Command-line interface
    - FILESYSTEM       # Direct file I/O
    - STDIO            # Standard streams
    - GUI              # Manual interaction
    - BROWSER_AUTO     # Browser automation
    - API              # REST/HTTP
  input_types:
    - TEXT
    - JSON
    - CODE
    # ... (any of the 8 canonical data types)
  output_types:
    - TEXT
    - JSON
    - CODE
    # ... (any of the 8 canonical data types)
```

### Canonical Capabilities (taxonomy.capabilities)
- **READ** — Retrieve, fetch, query, list
- **WRITE** — Create, update, modify, delete
- **SEARCH** — Full-text search, semantic search
- **EXECUTE** — Run code, scripts, containers, functions
- **ANALYZE** — Parse, inspect, lint, evaluate
- **DEPLOY** — Release, publish, ship, promote
- **GENERATE** — Create content, synthesis, code generation
- **TRANSFORM** — Convert, transpile, reformat
- **MONITOR** — Observe, track, log, alert
- **TEST** — Validate, verify, QA, regression testing
- **VISUALIZE** — Render, display, chart, diagram
- **STORE** — Persist, cache, archive
- **COMMUNICATE** — Send messages, notifications, export
- **ORCHESTRATE** — Coordinate, schedule, fan-out/fan-in, workflow

### Canonical Protocols (taxonomy.protocols)
- **MCP** — Model Context Protocol (structured, server-based, composable)
- **CLI** — Command-line interface (scriptable, STDIO-based)
- **FILESYSTEM** — Direct file I/O (read/write local files)
- **STDIO** — Standard streams (pipes, shell redirection)
- **GUI** — Manual interactive use (not automatable)
- **BROWSER_AUTO** — Browser automation (Playwright, Puppeteer, etc.)
- **API** — REST/HTTP (cloud services, webhooks)

### Canonical Data Types (taxonomy.data_types)
- **TEXT** — Plain text, markdown, unstructured
- **JSON** — Structured key-value data
- **CODE** — Source code (any language), configurations
- **HTML** — Web content, markup
- **DIAGRAM** — Mermaid, SVG, structured visualization
- **IMAGE** — PNG, JPEG, WebP, binary image data
- **STREAM** — Continuous data flow (logs, events)
- **CONFIG** — YAML, TOML, environment variables, INI
- **SQL** — Database queries, DDL, stored procedures

### Relationship Types (defined but unpopulated)
The ontology defines these relationship types at the top level but they have **no instances**:
- `depends_on` — Cluster A requires Cluster B
- `replaces` — Cluster A supersedes Cluster B
- `alternative_to` — Cluster A and B are interchangeable
- `enhances` — Cluster A adds capability to Cluster B
- `integrates_with` — Cluster A connects bidirectionally with Cluster B

**Status**: Defined in schema but not instantiated. These should be populated when adding routes to routing-matrix.yaml.

### Known Limitations (from E2G report)
- Tool entries use inconsistent typing (not yet programmatically resolvable)
- Relationship types defined but never instantiated
- Capabilities listed without primary/secondary distinction (all equally weighted)
- No automated tests for ontology validation

---

## PART 2: ROUTING-MATRIX.YAML ROUTES & CONFIGURATION

### Metadata
- **Version**: 1.0
- **Created**: 2026-03-03
- **Total Routes**: 32+ concrete directed edges between clusters
- **Routing Unit**: Cluster-to-cluster (not tool-to-tool)

### Routing Priority Matrix (automatable protocol ranking)
The system evaluates routes in this priority order:
1. **MCP → MCP** (highest automatable)
2. **CLI → CLI**
3. **MCP → CLI**
4. **CLI → MCP**
5. **FILESYSTEM**
6. **BROWSER_AUTO**
7. **GUI** (requires human intervention; lowest automatable)

### Complete Route List (32+ routes, organized by domain pairs)

#### Research → Knowledge (Ingestion, 6 routes)
- **search_to_kg**: web_search → knowledge_graph (protocol: MCP, data: JSON→JSON, automatable: yes)
- **wikipedia_to_kg**: wikipedia_research → knowledge_graph (CLI→MCP, TEXT→JSON, yes)
- **academic_to_kg**: academic_research → knowledge_graph (API→MCP, JSON→JSON, yes)
- **search_to_notion**: web_search → notion_apps (MCP→API, JSON→JSON, yes)
- **web_content_to_kg**: web_content_extraction → knowledge_graph (CLI→MCP, HTML→JSON, yes)
- **media_to_kg**: media_extraction → knowledge_graph (CLI→MCP, IMAGE/STREAM→JSON, yes)

#### Code → Git → GitHub (Development, 4 routes)
- **editor_to_git**: code_editing → git_core (FILESYSTEM→CLI, CODE→CODE, yes)
- **git_to_github**: git_core → github_platform (CLI→API, CODE→JSON, yes)
- **analysis_to_git**: code_analysis_mcp → git_core (MCP→CLI, JSON→CODE, yes)
- **security_to_github**: security_scanning → github_platform (CLI→API, JSON→JSON, yes)

#### GitHub → Cloud (Deployment, 4 routes)
- **github_to_vercel**: github_platform → vercel_platform (API→API, JSON→JSON, yes)
- **github_to_cloudflare**: github_platform → cloudflare_platform (API→API, JSON→JSON, yes)
- **github_to_netlify**: github_platform → netlify_platform (API→API, JSON→JSON, yes)
- **github_to_gcp**: github_platform → gcp_platform (API→API, JSON→JSON, yes)

#### Design → Code (Code Generation, 2 routes)
- **figma_to_code**: figma_design → code_generation (API→MCP, DIAGRAM→CODE, yes)
- **diagram_to_code**: diagramming → code_generation (FILESYSTEM→MCP, DIAGRAM→CODE, yes)

#### Code → Browser (Testing, 3 routes)
- **code_to_browser_test**: code_execution → browser_playwright (CLI→BROWSER_AUTO, CODE→STREAM, yes)
- **code_to_browser_e2e**: code_testing → browser_chrome (CLI→BROWSER_AUTO, CODE→STREAM, yes)
- **code_to_browser_record**: code_recording → browser_chrome (FILESYSTEM→BROWSER_AUTO, CODE→STREAM, yes)

#### Error Monitoring → Code (Bug Resolution, 3 routes)
- **sentry_to_code**: sentry_monitoring → code_analysis_mcp (API→MCP, JSON→JSON, yes)
- **sentry_to_github**: sentry_monitoring → github_platform (API→API, JSON→JSON, yes)
- **jam_to_code**: jam_reporting → code_analysis_mcp (API→MCP, JSON→JSON, yes)

#### Data ↔ Code (Bidirectional, 4 routes)
- **neon_to_code**: neon_database → code_execution (API→MCP, SQL/JSON→CODE, yes)
- **code_to_neon**: code_execution → neon_database (MCP→API, CODE→SQL, yes)
- **jupyter_to_code**: jupyter_notebooks → code_execution (API→MCP, CODE→STREAM, yes)
- **pandas_to_kg**: data_analysis → knowledge_graph (CLI→MCP, JSON→JSON, yes)

#### Cross-Domain Bridges (4 routes)
- **research_to_code**: web_search → code_generation (MCP→MCP, JSON→CODE, yes)
- **kg_to_notion**: knowledge_graph → notion_apps (MCP→API, JSON→JSON, yes)
- **notion_to_code**: notion_apps → code_generation (API→MCP, JSON→CODE, yes)
- **config_to_shell**: config_management → system_shell (FILESYSTEM→CLI, CONFIG→STDIO, yes)

#### Orchestration & Monitoring (3 routes)
- **container_to_monitor**: container_orchestration → monitoring_observability (CLI→API, STREAM→JSON, yes)
- **ai_to_creative**: ai_agents → creative_tools (MCP→API, TEXT→JSON, yes)
- **skill_dispatch**: orchestration_engine → <any_cluster> (MCP→*, *, yes)

#### Miscellaneous (2+ routes)
- **github_to_knowledge**: github_platform → knowledge_graph (API→MCP, CODE→JSON, yes)
- Additional routes for emerging patterns (to be documented in next review)

### Alternatives Section (Ranked Fallback Clusters)
The system specifies ranked fallbacks for each capability. Example for `web_search`:
```yaml
web_search:
  primary: perplexity_research
  fallbacks:
    - tavily_search
    - WebSearch
    - search  # built-in Claude capability
```

**Purpose**: When primary cluster is unavailable or rate-limited, workflow engine automatically tries ranked alternatives.

### Capability Routing Table (13 capabilities → prioritized cluster lists)

| Capability | Cluster Priority (left-to-right) |
|------------|-----------------------------------|
| **READ** | claude_code_core > filesystem_mcp > filesystem_cli > github_platform > neon_database > knowledge_apps |
| **WRITE** | claude_code_core > git_core > github_platform > neon_database > filesystem_cli > notion_apps |
| **SEARCH** | web_search > academic_research > knowledge_graph > documentation > wikipedia > github_platform |
| **EXECUTE** | code_execution > container_orchestration > system_shell > jupyter_notebooks > browser_playwright |
| **ANALYZE** | code_analysis_mcp > security_scanning > code_quality_cli > jupyter_notebooks > sentry_monitoring |
| **DEPLOY** | vercel_platform > cloudflare_platform > gcp_platform > container_orchestration > github_platform |
| **GENERATE** | code_generation > ai_agents > creative_tools > diagramming > documentation |
| **TRANSFORM** | code_execution > data_analysis > diagramming > figma_design > file_conversion |
| **MONITOR** | sentry_monitoring > monitoring_observability > github_platform > neon_database > log_aggregation |
| **TEST** | code_testing > browser_playwright > security_scanning > code_quality_cli > sentry_monitoring |
| **VISUALIZE** | figma_design > diagramming > jupyter_notebooks > creative_tools > knowledge_apps |
| **STORE** | neon_database > knowledge_graph > notion_apps > github_platform > file_storage |
| **ORCHESTRATE** | orchestration_engine > workflow_runners > github_platform > task_management > mcp_core |

**Usage**: Workflows reference capabilities (not clusters directly); router selects best cluster from this table based on context.

### Known Issues & Comments in Routing Matrix
1. **Sparse coverage**: 32 routes for 64 clusters = ~<1% of possible edges. Many cluster pairs have no documented route yet.
2. **Missing routes** (should be added):
   - governance_engine → ci_cd (for automated rule enforcement)
   - prompt_engineering → code_generation (for .cursorrules, agent configs)
   - knowledge_graph → governance_engine (for audit trails)
   - sentry_monitoring → governance_engine (for incident escalation)
   - security_scanning → github_platform needs explicit automatable=true flag

3. **Protocol gaps**: Some routes need protocol validation (e.g., figma_to_code currently assumes API but should check actual Figma MCP availability).

---

## PART 3: WORKFLOW-DSL.YAML SPECIFICATION

### Metadata
- **Version**: 1.0
- **Created**: 2026-03-03
- **Primitives**: 7 composition operators (+ 1 emit sink operator)
- **Example Workflows**: 7 complete, validated workflows included

### The 7 Primitives (with symbols and semantics)

#### 1. **PIPE** (|>)
**Symbol**: `|>`  
**Semantics**: Sequential composition; output of step N becomes input to step N+1  
**Use when**: Linear, dependency-ordered tasks  
**Constraints**: 
- N steps execute sequentially
- Output data type of step N must match input type of step N+1
- Failure in step N → entire pipe fails (unless wrapped in fallback)

**Example**:
```yaml
steps:
  - name: search
    cluster: web_search
    input: "${user_query}"
  - name: extract
    cluster: web_content_extraction
    input: "${search.output}"
  - name: summarize
    cluster: ai_agents
    input: "${extract.output}"
```

#### 2. **FAN_OUT** (=>)
**Symbol**: `=>`  
**Semantics**: Parallel branching; same input → multiple independent branches (concurrent execution)  
**Use when**: Multiple independent processing paths  
**Constraints**:
- All branches start with identical input
- Branches execute in parallel (up to concurrency limit per protocol)
- No dependency between branches

**Example**:
```yaml
fan_out:
  search_input: "${research_query}"
  branches:
    - name: web_results
      cluster: web_search
    - name: academic_results
      cluster: academic_research
    - name: code_results
      cluster: github_search
```

#### 3. **FAN_IN** (<=)
**Symbol**: `<=`  
**Semantics**: Merge strategy for collecting parallel results  
**Merge strategies**:
- `merge_all` — Combine all outputs (default)
- `first_success` — Return first successful output; skip rest
- `vote` — Aggregate results by consensus
- `select` — Apply predicate to select subset

**Use when**: Aggregating parallel branch results

**Example**:
```yaml
fan_in:
  sources:
    - web_results
    - academic_results
    - code_results
  strategy: merge_all
  output: "${web_results.output} + ${academic_results.output} + ${code_results.output}"
```

#### 4. **GATE** (?>)
**Symbol**: `?>`  
**Semantics**: Conditional routing (if-then-else for workflows)  
**Condition types**:
- `success` — Step succeeded
- `failure` — Step failed
- `output_matches(pattern)` — Output matches regex
- `approval` — Awaiting human checkpoint
- `timeout(seconds)` — Execution exceeded duration

**Use when**: Conditional branching based on step outcomes

**Example**:
```yaml
gate:
  condition: "output_matches(${sentry_severity}, 'critical|high')"
  then:
    - name: escalate
      cluster: incident_response
  else:
    - name: log_only
      cluster: monitoring_observability
```

#### 5. **LOOP** (@>)
**Symbol**: `@>`  
**Semantics**: Iteration with termination conditions  
**Loop modes**:
- `for_each(array)` — Iterate over array elements
- `until(condition)` — Repeat until condition true
- `retry(max_retries, backoff)` — Retry with exponential backoff

**Use when**: Processing collections or retrying failed steps

**Example**:
```yaml
loop:
  mode: for_each
  array: "${search_results}"
  step:
    name: process_result
    cluster: web_content_extraction
    input: "${item}"
```

#### 6. **FALLBACK** (!>)
**Symbol**: `!>`  
**Semantics**: Try alternatives on failure  
**Error strategies**:
- `abort` — Stop workflow
- `retry(max, backoff)` — Retry original
- `fallback(alternatives)` — Try alternatives
- `skip` — Continue to next step
- `ask` — Await human decision

**Use when**: Graceful degradation on failure

**Example**:
```yaml
fallback:
  primary:
    cluster: perplexity_research
  alternatives:
    - cluster: tavily_search
    - cluster: WebSearch
  on_error: fallback
  max_attempts: 3
```

#### 7. **CHECKPOINT** (||)
**Symbol**: `||`  
**Semantics**: Human-in-the-loop pause for review/modification  
**Actions**:
- `approve` — Accept current state
- `modify` — Edit inputs/parameters before continuing
- `abort` — Cancel workflow
- `redirect` — Send to different cluster

**Use when**: Critical decisions, approval gates, review points

**Example**:
```yaml
checkpoint:
  name: approve_deploy
  message: "Ready to deploy to production?"
  actions:
    - approve → deploy to vercel
    - modify → adjust config, retry
    - abort → cancel release
```

#### 8. **EMIT** (>>)
**Symbol**: `>>`  
**Semantics**: Output to sinks (write results, notifications, etc.)  
**Sink types**:
- `file` — Write to filesystem
- `github` — Create issue/PR/comment
- `notion` — Write to Notion database
- `knowledge` — Index in knowledge graph
- `stdout` — Print to console

**Use when**: Persisting results after workflow completes

**Example**:
```yaml
emit:
  - sink: github
    action: create_issue
    title: "${bug_title}"
    body: "${analysis_output}"
  - sink: knowledge
    action: index
    document: "${sentry_report}"
```

### Step Schema (required & optional fields)
```yaml
- name: <step_id>
  cluster: <cluster_name>         # REQUIRED
  tool: <specific_tool>           # optional, if cluster has >1 tool
  input: <input_spec>             # optional, default: previous step output
  output: <output_spec>           # optional, inferred from cluster
  depends_on:                      # optional, explicit dependencies
    - <step_id>
  condition: <boolean_expr>       # optional, step executes if true
  on_error: <error_strategy>      # optional, default: abort
  timeout: <seconds>              # optional, default: 120s
  parallel: <bool>                # optional, default: false
  loop: <loop_spec>               # optional, if iterating
  checkpoint: <checkpoint_spec>   # optional, if human gate needed
  metadata:                        # optional, custom data
    priority: high
    author: alice
```

### Expression Language

#### References
- `${step_name}` — Entire output
- `${step_name.field}` — Access nested field (JSON)
- `${step_name[0]}` — Array indexing (0-based)
- `${step_name.field[0].nested}` — Chained access

#### Transforms (pipe syntax: `input | transform`)
- `| json` — Parse as JSON
- `| text` — Convert to plain text
- `| lines` — Split into line array
- `| first` — Get first element
- `| last` — Get last element
- `| count` — Count elements
- `| flatten` — Flatten nested arrays
- `| unique` — Remove duplicates
- `| sort` — Sort array
- `| filter(predicate)` — Filter by condition
- `| map(expression)` — Transform each element
- `| join(separator)` — Join array to string
- `| take(n)` — Get first N elements
- `| summary` — Summarize large output

**Example**:
```yaml
input: "${search_results | filter(output_matches(., 'python')) | map(${item.title}) | join(', ')}"
```

#### Predicates (for conditionals & filters)
- `exists(field)` — Field is defined
- `empty(field)` — Field is empty
- `matches(field, regex)` — Field matches pattern
- `gt(field, number)` — Field > number
- `contains(field, string)` — Field contains substring
- `all_passed(step)` — All sub-steps passed
- `any_passed(step)` — At least one sub-step passed

### 7 Complete Example Workflows

#### 1. **research-ingest** (Research → Knowledge Graph)
```yaml
name: research-ingest
steps:
  - name: search
    cluster: web_search
    input: "${topic}"
    timeout: 30
  - name: extract_content
    cluster: web_content_extraction
    input: "${search.output}"
  - name: synthesize
    cluster: knowledge_graph
    input: "${extract_content.output}"
    checkpoint:
      message: "Review synthesis before indexing?"
  - name: notify
    cluster: communication
    input: "Research complete: ${synthesize.output}"
emit:
  - sink: knowledge
    document: "${synthesize.output}"
  - sink: slack
    message: "Indexed new research on ${topic}"
```

#### 2. **feature-dev-pipeline** (FRAME→SHAPE→BUILD→PROVE)
```yaml
name: feature-dev-pipeline
steps:
  - name: frame
    cluster: sequential_thinking
    input: "${feature_request}"
    output: spec.md
  - name: shape
    cluster: code_analysis_mcp
    input: "${frame.output}"
    output: plan.md
  - name: build
    cluster: code_execution
    input: "${shape.output}"
    output: code
    timeout: 600
  - name: test
    cluster: code_testing
    input: "${build.output}"
    on_error: retry
  - name: prove
    cluster: security_scanning
    input: "${build.output}"
    output: status.md
emit:
  - sink: github
    action: create_pr
    title: "feat: ${feature_request | take(50)}"
    body: "${prove.output}"
```

#### 3. **sentry-bug-fix** (Error → Root Cause → Fix → Deploy)
```yaml
name: sentry-bug-fix
steps:
  - name: fetch_issue
    cluster: sentry_monitoring
    input: "${issue_id}"
  - name: analyze
    cluster: code_analysis_mcp
    input: "${fetch_issue.output}"
  - name: fix
    cluster: code_generation
    input: "${analyze.output}"
    checkpoint:
      message: "Approve code fix?"
  - name: test
    cluster: code_testing
    input: "${fix.output}"
  - name: deploy
    cluster: vercel_platform
    input: "${test.output}"
    condition: "all_passed(test)"
emit:
  - sink: github
    action: create_pr
    title: "fix: ${analyze.output.title}"
  - sink: sentry
    action: post_comment
    message: "Fixed in ${deploy.output.url}"
```

#### 4. **figma-to-deploy** (Design → Code → Live)
```yaml
name: figma-to-deploy
steps:
  - name: export_design
    cluster: figma_design
    input: "${figma_file_id}"
  - name: generate_code
    cluster: code_generation
    input: "${export_design.output}"
  - name: review
    cluster: code_analysis_mcp
    input: "${generate_code.output}"
    checkpoint:
      message: "Code quality acceptable?"
  - name: deploy
    cluster: vercel_platform
    input: "${generate_code.output}"
emit:
  - sink: github
    action: create_issue
    title: "Design implementation complete"
    body: "Live at ${deploy.output.url}"
```

#### 5. **research-swarm** (Multi-source parallel research)
```yaml
name: research-swarm
steps:
  - name: research
    cluster: web_search
    fan_out:
      query: "${topic}"
      branches:
        - name: web_results
          cluster: web_search
        - name: academic_results
          cluster: academic_research
        - name: code_results
          cluster: github_search
  - name: aggregate
    cluster: knowledge_graph
    input: "${research.web_results.output} + ${research.academic_results.output} + ${research.code_results.output}"
    fan_in:
      strategy: merge_all
emit:
  - sink: knowledge
    document: "${aggregate.output}"
```

#### 6. **monitor-respond** (Observe → Alert → Act)
```yaml
name: monitor-respond
steps:
  - name: check_health
    cluster: monitoring_observability
    loop:
      mode: until
      condition: "health.status == 'unhealthy'"
      interval: 60
  - name: investigate
    cluster: code_analysis_mcp
    input: "${check_health.output}"
  - name: decide
    cluster: ai_agents
    input: "${investigate.output}"
    gate:
      condition: "matches(decide.recommendation, 'rollback')"
      then:
        - name: rollback
          cluster: vercel_platform
      else:
        - name: hotpatch
          cluster: code_execution
emit:
  - sink: slack
    message: "Alert resolved: ${decide.output}"
```

#### 7. **auto-document** (Code → Living Docs)
```yaml
name: auto-document
steps:
  - name: scan_code
    cluster: code_analysis_mcp
    input: "${repo_path}"
    loop:
      mode: for_each
      array: "${scan_code.results}"
  - name: generate_docs
    cluster: code_generation
    input: "${scan_code | map(${item.code_snippet})}"
  - name: index
    cluster: knowledge_graph
    input: "${generate_docs.output}"
  - name: publish
    cluster: notion_apps
    input: "${index.output}"
emit:
  - sink: github
    action: commit
    message: "docs: auto-generated from code ($(date))"
```

### Execution Semantics

#### Step Lifecycle
```
PENDING
  ↓ (dependencies satisfied)
BLOCKED (waiting for dependency or checkpoint)
  ↓ (unblocked)
READY (ready to execute)
  ↓ (start execution)
RUNNING (actively executing)
  ↓ (human checkpoint, if configured)
CHECKPOINT (awaiting decision)
  ↓ (decision made)
COMPLETED / FAILED / SKIPPED
```

#### Concurrency Defaults
- **Maximum parallel**: 4 steps globally
- **Per-protocol limits**:
  - MCP: 8 parallel
  - CLI: 4 parallel
  - BROWSER_AUTO: 2 parallel
  - API: 6 parallel

#### Timeout Defaults
- **Global default**: 120 seconds
- **Per-cluster overrides**:
  - web_search: 30s
  - code_analysis: 60s
  - browser_automation: 30s
  - container_operations: 300s
  - database_queries: 30s

#### Error Strategies
- `abort` — Stop, cascade failure
- `retry(max_retries, backoff)` — Exponential backoff
- `fallback(alternatives)` — Use alternatives (from routing-matrix)
- `skip` — Continue to next step
- `ask` — Checkpoint; await human decision

---

## PART 4: RESEARCH SYNTHESIS (Five Documents → Unified Recommendations)

### Research Sources (D1-D5)
| Ref | Title | Author | Key Strength |
|-----|-------|--------|--------------|
| D1 | deep-research-report.md | Claude Deep Research | Ground-truth audit, SDLC mapping, existing system catalog |
| D2 | compass_artifact_*.md | ChatGPT Compass | Shipping discipline, business models, 50-hour roadmap |
| D3 | I am undisciplined...procedu.md | Perplexity Run 1 | Rhetorician's framework, 3-phase commodification |
| D4 | I am undisciplined...procedu (1).md | Perplexity Run 2 | Frame/Shape/Build/Prove, session protocols |
| D5 | AI Conductor's Software Development Growth.md | ChatGPT Academic | Enterprise governance, GraphRAG, multi-agent frameworks |

### 10 Unanimous Consensus Points (U1-U10)

**U1: AI-conductor approach is a STRENGTH, not a deficiency**
- **All documents agree**: The human-directing-AI approach is the RIGHT model for 2026+
- **Implication**: Formalize it. Document it. Teach it. Don't apologize for it.
- **Action**: Create "AI Conductor's Handbook" (essays + interactive guide)

**U2: Minimal canonical lifecycle (3-5 step cycle)**
- **All documents converge** on a small, repeatable cycle
- **D1 calls it**: Score / Rehearse / Perform
- **D4 calls it**: Frame / Shape / Build / Prove
- **D5 calls it**: spec.md / plan.md / status.md (artifacts)
- **Implication**: Use D4's verbs as canonical. Phase names → GitHub Issue Custom Properties.
- **Action**: Adopt **FRAME / SHAPE / BUILD / PROVE** as canonical phases

**U3: WIP limits are the critical enforcement mechanism**
- **All documents**: WIP limits work better than willpower
- **Specific limits**: 3 CANDIDATE max per person, 1 PUBLIC_PROCESS per organ
- **Implication**: Encode in registry-v2.json; validate in CI
- **Action**: Add `wip_limits` section to seed.yaml; enforce in GitHub Actions

**U4: Different AI models serve different ROLES**
- **All documents**: One model can't do everything; role assignment matters
- **D4 + D5 elaborate**: Architect (reasoning), Implementer (execution), Tester (verification), Librarian (research)
- **Implication**: Configure per-role in agents.yaml; route tasks to right model
- **Action**: Create role-based agent configurations; reference in CI pipeline

**U5: The process itself is a commodifiable product**
- **All documents**: Templates → Courses → Consulting → SaaS subscription
- **Implication**: Version playbooks; create training curriculum; build SaaS dashboard
- **Action**: 5-stage funnel: Free templates → Templates repo → 50-hour course → Consulting → Membership SaaS

**U6: Automated enforcement beats willpower (turn discipline into defaults)**
- **All documents**: Rules written in code are better than rules written in docs
- **Implication**: Encode FRAME/SHAPE/BUILD/PROVE in CI; auto-validate branches; gate PRs
- **Action**: Create governance-rules.json; GitHub Branch Protection rules; auto-format templates

**U7: Trunk-based development with short-lived branches**
- **All documents**: Feature branches should last days, not weeks
- **D1 + D4 explicit**: Main branch is always deployable
- **Implication**: Feature flags for incomplete work; daily rebases; small PRs (one idea = one PR)
- **Action**: CI gating; mandate PR size limits (<10 files, <400 lines)

**U8: Document WHY, not WHAT (intent over implementation)**
- **All documents**: Comments explain *why* decisions were made, not what code does
- **Implication**: Enforce via linting; code review checklist; training
- **Action**: Create "comment hygiene" linting rule; CodeReview rubric

**U9: Small changes, fast feedback, fast CI (continuous delivery culture)**
- **All documents**: Deployment frequency → business outcome
- **D1 references DORA metrics**: Lead time, deployment frequency, MTTR
- **Implication**: CI must complete in <10 minutes; one PR = one idea; same-day deployment
- **Action**: Profile CI; identify slow tests; parallel test execution; per-cluster timeouts

**U10: Organs map naturally to bounded contexts (Domain-Driven Design)**
- **All documents**: Eight organs = eight domains with unidirectional flow
- **D5 explicit**: ORGAN-I (Theoria) → II (Poiesis) → III (Ergon); ORGAN-IV orchestrates; ORGAN-V observes; VII distributes
- **Implication**: Enforce boundaries in CI; no circular dependencies; promote contracts (seed.yaml) to governance
- **Action**: Extend organ-audit.py to validate dependency DAG; fail CI on violations

---

### 5 Strong Majority Positions (M1-M5)
*(Supported by 4/5 documents; 1 absent/silent)*

**M1: Kanban methodology** (D1, D2, D3, D4 agree; D5 absent)
- **Consensus**: Visual boards (GitHub Projects), WIP limits, flow metrics
- **Implementation**: GitHub Projects with custom statuses (FRAME / SHAPE / BUILD / PROVE)

**M2: Shape Up's appetite-based estimation** (D1, D2, D3, D4 agree; D5 absent)
- **Consensus**: Estimate in "appetite" (small/medium/large), not hours
- **Implementation**: Add `appetite` field to seed.yaml; query in planning

**M3: Named lifecycle loop variants** (D1, D3, D4 propose; D2 absent; D5 uses artifacts instead)
- **Consensus**: Canonical cycle should have explicit phase names
- **Contention resolved (C1)**: D4's verbs (FRAME/SHAPE/BUILD/PROVE) win; D5's artifacts (spec/plan/status) are outputs

**M4: 30-day ramp-up plan with weekly milestones** (D1, D2, D3, D4 agree; D5 absent)
- **Consensus**: New contributors should hit velocity in 4 weeks
- **Implementation**: Create onboarding path; learning roadmap (D2: 50 hours; D3: reading list)

**M5: DORA metrics for deployed services** (D1, D2, D3, D5 agree; D4 absent)
- **Consensus**: Measure deployment frequency, lead time, MTTR
- **Implementation**: Add observability to CI/CD; dashboard in meta-organvm

---

### 7 Contentions & Resolutions (C1-C7)

**C1: Lifecycle naming convention** ❌ UNRESOLVED (needs action)
- **D1 proposes**: Score / Rehearse / Perform (metaphorical)
- **D4 proposes**: Frame / Shape / Build / Prove (verbs)
- **D5 proposes**: spec.md / plan.md / status.md (artifacts)
- **RESOLUTION**: 
  - **Primary**: Use D4's verbs (FRAME / SHAPE / BUILD / PROVE) as canonical phase names
  - **Secondary**: D1's metaphor (Score → Rehearse → Perform) as mnemonic/framing
  - **Tertiary**: D5's artifacts (spec.md, plan.md, status.md) as required deliverables per phase
  - **Action**: Update FRAME/SHAPE/BUILD/PROVE in CLAUDE.md; add Custom Properties to GitHub Issues

**C2: Learning roadmap structure** ❌ PARTIALLY RESOLVED
- **D2 proposes**: 50-hour curriculum structure
- **D3 proposes**: Reading list (books, papers)
- **D1, D4 silent**
- **RESOLUTION**:
  - **Primary**: Use D2's 50-hour roadmap as the curriculum backbone
  - **Secondary**: Integrate D3's reading list; prioritize judgment over syntax
  - **Tertiary**: Create learning path tied to FRAME/SHAPE/BUILD/PROVE phases
  - **Action**: Create `/learning-path/` directory in meta-organvm; weekly milestones for 30-day onboarding

**C3: Session protocol / rituals** ✅ MOSTLY RESOLVED
- **D4 most explicit**: 6-step ritual (plan → execute → reflect → document → handoff → close)
- **D5 adds**: Artifact requirements + MCP + GraphRAG for context management
- **D1 implicitly agrees** (audit trail in registry)
- **D2, D3 silent**
- **RESOLUTION**: Adopt D4's ritual with D5's artifact requirements and D3's session closure protocol
- **Action**: Codify in CLAUDE.md session-start / session-end sections; enforce in GitHub Actions

**C4: Enterprise governance scope** ❌ NEEDS STRATEGY
- **D5 most ambitious**: Enterprise Cloud features (Okta SSO, audit logs, team hierarchy, GraphRAG)
- **D1 pragmatic middle**: Registry-based governance, seed.yaml contracts
- **D2 light**: Templates + templates repo
- **D3, D4 silent**
- **RESOLUTION**:
  - **Tier 1 (now, free)**: Registry-v2.json + governance-rules.json + seed.yaml (D1)
  - **Tier 2 (near-term, paid)**: GitHub Teams + Custom Properties + branch protection (light enterprise)
  - **Tier 3 (future, enterprise)**: Okta SSO + GraphRAG + audit dashboard (D5, when justified)
- **Action**: Tiered rollout plan; no need to ship Tier 3 features immediately

**C5: Multi-agent orchestration (manual vs. automated)** ❌ PROGRESSIVE APPROACH
- **D2, D3, D4 prefer**: Manual role-switching (AI conductor is human)
- **D5 prefers**: Automated orchestration (agentic, workflow-driven)
- **RESOLUTION**: Progressive levels
  - **Level 1 (now)**: Manual role assignment (human decides who does what)
  - **Level 2 (next quarter)**: Structured context (agents.yaml, role-based routing)
  - **Level 3 (this year)**: Automated task dispatch (workflow-dsl.yaml can route to appropriate role)
- **Action**: Design agent role registry; implement in Phase 2

**C6: Context window handling strategies** ❌ PROGRESSIVE APPROACH
- **D4 prefers**: Narrow slices (focused context per step)
- **D5 ambitious**: PTC (prompt tree compression) + MCP + GraphRAG + tree-sitter
- **RESOLUTION**: Layered approach
  - **Layer 1 (now)**: D4's narrow slices (one workflow at a time)
  - **Layer 2 (next)**: Structured session context (session.json with breadcrumbs)
  - **Layer 3 (this year)**: PTC + GraphRAG (long-context reasoning with sublinear scaling)
- **Action**: Infrastructure already exists (MCP + FS); invest in D5 approaches progressively

**C7: Commodification strategy (5-layer funnel)** ✅ CONSENSUS + EXPANSION
- **All agree on funnel**: Templates → Courses → Consulting
- **D5 adds**: SaaS subscription layer (membership, recurring revenue)
- **RESOLUTION**: 5-layer funnel
  1. **Free**: Markdown templates in GitHub (governance-templates/ repo)
  2. **Freemium**: Cookbooks + playbooks (public wiki, community curated)
  3. **Course**: 50-hour curriculum (D2 structure, D3 reading, D4 practices)
  4. **Consulting**: Custom implementations (team workshops, code review)
  5. **SaaS**: Subscription dashboard (metrics, orchestration, multi-org)
- **Action**: Phase rollout; start with templates, add course by EOQ

---

### 9 Identified Gaps (G1-G9)

| Gap | Severity | Note | Action |
|-----|----------|------|--------|
| **G1: Mobile development** | Medium | No iOS/Android workflows | Create mobile-dev-pipeline workflow |
| **G2: Data engineering / MLOps** | Medium | No ML training workflows | Design ML-focused bounded context |
| **G3: Incident response** | High | No post-mortem automation | Add incident-response cluster + routes |
| **G4: Accessibility** | High | No a11y testing cluster | Integrate axe, WAVE, screen reader testing |
| **G5: Licensing strategy** | Medium | No license compliance checks | Add license-scanning cluster |
| **G6: Performance engineering** | Medium | No perf profiling workflows | Add performance-testing cluster |
| **G7: Internationalization (i18n)** | Low | No localization workflows | Future: add i18n-tools cluster |
| **G8: Creative / artistic methodology** | **CRITICAL** | No creative workflows in ontology | Create creative-dev-pipeline (visual/audio/interactive) |
| **G9: Tool-interaction-design integration** | High | Ontology exists but not yet integrated into governance | Bridge ontology → CI validation, agent role selection |

---

### Implementation Priority Tiers

#### **Tier 1: IMMEDIATE (This Week)**
These are quick wins with high ROI; do first to establish momentum.

- [ ] Adopt **FRAME / SHAPE / BUILD / PROVE** as canonical phase names
  - Update CLAUDE.md (all organs)
  - Update meta-organvm/organvm-engine/governance-rules.json
  - Create GitHub Issue Custom Property templates

- [ ] Codify **WIP limits** in registry-v2.json
  - `candidate_max: 3` per person
  - `public_process_per_organ: 1`
  - Validate in `organ-audit.py`

- [ ] Create **spec.md / plan.md / status.md templates**
  - Add to governance-templates/ repo
  - Reference in CLAUDE.md
  - Link from seed.yaml

- [ ] Adopt **D4's session ritual**
  - 6-step protocol (plan → execute → reflect → document → handoff → close)
  - Codify in session-start / session-end in CLAUDE.md
  - Optional: enforce via bot

#### **Tier 2: NEAR-TERM (This Month)**
Mid-sized initiatives that require implementation.

- [ ] **GitHub Branch Protection & PR templates**
  - Require FRAME/SHAPE/BUILD/PROVE labels
  - Mandate spec.md in FRAME PRs
  - Require passing CI + code review

- [ ] **GitHub Issue Forms**
  - Template for feature (appetite-based)
  - Template for bug (Sentry integration)
  - Template for task (lifecycle-aware)

- [ ] **Extend organ-audit.py**
  - Validate seed.yaml completeness
  - Check WIP limits
  - Audit circular dependencies

- [ ] **30-day onboarding curriculum**
  - Weekly milestones
  - Reading list (D3's papers + D2's 50 hours)
  - Hands-on labs (governance repo walk-through)

- [ ] **CI audit**
  - Identify slow tests
  - Parallelize where possible
  - Set per-cluster timeouts
  - Goal: <10 min full CI

#### **Tier 3: THIS QUARTER**
Larger structural work.

- [ ] **Process Kit repo** (governance-kit/)
  - Public playbooks (from tool-interaction-design)
  - Workflow examples (from workflow-dsl.yaml)
  - Agent role configs (agents.yaml, CLAUDE.md snippets)

- [ ] **Organvm Patterns essays**
  - "Why Frame/Shape/Build/Prove?"
  - "WIP Limits: The Discipline That Scales"
  - "AI Conductor's Handbook"
  - "Eight Organs: Bounded Contexts for Creative Systems"

- [ ] **MkDocs playbook site**
  - Rendered from governance-kit/
  - Public-facing (no source code)
  - Accessible to students, consultants

- [ ] **Lifecycle phase Custom Properties**
  - Add to GitHub Issues (FRAME / SHAPE / BUILD / PROVE)
  - Add to GitHub Projects (sort/filter by phase)
  - Dashboard in meta-organvm

- [ ] **AI role configurations** (agents.yaml)
  - Define roles: Architect, Implementer, Tester, Librarian, DevOps
  - Map models to roles (Opus → Architect, Code → Implementer, etc.)
  - Router uses role-based capability lookup

#### **Tier 4: THIS YEAR**
Strategic, long-term initiatives.

- [ ] **Cohort course** (50-hour curriculum, paid)
  - Public signup
  - Weekly instructor office hours
  - Capstone project (build small system following discipline)

- [ ] **Organvm Patterns publication**
  - Essays → published booklet or journal
  - Open-source license
  - Cite in academic context

- [ ] **SaaS dashboard** (membership tier)
  - Multi-org support
  - Governance metrics + health indicators
  - Workflow execution + artifact storage

- [ ] **Grants & sponsorships**
  - NSF, NEH for AI-conductor research
  - MIT Media Lab fellowship?
  - Fund postdocs on creative computational systems

- [ ] **Enterprise Cloud upgrade**
  - Okta SSO + team hierarchy
  - Audit logs + compliance export
  - GraphRAG for long-context reasoning
  - Premium support + SLA

- [ ] **Full orchestrator-worker automation**
  - Agent role assignment from ontology
  - Task dispatch to appropriate model/tool
  - Fallback routing when cluster unavailable

- [ ] **GraphRAG implementation**
  - Tree-sitter AST for code understanding
  - Semantic indexing for long contexts
  - Sub-linear scaling for large codebases

---

## PART 5: INTEGRATION & ACTION ITEMS

### What Needs to Happen Next

1. **Unify the three YAML layers** (ontology, routing-matrix, workflow-dsl)
   - Cross-validate: every cluster in routing-matrix must exist in ontology
   - Every capability must have 2+ routing options (alternatives)
   - Every example workflow must be executable

2. **Add missing clusters from research recommendations**
   - `prompt_engineering` (CLAUDE.md, .cursorrules, agents.yaml)
   - `governance_engine` (registry, rules, contracts, audit scripts)
   - `knowledge_management` (Obsidian, Notion, PARA structure)

3. **Add missing routes from research recommendations**
   - governance_engine → ci_cd (enforce rules)
   - prompt_engineering → code_generation (agent configs guide implementation)
   - knowledge_graph → governance_engine (audit trails)
   - sentry_monitoring → governance_engine (incident escalation)

4. **Formalize the eight AI-conductor roles**
   - Document in agents.yaml (Architect, Implementer, Tester, Librarian, DevOps, Conductor, etc.)
   - Map models to roles (Claude Opus → Architect, etc.)
   - Create role-based capability routing

5. **Implement Tier 1 actions** (week 1)
   - FRAME/SHAPE/BUILD/PROVE adoption
   - WIP limits in registry
   - Template creation
   - Session ritual codification

---

## Appendix: File Locations & Commands

### Core YAML Files
```
/Users/4jp/Workspace/tool-interaction-design/
├── ontology.yaml              (578 tools, 64 clusters, 12 domains)
├── routing-matrix.yaml        (32+ routes, alternatives, capability routing)
├── workflow-dsl.yaml          (7 primitives, 7 example workflows, execution semantics)
├── router.py                  (BFS pathfinding, validation, CLI)
├── graph.mmd                  (Mermaid visualization)
└── research/
    ├── inbox/                 (raw documents from analysis)
    └── digested/              (processed YAML summaries)
        ├── 2026-03-03-tool-surface-integration.yaml
        └── 2026-03-03-five-doc-cross-analysis-digest.yaml
```

### Useful Commands
```bash
# Validate all YAML files parse correctly
python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ['ontology.yaml','routing-matrix.yaml','workflow-dsl.yaml']]"

# List all clusters
python3 router.py clusters

# Find routes between two clusters
python3 router.py route --from web_search --to knowledge_graph

# Find clusters by capability
python3 router.py capability READ

# Validate a workflow DSL file
python3 router.py validate <workflow.yaml>

# Export cluster graph as JSON
python3 router.py graph | jq .

# System briefing
cd /Users/4jp/Workspace/tool-interaction-design && python3 -m conductor patch --json
```

---

## Summary for Planning

You now have:
1. **Ontology architecture** — 578 tools, 64 clusters, 12 domains, 7 relationship types (unpopulated)
2. **Routing matrix** — 32+ concrete routes, alternatives fallbacks, capability-based routing
3. **Workflow DSL** — 7 primitives, 7 complete example workflows, expression language, execution semantics
4. **Research consensus** — 10 unanimous points, 5 strong majority positions, 7 contentions with resolutions, 9 gaps
5. **Implementation tiers** — Tier 1 (this week), Tier 2 (this month), Tier 3 (this quarter), Tier 4 (this year)

**Next step**: Decide which Tier 1 actions to prioritize and begin implementation.
