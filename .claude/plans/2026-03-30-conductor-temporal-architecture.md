# Conductor Temporal Architecture — The Click Track

**Date:** 2026-03-30
**Status:** SIDEBAR — informs contribution ledger design, governs all future dispatch planning
**Depends on:** `2026-03-30-agent-contribution-ledger-design.md`

## The Premise

Every action in the conductor is a beat on a clock. Plans are designed from owner (archetype) at the start to returning to source with expectations required and logged at the end. The click track is the BPM — the eternal propelling clock that all collision points exist upon.

## Complete Action Inventory

### Atomic Actions (smallest units of force)

Audit of every function that exerts side effects — writes files, calls subprocess, modifies state. Excludes pure data models and read-only queries.

#### Session Lifecycle (7 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| S1 | `SessionEngine.start()` | session.py:230 | CONDUCTOR | Creates session dir, writes session-log.yaml, writes state JSON, logs event | ALIVE |
| S2 | `SessionEngine.transition()` | session.py:230 | CONDUCTOR | Updates session state, logs phase transition, records duration | ALIVE |
| S3 | `SessionEngine.close()` | session.py:230 | CONDUCTOR | Writes final session log, updates stats, removes active state | ALIVE |
| S4 | `_update_stats()` | session.py:122 | CONDUCTOR | Reads/writes stats JSON, increments counters | ALIVE |
| S5 | `_append_session_event()` | session.py:189 | CONDUCTOR | Appends to session-events.jsonl | ALIVE |
| S6 | `_check_data_sensitivity()` | session.py:217 | CONDUCTOR | Pure check, warns on sensitive scope | ALIVE |
| S7 | `export_session()` | archive.py:14 | CONDUCTOR | Copies session dir to exports/ | ALIVE |

#### Preflight (8 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| P1 | `run_preflight()` | preflight.py:267 | CONDUCTOR | Reads all state, composes briefing, optionally starts session | ALIVE |
| P2 | `_collect_active_sessions()` | preflight.py:95 | CONDUCTOR | Reads active-sessions dir | ALIVE |
| P3 | `_collect_claims()` | preflight.py:110 | CONDUCTOR | Reads .conductor-session.json across workspace | ALIVE |
| P4 | `_detect_collisions()` | preflight.py:152 | CONDUCTOR | Detects multiple agents on same repo | ALIVE |
| P5 | `_build_work_items()` | preflight.py:169 | CONDUCTOR | Reads work registry, ranks items | ALIVE |
| P6 | `_get_oracle_advisory()` | preflight.py:191 | CONDUCTOR | Consults oracle for advisories | ALIVE |
| P7 | `_get_fleet_recommendation()` | preflight.py:205 | CONDUCTOR | Calls fleet router for agent ranking | ALIVE |
| P8 | `_check_pending_verification()` | preflight.py:251 | CONDUCTOR | Checks for active handoff needing review | ALIVE |

#### Fleet Dispatch (11 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| F1 | `FleetRouter.recommend()` | fleet_router.py:67 | CONDUCTOR | Scores and ranks agents | ALIVE |
| F2 | `TaskDispatcher.classify()` | task_dispatcher.py:59 | CONDUCTOR | Classifies work description → work type | ALIVE |
| F3 | `TaskDispatcher.plan()` | task_dispatcher.py:92 | CONDUCTOR | Creates DispatchPlan with ranked agents | ALIVE |
| F4 | `generate_handoff()` | fleet_handoff.py:125 | CONDUCTOR | Creates HandoffBrief from session state | ALIVE |
| F5 | `generate_guardrailed_handoff()` | fleet_handoff.py:151 | CONDUCTOR | Creates GuardrailedHandoffBrief with constraints | ALIVE |
| F6 | `format_markdown()` | fleet_handoff.py:200 | WRITER | Renders brief as markdown | ALIVE |
| F7 | `write_handoff()` | fleet_handoff.py:297 | WRITER | Writes handoff.md to repo | ALIVE |
| F8 | `log_handoff()` | fleet_handoff.py:308 | WRITER | Appends to handoff-log.jsonl | ALIVE |
| F9 | `write_active_handoff()` | fleet_handoff.py:318 | WRITER | Writes .conductor/active-handoff.json | ALIVE |
| F10 | `clear_active_handoff()` | fleet_handoff.py:331 | CONDUCTOR | Removes active-handoff.json on verify | ALIVE |
| F11 | `FleetUsageTracker.record()` | fleet_usage.py:55 | WRITER | Appends usage record to JSONL | ALIVE |

