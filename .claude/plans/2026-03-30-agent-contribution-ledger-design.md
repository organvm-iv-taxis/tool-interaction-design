# Agent Contribution Ledger & Prompt Refinement Engine — Design Spec

**Date:** 2026-03-30
**Author:** Claude (conductor) + user (architect)
**Status:** APPROVED — ready for implementation planning
**Repo:** `tool-interaction-design` (ORGAN-IV flagship)

## Problem

The dispatch layer (task_dispatcher.py, fleet_router.py, cross_verify.py) routes work to agents and verifies output, but operates statelessly. No structured record of what each agent produced, no cumulative performance profiles, no mechanism to evolve handoff prompts from observed failures. Evidence from field dispatches (2026-03-30):

- **Gemini** (4/10): Inflated metrics across 36 files in application-pipeline (full revert, 14 fix commits). Burned 100+ searches misreading "V1 IRF" as semver. Modified SEED directly without governed review.
- **OpenCode** (7/10): Fast mechanical execution but zero organism awareness. Interpreted "patch leak, fix universe" as a literal file search.
- **Codex** (9/10): Self-governing, spawned parallel sub-agents, caught real bugs others missed. Only weakness: child agents inherit parent's blindness gaps.

The recurring pattern: agent work returns damaged, Claude fixes it, but nothing prevents recurrence. GEMINI.md constraint docs exist but are hand-maintained and static.

## Solution: Six-Layer Contribution System

### Layer 1: Dispatch Receipt

Each dispatch gets an append-only structured record. Two halves: outbound (what was sent) and return (what came back).

```yaml
id: D-2026-0330-001
agent: gemini
model: gemini-3-flash-preview
repo: meta-organvm/post-flood
organ: META
work_type: corpus_cross_reference
cognitive_class: tactical

outbound:
  dispatched_at: "2026-03-30T15:00:00Z"
  prompt_hash: "sha256:..."
  envelope_path: ".conductor/envelopes/D-2026-0330-001.md"
  context_provided: [AGENTS.md, SEED.md]
  context_missing: ["IRF exact file path"]  # discovered post-hoc
  scope:
    files_expected: ["post-flood/SEED.md"]
    write_permission: propose_only
    work_description: "Cross-reference IRF against SEED"

return:
  completed_at: "2026-03-30T20:32:46Z"
  outcome: partial_fix  # clean | partial_fix | full_revert | abandoned
  rating: 4
  files_touched: ["post-flood/SEED.md"]
  files_unexpected: []
  violations:
    - type: governance_violation
      detail: "Modified SEED directly without §VII evolution law"
    - type: wasteful_search
      detail: "100+ text searches for semver strings"
  fix_commits: 1
  what_worked: "CHECKs 21-26 content was correct and coherent"
  what_failed: "Search strategy, write discipline"
  prompt_patches_generated: [PP-2026-0330-001, PP-2026-0330-002]
```

**Storage:** `.conductor/dispatch-ledger/D-{YYYY-MMDD}-{NNN}.yaml`

### Layer 2: Timecard (Punch-In / Punch-Out / Signature)

#### Punch-In (dispatch moment)

Records baseline state so the return can be diffed:

```yaml
punch_in:
  timestamp: "2026-03-30T15:00:00Z"
  dispatched_by: claude
  baseline:
    repo: meta-organvm/post-flood
    branch: main
    head_sha: "bdaa649"
    working_tree_clean: true
  briefing:
    envelope_sha: "sha256:e4a1b..."
    envelope_path: ".conductor/envelopes/D-2026-0330-001.md"
    work_type: corpus_cross_reference
    write_permission: propose_only
    context_manifest:
      - path: AGENTS.md
        sha: "sha256:7f2c..."
        bytes: 4200
      - path: SEED.md
        sha: "sha256:c91a..."
        bytes: 48200
    context_missing: []
    constraints_injected:
      - source: agent_profile
        rule: "Gemini: never modify SEED directly"
      - source: incident/D-2026-0327-003
        rule: "Never modify numeric metrics without CANONICAL check"
    scope_boundary:
      files_in_scope: ["post-flood/SEED.md", "post-flood/proposed-*.md"]
      files_forbidden: ["SEED.md (root)", "governance-rules.json"]
      actions_permitted: [read, propose, create_new_file]
      actions_forbidden: [git_commit, direct_edit_protected, package_install]
```

