# Convergence Architecture: The Conductor's Console

**Date:** 2026-03-04
**Input:** 4 documents cross-analyzed for convergence
**Output:** The architecture of the ONE system that serves GROW + COMMODIFY + EFFICIENCY simultaneously

---

## THE CONVERGENCE

All four documents point at the same thing from different angles. Here is what they agree on, stripped of principles and reduced to structure.

### What Each Document Contributes

| Document | Sees the problem as | Proposes |
|----------|---------------------|----------|
| Five-Doc Digest | 10 unanimous findings with no operational home | FRAME/SHAPE/BUILD/PROVE lifecycle + AI Orchestra + WIP limits |
| Tool Surface Integration | 578 tools sitting idle, 92% of routes unused | Lifecycle phases mapped to tool clusters + 3 executable workflows |
| System Review | 135 repos with zero enforcement, 55 stuck at CANDIDATE | Governance-as-runtime + registry sync + enforcement stack |
| E2G Report | A planning artifact that IS the product but doesn't know it (E1) | Ontology-as-MCP-server (E2) + DSL-to-Skill compiler (E4) |

### Where They Converge

Every document identifies the same structural gap: **the system has architecture without runtime**. Governance-rules.json is a document, not a process. The ontology catalogs tools but doesn't invoke them. The lifecycle exists in YAML but not in git history. The AI Orchestra has a seating chart but no downbeat.

The convergence is this: **build a single interactive system that is simultaneously the tool you use to work, the governance layer that enforces discipline, and the product you sell.**

---

## THE ARCHITECTURE

### Name: `conductor`

A CLI application (Python, single entry point) that wraps the existing `router.py` and extends it into a session-aware, governance-enforcing, lifecycle-tracking development console. It runs inside Claude Code sessions. It is also servable as an MCP server.

### Three Layers, One Binary

```
Layer 3: PRODUCT        ← What you sell (process kit, methodology, templates)
Layer 2: GOVERNANCE     ← What enforces discipline (WIP, lifecycle, registry)
Layer 1: SESSION ENGINE ← What you use every day (FRAME/SHAPE/BUILD/PROVE loop)
```

Each layer addresses one goal:
- Layer 1 = **GROW** (the session engine forces you through a learning loop every time you work)
- Layer 2 = **EFFICIENCY** (governance prevents the labyrinth; WIP limits stop sprawl; enforcement replaces willpower)
- Layer 3 = **COMMODIFY** (the system itself, its templates, its logs, its patterns become the sellable artifact)

### Layer 1: Session Engine (GROW)

**What it does:** Operationalizes the 6-step session ritual (D4) with the FRAME/SHAPE/BUILD/PROVE lifecycle (synthesized from all 5 docs) and the AI Orchestra role assignments (tool-surface-integration).

**Components:**

```
conductor session start --organ III --repo public-record-data-scrapper --scope "Add rate limiting"
```

1. **Session Init** (the "BEFORE" block, 10-15 min)
   - Reads `seed.yaml` from the target repo
   - Checks WIP limits against registry (Layer 2 call)
   - Checks promotion status (blocks work on ARCHIVED repos, warns on GRADUATED)
   - Creates a session log file: `.conductor/sessions/YYYY-MM-DD-HH-MM-{scope-slug}.yaml`
   - Sets the lifecycle phase to FRAME

2. **Phase Machine** (state machine, human advances with explicit commands)
   ```
   FRAME  →  SHAPE  →  BUILD  →  PROVE  →  DONE
     ↑         |                    |
     └─────────┘ (reshape)         └── (fail → back to BUILD)
   ```

   Each phase transition:
   - Records timestamp, duration, and what was produced
   - Activates the correct AI Orchestra section (tool cluster permissions)
   - Creates/updates the phase artifact (spec.md, plan.md, code, status.md)
   - Enforces constraints (e.g., BUILD cannot add dependencies not declared in SHAPE)

3. **Phase-Specific Tool Activation**

   | Phase | AI Role | Active Tool Clusters | Locked Out |
   |-------|---------|---------------------|------------|
   | FRAME | Librarian + Architect | sequential_thinking, web_search, academic_research, knowledge_graph, documentation | claude_code_core (write), code_execution |
   | SHAPE | Architect | sequential_thinking, code_analysis_mcp, diagramming | code_execution, security_scanning |
   | BUILD | Implementer | claude_code_core, code_execution, code_quality_cli, git_core | web_search, diagramming |
   | PROVE | Tester + Reviewer | code_quality_cli, security_scanning, browser_playwright, github_platform | claude_code_core (write) |

   "Locked Out" means the session engine warns (not hard-blocks) when you invoke a tool outside the current phase's cluster set. This is the **learning mechanism**: every warning teaches you why that tool belongs in a different phase. Over 50 sessions, you internalize the lifecycle without reading a single book about SDLC.