#### Cross-Verification (2 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| V1 | `CrossVerifier.verify()` | cross_verify.py:69 | AUDITOR | Checks files against constraints, returns report | ALIVE |
| V2 | `clear_active_handoff()` | fleet_handoff.py:331 | CONDUCTOR | Clears handoff on pass | ALIVE |

#### Governance (5 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| G1 | `GovernanceRuntime.promote()` | governance.py:158 | CONDUCTOR | Changes repo promotion state | ALIVE |
| G2 | `GovernanceRuntime.auto_promote()` | governance.py:158 | CONDUCTOR | Batch-promotes eligible repos | ALIVE |
| G3 | `GovernanceRuntime.audit()` | governance.py:158 | AUDITOR | Returns health report per organ | ALIVE |
| G4 | `GovernanceRuntime.stale()` | governance.py:158 | AUDITOR | Finds repos stale >N days | ALIVE |
| G5 | `GovernanceRuntime.wip_check()` | governance.py:158 | AUDITOR | Returns WIP limit status | ALIVE |

#### Oracle & Guardian (14 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| O1 | `Oracle.consult()` | oracle.py:189 | READER | Runs detectors, returns advisories | ALIVE |
| O2 | `Oracle.gate()` | oracle.py:189 | CONDUCTOR | Checks gate conditions before transition | ALIVE |
| O3 | `Oracle.wisdom()` | oracle.py:189 | READER | Returns accumulated wisdom entries | ALIVE |
| O4 | `Oracle.calibrate()` | oracle.py:189 | CONDUCTOR | Adjusts detector sensitivity | ALIVE |
| O5 | `Oracle.diagnose()` | oracle.py:189 | AUDITOR | Deep diagnostic of oracle state | ALIVE |
| O6 | `Oracle.export()` | oracle.py:189 | WRITER | Exports oracle state to file | ALIVE |
| O7 | `GuardianAngel.counsel()` | guardian.py:19 | READER | Contextual guidance from wisdom corpus | ALIVE |
| O8 | `GuardianAngel.whisper()` | guardian.py:19 | READER | Pre-action warning for risky operations | ALIVE |
| O9 | `GuardianAngel.teach()` | guardian.py:19 | READER | Deep-dive on a topic | ALIVE |
| O10 | `GuardianAngel.landscape()` | guardian.py:19 | READER | Decision landscape analysis | ALIVE |
| O11 | `GuardianAngel.mastery()` | guardian.py:19 | READER | Mastery assessment | ALIVE |
| O12 | `mark_internalized()` | wisdom | CONDUCTOR | Marks a wisdom entry as absorbed | ALIVE |
| O13 | `guardian_corpus()` | wisdom | READER | Searches wisdom corpus | ALIVE |
| O14 | `OracleProfile.detect_*()` | profiler.py | AUDITOR | Session cadence, burnout, collaboration patterns | ALIVE |

#### Workflow Execution (5 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| W1 | `WorkflowExecutor.start()` | executor.py:94 | CONDUCTOR | Initializes workflow state | ALIVE |
| W2 | `WorkflowExecutor.step()` | executor.py:94 | CONDUCTOR | Executes one workflow step, updates state | ALIVE |
| W3 | `WorkflowExecutor.status()` | executor.py:94 | READER | Returns current workflow state | ALIVE |
| W4 | `WorkflowCompiler.compile()` | compiler.py:20 | CONDUCTOR | JIT-compiles routing path into workflow score | ALIVE |
| W5 | `simulate_route_handoff()` | handoff.py:126 | CONDUCTOR | Simulates a route with health injection | ALIVE |

#### Observability & Feedback (8 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| B1 | `log_event()` | observability.py:174 | WRITER | Appends to events.jsonl, updates metrics | ALIVE |
| B2 | `compute_trend_report()` | observability.py:64 | AUDITOR | Analyzes event trends | ALIVE |
| B3 | `export_metrics_report()` | observability.py:116 | WRITER | Writes metrics report JSON | ALIVE |
| B4 | `rotate_log()` | observability.py:137 | WRITER | Rotates events.jsonl when too large | ALIVE |
| B5 | `record_pattern()` | product.py:27 | WRITER | Appends to pattern-history.jsonl | ALIVE |
| B6 | `record_step_outcome()` | feedback.py:43 | WRITER | Records step pass/fail to health cache | ALIVE |
| B7 | `inject_into_routing_engine()` | feedback.py:84 | CONDUCTOR | Injects health scores into route weights | ALIVE |
| B8 | `compute_dora()` | dora.py:104 | AUDITOR | Computes DORA metrics from session logs | ALIVE |

