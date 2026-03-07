# 2026-03-04 — Full Implementation: Executor Completion, Health Signals, Oracle/Sage, Growth Loop

## Context

The tool-interaction-design system has a layered architecture (ontology → routing → workflow DSL → conductor OS) that addresses the user's core pain points: undisciplined development procedures, getting lost in complexity, and wanting to commodify process. However, several critical gaps remain:

- **Workflow executor** has only 3 of 8 primitives implemented (pipe, gate, checkpoint) with 2 crash bugs
- **Auto-promote health signals** are placeholder string comparisons against registry fields, not real filesystem checks
- **No advisory system** exists to provide contextual guidance — the user wants an "omnipotent guide" that whispers wisdom, steers from disaster, and teaches
- **No growth feedback loop** correlates behavioral patterns with outcomes

This plan implements all four areas across 5 phases.

---

## Phase 0: Bug Fixes (2 files)

### 0a. StepState metadata field — `conductor/executor.py:24`

Add `metadata: dict[str, Any] = field(default_factory=dict)` to the `StepState` dataclass. Currently `compiler.py:116` passes `metadata={}` to `StepState()` which crashes with TypeError.

Update `save_state()` (~line 148) to include `metadata` in serialization.
Update `load_state()` (~line 125) to pass `metadata` through when reconstructing StepState.

### 0b. Compiler checkpoint injection — `conductor/compiler.py:109`

The checkpoint injection builds `target_step_name = f"step_{weakest_idx}_{cluster_path[weakest_idx]}"` but actual step names use `f"{goal_slug}_{cluster_id}"` format (line 62). Fix: build an `idx_to_name` mapping during step creation loop (lines 55-72), then use it at line 109.

---

## Phase 1: Workflow Executor Completion (1 file + tests)

**File**: `conductor/executor.py`

### 1a. Expression transforms (~line 416)

Add missing transforms to `_apply_transform()`:
- `lines` — split on newlines
- `flatten` — flatten nested lists
- `unique` — deduplicate preserving order
- `sort` — sort items
- `filter(pred)` — filter with simple predicate
- `join(sep)` — join list to string
- `take(n)` — first N items

### 1b. fan_out / fan_in primitives

**Approach**: Sequential simulation (no asyncio). When `run_step` encounters a `fan_out` step:
1. Read `branches` list from step definition
2. Expand into flat sub-steps named `{parent}__branch_{i}` inserted into `step_order`
3. Execute each branch sequentially, collecting outputs
4. Synthetic `{parent}__fan_in` step aggregates branch outputs into a list

Update `all_passed` / `any_passed` condition functions (line 266) to check all `{parent}__branch_*` steps.

### 1c. loop primitive

Add `iteration: int = 0` and `max_iterations: int = 0` fields to `StepState`.

When `run_step` encounters a `loop` step:
1. Read `max_iterations` and `until` condition from step definition
2. Execute body, increment iteration counter
3. Re-evaluate `until` condition; if false and under max, re-queue step
4. Store loop state in `step.metadata`

### 1d. on_error / fallback

Add `fail_step(step_name, error)` method that sets status to FAILED and records error.

Parse error strategy strings from workflow definition (e.g., `"retry(3)"`, `"fallback"`, `"skip"`):
- `retry(n)` — re-run step up to n times
- `fallback` — execute the step's declared fallback cluster
- `skip` — mark SKIPPED, continue

The `fallback` DSL primitive (`!>`) maps to a step with `on_error: fallback` and a declared fallback step name.

### 1e. emit primitive

`emit` steps fire an event via `observability.log_event()` with the step's output as payload. No cluster execution needed — purely a side-effect step.

### 1f. Tests — `tests/test_executor.py`

Add tests for each new primitive following existing pattern (YAML → tmp_path → WorkflowExecutor → assertions):
- `test_fan_out_fan_in_collects_branches` — 3 branches, verify aggregated output
- `test_loop_runs_until_condition` — loop with max_iterations=3
- `test_loop_respects_max_iterations` — loop exits at max even if condition not met
- `test_on_error_retry` — step fails then succeeds on retry
- `test_on_error_skip` — step fails, marked SKIPPED, workflow continues
- `test_fallback_step` — primary fails, fallback executes
- `test_emit_logs_event` — emit step calls log_event
- `test_transforms_unique_sort_flatten` — new transform functions
- `test_all_passed_requires_all_branches` — multi-branch condition

