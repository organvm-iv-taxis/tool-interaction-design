# Full System Review: meta-organvm Eight-Organ System

**Date:** 2026-03-03
**Evaluated by:** tool-interaction-design framework (ontology + research digest + E2G report)
**Scope:** All 8 GitHub organizations, 135 repos, registry-v2.json, governance-rules.json, local workspace

---

## 1. CURRENT STATE SNAPSHOT

### GitHub Reality (Live)

| Org | Repos | Active | Archived | Public | Private | Pushed Mar '26 |
|-----|-------|--------|----------|--------|---------|----------------|
| organvm-i-theoria | 30 | 27 | 3 | 29 | 1 | 16 |
| organvm-ii-poiesis | 32 | 26 | 6 | 31 | 1 | 8 |
| organvm-iii-ergon | 31 | 31 | 0 | 23 | 8 | 11 |
| organvm-iv-taxis | 9 | 9 | 0 | 8 | 1 | 3 |
| organvm-v-logos | 8 | 8 | 0 | 7 | 1 | 4 |
| organvm-vi-koinonia | 8 | 8 | 0 | 7 | 1 | 1 |
| organvm-vii-kerygma | 8 | 8 | 0 | 6 | 2 | 1 |
| meta-organvm | 9 | 9 | 0 | 7 | 2 | 2 |
| **TOTAL** | **135** | **126** | **9** | **118** | **17** | **46** |

### Registry Reality (registry-v2.json)

| Metric | Value |
|--------|-------|
| Registry entries | 103 |
| GitHub repos | 135 |
| **Delta** | **32 repos unregistered** |
| Schema version | 0.5 |
| Sprints completed | 15 named sprints |

**By Tier:** 10 flagship, 73 standard, 9 infrastructure, 11 archive
**By Promotion Status:** 55 CANDIDATE, 29 PUBLIC_PROCESS, 6 LOCAL, 4 GRADUATED, 9 ARCHIVED
**By Implementation:** 93 ACTIVE, 9 ARCHIVED, 1 PRODUCTION

### Governance Artifacts (Local Filesystem)

| Artifact | Count | Coverage vs 135 repos |
|----------|-------|-----------------------|
| seed.yaml | 112 | 83% |
| CI workflows | 226 | 1.7 per repo avg |
| CODEOWNERS | 24 | 18% |
| CHANGELOG.md | 80 | 59% |
| ADR files | 195 | 1.4 per repo avg |
| spec.md | 41 | 30% |
| plan.md | 43 | 32% |
| status.md | 1 | <1% |
| CLAUDE.md (per-organ) | 8 | 100% of organs |
| Org-level rulesets | 0 | 0% |
| Branch protection | 0 org-level | 0% |

---

## 2. EVALUATION AGAINST RESEARCH CONSENSUS

### U1: Rhetorician/AI-Conductor Identity — PASS

The system embodies the conductor model. 8 organ CLAUDE.md files, governance-rules.json, promotion state machine, and the project_status field (15 named sprints) all demonstrate a deliberate orchestration approach. The AI-conductor identity is structurally embedded, not just declared.

### U2: Minimal Canonical Lifecycle — PARTIAL FAIL

**Finding:** The FRAME/SHAPE/BUILD/PROVE lifecycle is not adopted.
- 41 spec.md files exist (FRAME artifacts) — but scattered, no consistent template
- 43 plan.md files exist (SHAPE artifacts) — same
- **1 status.md file** across 135 repos — PROVE is essentially absent
- No `frame:`, `shape:`, `build:`, `prove:` commit prefixes observed
- No lifecycle-phase labels on Issues or PRs
- Branch naming uses `feature/` and `fix/` — not `feat/<organ>/<slug>` consistently

**Verdict:** The lifecycle exists in research documents but is not operationalized. The system runs on sprint-based batch operations (Bronze, Silver, Gold, Platinum, etc.) rather than a per-feature lifecycle loop.

### U3: WIP Limits — CRITICAL FAIL