#### Sprint Retrospective (3 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| R1 | `build_ledger()` | sprint_ledger.py:466 | AUDITOR | Assembles session retrospective from logs + JSONL | ALIVE |
| R2 | `render_ledger_markdown()` | sprint_ledger.py:553 | WRITER | Renders retrospective as markdown | ALIVE |
| R3 | `alchemize_ledger()` | sprint_ledger.py:681 | CONDUCTOR | Feeds patterns back into oracle + observability | ALIVE |

#### Retrospective Analysis (5 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| A1 | `run_retro()` | retro.py:202 | AUDITOR | Multi-session analysis with phase/tool/outcome breakdown | ALIVE |
| A2 | `_analyze_phase_balance()` | retro.py:47 | AUDITOR | Phase time distribution analysis | ALIVE |
| A3 | `_analyze_tool_usage()` | retro.py:70 | AUDITOR | Tool frequency analysis | ALIVE |
| A4 | `_analyze_outcomes()` | retro.py:86 | AUDITOR | Outcome distribution analysis | ALIVE |
| A5 | `_derive_insights()` | retro.py:126 | AUDITOR | Synthesizes insights from analyses | ALIVE |

#### Infrastructure (12 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| I1 | `run_doctor()` | doctor.py:412 | AUDITOR | Integrity checks on all YAML + schemas | ALIVE |
| I2 | `run_integrity_checks()` | integrity.py:46 | AUDITOR | Cross-file consistency checks | ALIVE |
| I3 | `WiringEngine.inject_hooks()` | wiring.py:22 | CONDUCTOR | Writes hook scripts to workspace | ALIVE |
| I4 | `WiringEngine.configure_mcp()` | wiring.py:22 | CONDUCTOR | Updates MCP server config | ALIVE |
| I5 | `RegistryGraph.to_mermaid()` | graph.py:10 | WRITER | Generates Mermaid graph from registry | ALIVE |
| I6 | `RiskRegistry.add()` | risk_register.py:46 | WRITER | Adds risk to registry | ALIVE |
| I7 | `RiskRegistry.update()` | risk_register.py:46 | WRITER | Updates risk status/severity | ALIVE |
| I8 | `WorkQueue.push()` | workqueue.py:29 | WRITER | Adds work item to queue | ALIVE |
| I9 | `WorkQueue.pop()` | workqueue.py:29 | CONDUCTOR | Claims and returns next work item | ALIVE |
| I10 | `PromptRegistry.register()` | prompt_registry.py:73 | WRITER | Registers a prompt template | ALIVE |
| I11 | `PromptRegistry.evolve()` | prompt_registry.py:73 | CONDUCTOR | Version-bumps a prompt | ALIVE |
| I12 | `ProductExtractor.export_*()` | product.py:91 | WRITER | Exports process kits, Gemini extensions, dashboards | ALIVE |

#### Standalone Router (8 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| T1 | `cmd_route()` | router.py:801 | READER | Find path between clusters | ALIVE |
| T2 | `cmd_capability()` | router.py:847 | READER | Find clusters by capability | ALIVE |
| T3 | `cmd_path()` | router.py:876 | READER | BFS shortest path | ALIVE |
| T4 | `cmd_validate()` | router.py:895 | AUDITOR | Validate workflow DSL | ALIVE |
| T5 | `cmd_alternatives()` | router.py:943 | READER | Find alternative clusters | ALIVE |
| T6 | `cmd_clusters()` | router.py:971 | READER | List all clusters | ALIVE |
| T7 | `cmd_domains()` | router.py:980 | READER | List all domains | ALIVE |
| T8 | `cmd_search()` | router.py:990 | READER | Search tools by name | ALIVE |

#### External Tools (5 actions)

| # | Action | Module | Archetype | Side Effects | Status |
|---|--------|--------|-----------|-------------|--------|
| X1 | `release.py` | tools/ | CONDUCTOR | Release management | ALIVE |
| X2 | `release_guardrails.py` | tools/ | AUDITOR | Pre-release checks | ALIVE |
| X3 | `run_quality_gate.sh` | tools/ | AUDITOR | Quality gate runner | ALIVE |
| X4 | `validate_process_assets.py` | tools/ | AUDITOR | Process asset validation | ALIVE |
| X5 | `validate_schemas.py` | tools/ | AUDITOR | JSON schema validation | ALIVE |

