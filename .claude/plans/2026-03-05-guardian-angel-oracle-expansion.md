# Guardian Angel: Oracle Expansion Plan

## Context

All 8 original pain points are confirmed addressed by existing implementations (session discipline, governance guardrails, navigation, cost optimization, growth feedback, etc.). The Oracle module (`conductor/oracle.py`) currently provides 9 reactive detectors and produces terse advisory messages at session start/close and in patchbay briefings. It covers ~70% of the "guardian angel" vision.

This plan closes the remaining ~30% gap: transforming the Oracle from a passive, stateless advisor into a persistent, context-aware Guardian Angel that integrates at every critical decision point, learns from history, and speaks with narrative wisdom.

---

## Phase 1: Foundation — Enhanced Data Structures

### 1a. Extend `Advisory` dataclass (`conductor/oracle.py`)
Add backward-compatible fields:
- `detector: str` — which detector produced this
- `tools_suggested: list[str]` — recommended tool cluster IDs
- `gate_action: str` — `""`, `"block"`, `"warn"`, `"approve"` for decision gates
- `confidence: float` — 0.0-1.0
- `narrative: str` — rich contextual wisdom text
- `tags: list[str]` — for filtering/grouping
- Add `"critical"` to `SEVERITY_ORDER`

### 1b. Create `OracleContext` dataclass (`conductor/oracle.py`)
Structured input replacing loose `context: dict`:
- `trigger`: `"session_start"`, `"session_close"`, `"phase_transition"`, `"workflow_pre_step"`, `"workflow_post_step"`, `"patchbay"`, `"promotion"`, `"manual"`
- `session_id`, `current_phase`, `target_phase`, `workflow_step`, `workflow_name`, `promotion_repo`, `organ`, `extra`
- `from_dict()` classmethod for backward-compatible dict conversion

### 1c. Oracle state persistence (`conductor/oracle.py` + `conductor/constants.py`)
- Add `ORACLE_STATE_FILE = BASE / ".conductor-oracle-state.json"` to `constants.py`
- Add `_load_oracle_state()`, `_save_oracle_state()`, `_record_advisories()` methods
- State tracks: advisory log (last 500), detector effectiveness scores, suppressed advisory hashes

### 1d. Update `consult()` signature (backward-compatible)
```python
def consult(self, context=None, max_advisories=8, *, include_narrative=False, gate_mode=False):
```
- `context` accepts dict (old) or `OracleContext` (new)
- `include_narrative=True` triggers narrative enrichment
- `gate_mode=True` returns all gate-relevant advisories untruncated

---

## Phase 2: New Detectors (6 new detectors)

### 2a. `_detect_tool_recommendations`
- **Purpose**: Suggest tool clusters based on current phase + ontology
- **Sources**: Session state, `PHASE_CLUSTERS`, ontology
- **Logic**: If user hasn't used tools from active phase clusters, suggest them. If using wrong-phase tools repeatedly, suggest phase transition.

### 2b. `_detect_gate_checks`
- **Purpose**: Advisory guidance at phase transitions and promotions
- **Sources**: Session state, governance registry, `OracleContext.trigger`
- **Logic**:
  - Phase gate: Warn if FRAME too short, no research tools used, no commits before PROVE, active warnings before DONE
  - Promotion gate: Check CI, seed.yaml, WIP headroom

### 2c. `_detect_predictive_warnings`
- **Purpose**: Forecast issues using cross-session historical data
- **Sources**: Session logs, stats, pattern history, trends
- **Logic**: Same organ+scope failure correlation, earlier marathon detection (1.5x threshold), composite "session health score"

### 2d. `_generate_narrative_wisdom`
- **Purpose**: Rich contextual messages — the "wise sage whispering in your ear"
- **Sources**: All loaded state
- **Logic**: Milestone narratives (5th/10th/25th session), pattern evolution acknowledgment, process metaphors for transitions, streak encouragement, time-of-day/week patterns from actual data
- Populates the `narrative` field on Advisory (capped at 200 chars)

### 2e. `_detect_cross_session_patterns`
- **Purpose**: Learn which advisories were heeded vs ignored, correlate with outcomes
- **Sources**: Oracle state file
- **Logic**: If detector consistently ignored + sessions fail, produce meta-advisory. Boost/lower detector confidence based on effectiveness.

### 2f. `_detect_workflow_risks`
- **Purpose**: Advise during workflow step execution
- **Sources**: Workflow state, feedback health scores, primitive maturity
- **Logic**: Pre-step: warn on degraded cluster health (<0.7) or alpha primitives. Post-step: advise on failures, suggest checkpointing for long workflows.