#### Punch-Out (return moment)

```yaml
punch_out:
  timestamp: "2026-03-30T20:32:46Z"
  reviewed_by: claude
  return_state:
    head_sha: "b3391d7"
    commits_by_agent: 1
    commits_to_fix: 1
  delivery:
    files_created:
      - path: post-flood/SEED.md
        lines_added: 39
        lines_removed: 1
        content_sha: "sha256:d8f3..."
    files_outside_scope: []
    tests_added: 0
    tests_broken: 0
  self_report:
    claimed_complete: true
    claimed_violations: 0
    self_audit_text: "CHECKs 21-26 added successfully"
  review:
    outcome: partial_fix
    rating: 4
    violations:
      - type: scope_violation
        rule_broken: "write_permission: propose_only"
        detail: "Edited SEED.md directly instead of creating proposed-checks.md"
        severity: warning
        remediation: "Claude synced 38 lines back to source of truth"
      - type: wasteful_execution
        detail: "100+ text searches for semver strings"
        tokens_wasted_estimate: 40000
    what_survived_review: ["CHECKs 21-26 content"]
    what_was_reverted: ["Direct SEED.md edit"]
    prompt_patches_earned: [PP-2026-0330-001, PP-2026-0330-002]
```

#### Signature (content-forensic attribution)

```yaml
signature:
  dispatch_id: D-2026-0330-001
  agent: gemini
  model: gemini-3-flash-preview
  envelope_hash: "sha256:e4a1b..."
  baseline_tree_hash: "sha256:a91c..."
  return_tree_hash: "sha256:f72d..."
  diff_hash: "sha256:3b8e..."
  commits_attributed:
    - sha: "b3391d7"
      attribution: gemini
    - sha: "79b7912"
      attribution: claude
      remediation_for: D-2026-0330-001
  co_author_line: "Co-Authored-By: Gemini 3 Flash Preview <noreply@google.com>"
```

### Layer 3: Energy Ledger (contribution balance sheet)

```yaml
energy:
  consumed:
    tokens_input: 55000
    tokens_output: 12000
    tokens_wasted: 40000
    preparation_cost_minutes: 15
    reviewer_tokens: 8000
    fix_commits: 1
    calendar_duration_minutes: 332

  produced:
    files_net_created: 0
    files_net_modified: 1
    lines_survived: 39
    lines_reverted: 0
    tests_added: 0
    bugs_caught: 0
    structural_additions:
      - "CHECKs 21-26 (6 health checks for SEED genome)"

  net:
    survival_rate: 1.0
    efficiency: 0.12
    remediation_ratio: 0.08
    waste_ratio: 0.57
    verdict: net_positive  # net_positive | net_neutral | net_negative
```

**Cumulative scorecard** per agent at `.conductor/scorecards/{agent}.yaml`:
- Total dispatches, avg rating, outcome distribution
- Per work-type performance (survival rate, common violations)
- Per repo performance
- Active prompt patches and their effectiveness

### Layer 4: Prompt Patch Engine (the refinement loop)

Each violation generates a constraint rule injected into future handoff envelopes.

```yaml
# .conductor/prompt-patches/PP-2026-0330-001.yaml
id: PP-2026-0330-001
created_from: D-2026-0330-001
rule: "Include exact filesystem path of any referenced document. Never use descriptions — Gemini interprets these as search queries."
applies_to:
  agents: [gemini]
  repos: ["*"]
  work_types: ["*"]
lifecycle:
  status: active  # draft | active | proven | retired
  times_injected: 0
  times_prevented: 0
  times_failed: 0
  effectiveness: null
  # Promoted to "proven" after 3+ preventions with 0 failures
  # "Retired" if agent model changes
```

GEMINI.md / AGENTS.md constraint docs become **generated outputs** — assembled from scorecard + patches + repo overlay at container build time.