#### MCP Tools (34 tools)

| # | Tool | Maps To | Archetype | Status |
|---|------|---------|-----------|--------|
| M1 | `conductor_route_to` | T1 | READER | ALIVE |
| M2 | `conductor_capability` | T2 | READER | ALIVE |
| M3 | `conductor_wip_status` | G5 | AUDITOR | ALIVE |
| M4 | `conductor_session_phase` | S2 | CONDUCTOR | ALIVE |
| M5 | `conductor_orchestra_briefing` | patchbay | READER | ALIVE |
| M6 | `conductor_suggest` | router | READER | ALIVE |
| M7 | `conductor_patch` | patchbay | READER | ALIVE |
| M8 | `conductor_edge_health` | handoff | AUDITOR | ALIVE |
| M9 | `conductor_trace_get` | handoff | READER | ALIVE |
| M10 | `conductor_handoff_validate` | handoff | AUDITOR | ALIVE |
| M11 | `conductor_compose_mission` | compiler | CONDUCTOR | ALIVE |
| M12 | `conductor_oracle` | O1 | READER | ALIVE |
| M13 | `conductor_oracle_gate` | O2 | CONDUCTOR | ALIVE |
| M14 | `conductor_oracle_wisdom` | O3 | READER | ALIVE |
| M15 | `conductor_oracle_profile` | O14 | READER | ALIVE |
| M16 | `conductor_oracle_detectors` | O5 | READER | ALIVE |
| M17 | `conductor_oracle_trends` | B2 | AUDITOR | ALIVE |
| M18 | `conductor_oracle_diagnose` | O5 | AUDITOR | ALIVE |
| M19 | `conductor_oracle_calibrate` | O4 | CONDUCTOR | ALIVE |
| M20 | `conductor_guardian_counsel` | O7 | READER | ALIVE |
| M21 | `conductor_guardian_whisper` | O8 | READER | ALIVE |
| M22 | `conductor_guardian_teach` | O9 | READER | ALIVE |
| M23 | `conductor_guardian_landscape` | O10 | READER | ALIVE |
| M24 | `conductor_guardian_mastery` | O11 | READER | ALIVE |
| M25 | `conductor_mark_internalized` | O12 | CONDUCTOR | ALIVE |
| M26 | `conductor_guardian_corpus` | O13 | READER | ALIVE |
| M27 | `conductor_preflight` | P1 | CONDUCTOR | ALIVE |
| M28 | `conductor_active_sessions` | P2 | READER | ALIVE |
| M29 | `conductor_session_start` | S1 | CONDUCTOR | ALIVE |
| M30 | `conductor_session_transition` | S2 | CONDUCTOR | ALIVE |
| M31 | `conductor_gate_check` | O2 | CONDUCTOR | ALIVE |
| M32 | `conductor_workflow_status` | W3 | READER | ALIVE |
| M33 | `conductor_workflow_step` | W2 | CONDUCTOR | ALIVE |
| M34 | `conductor_fleet_status` | F1 | READER | ALIVE |
| M35 | `conductor_fleet_recommend` | F1 | CONDUCTOR | ALIVE |
| M36 | `conductor_fleet_dispatch` | F3 | CONDUCTOR | ALIVE |
| M37 | `conductor_fleet_guardrailed_handoff` | F5 | CONDUCTOR | ALIVE |
| M38 | `conductor_fleet_cross_verify` | V1 | AUDITOR | ALIVE |
| M39 | `conductor_retro_session` | R1 | AUDITOR | ALIVE |
| M40 | `conductor_ingest` | (research) | WRITER | ALIVE |

**Totals: 93 atomic actions, 40 MCP tools, 0 dead, 0 retired, 0 missing**

---

## The Archetypes (5 owners)

Every action has an archetype — the cognitive role it plays on the clock track:

| Archetype | Symbol | Role | Direction | Count |
|-----------|--------|------|-----------|-------|
| CONDUCTOR | ⟐ | Orchestrates, transitions, dispatches | bidirectional | 31 |
| READER | ◉ | Observes, queries, synthesizes | inbound | 24 |
| WRITER | ▶ | Creates, persists, exports | outbound | 17 |
| AUDITOR | ◈ | Verifies, checks, diagnoses | inbound | 19 |
| REFACTORER | ⟳ | Transforms in place | circular | 2 |

---

## The Timeline: Three Scales

