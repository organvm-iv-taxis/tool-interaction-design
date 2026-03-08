---
date: 2026-03-08
action: cross-reference
---

# Cross-Reference: Research Audit Features (F-01–F-83) ↔ Phase 2 Activation Tasks (Q1–Q9, M1–M15, L1–L5)

## Summary

| Set | Count | Scope |
|-----|-------|-------|
| Research Audit features (F-01–F-83) | 83 | 4 repos (orchestration-start-here, agentic-titan, agent--claude-smith, petasum-super-petasum) |
| Phase 2 Activation tasks (Q1–Q9, M1–M15, L1–L5) | 29 | tool-interaction-design/conductor only |

The research audit (2026-03-06) covers the full ORGAN-IV ecosystem, while Phase 2 activation focuses specifically on the Conductor OS. Overlap is concentrated in governance, session lifecycle, and observability areas.

## Direct Overlaps (Same concept, both sets)

| Phase 2 Task | Audit Feature(s) | Notes |
|---|---|---|
| Q4 (per-tier staleness) | F-63 (automated archive policy) | Q4 implements tier thresholds; F-63 extends to archive automation |
| Q5 (governance compliance KPI) | F-29 (conductor's scorecard) | Q5 is one of F-29's 4 metrics |
| Q6 (CODEOWNERS generation) | F-16 (CODEOWNERS for organ-aware review) | Direct match |
| Q8 (appetite/time-box) | F-07 (fixed-time/variable-scope) | Q8 implements F-07's core concept in conductor |
| Q9 (MoSCoW priority) | F-07 (fixed-time/variable-scope) | Q9 adds the prioritization framework F-07 prescribes |
| M1 (event-sourced session log) | F-57 (agent run logging standard) | M1 is conductor-specific; F-57 is agent-wide. Complementary. |
| M2 (phase transition artifact gates) | F-01 (Frame/Shape/Build/Prove lifecycle) | M2 implements enforcement of what F-01 defines |
| M4 (triple-serving tracking) | F-52 (triple-serving project template) | M4 is conductor implementation; F-52 is template/repo-level |
| M5 (impasse detection) | F-32 (labyrinth frequency metric) | M5 detects impasses; F-32 tracks them as a KPI |
| M6 (token/cost tracking) | F-31 (cost and latency monitoring) | M6 is session-level; F-31 is agent-level. Both needed. |
| M7 (risk register) | — | Unique to Phase 2 (sourced from tech-spec-best-practices) |
| M9 (GitHub rulesets) | F-17 (org-wide repository rulesets) | M9 generates what F-17 deploys |
| M10 (GitHub queue push) | F-10 (governance-aware issue forms) | M10 pushes items; F-10 defines the forms they use |
| M11 (prove checklist) | F-12 (tier-based testing matrix) | M11 is session-level checks; F-12 defines per-tier requirements |
| M12 (circuit breaker warnings) | F-02 (6-step session protocol) | M12 enforces time bounds within F-02's session structure |
| M14 (tier-based CI generation) | F-14 (CI templates per stack) | M14 generates per-tier; F-14 generates per-stack. Complementary. |
| M15 (cluster usage tracking) | — | Unique to Phase 2 (conductor-specific taxonomy analytics) |
| L1 (DORA metrics) | F-30 (KPI dashboard panels) | L1 computes what F-30 displays |
| L2 (prompt version registry) | F-41 (prompt template library) | L2 adds versioning/CI to F-41's library |
| L5 (Doctor MAS health checks) | — | Unique to Phase 2 (sourced from Modern Prometheus) |

## Unique to Research Audit (no Phase 2 equivalent)

These 83-feature audit items have no corresponding Phase 2 activation task:

- **F-03–F-06, F-08**: WIP limits, SDLC-to-organ mapping, AI chairs, breadcrumb protocol, 30-day growth template
- **F-09, F-11, F-13, F-15**: Score/Rehearse/Perform, PR template, branching strategy, release checklist
- **F-18–F-28**: agentic-titan features (removable layers, retrieval memory, TDP, multi-agent frameworks, local inference)
- **F-33–F-35**: agent--claude-smith features (role-based prompting, multi-model review, one-repo scope)
- **F-36–F-48**: petasum safety protocol (4-layer model, data classification, writing vault, redaction, AI gateway)
- **F-49–F-59**: Skills pipeline, productization, community/education, Domus infrastructure
- **F-60–F-73**: Completeness remediation (three-prompt rule, decision matrices, archive policy, case law)
- **F-74–F-83**: Orphan audit (PTC bridge, config audit, pipe composition, safety constraints)

## Unique to Phase 2 (no audit equivalent)

| Task | Why unique |
|---|---|
| Q1 (spec template overhaul) | Template-level detail not in audit scope |
| Q2 (ADR template) | New artifact type for conductor |
| Q3 (document status lifecycle) | Frontmatter convention, not tracked in audit |
| Q7 (agent assignment metadata) | Workflow engine internals |
| M3 (compound faceted search) | Router/taxonomy feature |
| M8 (session artifact export) | Conductor archival system |
| M13 (data classification gate) | Pre-session safety gate |
| L3 (ontology tool typing normalization) | Taxonomy maintenance |
| L4 (literate programming export) | Product/export feature |

## Key Insight

The audit's 83 features span the full ORGAN-IV portfolio (4 repos), while Phase 2's 29 tasks are conductor-specific implementations. ~60% of Phase 2 tasks implement or refine concepts from the audit, but the audit's scope is much broader — covering safety, agent architecture, productization, and community/education dimensions that Phase 2 doesn't address. Both sets are needed: Phase 2 delivers the conductor engine, while the audit backlog delivers the ecosystem.