4. **Session Close** (the "AFTER" block, 10-15 min)
   ```
   conductor session close
   ```
   - Generates `status.md` entry (breadcrumb: what was done, what is next, where it sits in promotion)
   - Commits session log to `.conductor/sessions/`
   - Updates registry entry's `last_session` timestamp
   - If PROVE passed: offers to create PR with governance checklist
   - Records metrics: time-in-phase, tool-invocations-per-phase, phase-transition-count

**Why this is GROW:** You learn by doing, not by reading. The phase machine creates 4 micro-experiences per work session. The tool activation warnings are real-time feedback on "what tool belongs where." After 50 sessions you have 50 session logs that document your growth trajectory, and the metrics show your phase durations shortening as you gain judgment.

### Layer 2: Governance Runtime (EFFICIENCY)

**What it does:** Transforms governance-rules.json and registry-v2.json from documents into an enforced runtime. Addresses every CRITICAL FAIL from the system review.

**Components:**

1. **Registry Sync Daemon**
   ```
   conductor registry sync
   ```
   - Compares GitHub API (135 repos) against registry-v2.json (103 entries)
   - Auto-adds missing repos as `promotion_status: LOCAL, tier: infrastructure`
   - Flags repos on GitHub not in registry, repos in registry not on GitHub
   - Runs on `conductor session start` (so registry is never more than one session stale)

2. **WIP Limiter**
   ```
   conductor wip check
   conductor wip promote <repo> --to CANDIDATE
   ```
   - Reads WIP limits from `governance-rules.json` (new section: `wip_limits`)
   - Default: max 3 CANDIDATE per organ, max 1 PUBLIC_PROCESS per organ
   - `conductor session start` checks WIP before allowing work on a CANDIDATE repo
   - `conductor wip promote` gates promotion on WIP availability
   - Provides the triage view: "55 CANDIDATE repos, 4 GRADUATED. Here are the 10 untouched for 30+ days."

3. **Enforcement Generator**
   ```
   conductor enforce generate --org organvm-iii-ergon
   ```
   - Reads governance-rules.json predicates
   - Generates GitHub org-level rulesets via API (require status checks, squash merge, linear history)
   - Generates GitHub Actions workflows from governance rules:
     - `validate-wip.yml` - checks WIP limits before PR merge
     - `validate-lifecycle.yml` - checks that PR references Issue with lifecycle-phase label
     - `validate-deps.yml` - checks no back-edge dependencies (already exists, wraps it)
     - `validate-branch.yml` - checks branch naming: `feat/<organ>/<slug>`
   - Generates Issue Forms from lifecycle phases (FRAME/SHAPE/BUILD/PROVE templates)
   - Generates PR template with governance gates checklist

4. **Staleness Detector**
   ```
   conductor stale --days 30
   ```
   - Identifies CANDIDATE repos with no push in N days
   - Suggests demotion to LOCAL or promotion to PUBLIC_PROCESS
   - Generates a weekly digest (can feed into ORGAN-VII distribution)

**Why this is EFFICIENCY:** Every "remember to do X" becomes a runtime check. You stop getting lost in the labyrinth because the labyrinth has walls now. WIP limits prevent 55-CANDIDATE pileups. Registry sync prevents phantom repos. The enforcement generator turns your existing governance documents into actual GitHub constraints in one command. You stop spending cognitive cycles on "am I doing this right?" because the system tells you.

### Layer 3: Product Extractor (COMMODIFY)

**What it does:** Extracts sellable artifacts from Layers 1 and 2 as a natural byproduct of using them. Addresses U5 (process as product), E1 (this IS the product), and the commodification funnel.

**Components:**

1. **Template Extractor**
   ```
   conductor export process-kit --output ./organvm-process-kit/
   ```
   Exports from the running system:
   - `spec.md` template (from FRAME phase)
   - `plan.md` template (from SHAPE phase)
   - `status.md` template (from PROVE phase)
   - `seed.yaml` template
   - `CLAUDE.md` template (from AI Orchestra config)
   - CI workflow templates (from enforcement generator)
   - Issue Form templates (from lifecycle phases)
   - PR template (from governance gates)
   - `session-config.yaml` template (from session engine config)

   This is the free tier. Open source. The "organvm-process-kit" that every document recommends.

2. **Pattern Miner**
   ```
   conductor patterns --sessions 50 --output patterns/
   ```
   Analyzes session logs to extract:
   - Most common phase-transition sequences (what does your actual workflow look like?)
   - Average time-in-phase trends (are you getting faster at FRAME?)
   - Tool usage patterns (which clusters do you reach for most?)
   - Common failure modes (where do you loop back from PROVE to BUILD?)
   - Generates "Organvm Pattern" essay stubs for ORGAN-V publication

   This feeds the mid-tier: pattern language publication, cohort course material, newsletter content.