**Finding:** 55 repos in CANDIDATE status. No WIP limits defined anywhere.
- Registry has no `wip_limit` field per organ
- governance-rules.json has no WIP section
- organ-audit.py does not check WIP limits
- ORGAN-II alone has 22 CANDIDATE repos — the research recommends max 3 CANDIDATE across the entire system
- Only 4 repos have reached GRADUATED (the promotion state machine's terminal success state)

**Verdict:** The promotion state machine exists but functions as a one-way ratchet. Repos get promoted to CANDIDATE in batch (48 repos promoted in PROPULSIO MAXIMA sprint) but almost none progress further. This is the textbook anti-pattern the research unanimously warns against.

### U4: AI Role Differentiation — PARTIAL PASS

CLAUDE.md files exist for all 8 organs with organ-specific instructions. The workspace CLAUDE.md defines navigation protocol and stack patterns. However:
- No `agents.yaml` per organ defining AI role assignments
- No formalized Architect/Implementer/Tester/Librarian role separation
- No per-phase model selection (the AI Orchestra Seating Chart is theoretical)

### U5: Process as Commodifiable Product — NOT STARTED

- No `organvm-process-kit` template repo
- No pattern language essays beyond the 10 meta-system essays in ORGAN-V
- No cohort course, no newsletter, no MkDocs playbook
- The tool-interaction-design project (E1 insight) represents the strongest version of this, but it's not yet positioned as a product

### U6: Automated Enforcement — CRITICAL FAIL

**Finding:** Zero org-level rulesets across all 8 organizations. Zero branch protection rules visible via API.
- CI workflows exist (226 total, ~1.7/repo) but are not required status checks
- No PR review requirements
- No squash-merge enforcement
- No branch name validation
- Governance-rules.json defines dependency rules and promotion rules, but no automation enforces them on GitHub
- CODEOWNERS exists in only 24/135 repos (18%)

**Verdict:** Discipline relies entirely on human willpower. This directly contradicts the #1 recurring theme across all 5 research documents: "encode discipline as automated checks."

### U7: Trunk-Based Development — PARTIAL PASS

- Default branch is `main` across all repos (metasystem-master exception documented)
- No squash-merge enforcement at org level
- No branch naming validation
- Conventional Commits adopted (`feat:`, `fix:`, `docs:`, etc.) per workspace CLAUDE.md

### U8: "Why" Documentation — PASS

- 195 ADR files across the system (Architecture Decision Records)
- 80 CHANGELOGs
- 41 spec.md files
- README depth is exceptional (~289K words across 72 documented repos + 8 profiles)
- `seed.yaml` contracts include description fields

### U9: Small Changes, Fast CI — CANNOT EVALUATE

- CI workflows exist but are not gated (no required status checks)
- No data on CI runtime duration
- No PR size checker workflows found
- Sprint model (batch deployments of 48+ repos) contradicts "one PR = one idea"

### U10: Organs as DDD Bounded Contexts — PASS

- governance-rules.json codifies unidirectional dependency flow (I→II→III)
- 20 allowed edges, 3 forbidden edges defined
- Restricted organs identified
- Each organ has distinct domain semantics
- `seed.yaml` declares produces/consumes edges

---

## 3. GAP ANALYSIS

### Registry Drift: 32 Phantom Repos

135 repos on GitHub vs 103 in registry. The 32 unregistered repos likely include:
- 9 `.github.io` landing page repos (one per org + personal, hosted in ORGAN-I)
- 8 `organvm-{X}--superproject` private repos (one per org)
- ~15 repos created since last registry sync (post-PROPULSIO MAXIMA sprint)

**Impact:** The registry-v2.json, declared as "single source of truth," is 24% out of date. organ-audit.py and validate-deps.py operate on stale data.

### Promotion Pipeline Bottleneck

```
LOCAL (6) → CANDIDATE (55) → PUBLIC_PROCESS (29) → GRADUATED (4) → ARCHIVED (9)
                ↑ BOTTLENECK
```

55 repos stuck at CANDIDATE. Only 4 have ever graduated. The promotion_rules in governance-rules.json define conditions for promotion (e.g., "at least 3 documented use cases" for commerce promotion) but nothing enforces or even tracks these conditions automatically.

### Missing Enforcement Stack

| What Research Recommends | Current State |
|--------------------------|---------------|
| Org-level rulesets | 0 across 8 orgs |
| Required status checks | None |
| Squash-merge enforcement | Not set |
| Branch name validation CI | Not found |
| PR review requirements | Not set |
| WIP limit checking in CI | Not implemented |
| PR size checker | Not found |
| Lifecycle-phase labels | Not created |
| Issue Forms | Not deployed to org `.github` repos |

### status.md — The Missing Artifact

The FRAME/SHAPE/BUILD/PROVE lifecycle produces 4 artifacts: spec.md, plan.md, code+tests, status.md.
- spec.md: 41 files (30% coverage)
- plan.md: 43 files (32% coverage)
- status.md: **1 file** (<1% coverage)

The PROVE phase is structurally absent. There is no systematic post-work reflection, no session breadcrumbing, no 5-sentence postmortems.

---

## 4. SHATTER POINTS (System-Level)

**SP-SYS-1 (CRITICAL): No enforcement = no governance.**
Governance-rules.json is a document, not a system. Nothing on GitHub prevents a back-edge dependency, a WIP limit violation, or a merge without CI passing. The 15 sprint names in project_status represent human discipline, not automated guardrails. One tired afternoon of bulk-merging could violate every rule simultaneously.

**SP-SYS-2 (HIGH): Registry drift compounds over time.**
32 unregistered repos today. Every new repo created without registry update widens the gap. The organ-audit.py script validates against a registry that doesn't reflect reality.

**SP-SYS-3 (HIGH): CANDIDATE graveyard.**
55 CANDIDATE repos with no path to GRADUATED except human memory. No automated nudge, no staleness check, no "this repo hasn't been touched in 30 days" alert. The batch-promotion model (48 repos in one sprint) guaranteed this bottleneck.

**SP-SYS-4 (MEDIUM): Landing page duplication.**
16 `.github.io` repos (9 centralized in ORGAN-I + 7 duplicates per-org). Maintenance burden scales linearly with organs. No shared template or build pipeline.

**SP-SYS-5 (MEDIUM): Creative organs are infrastructure-only.**
ORGAN-VI (Koinonia) and ORGAN-VII (Kerygma) each show 1 push in March 2026 (landing page only). Their repos exist structurally but have no active development. The system is architecturally complete but operationally concentrated in Organs I-III.

---

## 5. WHAT THE TOOL-INTERACTION-DESIGN FRAMEWORK REVEALS

### Tool Routes Not Being Used

The routing matrix defines 32 routes. Mapping against actual organvm system usage:

| Route | Status | Observation |
|-------|--------|-------------|
| `search_to_kg` (web_search → knowledge_graph) | **UNUSED** | No knowledge graph populated from research |
| `sentry_to_github` (monitoring → issues) | **UNUSED** | Sentry not connected to any organ |
| `figma_to_code` (design → implementation) | **UNUSED** | No Figma integration for any organ |
| `github_to_vercel` (code → deploy) | **USED** | ORGAN-V Jekyll site + landing pages |
| `editor_to_git` (code → commit) | **USED** | Primary development loop |
| `git_to_github` (local → remote) | **USED** | All 135 repos |
| `research_to_spec` (research → spec.md) | **PARTIAL** | 41 spec.md files but not via systematic pipeline |

### Lifecycle Phase → Tool Cluster Gaps

| Phase | Tool Clusters Available | Tool Clusters Used |
|-------|------------------------|--------------------|
| FRAME | sequential_thinking, web_search, academic_research, knowledge_graph, notion | web_search only (ad hoc) |
| SHAPE | sequential_thinking, code_analysis, diagramming | None systematically |
| BUILD | claude_code_core, code_execution, code_quality_cli, git_core | claude_code_core + git_core |
| PROVE | code_quality_cli, security_scanning, browser_playwright, github_platform | github_platform only (PRs without gates) |

### Missing Orchestration Workflows

The workflow DSL defines 7 example pipelines. None are executable, but mapping them against what organvm actually does:

- **feature-dev-pipeline**: The system uses sprint-based batch operations, not per-feature pipelines
- **sentry-bug-fix**: No monitoring → fix loop exists
- **research-ingest**: The tool-interaction-design project demonstrated this once; not adopted system-wide
- **session-ritual**: D4's 6-step session protocol is not implemented

---

## 6. RECOMMENDATIONS (Prioritized by Leverage)

### Tier 0 — Do Today (15 minutes, prevents compound damage)

1. **Add org-level rulesets to all 8 orgs** requiring: status checks to pass before merge, signed commits recommended, linear history (squash merge). This is 8 API calls.
2. **Sync registry-v2.json** — add the 32 missing repos with `promotion_status: LOCAL` and `tier: infrastructure` as defaults.

### Tier 1 — Do This Week (prevents CANDIDATE graveyard from growing)

3. **Add WIP limits to registry-v2.json** — max 3 CANDIDATE per organ, max 1 PUBLIC_PROCESS per organ. Implement checking in organ-audit.py.
4. **Triage the 55 CANDIDATE repos**: which are actually being worked on? Demote stale ones back to LOCAL or promote active ones to PUBLIC_PROCESS. Target: <15 total CANDIDATE.
5. **Create `status.md` template** and deploy to the 10 flagship repos as the minimum PROVE artifact.
6. **Enable required status checks** on the 10 flagship repos for CI workflows that already exist.

### Tier 2 — Do This Month (operationalizes the lifecycle)

7. **Create GitHub Issue Forms** in all 8 org `.github` repos with lifecycle-phase fields (Frame/Shape/Build/Prove).
8. **Create PR template** with governance gates checklist (references Issue, spec.md exists, tests pass, status.md updated).
9. **Extend organ-audit.py** to: check WIP limits, detect registry drift (compare GitHub API vs registry), flag CANDIDATE repos untouched for 30+ days.
10. **Deploy CODEOWNERS** to remaining 111 repos (currently only 24/135).
11. **Adopt branch naming**: `feat/<organ>/<slug>` enforced by CI check.

### Tier 3 — Do This Quarter (builds the product)

12. **Consolidate landing pages**: single template repo, one build pipeline, per-organ config files. Eliminate 16-repo maintenance burden.
13. **Build the process kit** as a template repo (`organvm-process-kit`): seed.yaml template, spec/plan/status.md templates, CI workflows, CLAUDE.md template, governance gates.
14. **Activate ORGAN-VI and VII** beyond infrastructure: pick one real project per organ and shepherd it through full FRAME→PROVE lifecycle.
15. **Connect Sentry** to at least ORGAN-III repos that have deployed services.

---

## 7. VERDICT

The meta-organvm system is **architecturally mature but operationally undisciplined** — exactly the condition the 5 research documents diagnosed.

**What works:**
- Eight-organ DDD bounded contexts with codified dependency rules
- Comprehensive documentation (~289K words)
- Promotion state machine with clear transitions
- seed.yaml contracts, CLAUDE.md per organ, CI workflows present
- Registry as single source of truth (when synced)

**What doesn't:**
- Zero automated enforcement of any governance rule on GitHub
- WIP limits nonexistent; 55 CANDIDATE repos stuck in limbo
- Lifecycle phases (Frame/Shape/Build/Prove) not operationalized
- Registry 24% out of sync with GitHub reality
- PROVE phase artifacts (status.md) absent
- Creative organs (VI, VII) structurally complete but dormant

**The system built the stage, wrote the score, and tuned the instruments — but hasn't started the concert.** The tool-interaction-design project provides the conductor's score. The organvm system provides the orchestra. What's missing is the downbeat: automated enforcement that makes governance a runtime constraint, not a planning aspiration.

The single highest-leverage action remains the same as identified in the E2G report: **encode discipline as CI checks, not documentation.** Every governance-rules.json predicate should be a GitHub Action. Every WIP limit should be a required status check. Every lifecycle phase should be a label that gates PR merge.
