# Evaluation-to-Growth Report: tool-interaction-design

**Date:** 2026-03-03
**Mode:** Autonomous, Full Report
**Subject:** Complete project review of `~/Workspace/tool-interaction-design/`

---

## Phase 1: EVALUATION

### 1.1 Critique

#### Strengths

**S1. Unprecedented scope and completeness of inventory.**
No comparable artifact exists that maps ~950 tools across built-in CLI tools, MCP servers, macOS apps, Homebrew packages, npm globals, Docker images, pipx tools, Go binaries, and user-invocable skills into a single queryable taxonomy. This is genuinely novel.

**S2. The ontology's cluster abstraction is the right design decision.**
Collapsing 950 tools into 64 clusters makes the system tractable. Individual tools change (MCP servers get added/removed), but clusters are stable units of capability. This is a sound architectural choice that mirrors how DDD bounded contexts work.

**S3. The routing matrix encodes real, tested data flows.**
The 32 defined routes aren't theoretical — they map to tool chains that actually work in this Claude Code environment (e.g., `perplexity_research → create_entities` is a real MCP→MCP pipeline). The exemplars make routes actionable.

**S4. The workflow DSL is well-designed and has good primitives.**
Seven primitives (pipe, fan_out, fan_in, gate, loop, fallback, checkpoint) cover the fundamental composition patterns. The 7 example workflows demonstrate real-world applicability. The expression language is concise.

**S5. The router.py is functional and immediately useful.**
Eight working CLI commands, BFS path-finding, data-type compatibility checking, and workflow validation. It was tested and works. This is a working tool, not just a spec.

**S6. The research cross-analysis is rigorous and honest.**
The 5-document digest doesn't cherry-pick agreement — it surfaces 7 genuine contentions with reasoned resolutions. The "Gaps" section (G1-G9) shows intellectual honesty about what the research doesn't cover.

**S7. The AI Orchestra Seating Chart maps the conductor metaphor to concrete tool assignments.**
This bridges the user's identity (rhetorician/conductor) with executable tool configurations. The "conductor_only" list of human-reserved actions is an important boundary.

**S8. The research processing pipeline (inbox → digested → implemented) is a reusable pattern.**
Three-stage processing with naming conventions and validation gates. This could apply to any knowledge ingestion workflow.

#### Weaknesses

**W1. The ontology is DESCRIPTIVE but not PRESCRIPTIVE.**
It catalogs what exists but doesn't say what SHOULD be used when. The `capability_routing` table in the routing matrix partially addresses this, but the ontology itself lacks a "recommended default" field per cluster.

**W2. The routing matrix has 32 routes for 64 clusters — that's sparse.**
With 64 clusters, there are 4,032 possible directed edges. 32 routes means <1% coverage. Many obviously valid routes are missing (e.g., `neon_database → diagramming` for ER diagram generation, `jupyter_notebooks → publishing` for notebook-to-PDF, `sentry_monitoring → bug_reporting` for Jam integration).

**W3. The workflow DSL has no runtime — it's a specification without an executor.**
The 7 example workflows look correct but can't actually be run. The router.py validates structure but doesn't execute workflows. This makes the DSL aspirational rather than operational.

**W4. The Mermaid graph uses emojis in subgraph labels.**
The user's CLAUDE.md says "Only use emojis if the user explicitly requests it." The graph.mmd file uses emojis in every subgraph header. Minor but inconsistent with stated preferences.

**W5. The ontology's tool lists are inconsistently typed.**
Some clusters use `- cli: name`, others use `- mcp: name`, others use `- app: name`, and some use bare strings. This inconsistency means the tools can't be programmatically resolved to actual tool names for invocation.

**W6. The research digest is 700+ lines of YAML — dense to navigate.**
The cross-analysis contains enormous value but its YAML format makes it hard to scan. The unanimous/contentions/gaps/expansions structure is logical but the file is too long to serve as a quick reference.

**W7. No versioning or change tracking strategy.**
The ontology, routing matrix, and DSL will all evolve as tools are added/removed. There's no strategy for tracking what changed, when, or why. The `version: "1.0"` field is static.

**W8. The project has no git repository.**
`~/Workspace/tool-interaction-design/` sits in the workspace but isn't version-controlled. Given the user's plan file discipline ("never overwrite"), this is a significant gap.

**W9. router.py lacks tests.**
The router was manually tested but has no automated test suite. For a tool meant to validate other artifacts, it should validate itself.

