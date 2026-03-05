# Evaluation-to-Growth: tool-interaction-design

**Date**: 2026-03-05
**Mode**: Autonomous (full report)
**Scope**: Project-wide review — all layers, code, tests, architecture
**Version reviewed**: 0.5.0 (2026-03-04)

---

## Phase 1: Evaluation

### 1.1 Critique

#### Strengths

1. **Clean abstraction hierarchy**: Cluster-based routing decouples tool inventory from data flow topology. When individual tools change (Perplexity → Tavily), routes remain valid. This is the system's defining architectural insight.

2. **Layered independence**: `router.py` runs standalone with only PyYAML. The conductor package adds sessions/governance on top. MCP server wraps conductor. Each layer is independently testable and deployable.

3. **Resilient Patchbay**: Per-section `try/except` in briefing generation means a corpus failure doesn't crash the dashboard. Seven independent sections compose gracefully.

4. **Atomic persistence**: `atomic_write()` using tmp-file-then-rename is POSIX-correct. State files survive process interruption without corruption.

5. **Phase-gated discipline**: FRAME→SHAPE→BUILD→PROVE with explicit allowed/forbidden actions per phase. PROVE forbids direct code fixes — forces report-only. This is genuine process enforcement, not suggestion.

6. **Comprehensive test suite**: 271 tests, 100% pass rate, real data integration (loads actual YAML files), proper `tmp_path` isolation. Fuzz testing via Hypothesis covers parser totality.

7. **Schema-contract system**: 12 JSON Schemas validate handoffs, traces, route decisions, and MCP responses. `assert_contract()` ensures structured outputs.

8. **Health-aware pathfinding**: `inject_health_metrics()` lets live success rates bias routing without code changes. Cache invalidates automatically when metrics shift.

#### Weaknesses

1. **Workflow DSL spec-vs-implementation gap**: 7 DSL primitives are beautifully specified (`pipe`, `fan_out`, `fan_in`, `gate`, `loop`, `fallback`, `checkpoint`) but the executor is a prototype. Fan-out is sequential, gate conditions are incomplete, loop control logic is partial. Users writing workflows against the spec will hit runtime failures.

2. **External corpus dependency is brittle**: Conductor hard-depends on `~/Workspace/meta-organvm/organvm-corpvs-testamentvm/` for registry and governance rules. No offline fallback. If that path is missing, governance commands crash instead of degrading.

3. **E2E test coverage is skeletal**: `test_e2e_flow.py` has only 2 tests (39 lines). No test covers session→workflow→product pipeline. No error propagation test across layers. This is the weakest point in the test suite.

4. **Module coupling**: Session↔Oracle bidirectional dependency. Patchbay silently syncs WorkRegistry on every read. Compiler accesses RoutingEngine internals. These create hidden failure modes.

5. **Observability logs grow unbounded**: `.conductor-observability.jsonl` (1.1MB already), `.conductor-handoffs.jsonl`, `.conductor-traces.jsonl` — no rotation, no archival, no size limits.

6. **CHANGELOG is minimal**: Two entries total. A project with 24 modules, 12 schemas, and 271 tests has more history than "Initial conductor lifecycle" captures.

**Priority areas** (ranked):
1. DSL implementation completeness or honest capability documentation
2. E2E test expansion
3. Corpus offline fallback
4. Log rotation
5. Module decoupling

---

### 1.2 Logic Check

#### Contradictions Found

1. **WIP limits: constants vs. governance-rules.json**
   - `constants.py` hardcodes `MAX_CANDIDATE_PER_ORGAN = 3`, `MAX_PUBLIC_PROCESS_PER_ORGAN = 1`
   - `governance-rules.json` (external file) also defines limits
   - If both sources disagree, which wins? No resolution documented. `policy.py` exists but the precedence chain is unclear.

2. **Workflow DSL documentation claims full primitive support; executor doesn't deliver**
   - `workflow-dsl.yaml` documents `fan_out =>` with parallel semantics
   - `executor.py` runs branches sequentially with `scatter__branch_N` naming
   - The spec says "parallel"; the runtime does serial

3. **Session phase model claims linear progression but allows backtracking**
   - VALID_TRANSITIONS allows SHAPE→FRAME and PROVE→BUILD
   - Phase-cluster documentation presents FRAME→SHAPE→BUILD→PROVE as a pipeline
   - Backtracking is a feature, but messaging implies linearity

#### Reasoning Gaps