### Scale 1: Atomic Pair (the beat — smallest functional unit)

The smallest unit of work that produces a measurable result. Two actions that together complete one cycle:

```
╔═══════════════════════════════════════════════════╗
║  DISPATCH PAIR: dispatch + verify                  ║
║  ──────────────────────────────────────────────── ║
║  F3 TaskDispatcher.plan() → V1 CrossVerifier.verify() ║
║  CONDUCTOR → AUDITOR                                ║
║  [clock: 1 beat]                                    ║
╚═══════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════╗
║  SESSION PAIR: start + close                       ║
║  ──────────────────────────────────────────────── ║
║  S1 SessionEngine.start() → S3 SessionEngine.close() ║
║  CONDUCTOR → CONDUCTOR                              ║
║  [clock: 1 beat]                                    ║
╚═══════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════╗
║  FEEDBACK PAIR: log + inject                       ║
║  ──────────────────────────────────────────────── ║
║  B1 log_event() → B7 inject_into_routing_engine()  ║
║  WRITER → CONDUCTOR                                 ║
║  [clock: 1 beat]                                    ║
╚═══════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════╗
║  RETRO PAIR: build + alchemize                     ║
║  ──────────────────────────────────────────────── ║
║  R1 build_ledger() → R3 alchemize_ledger()         ║
║  AUDITOR → CONDUCTOR                                ║
║  [clock: 1 beat]                                    ║
╚═══════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════╗
║  CONTRIBUTION PAIR: punch-in + punch-out           ║
║  ──────────────────────────────────────────────── ║
║  (NEW) timecard.punch_in() → timecard.punch_out()  ║
║  CONDUCTOR → AUDITOR                                ║
║  [clock: 1 beat]                                    ║
╚═══════════════════════════════════════════════════╝
```

### Scale 2: Sequence (the measure — one dispatch lifecycle)

A complete dispatch lifecycle from owner at start to returning to source:

```
MEASURE: Single Agent Dispatch
═══════════════════════════════════════════════════════
Beat 1: PLAN
  ⟐ P1 preflight → ⟐ F2 classify → ⟐ F3 plan
  [CONDUCTOR reads state → classifies work → ranks agents]

Beat 2: PREPARE
  ⟐ F5 guardrailed_handoff → ▶ F7 write_handoff → ▶ F9 write_active
  [CONDUCTOR builds envelope → WRITER persists container]

  NEW: container_builder.build() → timecard.punch_in()
  [CONDUCTOR assembles container → CONDUCTOR records baseline]

Beat 3: DISPATCH
  ▶ F8 log_handoff → ▶ F11 record_usage
  [WRITER logs dispatch → WRITER records token allotment]

  === AGENT WORKS (off-clock — external process) ===

Beat 4: RETURN
  ◈ V1 verify → ⟐ F10 clear_active → ▶ B1 log_event
  [AUDITOR checks output → CONDUCTOR clears handoff → WRITER logs result]

  NEW: timecard.punch_out() → energy_ledger.compute()
  [AUDITOR records delivery → AUDITOR computes balance]

Beat 5: LEARN
  ▶ B5 record_pattern → ⟐ B7 inject_feedback → ◈ R1 build_ledger
  [WRITER records incident → CONDUCTOR injects into routing → AUDITOR retrospects]

  NEW: scorecard.compute() → prompt_patches.create() → container_builder.evolve()
  [AUDITOR profiles agent → WRITER creates constraint → CONDUCTOR evolves template]
═══════════════════════════════════════════════════════
```

### Scale 3: Macro (the song — one planning session, multiple dispatches)