**W10. The ontology doesn't capture the SKILLS layer adequately.**
90+ skills are mentioned in the surface count but aren't mapped to clusters, capabilities, or routes. Skills are a meta-layer that invoke other tools — they need their own ontology treatment.

#### Priority Areas (ranked)

1. **W3** — DSL executor (highest leverage: makes workflows runnable)
2. **W8** — Git init (prevents data loss; enables change tracking)
3. **W2** — Route completeness (32 routes is too sparse for useful path-finding)
4. **W5** — Tool typing consistency (blocks programmatic tool resolution)
5. **W1** — Prescriptive defaults (tells the user what to use, not just what exists)

---

### 1.2 Logic Check

#### Contradictions Found

**LC1.** The ontology claims `surface_count: 950` but the actual enumerated tools across all 64 clusters total approximately 580-620. The gap is partially explained by Skills (90+) and tools listed in the original conversation that weren't mapped to clusters, but the number is overstated.

**LC2.** The routing matrix says `routing_rules` define three rules (protocol compatibility, data type compatibility, automation level), but these rules are encoded as YAML comments, not as machine-readable data. The router.py's `compatible_targets()` method implements its own version of Rules 1 and 2 but doesn't reference the YAML.

**LC3.** The digest says "D1 unanimously agrees" on AI role differentiation (U4), but the evidence for D1 is "Not explicitly stated but implied by tiered CI and review workflows." Calling something "implied" doesn't constitute agreement. This weakens the "unanimous" claim to a strong-majority claim.

**LC4.** The tool-surface-integration proposes `prompt_engineering` and `governance_engine` as new ontology clusters, but these haven't been added to ontology.yaml yet. The digest says what SHOULD exist, but the artifacts haven't been updated.

#### Reasoning Gaps

**RG1.** The ontology defines `relationship_types` (INVOKES, FEEDS, ALTERNATIVE_TO, ENHANCES, DEPENDS_ON, BRIDGES) but no actual relationship instances are populated. The routing matrix only covers FEEDS relationships. The other 5 relationship types are defined but empty.

**RG2.** The capability taxonomy lists 20 capabilities but doesn't define which are primary vs. secondary for each cluster. A cluster with `capabilities: [READ, WRITE, EDIT, SEARCH, EXECUTE, ORCHESTRATE, FETCH, GENERATE]` (claude_code_core) has 8 capabilities — but the primary function is ORCHESTRATE, not READ. Without weighting, capability search returns too many results.

**RG3.** The DSL concurrency model says "max 4 CLI processes" for 16GB RAM, but this is a rough heuristic, not a measured constraint. Some CLI tools (git, jq) use negligible memory while others (neovim, ffmpeg) can consume gigabytes.

#### Unsupported Claims

**UC1.** "~950 tools" — see LC1.

**UC2.** The digest claims "25-40 hours" of learning is sufficient (contention C2 resolution), revising D2's "50-70 hours" downward, with the justification "the AI handles the rest." This revision is unsupported by any evidence — it's an opinion that optimistically assumes AI compensates for less learning.

#### Coherence Recommendations

- Recount actual tools and update `surface_count` to accurate number
- Move routing rules from comments to structured YAML fields
- Downgrade U4 to "strong majority" or strengthen D1 evidence
- Apply the digest's proposed changes to the actual ontology/routing files
- Add primary/secondary capability weighting to clusters

---

### 1.3 Logos Review (Rational Appeal)

**Argument clarity: STRONG.** The project makes a clear argument: "950 tools are unmanageable → cluster them into 64 units → define routes between clusters → compose workflows from routes → execute with a router." Each layer builds on the previous one. The logical chain is sound.

**Evidence quality: MODERATE.** The ontology is grounded in actual tool inventories (verified via Bash commands). The routing matrix exemplars reference real tools. But the research digest relies on 5 AI-generated documents whose own citations are mixed (some peer-reviewed, some blog posts, some hallucinated). The evidence chain from "research says X" to "therefore do Y" is sometimes weak.

**Persuasive strength: STRONG for internal use, WEAK for external.** The project is convincing as a personal planning artifact. But it lacks the validation and testing that would make it persuasive to others. No external users have tested the router. No workflows have been executed end-to-end.

**Enhancement recommendations:**
- Add a "Validation Status" field to each artifact (TESTED / UNTESTED / THEORETICAL)
- Run at least 3 workflows end-to-end manually and document results
- Cross-reference research citations against actual sources (several D5 citations may be hallucinated)

---

### 1.4 Pathos Review (Emotional Resonance)