---

## Phase 2: Real Health Signals (1 file)

**File**: `conductor/governance.py` — `_health_signals()` static method (line 426)

Replace placeholder string comparisons with filesystem checks:

```python
@staticmethod
def _health_signals(repo: dict[str, Any], organ_key: str = "") -> dict[str, bool]:
    repo_name = repo.get("name", "")
    # Try to find repo on disk
    repo_path = _find_repo_path(repo_name, organ_key)
    if repo_path and repo_path.is_dir():
        docs_ok = (repo_path / "README.md").is_file() and (repo_path / "README.md").stat().st_size > 500
        ci_ok = (repo_path / ".github" / "workflows").is_dir() and any((repo_path / ".github" / "workflows").iterdir())
        src_dirs = [d for d in ["src", "lib", repo_name.replace("-", "_")] if (repo_path / d).is_dir()]
        test_dirs = [d for d in ["tests", "test"] if (repo_path / d).is_dir()]
        impl_ok = bool(src_dirs) and bool(test_dirs)
    else:
        # Fallback to registry fields
        docs_ok = str(repo.get("documentation_status", "")).upper() == "DEPLOYED"
        ci_ok = bool(str(repo.get("ci_workflow", "")).strip())
        impl_ok = str(repo.get("implementation_status", "")).upper() in {"ACTIVE", "COMPLETE", "COMPLETED", "READY", "MATURE", "STABLE"}
    return {"docs_ok": docs_ok, "ci_ok": ci_ok, "implementation_ok": impl_ok}
```

Add helper `_find_repo_path(repo_name, organ_key)` that searches `~/Workspace/<organ_dir>/` for the repo directory, using `ORGAN_MAP` from constants.

Update `auto_promote()` (line 444) to pass `organ_key` through to `_health_signals()`.

---

## Phase 3: Oracle/Sage Advisory System (new file + 3 integrations)

### 3a. New file: `conductor/oracle.py`

```python
@dataclass
class Advisory:
    category: str        # e.g., "process", "risk", "growth", "history"
    severity: str        # "info", "caution", "warning"
    message: str         # Human-readable guidance
    context: dict        # Supporting data
    recommendation: str  # Actionable next step
```

**Oracle class** — read-only advisory engine that consumes all available data:
- Session stats (from `session.py`)
- Observability trends (from `observability.compute_trend_report()`)
- Pattern data (from `product.mine_patterns()`)
- Governance state (from `governance.py`)
- Workflow execution history

**8 detector methods**, each returns `list[Advisory]`:

| Detector | What it checks | Example advisory |
|----------|---------------|------------------|
| `_detect_process_drift` | Phase violations, skipped phases | "You've skipped FRAME in 3 of your last 5 sessions. Framing prevents scope creep." |
| `_detect_scope_risk` | Session duration outliers, WIP limits | "This session is 2x your average BUILD phase. Consider checkpointing." |
| `_detect_momentum` | Streak, ship rate trends | "Your ship rate improved 40% this month. The PROVE phase investment is paying off." |
| `_detect_governance_gaps` | Repos stuck in promotion, health signal failures | "12 repos have been CANDIDATE for 30+ days. Consider promoting or archiving." |
| `_detect_pattern_antipatterns` | Known risky patterns (EAGER_CODER, MARATHON_BUILD) | "MARATHON_BUILD detected — long builds without checkpoints correlate with 60% higher failure rates." |
| `_detect_knowledge_gaps` | Repeated failures in specific clusters/domains | "Web scraping workflows have failed 5 times this month. Consider the research/digest pattern instead." |
| `_detect_growth_opportunities` | Unused capabilities, unexplored domains | "You haven't used any DEPLOY capabilities. Shipping practice builds confidence." |
| `_detect_seasonal_wisdom` | Time-based patterns, streak context | "Friday evening sessions have 30% lower completion rates. Consider a lighter scope." |

**Main method**: `consult(context: dict) -> list[Advisory]` — runs all detectors, deduplicates, sorts by severity, returns top-N advisories.

### 3b. Patchbay integration — `conductor/patchbay.py`