---

## Phase 3: Integration Points

### 3a. Phase transition hook (`conductor/session.py` — `SessionEngine.phase()`)
After transition validation, before state save: consult Oracle with `trigger="phase_transition"`. Print gate advisories. Non-blocking (advisory only).

### 3b. Session close effectiveness (`conductor/session.py` — `SessionEngine.close()`)
After pattern recording (~line 523): call `oracle._update_effectiveness(session_id, result)` to record which advisories were heeded and their outcomes.

### 3c. Workflow step hooks (`conductor/executor.py` — `WorkflowExecutor.run_step()`)
- Pre-step: consult Oracle, embed advisories in step metadata
- Post-step: consult Oracle, embed advisories in result dict

### 3d. Enhanced patchbay section (`conductor/patchbay.py`)
- Pass `OracleContext(trigger="patchbay")` with session info
- Use `include_narrative=True`
- Render new fields: narrative, tools_suggested, confidence

---

## Phase 4: CLI + MCP Exposure

### 4a. CLI `oracle` command (`conductor/cli.py`)
New top-level command with subcommands:
- `oracle consult` — Full advisory with narratives
- `oracle gate --trigger phase_transition --target SHAPE` — Decision-gate check
- `oracle wisdom` — Deep narrative wisdom (3 advisories, narrative-enriched)
- `oracle status` — Detector effectiveness scores
- `oracle history` — Recent advisory log
- `oracle ack <hash>` — Acknowledge an advisory

### 4b. MCP tools (`mcp_server.py`)
- Enhance existing `conductor_oracle` — add `include_narrative` param, return new fields
- Add `conductor_oracle_gate` — decision-gate advisory for phase transitions/promotions
- Add `conductor_oracle_wisdom` — rich narrative wisdom on a given topic

---

## Phase 5: Testing + Polish

### 5a. New test file: `tests/test_oracle.py`
- Unit tests for each new detector (12+ tests)
- State persistence round-trip tests
- Effectiveness recording tests
- `OracleContext` backward compatibility tests

### 5b. Extend `tests/test_e2e_flow.py`
- Full lifecycle test: session start -> phase transitions -> workflow -> close with oracle checks at each point

### 5c. Extend `tests/test_mcp_server.py`
- Tests for enhanced oracle tool and new gate/wisdom tools

### 5d. Contract schema: `schemas/v1/contracts/oracle_advisory_v1.schema.json`

### 5e. Update `conductor/__init__.py` exports: `OracleContext`

---

## Critical Files

| File | Changes |
|------|---------|
| `conductor/oracle.py` | Core expansion: new dataclasses, 6 new detectors, state persistence, enhanced consult() |
| `conductor/constants.py` | Add `ORACLE_STATE_FILE` |
| `conductor/session.py` | Phase transition hook (~line 312), effectiveness recording (~line 523) |
| `conductor/executor.py` | Pre/post step hooks in `run_step()` |
| `conductor/patchbay.py` | Enhanced `_oracle_section()`, updated text formatter |
| `conductor/cli.py` | New `oracle` command with 6 subcommands |
| `mcp_server.py` | Enhanced oracle tool + 2 new MCP tools |
| `conductor/__init__.py` | Export `OracleContext` |
| `tests/test_oracle.py` | New — comprehensive oracle unit tests |
| `tests/test_e2e_flow.py` | Extend with oracle integration tests |

## Design Principles

- **Read-only invariant preserved**: Oracle writes ONLY to its own state file, never to session/governance/workflow state
- **Backward compatible**: Existing `consult()` API unchanged; new params are keyword-only
- **Advisory only, never blocking**: Gate checks print warnings but never prevent transitions — trust the human conductor
- **Graceful degradation**: Every detector wrapped in try/except; one failure doesn't break others
- **Narrative cap**: 200 chars max to keep output scannable

## Verification

1. `python3 -m pytest tests/test_oracle.py -v` — All new detector tests pass
2. `python3 -m pytest tests/ -v` — Full suite passes (287+ tests)
3. `python3 -m conductor oracle consult` — Produces advisories with narratives
4. `python3 -m conductor oracle gate --trigger phase_transition --target SHAPE` — Gate advisory renders
5. `python3 -m conductor patch` — Patchbay ORACLE section shows enriched advisories
6. MCP: `conductor_oracle_wisdom` returns narrative-enriched response