3. **Methodology Audit Report**
   ```
   conductor audit --org organvm-iii-ergon --output audit-report.md
   ```
   Generates a full methodology audit of an organ:
   - Registry health (sync status, WIP compliance, promotion pipeline flow)
   - Governance coverage (rulesets, CODEOWNERS, CI gates)
   - Lifecycle adoption (% repos with spec/plan/status, phase label usage)
   - Session metrics (if available)
   - Recommendations with priority tiers

   This is the consulting product. Run it for a client's GitHub org (with their registry). Price: $2K-$15K per the commodification funnel.

4. **MCP Server Mode**
   ```
   conductor serve --mcp
   ```
   Serves the ontology, routing matrix, and governance data as an MCP server. Claude Code (or any MCP client) can query it live:
   - `conductor.suggest_tools(capability="SEARCH", domain="RESEARCH")` → tool cluster recommendations
   - `conductor.check_wip(organ="III")` → WIP status
   - `conductor.session_status()` → current phase, active tool clusters, time elapsed
   - `conductor.route(from="web_search", to="knowledge_graph")` → data flow path

   This is E2 from the E2G report realized. The ontology becomes a living intelligence layer, not a reference document.

**Why this is COMMODIFY:** You don't write a product separately from working. The templates are extracted from the system you use. The patterns are mined from your session logs. The audit report runs against your live governance data. The MCP server makes the ontology queryable in real-time. Every work session produces both the work AND the methodology artifact. The process IS the product, structurally, not aspirationally.

---

## DATA MODEL

### Session Log (`.conductor/sessions/YYYY-MM-DD-HH-MM-{slug}.yaml`)

```yaml
session:
  id: "2026-03-04-14-30-rate-limiting"
  organ: "organvm-iii-ergon"
  repo: "public-record-data-scrapper"
  scope: "Add rate limiting to API endpoints"
  started: "2026-03-04T14:30:00Z"
  ended: "2026-03-04T16:15:00Z"

phases:
  - phase: FRAME
    started: "2026-03-04T14:30:00Z"
    ended: "2026-03-04T14:45:00Z"
    duration_minutes: 15
    artifact: "spec.md"
    tools_invoked: [web_search, sequential_thinking]
    notes: "Researched rate limiting patterns. Decided on token bucket."

  - phase: SHAPE
    started: "2026-03-04T14:45:00Z"
    ended: "2026-03-04T15:00:00Z"
    duration_minutes: 15
    artifact: "plan.md"
    tools_invoked: [sequential_thinking, code_analysis_mcp]
    notes: "4-step plan: middleware, config, tests, docs."

  - phase: BUILD
    started: "2026-03-04T15:00:00Z"
    ended: "2026-03-04T15:50:00Z"
    duration_minutes: 50
    artifact: "4 commits"
    tools_invoked: [claude_code_core, code_execution, git_core]
    commits: ["build: add rate limit middleware", "build: add config", "build: add tests", "build: update docs"]
    warnings: 1  # tried to use web_search during BUILD

  - phase: PROVE
    started: "2026-03-04T15:50:00Z"
    ended: "2026-03-04T16:10:00Z"
    duration_minutes: 20
    artifact: "status.md entry"
    tools_invoked: [code_quality_cli, security_scanning, github_platform]
    result: PASS
    pr_url: "https://github.com/organvm-iii-ergon/public-record-data-scrapper/pull/42"

metrics:
  total_minutes: 100
  phase_transitions: 4  # clean run, no loops back
  tool_invocations: 14
  warnings: 1
  commits: 4
  result: SHIPPED
```

### Governance Extension (`governance-rules.json` new sections)

```json
{
  "wip_limits": {
    "candidate_per_organ": 3,
    "public_process_per_organ": 1,
    "total_candidate_system": 15
  },
  "lifecycle_phases": ["FRAME", "SHAPE", "BUILD", "PROVE"],
  "enforcement": {
    "require_status_checks": true,
    "require_squash_merge": true,
    "require_linear_history": true,
    "require_branch_naming": "feat/<organ>/<slug>|fix/<organ>/<slug>",
    "require_issue_reference": true,
    "require_lifecycle_label": true
  },
  "staleness": {
    "candidate_warn_days": 30,
    "candidate_demote_days": 90
  }
}
```

---

## IMPLEMENTATION SEQUENCE

Not "what to do this week/month/quarter." What to build, in what order, so each piece enables the next.

### Build 1: Session Engine Core (enables GROW immediately)

**Files:** `conductor.py` (single file, extends router.py)
**Depends on:** `ontology.yaml`, `routing-matrix.yaml`, `governance-rules.json`, `registry-v2.json`
**Delivers:**
- `conductor session start/close`
- Phase state machine (FRAME/SHAPE/BUILD/PROVE)
- Session log generation
- Tool cluster activation warnings
- spec.md / plan.md / status.md template generation