**Current emotional tone: Architectural / clinical.** The project reads like infrastructure documentation. It's precise and thorough but emotionally flat.

**Audience connection: VARIABLE.** For the user (the AI-conductor), the orchestra metaphor in the tool-surface-integration creates genuine resonance — mapping First Violin/Cello/Bass to AI roles is evocative and memorable. But this emotional resonance appears only in one file and isn't carried through the rest of the project.

**Engagement level: LOW for sustained use.** A 700-line YAML digest and 800-line ontology are reference materials, not things you engage with daily. The router.py CLI is the most engaging artifact because it's interactive.

**Recommendations:**
- Create a one-page "cheat sheet" that distills the entire project into a quick reference card
- Carry the orchestra metaphor into the ontology and routing matrix (not just the integration doc)
- Build a dashboard view (HTML or TUI) that makes the system feel alive, not archival

---

### 1.5 Ethos Review (Credibility)

**Perceived expertise: HIGH within the Claude Code context.** The tool inventory is demonstrably thorough. The router works. The ontology covers tools that most practitioners don't know exist.

**Trustworthiness signals:**
- Present: Working code (router.py), verified tool inventories, tested commands
- Missing: Git history, version control, automated tests, external validation, peer review

**Authority markers: MODERATE.** The project draws on 5 research documents but doesn't independently verify their claims. Some D5 citations (e.g., the "120+ agentic tools" statistic, specific arXiv papers) should be verified.

**Credibility recommendations:**
- Initialize git repo with proper .gitignore
- Add a test suite for router.py
- Verify at least the top 10 external citations from the research documents
- Add a CHANGELOG tracking project evolution

---

## Phase 2: REINFORCEMENT

### 2.1 Synthesis — Contradictions to Resolve

| Issue | Resolution | Priority |
|-------|-----------|----------|
| LC1: 950 vs ~600 actual tools | Recount; update to actual number; note Skills separately | Medium |
| LC2: Routing rules as comments | Extract into structured `rules:` YAML section with machine-readable predicates | High |
| LC3: U4 "unanimous" is overstated | Reclassify as M6 (strong majority) or add genuine D1 evidence | Low |
| LC4: Proposed clusters not yet in ontology | Apply changes: add `prompt_engineering`, `governance_engine`, `knowledge_management` clusters | High |
| RG1: Empty relationship types | Populate at least ALTERNATIVE_TO and DEPENDS_ON relationships | Medium |
| RG2: No capability weighting | Add `primary_capabilities` and `secondary_capabilities` fields to cluster schema | Medium |
| W5: Inconsistent tool typing | Define a tool reference schema: `{type: mcp|cli|app|builtin|docker|npm|pipx, name: string, invocation: string}` | High |

---

## Phase 3: RISK ANALYSIS

### 3.1 Blind Spots

**BS1. The project assumes Claude Code is the orchestrator.**
The entire ontology, routing matrix, and DSL are built around Claude Code as the central hub. If the user switches to Cursor Agent, Codex CLI, or another orchestrator, the project's utility drops sharply. There's no abstraction layer between "orchestrator" and "Claude Code built-in tools."

**BS2. Tool availability is assumed to be static.**
MCP servers, Homebrew packages, and npm globals change. Tools get deprecated, renamed, or replaced. The ontology has no mechanism for marking tools as deprecated, experimental, or version-pinned.

**BS3. The research documents were AI-generated about AI-generated work.**
All 5 input documents were produced by LLMs (Claude, ChatGPT, Perplexity) analyzing the user's LLM-built system. This creates a recursive echo chamber where AI biases (over-engineering, framework proliferation, methodology inflation) are amplified through multiple layers. No human practitioner or peer reviewed any of the research.

**BS4. The project serves one user.**
The entire system is designed for a specific individual's tool configuration on a specific machine. There's no portability story. The `surface_count` is literally a count of apps on this Mac.

**BS5. Creative tooling (ORGAN-I/II) is underrepresented.**
The ontology has 7 CREATIVE clusters but they're mostly cataloged as GUI-only tools with no automation paths. The research digest's Gap G8 flags this. For a user whose core identity is artistic, the engineering-heavy bias is a significant blind spot.

#### Mitigation Strategies