### Layer 5: Assignment Container (the input transformer)

Self-contained package — everything the agent needs, nothing it needs to search for.

```
.conductor/containers/D-{id}/
├── ASSIGNMENT.md        # Structured prompt: role, objective, deliverable, verification, boundaries
├── CONSTRAINTS.md       # Generated: agent profile + prompt patches + repo overlay
├── DIRECTORY.md         # Exact paths — no searching required
├── KNOWN-ISSUES.md      # Incident-derived warnings from this agent's history
├── skills/              # Relevant SKILL.md files from a-i--skills
├── context/             # Pre-fetched files the agent will need
└── RECEIPT.yaml         # Punch-in record (baseline state, hashes)
```

#### ASSIGNMENT.md structure

Structured sections mapped to agent cognitive type:
- **Agent** — name, model
- **Role** — READER, WRITER, REFACTORER, AUDITOR (not free-form)
- **Objective** — one sentence, what to accomplish
- **Deliverable** — exact file(s) to produce, exact format
- **Verification** — steps the agent must run before declaring done
- **Boundaries** — READ/CREATE/MODIFY/COMMIT permissions, explicit

#### CONSTRAINTS.md generation

Three sources merged:
1. Agent profile (from scorecard — avg rating, survival rate, trust level)
2. Active prompt patches (filtered by agent + repo + work type)
3. Repo overlay (existing GEMINI.md / MACHINIST rules)

#### DIRECTORY.md

Eliminates search entirely. All referenced documents provided by exact path in `context/`. Key paths in the organism listed as reference-only. Naming conventions spelled out (IRF-{DOMAIN}-{NNN}, not semver).

#### KNOWN-ISSUES.md

Generated from:
- Agent's incident history in this specific repo
- Agent's incident history elsewhere (transferable failures)
- Common failure modes for this agent (from scorecard)

#### Skills injection

Work type → skills mapping in `work_types.yaml`:
- `mechanical_refactoring` → coding-standards-enforcer, verification-loop
- `content_generation` → creative-writing-craft, voice-enforcement
- `corpus_cross_reference` → document-audit-extraction, research-synthesis-workflow
- `testing` → testing-patterns, tdd-workflow
- `boilerplate_generation` → coding-standards-enforcer, backend-implementation-patterns

### Layer 6: Fleet Awareness & Plan-First Dispatch

#### Fleet Bulletin (cross-agent visibility)