```
SONG: Plan-First Fleet Dispatch
═══════════════════════════════════════════════════════

INTRO (FRAME phase)
  ⟐ M29 session_start
  ⟐ M27 preflight → ◉ M7 patch (bulletin) → ◉ M12 oracle
  [CONDUCTOR opens → reads state → consults oracle]

  NEW: fleet_bulletin.generate() → return_queue.process()
  [READER shows fleet state → CONDUCTOR reviews pending returns]

VERSE 1 (SHAPE phase)
  ⟐ M30 transition(SHAPE)
  ⟐ F2 classify × N tasks → ⟐ F3 plan × N
  [CONDUCTOR maps A→Z, decomposes into segments]

  NEW: plan_dispatch.create() → container_builder.build_stores()
  [CONDUCTOR builds full plan → CONDUCTOR pre-builds all containers]

CHORUS (BUILD phase — dispatches fire)
  ⟐ M30 transition(BUILD)

  For each segment in dependency order:
    ⟐ container_builder.verify_store()     # completeness check
    ⟐ F5 guardrailed_handoff               # envelope from container
    ▶ F7 write_handoff + F9 write_active   # persist
    ⟐ timecard.punch_in()                  # record baseline
    ▶ F8 log + F11 usage                   # log dispatch

    === AGENT WORKS ===

    ◈ V1 verify                            # cross-verify return
    ⟐ timecard.punch_out()                 # record delivery
    ◈ energy_ledger.compute()              # measure balance
    ⟐ contribution_ledger.close()          # close receipt

    If violations:
      ▶ prompt_patches.create()            # generate constraint
      ◈ scorecard.update()                 # update profile

  Parallel independent segments run concurrently on the same beat.

BRIDGE (PROVE phase)
  ⟐ M30 transition(PROVE)
  ◈ I1 doctor → ◈ I2 integrity → ◈ B2 trends
  [AUDITOR checks system health post-dispatch]

  ◈ R1 build_ledger → ⟐ R3 alchemize
  [AUDITOR retrospects → CONDUCTOR feeds back into oracle]

OUTRO (DONE)
  ⟐ S3 close
  ▶ S7 export (optional)
  ◈ B8 compute_dora
  [CONDUCTOR closes → WRITER exports → AUDITOR measures DORA]

  NEW: scorecard.persist() → fleet_bulletin.refresh()
  [WRITER saves updated scorecards → READER refreshes bulletin for next session]
═══════════════════════════════════════════════════════
```

---

## The Clock Track

All collision points on one timeline:

```
BPM: SESSION_OPEN ─────────────────────────────── SESSION_CLOSE
     │                                                   │
     ├─ FRAME ──────┐                                    │
     │  preflight    │                                    │
     │  bulletin     │                                    │
     │  return_queue │                                    │
     │  oracle       │                                    │
     │               │                                    │
     ├─ SHAPE ──────┐│                                    │
     │  classify ×N  ││                                   │
     │  plan A→Z     ││                                   │
     │  build stores ││                                   │
     │               ││                                   │
     ├─ BUILD ──────┐││                                   │
     │  ┌─────────┐ │││  ┌─────────┐  ┌─────────┐       │
     │  │Dispatch │ │││  │Dispatch │  │Dispatch │       │
     │  │ S-001   │ │││  │ S-002   │  │ S-003   │       │
     │  │ codex   │ │││  │ gemini  │  │ opencode│       │
     │  │ punch▸  │ │││  │ punch▸  │  │ punch▸  │       │
     │  │ ...     │ │││  │ ...     │  │ ...     │       │
     │  │ ◀punch  │ │││  │ ◀punch  │  │ ◀punch  │       │
     │  │ verify  │ │││  │ verify  │  │ verify  │       │
     │  │ energy  │ │││  │ energy  │  │ energy  │       │
     │  │ patch?  │ │││  │ patch?  │  │ patch?  │       │
     │  └─────────┘ │││  └─────────┘  └─────────┘       │
     │               │││                                  │
     ├─ PROVE ──────┐│││                                  │
     │  doctor       ││││                                 │
     │  retro        ││││                                 │
     │  alchemize    ││││                                 │
     │  DORA         ││││                                 │
     │               ││││                                 │
     └───────────────┘││││                                │
                      └┘└┘────────────────────────────────┘
```

## The Design Principle

> Plans are designed from owner (archetype) at the start to returning to source with expectations required and logged at the end.

Every dispatch follows: **CONDUCTOR dispatches → AGENT works → AUDITOR verifies → WRITER logs → CONDUCTOR learns**

The contribution ledger IS this cycle formalized. The click track IS the session lifecycle. The BPM IS the phase transitions. Every action in the inventory has a position on this clock.

## What This Changes About the Contribution Ledger

The ledger plan (Tasks 1-11) already implements the core cycle. This temporal spec adds:

1. **Archetype tagging** — every action in the ledger carries its archetype (CONDUCTOR, READER, WRITER, AUDITOR, REFACTORER)
2. **Beat numbering** — dispatches are numbered beats on the plan's click track, not independent events
3. **Parallel beat support** — independent segments fire on the same beat (concurrent dispatches)
4. **The return-to-source invariant** — every dispatch MUST complete the cycle back to the CONDUCTOR who initiated it. No fire-and-forget. The clock doesn't advance until the beat resolves.