- BS1: Add an `orchestrator` abstraction layer to the ontology; define Claude Code as the default implementation but allow substitution
- BS2: Add `status: active|deprecated|experimental` and `version_pinned: string` to tool entries
- BS3: Acknowledge the recursive AI provenance explicitly; prioritize recommendations that have external (non-AI) validation; verify citations
- BS4: Accept this as a feature, not a bug — this is a personal tool. But extract generalizable patterns into the process kit
- BS5: Create dedicated creative-workflow DSL examples; map SuperCollider/TouchDesigner/Pure Data scripting interfaces as automatable (they have CLI/OSC interfaces)

### 3.2 Shatter Points

**SP1. (CRITICAL) No git repo = one `rm -rf` from total loss.**
The entire project exists only on the local filesystem. No backup, no history, no recovery. Severity: CRITICAL.

**SP2. (HIGH) The ontology is a single 800-line file with no schema validation.**
A single typo in ontology.yaml (e.g., mismatched cluster ID reference) silently breaks the router. There's no JSON Schema or YAML schema validating the ontology structure. Severity: HIGH.

**SP3. (HIGH) The DSL is unexecutable — it may contain design flaws invisible without runtime.**
The 7 example workflows look correct on paper but have never been run. Step dependencies, data type mismatches, and concurrency conflicts would only surface during execution. The workflow DSL could be fundamentally flawed in ways that static analysis can't detect. Severity: HIGH.

**SP4. (MEDIUM) The routing matrix's `alternatives` section was a YAML parse error that was patched.**
This indicates the YAML files were written rapidly and may contain other structural issues that haven't been caught. Severity: MEDIUM.

**SP5. (MEDIUM) The digest's implementation_priority has no owner or timeline.**
Tier 1 says "Do This Week" but there's no tracking mechanism (no GitHub Issues, no task list, no calendar). Priorities without tracking are aspirations. Severity: MEDIUM.

**SP6. (LOW) The router.py has no error handling for malformed YAML.**
If ontology.yaml or routing-matrix.yaml has a syntax error, the router crashes with a raw Python traceback. Severity: LOW.

#### Preventive Measures

| Shatter Point | Prevention | Effort |
|---------------|-----------|--------|
| SP1 | `git init` + initial commit + remote push | 5 min |
| SP2 | Create `schemas/ontology-schema.json` + validate in CI | 2 hours |
| SP3 | Implement a minimal DSL interpreter that dry-runs workflows | 8 hours |
| SP4 | Run `python3 -c "import yaml; yaml.safe_load(open('file.yaml'))"` on all YAML files | 5 min |
| SP5 | Create GitHub Issues from implementation_priority tiers | 30 min |
| SP6 | Add try/except with user-friendly error messages in router.py | 30 min |

---

## Phase 4: GROWTH

### 4.1 Bloom (Emergent Insights)

**E1. This project IS the "process kit" the research recommends commodifying.**
The digest says "create an organvm-process-kit." But the tool-interaction-design project itself — ontology + routing + DSL + router — is a more powerful version of that kit. It's not just templates; it's a queryable, executable model of the entire development surface. Reframe this project as the product, not just the planning artifact.

**E2. The ontology could become a living system via MCP.**
The router.py is a CLI tool, but the ontology could be served as an MCP server itself. Claude Code could query it in real-time: "what cluster handles SEARCH?" → capability routing → tool suggestion. This turns the ontology from a reference document into an active intelligence layer.

**E3. The AI Orchestra Seating Chart maps directly to Claude Code's Agent tool.**
The `subagent_type` parameter already supports `Explore`, `Plan`, `general-purpose`. The seating chart suggests additional specialized agent types could be defined (Architect, Implementer, Tester, Librarian). This could be implemented as custom Agent configurations.

**E4. The workflow DSL could compile to Claude Code Skill definitions.**
Skills are YAML-based workflow definitions. The DSL's step schema is similar to skill step definitions. A compiler from DSL → Skill would make workflows executable within the existing Claude Code infrastructure.

**E5. The cross-analysis methodology (5 docs → digest → integration) is itself a reusable pattern.**
"Feed the same prompt to 5 different AI systems, cross-analyze for consensus/contention/gaps, synthesize into actionable integration" — this is a methodology that could be packaged as a skill or workflow.

**E6. The FRAME/SHAPE/BUILD/PROVE lifecycle maps directly to git branch naming.**
`frame/<slug>` → `shape/<slug>` → `build/<slug>` → `prove/<slug>` as branch prefixes would make the lifecycle phase visible in the git log. Combined with Conventional Commits (`frame:`, `shape:`, `build:`, `prove:`), the entire development history becomes self-documenting.

#### Expansion Opportunities