Displayed at session start. Shows:
- Recent contributions from all agents (repo, deliverable, status, rating)
- Pending review items (what needs Claude's attention)
- Acknowledgments (notable contributions — bugs caught, structural additions)
- Active dispatches (in-flight containers)

#### Token Economy Dashboard

Part of the bulletin:
- Per-agent: dispatches, tokens in/out, waste ratio, fix commits, net verdict
- Budget remaining per service (estimated)
- Efficiency trend arrows (improving/flat/degrading)

#### Plan-First Dispatch Protocol

No ad-hoc dispatch. The conductor plans A→Z first:

```
PLAN (Claude maps full scope into segments)
  → ASSIGN (each segment gets an agent based on work type + scorecard)
  → BUILD STORES (containers pre-assembled for all segments)
  → VERIFY STORES (each container checked for completeness)
  → DISPATCH (release containers in dependency order)
  → COLLECT (punch-out receipts return)
  → REVIEW (Claude cross-verifies, closes energy ledger)
  → PATCH (violations → prompt patches for next cycle)
```

#### Plan structure

```yaml
plan_id: P-2026-0330-{slug}
segments:
  - id: S-001
    label: "description"
    work_type: architecture
    assigned_to: claude | codex | gemini | opencode | perplexity
    cognitive_class: strategic | tactical | mechanical
    depends_on: []
    container_id: D-...
    status: pending | dispatched | completed | failed
    outcome: clean | partial_fix | full_revert | abandoned
```

Segments with `depends_on` don't dispatch until dependencies complete. If a segment fails with `full_revert`, re-plan from that point — don't retry blindly.

#### Store manifest

Pre-built containers with completeness checks:
- assignment: ✓/✗
- constraints: ✓/✗ (N patches injected)
- directory: ✓/✗
- known_issues: ✓/✗ (N prior incidents cited)
- skills: ✓/✗
- context: ✓/✗ / ⏳ (blocked by dependency)
- estimated_tokens: NK
- blocked_by: S-NNN (if dependency not yet satisfied)

## Critical Files (implementation)

| File | Action | Purpose |
|------|--------|---------|
| `conductor/contribution_ledger.py` | CREATE | Dispatch receipt CRUD, YAML I/O |
| `conductor/timecard.py` | CREATE | Punch-in/out, signature generation, baseline diffing |
| `conductor/energy_ledger.py` | CREATE | Energy accounting, net verdict calculation |
| `conductor/scorecard.py` | CREATE | Cumulative agent profiles, per-type/repo breakdowns |
| `conductor/prompt_patches.py` | CREATE | Patch lifecycle, injection logic, effectiveness tracking |
| `conductor/container_builder.py` | CREATE | Container assembly, store pre-building, completeness checks |
| `conductor/fleet_bulletin.py` | CREATE | Session-start bulletin, token dashboard, acknowledgments |
| `conductor/plan_dispatch.py` | CREATE | A→Z planning, segment dependency resolution, store manifest |
| `conductor/work_types.yaml` | MODIFY | Add skills_mapping per work type |
| `conductor/fleet.yaml` | MODIFY | Add agent model identifiers for signature |
| `conductor/preflight.py` | MODIFY | Wire bulletin into session start |
| `mcp_server.py` | MODIFY | Add MCP tools for dispatch, review, bulletin |
| `schemas/v1/dispatch_receipt.schema.json` | CREATE | Receipt validation |
| `schemas/v1/timecard.schema.json` | CREATE | Timecard validation |
| `schemas/v1/container.schema.json` | CREATE | Container completeness validation |
| `tests/test_contribution_ledger.py` | CREATE | Receipt CRUD tests |
| `tests/test_timecard.py` | CREATE | Punch-in/out, signature tests |
| `tests/test_energy_ledger.py` | CREATE | Energy calculation tests |
| `tests/test_scorecard.py` | CREATE | Cumulative profile tests |
| `tests/test_prompt_patches.py` | CREATE | Patch lifecycle tests |
| `tests/test_container_builder.py` | CREATE | Container assembly tests |
| `tests/test_fleet_bulletin.py` | CREATE | Bulletin generation tests |
| `tests/test_plan_dispatch.py` | CREATE | Plan + dependency resolution tests |

## Data Flow

```
User intent
  → Claude plans A→Z (plan_dispatch.py)
  → Segments assigned by work_type + scorecard (scorecard.py + fleet_router.py)
  → Containers pre-built (container_builder.py)
    → ASSIGNMENT.md from work_type templates
    → CONSTRAINTS.md from scorecard + prompt_patches + repo overlay
    → DIRECTORY.md from repo structure + context manifest
    → KNOWN-ISSUES.md from scorecard incidents
    → skills/ from work_type → skills mapping
    → context/ pre-fetched from filesystem
  → Stores verified for completeness
  → Dispatched in dependency order
  → Punch-in recorded (timecard.py)
  → Agent works inside container
  → Agent returns
  → Punch-out recorded (timecard.py)
  → Claude cross-verifies (cross_verify.py)
  → Energy ledger computed (energy_ledger.py)
  → Receipt closed (contribution_ledger.py)
  → Violations → prompt patches (prompt_patches.py)
  → Scorecard updated (scorecard.py)
  → Fleet bulletin refreshed (fleet_bulletin.py)
  → Next dispatch from plan proceeds
```

## Hardening Amendments (three-persona review, 2026-03-30)

### Amendment 1: Return Queue (async inbox)

Claude sessions are not continuous. Dispatched agents return between sessions. Add a return queue:

```
.conductor/return-queue/
├── D-2026-0330-001.yaml    # Gemini returned, pending review
├── D-2026-0330-003.yaml    # OpenCode returned, pending review
```

Fleet bulletin at session start shows pending returns. Overdue reviews (>24h) block new dispatches. Claude processes the return queue before planning new work.

### Amendment 2: Observable vs Estimated Metrics

`tokens_wasted` is unobservable for external agents. Change to:
- `tokens_wasted_estimate` (optional) — derived from calendar duration × model throughput when anecdotal evidence exists
- `calendar_duration_minutes` remains the reliable proxy for cost
- Agent self-reported metrics carry a `trust_level` flag (from scorecard)

### Amendment 3: Container Transport Modes

The container is a logical package. Physical delivery varies by agent:

| Agent | Transport | How |
|-------|-----------|-----|
| Codex | directory | Container directory placed in repo, Codex reads ASSIGNMENT.md as initial prompt |
| Gemini | GEMINI.md regen | CONSTRAINTS.md + ASSIGNMENT.md compiled into repo's `.github/GEMINI.md`, context/ files placed alongside |
| OpenCode | prompt paste | ASSIGNMENT.md content pasted as initial prompt, context/ files referenced by path |
| Perplexity | query | Assignment distilled to a research query with scope constraints |

### Amendment 4: Patch Model-Version Binding

Patches bind to the model version they were tested against:

```yaml
model_version_tested: gemini-3-flash-preview
auto_demote_on_model_change: true  # reverts to "unverified" if model updates
```

Incidents in KNOWN-ISSUES.md carry `model_version` and display `[unverified on current model]` when stale.

### Amendment 5: Dispatch Confidence & Circuit Breaker

Each agent+work_type pair has a `dispatch_confidence` score (0.0-1.0) derived from recent survival rate:

- Below 0.3: container builder **refuses** to build — agent is blocked for this work type
- Below 0.5: agent excluded from strategic work routing
- Above 0.7: agent eligible for autonomous dispatch (reduced cross-verification)

After 3 consecutive failures from the same agent on the same plan, stop dispatching to that agent for this plan. Escalate to conductor for re-routing.

### Amendment 6: Scorecard Statistical Thresholds

`min_dispatches_for_repo_routing: 3` — repo-level stats below this threshold are informational only, not used for routing decisions. Prevents over-fitting to single-dispatch noise.

### Amendment 7: Container Permeability Types

```yaml
container_type: READER | WRITER | REFACTORER | AUDITOR

# Determines mandatory fields:
# READER:     context/ mandatory (large), write_permission: propose_only
# WRITER:     CONSTRAINTS.md mandatory (large), context/ minimal
# REFACTORER: KNOWN-ISSUES.md mandatory, scope_boundary strict
# AUDITOR:    context/ mandatory, actions_permitted: [read] only
```

### Amendment 8: Scorecard as Router Input

Add `historical_survival_weight: 0.15` to fleet_router.py scoring. The scorecard's survival rate for this agent+work_type combination becomes a routing factor alongside phase affinity and tag matching. The scorecard is not just a report — it's a closed-loop routing input.

### Amendment 9: Review Queue Priority

Bulletin marks overdue reviews with escalating urgency:
- `< 12h`: normal priority
- `12-24h`: elevated — shown first in bulletin
- `> 24h`: **blocks new dispatches** — must clear review queue before planning

### Amendment 10: Git Attribution

Agent commits must carry trailers:
```
Dispatched-By: conductor/D-2026-0330-001
Agent: gemini (gemini-3-flash-preview)
Co-Authored-By: Gemini 3 Flash Preview <noreply@google.com>
```

These trailers are specified in the ASSIGNMENT.md and enforced during cross-verification.

### Amendment 11: Amplification Patches (positive learning)

Complement to prompt patches (corrections). Amplifications record proven techniques:

```yaml
id: AMP-2026-0330-001
created_from: D-2026-0330-004
technique: "Codex spawns named sub-agents (Nietzsche, Herschel, Pauli) for multi-repo parallel work"
applies_to:
  agents: [codex]
  work_types: [multi_repo_parallel]
injection_mode: suggestion  # not constraint — "consider using this technique"
```

### Amendment 12: Patch Effectiveness → Recurrence Rate

Replace causal `effectiveness` metric with binary `recurrence_rate`:
- After patch introduction, did this violation type recur for this agent? (yes/no per dispatch)
- `recurrence_rate = recurrences / dispatches_since_patch`
- Simpler, no causal inference claims, directly observable

### Amendment 13: Context Staleness

Container records `context_fetched_at` per file. Volatile files (IRF, registry, SEED) have a staleness threshold of 1 hour. At dispatch time, if context age exceeds threshold, container builder refreshes or warns.

```yaml
context_manifest:
  - path: IRF.md
    sha: "sha256:..."
    fetched_at: "2026-03-30T14:55:00Z"
    volatile: true
    staleness_threshold_minutes: 60
```

## Implementation Waves

**Wave 1: RECORD** (standalone value, zero external dependencies)
- `conductor/contribution_ledger.py` — dispatch receipt CRUD, YAML I/O
- `conductor/timecard.py` — punch-in/out, signature generation, baseline diffing
- `conductor/energy_ledger.py` — energy accounting, net verdict calculation
- `.conductor/return-queue/` — async return inbox
- `schemas/v1/dispatch_receipt.schema.json`
- `schemas/v1/timecard.schema.json`
- `tests/test_contribution_ledger.py`
- `tests/test_timecard.py`
- `tests/test_energy_ledger.py`

**Wave 2: LEARN** (requires Wave 1 data to exist)
- `conductor/scorecard.py` — cumulative profiles, dispatch confidence
- `conductor/prompt_patches.py` — patch + amplification lifecycle, recurrence tracking
- Wire scorecard survival rate into `conductor/fleet_router.py` as routing weight
- Dispatch confidence gating in `conductor/task_dispatcher.py`
- Model-version binding and auto-demotion
- `tests/test_scorecard.py`
- `tests/test_prompt_patches.py`

**Wave 3: ANTICIPATE** (requires Wave 2 intelligence)
- `conductor/container_builder.py` — assembly with transport modes, permeability types, context staleness, skills injection
- `conductor/fleet_bulletin.py` — cross-agent awareness, review queue priority, token dashboard
- `conductor/plan_dispatch.py` — A→Z planning, segment dependency resolution, store manifest
- GEMINI.md / AGENTS.md generation from scorecard + patches
- `mcp_server.py` — new MCP tools for dispatch, review, bulletin
- `tests/test_container_builder.py`
- `tests/test_fleet_bulletin.py`
- `tests/test_plan_dispatch.py`

## Verification

### Wave 1 Verification
1. Receipt CRUD: create, read, update return, close — round-trip YAML
2. Punch-in/out: baseline SHA captured, return diff computed, signature hashes match
3. Energy ledger: simulate application-pipeline 36-file revert → `net_negative` verdict
4. Return queue: 3 receipts queued, sorted by age, oldest first
5. Existing tests: `python3 -m pytest tests/ -v` — all pass unchanged

### Wave 2 Verification
6. Scorecard: 5 receipts → cumulative profile with per-type and per-repo breakdowns
7. Dispatch confidence: agent at 0.2 survival rate → container build refused
8. Prompt patch lifecycle: create → inject 3x → recurrence_rate 0.0 → status `proven`
9. Amplification: Codex sub-agent pattern suggested in envelope for multi-repo work
10. Model version: patch auto-demoted to `unverified` when model changes
11. Router integration: agent with 0.9 survival rate scores higher than agent with 0.4

### Wave 3 Verification
12. Container build: Gemini on post-flood → CONSTRAINTS.md includes all active patches
13. Container transport: GEMINI.md regenerated from container for Gemini transport mode
14. Context staleness: volatile file older than 1h → warning emitted
15. Plan dispatch: 5-segment plan with dependencies → dispatch order respects DAG
16. Store completeness: missing context (blocked dep) → `⏳` status
17. Fleet bulletin: generated from 4 receipts, shows all agents, marks overdue reviews
18. Review priority: receipt >24h old → blocks new dispatch creation
19. Full doctor: `python3 -m conductor doctor --strict` passes with all new modules loaded
