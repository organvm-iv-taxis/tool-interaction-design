# Phase 2: Activation Pipeline — Research → Implementation Tasks

**Date**: 2026-03-08
**Status**: ANALYSIS COMPLETE, implementation ready
**Source**: 11 research documents analyzed (5 gap docs + 6 new HIGH docs)

---

## Tier 1: Quick Wins (Small effort, immediate value)

These are template/config changes that can ship in a single session.

| # | Task | Source Doc | Files | Effort |
|---|------|-----------|-------|--------|
| Q1 | **Spec template overhaul**: Add RTM section, MoSCoW priorities, Assumptions vs Constraints split, Won't-have list, TBR format (not TBD), revision history table, SHALL/SHOULD/MAY convention header | tech-spec-best-practices, shipping-guide | `templates/spec.md` | Small |
| Q2 | **ADR template**: Create Architecture Decision Record template (context, decision, alternatives, consequences, status) and scaffold it in session start | tech-spec-best-practices | New: `templates/adr.md`, `conductor/session.py` | Small |
| Q3 | **Document status lifecycle**: Add YAML frontmatter with status field (Draft/Review/Approved/Superseded) to spec.md and plan.md templates | ai-interaction-doc-guide | `templates/spec.md`, `templates/plan.md` | Small |
| Q4 | **Per-tier staleness thresholds**: Replace flat `--days` with tier-based defaults (flagship=14d, standard=30d, stub=90d) | sdlc-deep-research | `conductor/governance.py`, `conductor/policy.py` | Small |
| Q5 | **Governance compliance rate KPI**: Compute % of repos meeting their tier's requirements, surface in patchbay | sdlc-deep-research | `conductor/governance.py` or `conductor/observability.py` | Small |
| Q6 | **CODEOWNERS generation**: Generate CODEOWNERS from seed.yaml ownership data during `enforce generate` | sdlc-framework | `conductor/governance.py` | Small |
| Q7 | **Agent assignment metadata**: Add `agent` field to WorkflowState steps for multi-agent delegation tracking | sdlc-framework | `conductor/executor.py`, `conductor/compiler.py` | Small |
| Q8 | **Appetite/time-box on sessions**: Add optional `appetite_minutes` parameter to session start with escalating warnings | shipping-guide | `conductor/session.py` | Small |
| Q9 | **MoSCoW priority on work items**: Add `priority` field (must/should/could/wont) to work queue items | tech-spec-best-practices | `conductor/work_item.py`, `conductor/workqueue.py` | Small |

---

## Tier 2: Medium Effort, High Value

Core system enhancements that strengthen the conductor's operational model.