- Turn router.py into an MCP server (highest leverage)
- Create a DSL → Skill compiler
- Package the 5-doc cross-analysis methodology as a reusable skill
- Build a TUI dashboard using `rich` that shows live cluster/route/workflow status
- Add a `router.py suggest` command that recommends tools given a natural language task description

#### Cross-Domain Connections

- The ontology's cluster model mirrors ORGAN-IV's registry-v2.json structure — they could share a schema
- The routing matrix's capability_routing table could be served by the system-dashboard
- The workflow DSL's checkpoint primitive maps to GitHub PR review gates
- The AI Orchestra Seating Chart maps to the AGENTS.md files that D4 recommends creating per repo

### 4.2 Evolve (Implementation Plan)

Based on all phases, here is the prioritized implementation plan:

#### IMMEDIATE (Today)

| # | Action | Artifact | Addresses |
|---|--------|----------|-----------|
| 1 | `git init` + initial commit | project root | SP1 |
| 2 | Validate all YAML files parse correctly | all .yaml | SP4 |
| 3 | Remove emojis from graph.mmd subgraph labels | graph.mmd | W4 |
| 4 | Update `surface_count` to accurate number | ontology.yaml | LC1 |

#### THIS WEEK

| # | Action | Artifact | Addresses |
|---|--------|----------|-----------|
| 5 | Add proposed clusters (prompt_engineering, governance_engine, knowledge_management) to ontology | ontology.yaml | LC4 |
| 6 | Define tool reference schema and normalize all tool entries | ontology.yaml | W5 |
| 7 | Add 20+ missing routes to routing matrix | routing-matrix.yaml | W2 |
| 8 | Move routing_rules from comments to structured YAML | routing-matrix.yaml | LC2 |
| 9 | Add primary/secondary capability weighting | ontology.yaml | RG2 |
| 10 | Add error handling to router.py | router.py | SP6 |
| 11 | Create one-page cheat sheet | cheatsheet.md | Pathos |

#### THIS MONTH

| # | Action | Artifact | Addresses |
|---|--------|----------|-----------|
| 12 | Create JSON Schema for ontology validation | schemas/ | SP2 |
| 13 | Add automated tests for router.py | tests/ | W9 |
| 14 | Build minimal DSL dry-run interpreter | router.py or executor.py | SP3, W3 |
| 15 | Populate ALTERNATIVE_TO and DEPENDS_ON relationships | ontology.yaml | RG1 |
| 16 | Map Skills layer to clusters | ontology.yaml | W10 |
| 17 | Create GitHub Issues from implementation tiers | GitHub | SP5 |
| 18 | Add tool status fields (active/deprecated/experimental) | ontology.yaml | BS2 |

#### THIS QUARTER

| # | Action | Artifact | Addresses |
|---|--------|----------|-----------|
| 19 | Build router as MCP server | mcp-router/ | E2 |
| 20 | Create DSL → Skill compiler | compiler.py | E4 |
| 21 | Build TUI dashboard | dashboard.py | Pathos |
| 22 | Package cross-analysis methodology as skill | a-i--skills/ | E5 |
| 23 | Add creative-domain workflow examples | workflow-dsl.yaml | BS5, G8 |
| 24 | Verify top 10 research citations | research/ | Ethos |

---

## Summary

| Phase | Key Finding |
|-------|-------------|
| **Critique** | Strong foundations (ontology, routing, DSL, router) but sparse route coverage, no git, no tests, no DSL runtime |
| **Logic Check** | 3 contradictions (tool count, routing rules as comments, overstated unanimity), 3 reasoning gaps (empty relationships, no capability weighting, heuristic concurrency) |
| **Logos** | Logical chain is sound; evidence quality moderate; needs external validation |
| **Pathos** | Orchestra metaphor creates resonance but is confined to one file; project overall reads as clinical infrastructure docs |
| **Ethos** | Strong within Claude Code context; needs git history, tests, and citation verification for external credibility |
| **Blind Spots** | Orchestrator lock-in, static tool assumptions, recursive AI echo chamber, single-user design, creative tooling underserved |
| **Shatter Points** | No git repo (CRITICAL), no schema validation (HIGH), unexecutable DSL (HIGH) |
| **Growth** | Ontology-as-MCP-server, DSL-to-Skill compiler, cross-analysis-as-methodology, router.py suggest command |

**The single highest-leverage action is initializing a git repository.** Everything else builds on that foundation.

**The single highest-value insight is E1:** this project IS the process kit. Stop treating it as planning infrastructure and start treating it as the product.