Add Oracle section to `briefing()` (after line 77):
- Instantiate Oracle, call `consult()` with current system context
- Add `_oracle_section()` method that formats advisories
- Render in `format_text()` after existing sections (~line 514)

### 3c. Session integration — `conductor/session.py`

- At session start (after line 228): Call `oracle.consult()` with session context, include advisories in start output
- At session close (after line 474): Call `oracle.consult()` with session results, include retrospective advisories

### 3d. MCP tool — `mcp_server.py`

Add `conductor_oracle` tool to the dispatch table:
- Input: optional `context` dict (current phase, recent actions, specific question)
- Output: list of advisories formatted as structured JSON
- Register in dispatch table (~line 635)

---

## Phase 4: Growth Feedback Loop (2 files)

### 4a. Pattern-shipping correlation — `conductor/product.py`

Add `correlate_patterns_with_outcomes()` function after `mine_patterns()`:
- Cross-reference detected patterns with session outcomes (completed vs abandoned)
- Calculate per-pattern success rates
- Feed into Oracle's `_detect_pattern_antipatterns` detector

### 4b. Pattern history — `conductor/product.py`

Add JSONL-based pattern history tracking:
- New constant `PATTERN_HISTORY_FILE` in `conductor/constants.py`
- `record_pattern(pattern_name, session_id, outcome)` — append to JSONL
- `load_pattern_history(window_days=90)` — read recent patterns
- Called from `session.close()` when patterns are detected

### 4c. Growth recommendations — `conductor/oracle.py`

Add `_generate_growth_plan()` method:
- Analyze pattern history trends
- Identify which behavioral changes correlate with improved outcomes
- Generate specific, actionable recommendations (e.g., "Spending 5+ minutes in FRAME correlates with 2x higher completion rate for you")

---

## Phase 5: Package Integration (3 files)

- **`conductor/__init__.py`**: Add exports for `Oracle`, `Advisory`, `correlate_patterns_with_outcomes`
- **`conductor/constants.py`**: Add `PATTERN_HISTORY_FILE = DATA_DIR / "pattern-history.jsonl"`
- **`.gitignore`**: Add `pattern-history.jsonl` to persisted state section if not already covered

---

## Files Modified

| File | Phase | Changes |
|------|-------|---------|
| `conductor/executor.py` | 0a, 1a-1e | Add metadata field, transforms, fan_out/fan_in, loop, on_error, fallback, emit |
| `conductor/compiler.py` | 0b | Fix checkpoint injection step name mapping |
| `conductor/governance.py` | 2 | Real filesystem health signals + _find_repo_path helper |
| `conductor/oracle.py` | 3a | **NEW** — Oracle class, Advisory dataclass, 8 detectors |
| `conductor/patchbay.py` | 3b | Oracle section in briefing + format_text |
| `conductor/session.py` | 3c, 4b | Oracle integration at start/close + pattern recording |
| `conductor/product.py` | 4a, 4b | Pattern correlation + history tracking |
| `conductor/constants.py` | 5 | PATTERN_HISTORY_FILE constant |
| `conductor/__init__.py` | 5 | New exports |
| `mcp_server.py` | 3d | conductor_oracle tool |
| `tests/test_executor.py` | 1f | 9+ new tests for all primitives |

---

## Verification

1. **Unit tests**: `pytest tests/ -v` — all existing + new tests pass
2. **YAML validation**: `python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ['ontology.yaml','routing-matrix.yaml','workflow-dsl.yaml']]"`
3. **Bug fix verification**: `python3 -c "from conductor.compiler import WorkflowCompiler; from conductor.executor import StepState; s = StepState(name='test', metadata={'key': 'val'}); print(s)"` — no crash
4. **Oracle smoke test**: `python3 -c "from conductor.oracle import Oracle; o = Oracle(); print(o.consult({}))"` — returns advisories
5. **Patchbay integration**: `python3 -m conductor patch` — Oracle section appears in briefing
6. **MCP tool**: Start MCP server, call `conductor_oracle` tool — returns structured advisories
7. **Health signals**: `python3 -c "from conductor.governance import GovernanceEngine; print(GovernanceEngine._health_signals({'name': 'tool-interaction-design'}, 'IV'))"` — returns filesystem-based results