**You can use this the same day you build it.** Every subsequent coding session runs through it. Growth starts accumulating from session 1.

### Build 2: Governance Runtime (enables EFFICIENCY immediately)

**Files:** Add to `conductor.py` or `governance.py` module
**Depends on:** Build 1 (session engine reads governance data)
**Delivers:**
- `conductor registry sync`
- `conductor wip check/promote`
- `conductor stale`
- `conductor enforce generate` (GitHub API calls for rulesets, Issue Forms, PR templates)

**The 55-CANDIDATE bottleneck gets triaged.** Registry drift gets fixed. Org-level rulesets get deployed. This is the "downbeat" the system review says is missing.

### Build 3: Product Extractor (enables COMMODIFY after ~20 sessions)

**Files:** `export.py` or extend `conductor.py`
**Depends on:** Build 1 (session logs exist), Build 2 (governance data is clean)
**Delivers:**
- `conductor export process-kit`
- `conductor patterns`
- `conductor audit`

**After 20 sessions, you have enough data to extract patterns.** The process kit is exportable from day 1 (it's just templates). The pattern mining needs session volume.

### Build 4: MCP Server (enables COMMODIFY as a service)

**Files:** `mcp_server.py`
**Depends on:** All previous builds
**Delivers:**
- `conductor serve --mcp`
- Live ontology queries from Claude Code sessions
- Real-time WIP/governance status
- Session-aware tool suggestions

**This is the E2 insight realized.** The ontology stops being a YAML file you read and becomes a service you query.

---

## HOW THIS ADDRESSES THE 92% TOOL DORMANCY

The system review found that most tool clusters are unused. The session engine activates them by phase:

- **FRAME activates:** sequential_thinking, web_search, academic_research, knowledge_graph, documentation, knowledge_apps (6 clusters currently dormant)
- **SHAPE activates:** code_analysis_mcp, diagramming, neon_database (3 clusters currently dormant)
- **BUILD activates:** code_execution, code_quality_cli, jupyter_notebooks (3 clusters currently dormant)
- **PROVE activates:** security_scanning, browser_playwright, sentry_monitoring, vercel_platform (4 clusters currently dormant)

That is 16 clusters activated by making them phase-specific. The AI Orchestra seating chart becomes not a diagram but the actual tool-loading logic of the session engine.

---

## HOW THIS ADDRESSES THE PROMOTION PIPELINE BOTTLENECK

```
Current:  LOCAL(6) → CANDIDATE(55) → PUBLIC_PROCESS(29) → GRADUATED(4)
                         ↑ STUCK

After conductor:
  LOCAL(6) → CANDIDATE(≤15) → PUBLIC_PROCESS(29+) → GRADUATED(4+)
                  ↑ WIP-gated          ↑ session-driven         ↑ auto-detected
```

- WIP limits cap CANDIDATE at 3 per organ (24 max system-wide, down from 55)
- Staleness detector demotes untouched CANDIDATE repos back to LOCAL
- Session engine creates the artifacts (spec, plan, status) that satisfy promotion criteria
- `conductor wip promote` enforces promotion rules from governance-rules.json

---

## HOW THIS ADDRESSES E1-E6 FROM THE E2G REPORT

| Insight | Resolution |
|---------|------------|
| E1: This project IS the process kit | The conductor CLI exports itself as the process kit (Layer 3) |
| E2: Ontology as MCP server | Build 4: `conductor serve --mcp` |
| E3: AI Orchestra maps to Agent tool | Session engine's phase-based tool activation is the implementation |
| E4: DSL compiles to Skills | Deferred — the session engine subsumes the need for a DSL executor by making the lifecycle the execution model |
| E5: Cross-analysis is a reusable pattern | The research-to-spec workflow in the DSL becomes a FRAME-phase recipe |
| E6: Lifecycle maps to git branch naming | Session engine creates branches as `frame/<slug>`, `shape/<slug>`, `build/<slug>`, `prove/<slug>` |

---

## WHAT THIS IS NOT

- Not a framework. It is one CLI with one entry point.
- Not a rewrite of the organvm system. It sits alongside, reads existing files, enforces existing rules.
- Not a multi-agent orchestration platform (that is premature). It is a single-user development console.
- Not theoretical. Build 1 is usable the day it is written. No prerequisites beyond the YAML files that already exist.

---

## THE SINGLE SENTENCE

**`conductor` is a session-aware CLI that forces the FRAME/SHAPE/BUILD/PROVE lifecycle on every work session, enforces WIP limits and governance rules as runtime constraints instead of documentation, and exports its own templates/patterns/audits as the sellable product — making GROW, EFFICIENCY, and COMMODIFY three views of the same running process.**