| # | Task | Source Doc | Files | Effort |
|---|------|-----------|-------|--------|
| M1 | **Event-sourced session log**: Append `SessionEvent` records to `.conductor-session-events.jsonl` instead of overwriting state. Current `.conductor-session.json` becomes a computed projection. Full auditability and recoverability. | modern-prometheus | `conductor/session.py`, new schema | Medium |
| M2 | **Phase transition artifact gates**: Validate that each phase produced required artifacts before allowing transition (SHAPE→BUILD requires plan, BUILD→PROVE requires code changes). Soft gate initially (warn, don't block). | ai-tools-research, sdlc-deep-research | `conductor/session.py` | Medium |
| M3 | **Compound faceted search**: Enable `conductor search --capability SEARCH --domain RESEARCH --protocol MCP` compound queries across the 578-tool taxonomy. Intersection of filtered sets. | taxonomy-schema-classification | `router.py` | Medium |
| M4 | **Triple-serving output tracking**: Session close prompts for / tracks three output types: product (code/feature), portfolio (case study/screenshot), publication (blog draft/abstract). | shipping-guide | `conductor/session.py`, `conductor/retro.py` | Medium |
| M5 | **Impasse detection in Oracle**: Compare current phase duration against historical median. If 2x exceeded, emit impasse advisory with specific recommendations (narrow scope, transition, escalate). | modern-prometheus | `conductor/oracle.py` | Medium |
| M6 | **Token/cost tracking per session**: Add `tokens_consumed` and `estimated_cost_usd` fields. Update via MCP tool or CLI. Display in patchbay stats. Aligns with "effort measured in tokens, not hours." | multi-agent-critique | `conductor/session.py`, `mcp_server.py` | Medium |
| M7 | **Risk register**: Persistent risk register per session/organ with probability, impact, mitigation, owner, status. Schema-validated. | tech-spec-best-practices | New: `conductor/risk_register.py`, `schemas/v1/risk_register.schema.json` | Medium |
| M8 | **Session artifact export/archival**: Export a session's full context (scope, decisions, artifacts, prompts used) into a portable, provider-independent archive. | ai-interaction-doc-guide | New: `conductor/archive.py`, CLI: `conductor session export` | Medium |
| M9 | **GitHub rulesets generation**: Generate org-level Repository Ruleset JSON from governance-rules.json articles. Apply via `gh api` or output to `generated/`. | github-business-playbook | `conductor/governance.py`, new subcommand | Medium |
| M10 | **GitHub queue push**: `conductor queue push` creates GitHub Issues from top-N work items with labels from category/organ. Closes the governance→action loop. | github-business-playbook | New CLI subcommand, uses `gh issue create` | Medium |
| M11 | **Prove checklist**: Configurable verification assertions (tests_pass, lint_clean, no_regressions) checked before PROVE→DONE. Advisory initially. | multi-agent-critique | `conductor/session.py`, session config | Medium |
| M12 | **Circuit breaker warnings**: `max_phase_minutes` and `max_session_minutes` in config. Escalate warnings info→warning→critical via Oracle. | architectural-synthesis | `conductor/constants.py`, `conductor/session.py` | Medium |
| M13 | **Data classification gate**: Pre-session warning when sensitive data categories might be passed to consumer-tier AI endpoints. | ai-interaction-doc-guide | `conductor/session.py`, new: `conductor/data_classification.py` | Medium |
| M14 | **Tier-based CI template generation**: `enforce generate` produces differentiated CI configs per tier (flagship=full matrix, standard=lint+unit, stub=lint-only). | sdlc-deep-research | `conductor/governance.py`, `generated/` | Medium |
| M15 | **Cluster usage tracking**: Log `cluster_activation` events when sessions reference clusters. Aggregate into patchbay briefing for data-driven taxonomy evolution. | taxonomy-schema-classification | `conductor/observability.py`, `conductor/patchbay.py` | Medium |

---

## Tier 3: Large Effort, Strategic

These require sustained multi-session work and potentially new subsystems.

| # | Task | Source Doc | Files | Effort |
|---|------|-----------|-------|--------|
| L1 | **DORA metrics collection**: Compute Deployment Frequency, Lead Time, Change Failure Rate, MTTR from session/git data. | sdlc-deep-research | New: `conductor/dora.py` | Large |
| L2 | **Prompt version registry**: Track prompt templates with version, model compatibility, performance metrics. CI/CD evaluation pipeline. | ai-interaction-doc-guide | New: `conductor/prompt_registry.py`, `schemas/v1/prompt_template.schema.json` | Large |
| L3 | **Ontology tool typing normalization**: Standardize all 578 tool entries to consistent typing format. Known limitation already flagged. | taxonomy-schema-classification | `ontology.yaml` (major edit) | Large |
| L4 | **Literate programming export**: Weave session logs + code + commentary into a literate programming document. | sdlc-framework | `conductor/product.py` | Large |
| L5 | **Doctor MAS health checks**: Encode 9 failure modes from Modern Prometheus as diagnostic checks (role confusion, missing termination conditions, context loss). | modern-prometheus | `conductor/doctor.py` or new module | Large |

---

## Recommended Implementation Order

### Sprint 1: Templates + Config (Q1–Q9)
All quick wins. Ship the template overhaul and config improvements. No architectural changes.

### Sprint 2: Core Model Hardening (M1, M2, M5, M11, M12)
Event-sourced sessions, artifact gates, impasse detection, prove checklist, circuit breakers. These collectively transform the session lifecycle from a tracking tool into an enforcement tool.

### Sprint 3: Operational Intelligence (M3, M4, M6, M8, M15)
Faceted search, triple-serving, token tracking, session export, cluster usage. These make the conductor self-aware — it knows what tools it uses, what it costs, and what it produces.

### Sprint 4: Governance Loop (M9, M10, M7, M13, M14)
GitHub rulesets, queue push, risk register, data classification, tier-based CI. These close the loop between conductor governance and GitHub enforcement.

### Sprint 5+: Strategic (L1–L5)
DORA metrics, prompt registry, ontology normalization, literate export, MAS health checks. These are multi-session efforts that build on the foundation from Sprints 1–4.

---

## Cross-Reference: Research Document → Implementation Coverage

| Document | Tasks Extracted | Gap Category |
|----------|----------------|--------------|
| ai-interaction-documentation-guide | Q3, M8, M13, L2 | Prompt ops, archival, data classification |
| technical-spec-best-practices | Q1, Q2, Q9, M7 | Templates, risk register |
| ai-conductor-shipping-guide | Q8, M4 | Triple-serving, time-boxing |
| ai-conductor-sdlc-deep-research | Q4, Q5, M2, M11, M14, L1 | Enforcement, metrics, tier-based CI |
| ai-conductor-sdlc-framework | Q6, Q7, M9, L4 | GitHub sync, agent tracking |
| ai-tools-research-automation | M2 | Artifact gates |
| architectural-synthesis-multi-agent | M12 | Circuit breakers |
| github-business-playbook | M9, M10 | GitHub governance loop |
| multi-agent-architecture-critique | M6, M11 | Token tracking, prove checklist |
| taxonomy-schema-classification | M3, M15, L3 | Faceted search, usage tracking |
| modern-prometheus-protocol | M1, M5, L5 | Event sourcing, impasse detection |