1. **No capacity model**: How many concurrent sessions can the system handle? File-based state with no locking suggests single-user, but nothing states this explicitly.

2. **Plugin lifecycle undefined**: Plugins can register clusters, but what happens when a plugin is removed? Are routes involving that cluster invalidated? No cleanup protocol.

3. **Health metric provenance**: `inject_health_metrics()` accepts arbitrary floats, but where do production health numbers come from? No collector or integration documented.

#### Unsupported Claims

1. **"578 tools"** — This count appears in CLAUDE.md but the ontology may have drifted. The exploration agent counted 592 in one pass and 578 in another. The canonical count should be computed, not stated.

2. **"JIT compilation"** — `compiler.py` generates a WorkflowState dataclass from a routing path. This is template generation, not just-in-time compilation in the conventional sense. The term overpromises.

#### Coherence Recommendations

- Add a "System Assumptions" section to CLAUDE.md explicitly stating: single-user, file-based state, no concurrent session support
- Rename JIT compilation to "workflow synthesis" or "path compilation" to avoid misleading
- Add computed tool count to doctor output rather than hardcoding in docs
- Define WIP limit precedence: `policy bundle > governance-rules.json > constants.py`

---

### 1.3 Logos Review (Rational Appeal)

#### Argument Clarity: Strong

The four-layer architecture (taxonomy → routing → DSL → OS) is well-articulated. Each layer's purpose is distinct and documented. The cluster abstraction — "tools change, clusters persist" — is a clear, defensible design principle.

#### Evidence Quality: Mixed

- **Strong**: 271 passing tests validate the implementation. Schema contracts formalize outputs. The promotion state machine is exhaustively tested.
- **Weak**: No benchmarks, no performance data, no usage metrics. The system claims to handle 578+ tools but there's no evidence it's been stress-tested at scale. The "0.5.0" version with a two-entry changelog suggests rapid development without recorded iteration history.

#### Persuasive Strength: Moderate

The system convincingly argues for structured AI-conductor workflows. The phase discipline (especially PROVE's "report only, no fixes") is genuinely novel. But the gap between specification (7 DSL primitives) and implementation (sequential pipe only) weakens credibility for anyone who tries to use the advanced features.

#### Enhancement Recommendations

- Add a "Design Decisions" document explaining key trade-offs (why file-based state over SQLite, why clusters over tools, why 4 phases not 3 or 5)
- Include performance benchmarks in doctor output
- Track version history properly — the changelog should reflect the actual development arc

---

### 1.4 Pathos Review (Emotional Resonance)

#### Current Emotional Tone: Symphonic/Ambitious

The orchestral metaphor (conductor, instruments, score, patchbay) creates strong conceptual unity. Phase instruments (Viola for Research, First Violin for Architecture, Second Violin for Implementation, Cello for Verification) add personality to what could be dry workflow management. The "streak" gamification in session stats adds subtle motivational pressure.

#### Audience Connection: Strong for the Creator, Opaque for Outsiders

The system is deeply personal — it maps to the ORGANVM eight-organ model, uses Latin naming conventions, and references a specific creative-institutional vision. For the creator, this is a coherent world. For an outside collaborator or contributor, the vocabulary barrier is high.

#### Engagement Level: High-Commitment

The patchbay briefing, session lifecycle, and governance enforcement create an immersive operating environment. But the learning curve is steep. There's no "hello world" — the minimum viable interaction requires understanding organs, phases, clusters, and routing.

#### Recommendations

- Add a 5-minute quickstart that demonstrates one session cycle without requiring full system context
- Consider a glossary mapping ORGANVM terms to conventional equivalents (organ → division, promotion → release stage, patchbay → dashboard)
- The streak mechanic is good — consider extending gamification (phase velocity trends, routing efficiency scores)

---

### 1.5 Ethos Review (Credibility)

#### Perceived Expertise: High

The system demonstrates deep knowledge of: workflow orchestration, state machines, BFS pathfinding, JSON Schema contracts, MCP protocol integration, and POSIX-safe file operations. Code quality is consistently high across 7,883 LOC.

#### Trustworthiness Signals

**Present:**
- Schema validation on all outputs
- Atomic writes preventing corruption
- Promotion state machine with no state-skipping
- `save_registry()` guard against test data leaking to production
- Comprehensive error hierarchy (ConductorError → SessionError, GovernanceError)

**Missing:**
- No version pinning in dependencies (pyproject.toml says `pyyaml>=6.0`)
- No CI/CD pipeline for the project itself (ironically, it generates CI for others)
- No security audit or threat model for the MCP server
- No contributor guidelines or code review process documented

#### Authority Markers: Domain-Specific

The system establishes authority within its own domain (ORGANVM orchestration) but doesn't reference external precedents. No comparison to Temporal, Prefect, Airflow, or other workflow engines. No academic references for the routing algorithm or governance model.

#### Credibility Recommendations

- Pin dependency versions or add lock file
- Add a CI workflow for the project itself (eat your own dog food)
- Document security model for MCP server exposure
- Add a "Prior Art" section acknowledging related systems

---

## Phase 2: Reinforcement

### 2.1 Synthesis

**Contradictions to resolve:**

| Issue | Resolution |
|-------|-----------|
| WIP limit sources (constants vs governance-rules) | Define precedence chain in constants.py docstring: policy bundle overrides governance-rules.json overrides constants.py defaults |
| DSL spec vs implementation | Add `maturity` field to each primitive in workflow-dsl.yaml: `stable`, `alpha`, `planned`. Executor should warn on alpha primitives |
| Session linearity vs backtracking | Reframe docs: "iterative phase model with forward bias" — backtracking is intentional but should require explicit reason |

**Reasoning gaps to fill:**

| Gap | Fix |
|-----|-----|
| Concurrency model | Add to CLAUDE.md: "Single-user, single-session. File-based state is not concurrent-safe." |
| Plugin cleanup | Add `conductor plugins unregister` command that removes cluster entries and invalidates affected routes |
| Health metric source | Document in routing-matrix.yaml: health metrics are injected by session close (observed success/failure) or by external monitoring |

**Unsupported claims to address:**

| Claim | Fix |
|-------|-----|
| "578 tools" | Replace with `conductor doctor` computed count; remove hardcoded number from CLAUDE.md |
| "JIT compilation" | Rename to "workflow synthesis" in compiler.py docstrings and CLAUDE.md |

---

## Phase 3: Risk Analysis

### 3.1 Blind Spots

#### Hidden Assumptions

1. **Single-user assumption is implicit**: All state files are process-local with no locking. If two terminal sessions run `conductor session start` simultaneously, state corruption is guaranteed. This assumption is never stated.

2. **Corpus availability assumed**: Governance commands crash if `~/Workspace/meta-organvm/` doesn't exist. The system was built for one developer's specific workspace layout.

3. **Tool availability assumed**: Ontology lists 578+ tools but doesn't track which are actually installed or available. A route through `neon_database` will fail if the Neon MCP server isn't running.

4. **macOS-specific**: `atomic_write()` uses `os.replace()` which is POSIX-safe but not tested on Windows. Path conventions assume Unix. No platform portability consideration.

#### Overlooked Perspectives

1. **Team usage**: The system is designed for a solo practitioner. There's no multi-user model, no role-based access, no shared state. If the ORGANVM system grows to involve collaborators, this becomes a bottleneck.

2. **Observability consumers**: Traces, handoffs, and metrics are written but nothing reads them systematically. The `ProductExtractor` mines session logs, but there's no dashboard, no alerting, no trend regression detection.

3. **Failure recovery**: If a workflow fails mid-execution, the user must manually inspect `.conductor-workflow-state.json` and decide how to resume. No `conductor workflow resume` or automatic retry.

#### Potential Biases

1. **Complexity bias**: The system solves a problem that may not need this level of infrastructure. 24 conductor modules, 12 schemas, and 7 DSL primitives for what is fundamentally a personal tool routing system. The architecture is impressive but the cost/benefit ratio for a single user is unclear.

2. **Abstraction enthusiasm**: Clusters, routes, protocols, capabilities, domains, phases, roles, instruments — the abstraction count is high. Each adds cognitive load. Some may not pay for themselves.

#### Mitigation Strategies

- Add explicit "Non-Goals" section: multi-user, Windows, real-time, distributed
- Implement `conductor workflow resume --from <step>` for crash recovery
- Add `conductor doctor --tools` to check which ontology tools are actually available
- Regularly audit whether abstractions (instruments, relationship_types) are used or just declared

---

### 3.2 Shatter Points

#### Critical Vulnerabilities (by severity)

**CRITICAL: External corpus dependency**
- **What**: Governance commands import from `~/Workspace/meta-organvm/organvm-corpvs-testamentvm/`
- **Failure mode**: If that directory is moved, renamed, or corrupted, governance module throws unhandled exceptions
- **Blast radius**: Patchbay briefing degrades. WIP checks fail. Promotion blocked.
- **Fix**: Add `--corpus-offline` mode. Cache last-known-good registry locally.

**HIGH: Unbounded log growth**
- **What**: `.conductor-observability.jsonl` is already 1.1MB. Three other JSONL files grow monotonically.
- **Failure mode**: Over months, files reach tens of MB. `get_metrics()` scans entire history each call. Patchbay briefings slow down.
- **Fix**: Add log rotation (keep last N entries or last 30 days). Archive old entries to `sessions/archive/`.

**HIGH: Workflow state fragility**
- **What**: Active workflow tracked via `.conductor-active-workflow` pointer file + per-workflow state files
- **Failure mode**: If pointer file is stale (points to deleted workflow), executor fails with confusing error
- **Fix**: Validate pointer on every executor operation. Auto-cleanup stale pointers in `doctor`.

**MEDIUM: Test isolation gap**
- **What**: `test_e2e_flow.py` (39 lines) is the only integration test. No test covers session→workflow→briefing pipeline.
- **Failure mode**: Regression in module interaction goes undetected. Cross-layer bugs escape to production.
- **Fix**: Expand to 15-20 E2E tests covering happy path, error propagation, and product extraction.

**MEDIUM: Condition parser fragility**
- **What**: Executor condition evaluation uses regex-based function name extraction and hardcoded naming conventions (`scatter__branch_N`)
- **Failure mode**: Step names with underscores break fan-out branch detection. Invalid conditions silently evaluate to False.
- **Fix**: Implement proper expression parser. Validate condition syntax at workflow load time, not execution time.

#### Potential Attack Vectors (how critics might respond)

1. "You built a workflow engine but only sequential pipe actually works"
2. "24 modules and 12 schemas for a single-user CLI — this is over-engineered"
3. "The CHANGELOG has two entries for a system with 271 tests — development process isn't practiced"
4. "No CI for a project that generates CI for others"

#### Preventive Measures

1. Mark DSL primitives with maturity levels; be honest about what works
2. Document the evolutionary roadmap that justifies the architecture investment
3. Maintain the CHANGELOG retroactively with actual development milestones
4. Add `.github/workflows/test.yml` to the project

#### Contingency Preparations

- If corpus path changes: environment variable override already exists (`ORGANVM_CORPUS_DIR`)
- If logs corrupt: doctor command can detect and rebuild
- If workflow state corrupts: session close is always safe (writes new session, not modifying old)

---

## Phase 4: Growth

### 4.1 Bloom (Emergent Insights)

#### Emergent Themes

1. **The system is a meta-tool**: It doesn't do work — it orchestrates work-doing. This is a genuinely distinct product category. Most workflow engines execute tasks; this one routes *attention* between tool clusters. That's closer to an IDE than an orchestrator.

2. **Phase discipline as competitive advantage**: FRAME→SHAPE→BUILD→PROVE with enforced role constraints is not common in AI tooling. Most AI coding assistants let you jump straight to BUILD. The enforced research-then-design-then-code sequence is genuinely valuable.

3. **The ontology is the real asset**: 578+ tools mapped with capabilities, protocols, and domains. This taxonomy would be valuable even without the conductor — as a reference database for AI tool selection.

4. **Health-aware routing could become adaptive**: Currently health metrics are injected manually. If session outcomes automatically fed back into cluster health scores, the system would self-optimize over time.

#### Expansion Opportunities

1. **Standalone ontology package**: Extract `ontology.yaml` + `router.py` as an independent pip package. Other projects could query "what tools can SEARCH?" without the full conductor.

2. **Multi-agent coordination**: The swarm objective generation in `compiler.py` hints at multi-agent usage. Flesh this out: Conductor assigns sub-goals to different Claude Code instances, collects results, advances workflow.

3. **Cross-project conductor**: Currently scoped to one project at a time. Extend sessions to span multiple repos within an organ. The registry already tracks cross-repo dependencies.

4. **Retrospective mining**: The observability data (`1.1MB+` of event logs) is untapped. Build a `conductor retro` command that identifies: which phases take longest, which clusters fail most, which routes are never used.

#### Novel Angles

1. **Conductor as teaching tool**: The phase-gated workflow could be packaged as a "structured AI pair programming" methodology for teams learning to work with AI assistants.

2. **Ontology as LLM prompt engineering**: The capability/protocol metadata could generate system prompts automatically — "You have access to these SEARCH tools via MCP protocol. Prefer Perplexity for web, Neon for database queries."

3. **Routing as cost optimization**: If tool costs are added to the ontology (API pricing, token counts), the router could find not just the shortest path but the cheapest path between capabilities.

#### Cross-Domain Connections

- **DevOps pipeline design**: The FRAME→SHAPE→BUILD→PROVE model maps naturally to RFC→Design→Implement→Release gates in enterprise engineering
- **Musical composition**: The orchestral metaphor isn't just decorative — the concept of "instruments" with distinct voices solving different parts of a problem is a genuine distributed systems insight
- **Knowledge management**: The ontology-as-queryable-database pattern connects to knowledge graph literature (semantic web, linked data)

---

### 4.2 Evolve (Implementation Plan)

#### Revision Summary

Based on all analysis phases, the following concrete improvements are recommended:

##### Tier 0 — Integrity (do first)

| # | Change | Files | Effort |
|---|--------|-------|--------|
| 1 | Add DSL primitive maturity levels (`stable`/`alpha`/`planned`) to `workflow-dsl.yaml` | workflow-dsl.yaml, executor.py | S |
| 2 | Add corpus offline fallback to governance.py | governance.py, constants.py | M |
| 3 | Expand `test_e2e_flow.py` from 2 to 15+ tests | tests/test_e2e_flow.py | M |
| 4 | Add log rotation to observability.py and handoff.py | observability.py, handoff.py | S |
| 5 | Validate workflow pointer in executor on every operation | executor.py | S |

##### Tier 1 — Credibility (do next)

| # | Change | Files | Effort |
|---|--------|-------|--------|
| 6 | Add CI workflow for the project itself | .github/workflows/test.yml | S |
| 7 | Backfill CHANGELOG with actual development milestones | CHANGELOG.md | S |
| 8 | Define WIP limit precedence chain | constants.py docstring | S |
| 9 | Add `conductor doctor --tools` to check tool availability | doctor.py, ontology.yaml | M |
| 10 | Create conftest.py with shared test fixtures | tests/conftest.py | S |

##### Tier 2 — Growth (do when ready)

| # | Change | Files | Effort |
|---|--------|-------|--------|
| 11 | Extract ontology + router as standalone pip package | new package | L |
| 12 | Implement `conductor retro` for session pattern mining | new module | M |
| 13 | Add cost/latency metadata to ontology clusters | ontology.yaml, router.py | M |
| 14 | Implement `conductor workflow resume --from <step>` | executor.py, cli.py | M |
| 15 | Add adaptive health feedback (session outcomes → cluster scores) | session.py, router.py | L |

**Effort key**: S = hours, M = half-day, L = days

---

## Summary

### Key Findings

| Dimension | Grade | Rationale |
|-----------|-------|-----------|
| **Architecture** | A- | Clean layering, good abstractions, but DSL implementation gap and module coupling reduce score |
| **Code Quality** | A | Consistent style, atomic writes, proper error hierarchy, type hints throughout |
| **Test Coverage** | B+ | 271 tests with good isolation, but E2E is skeletal and no concurrency/scale tests |
| **Documentation** | B | CLAUDE.md is excellent, but CHANGELOG is sparse and design rationale undocumented |
| **Resilience** | B | Graceful degradation in Patchbay, but unbounded logs, no crash recovery, corpus fragility |
| **Credibility** | B- | No CI, no benchmarks, no prior art references, no version pinning |
| **Growth Potential** | A | Ontology as standalone asset, adaptive routing, multi-agent coordination, teaching tool |

### The Strongest Version

This system's core strength is the **cluster-routing-phase trinity**: tools grouped into stable clusters, connected by health-aware routes, accessed through disciplined phases. Everything else — governance, observability, product extraction — supports this core.

The path to the strongest version is:
1. **Be honest about DSL maturity** (mark primitives, warn on alpha)
2. **Harden the foundation** (corpus fallback, log rotation, E2E tests)
3. **Practice what you preach** (CI, changelog, version pinning)
4. **Extract the unique asset** (ontology as standalone package)
5. **Close the adaptive loop** (session outcomes feeding routing health)

The system is at v0.5.0. It has the architecture of a v1.0 system but the operational discipline of a v0.3. Closing that gap is the primary growth opportunity.
