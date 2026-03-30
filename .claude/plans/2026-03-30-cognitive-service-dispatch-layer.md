# Cognitive Service Dispatch Layer — Design Spec

## Context

The ORGANVM system has a 578-tool ontology with 64 clusters and 32 directed routes, plus a Conductor OS with session lifecycle, governance, and a fleet subsystem (`fleet.yaml`, `fleet_router.py`, `fleet_handoff.py`). The fleet router scores agents by phase affinity, tag matching, utilization pressure, context fit, and cost efficiency.

**The gap:** The fleet router asks "which agent given this phase and tags?" but has no concept of:
- **Work type classification** — "architecture" vs "boilerplate" are not distinguished
- **Service restrictions** — nothing blocks Gemini from touching package.json or making schema decisions
- **Constraint transfer** — handoff briefs carry free-text decisions but nothing structured or enforceable
- **Cross-verification** — no mechanism to verify output conforms to constraints; self-audit is accepted at face value

Three production incidents document the damage:
1. Gemini generated 79 files with camelCase in a snake_case Drizzle ORM schema (20+ files broken, 14 fix commits)
2. Gemini installed React+CMS into a static Astro site (5KB→3MB), left 15 issues, never visually reviewed
3. Codex→Claude handoff lost all context — Claude repeated already-established work

## Approach

Extend the existing fleet subsystem with four additions: work type taxonomy, service restrictions, guardrailed handoff envelopes, and cross-verification protocol.

## Implementation Plan

### Step 1: Work Type Taxonomy (`conductor/work_types.yaml` + schema)

New YAML data file defining cognitive work classes:

```yaml
work_types:
  architecture:
    label: "Architectural decisions"
    cognitive_class: strategic
    examples: ["schema design", "dependency selection", "module boundaries", "config structure"]
    required_phase_affinity: { SHAPE: 0.8, BUILD: 0.9 }
    required_sensitivity: { can_push_git: true }
    verification: cross_agent_mandatory

  boilerplate_generation:
    label: "Bulk file scaffolding"
    cognitive_class: mechanical
    examples: ["CRUD endpoints", "test stubs", "template files", "migration scripts"]
    required_phase_affinity: { BUILD: 0.6 }
    verification: cross_agent_mandatory

  research:
    label: "Knowledge gathering and synthesis"
    cognitive_class: strategic
    examples: ["API evaluation", "pricing research", "competitor analysis", "documentation review"]
    required_phase_affinity: { FRAME: 0.7 }
    verification: self_sufficient

  mechanical_refactoring:
    label: "Convention-conformant bulk edits"
    cognitive_class: mechanical
    examples: ["naming convention conversion", "import reordering", "type annotation addition"]
    required_sensitivity: { can_push_git: true }
    verification: cross_agent_mandatory

  audit:
    label: "Cross-verification of prior work"
    cognitive_class: strategic
    examples: ["type boundary check", "convention compliance", "dependency audit", "security review"]
    verification: independent

  content_generation:
    label: "Documentation, README, essay writing"
    cognitive_class: tactical
    examples: ["README", "CHANGELOG", "API docs", "blog posts"]
    required_phase_affinity: { BUILD: 0.5 }
    verification: self_sufficient
```

Plus `schemas/v1/work_types.schema.json` for validation.

### Step 2: Service Restrictions in `fleet.yaml`

Extend each agent entry with `restrictions` and `guardrails`:

**Claude:**
```yaml
restrictions:
  never_touch: []
  never_decide: []
  max_cognitive_class: strategic  # can do everything
guardrails:
  self_audit_trusted: true
  max_files_before_checkpoint: 50
```

**Gemini:**
```yaml
restrictions:
  never_touch:
    - "package.json"
    - "*.config.ts"
    - "*.config.js"
    - "*.config.mjs"
    - "drizzle.config.*"
    - "astro.config.*"
    - ".env*"
    - "seed.yaml"
    - "pyproject.toml"
  never_decide:
    - architecture
    - dependency_selection
    - schema_design
  max_cognitive_class: mechanical
guardrails:
  self_audit_trusted: false
  max_files_before_checkpoint: 20
```

**Codex:**
```yaml
restrictions:
  never_touch: []
  never_decide: []
  max_cognitive_class: tactical  # can do tactical but not strategic architecture alone
guardrails:
  self_audit_trusted: true
  max_files_before_checkpoint: 30
  handoff_envelope_required: true  # must generate full envelope on session close
```

### Step 3: Extend `FleetRouter.recommend()`

Add `work_type: str | None` parameter to `recommend()`:

1. If `work_type` provided, look up from `work_types.yaml`
2. Apply `required_phase_affinity` as minimum thresholds (hard filter)
3. Apply `required_sensitivity` as hard filter (existing logic)
4. Apply `max_cognitive_class` as hard filter — if work type is `strategic` and agent max is `mechanical`, exclude agent
5. Apply `never_decide` — if work type matches any `never_decide` entry, exclude agent
6. Score remaining agents with existing weights + new work-type-awareness bonus

**File:** `conductor/fleet_router.py`
**Changes:** ~60 lines — add parameter, load taxonomy, apply filters before scoring loop

### Step 4: Guardrailed Handoff Envelope

Extend `HandoffBrief` in `conductor/fleet_handoff.py`:

```python
@dataclass
class GuardrailedHandoffBrief(HandoffBrief):
    constraints_locked: list[str] = field(default_factory=list)
    files_locked: list[str] = field(default_factory=list)
    work_completed: list[str] = field(default_factory=list)
    conventions: dict[str, str] = field(default_factory=dict)
    work_type: str = ""
    verification_required: bool = False
    receiver_restrictions: dict[str, Any] = field(default_factory=dict)
```

Plus `generate_guardrailed_handoff()` that auto-populates `receiver_restrictions` from `fleet.yaml` for the `to_agent`.

**Schema:** `schemas/v1/contracts/guardrailed_handoff_v1.schema.json`

### Step 5: Cross-Verification Module

New file `conductor/cross_verify.py`:

```python
@dataclass
class Violation:
    rule: str           # "never_touch", "convention_drift", "constraint_broken"
    detail: str         # human-readable description
    file: str           # affected file path
    severity: str       # "error" | "warning"

@dataclass
class VerificationReport:
    violations: list[Violation]
    passed: bool
    checked_at: str
    handoff_id: str

class CrossVerifier:
    def verify(self, handoff: GuardrailedHandoffBrief,
               changed_files: list[str], diff_content: str = "") -> VerificationReport:
        # 1. Check changed_files against handoff.files_locked
        # 2. Check changed_files against receiver_restrictions.never_touch (glob matching)
        # 3. Check conventions (e.g., grep for camelCase in snake_case projects)
        # 4. Check constraints_locked are not violated
        ...
```

**Estimated:** ~150 lines

### Step 6: Task Dispatcher (Orchestration Entrypoint)

New file `conductor/task_dispatcher.py`:

```python
class TaskDispatcher:
    def __init__(self, fleet_router: FleetRouter, work_types: dict):
        self.router = fleet_router
        self.work_types = work_types

    def plan(self, description: str, phase: str,
             context_size: int = 0,
             sensitivity: dict | None = None) -> DispatchPlan:
        # 1. Classify work type from description (keyword match + explicit override)
        # 2. Look up work type requirements
        # 3. Call fleet_router.recommend() with work_type filter
        # 4. Return ranked agent list with per-agent scope boundaries
        ...

    def classify(self, description: str) -> str:
        # Keyword matching against work_type examples
        # Returns work_type id or "unclassified"
        ...
```

**Estimated:** ~200 lines

### Step 7: Wire into Preflight and MCP

**`conductor/preflight.py`:** Replace `_get_fleet_recommendation()` call with `TaskDispatcher.plan()` when work type is known.

**`conductor/commands/fleet_cmd.py`:** Add subcommands:
- `conductor fleet dispatch --work-type architecture --phase SHAPE`
- `conductor fleet verify --handoff-id <id> --changed-files <files>`

**`mcp_server.py`:** Add tools:
- `conductor_dispatch_plan` — returns ranked agents for a work type
- `conductor_cross_verify` — checks output against handoff constraints
- `conductor_guardrailed_handoff` — generates envelope for agent switch

### Step 8: Oracle Detectors

Add to `conductor/oracle.py`:
- `detect_service_mismatch`: Fires when current agent has restrictions that conflict with current work
- `detect_verification_overdue`: Fires when `self_audit_trusted: false` agent completed work without cross-check
- `detect_handoff_context_missing`: Fires when switching agents without a guardrailed envelope

### Step 9: Tests

New test files following existing patterns:
- `tests/test_task_dispatcher.py` — classification accuracy, restriction filtering, dispatch plans
- `tests/test_cross_verify.py` — violation detection, glob matching, convention checking
- `tests/test_guardrailed_handoff.py` — envelope generation, constraint propagation
- Extend `tests/test_fleet.py` — restriction hard filters, work type integration

## Critical Files

| File | Action |
|------|--------|
| `conductor/work_types.yaml` | **CREATE** — work type taxonomy |
| `conductor/task_dispatcher.py` | **CREATE** — classification + dispatch orchestration |
| `conductor/cross_verify.py` | **CREATE** — output verification against constraints |
| `schemas/v1/work_types.schema.json` | **CREATE** — schema validation |
| `schemas/v1/contracts/guardrailed_handoff_v1.schema.json` | **CREATE** — envelope schema |
| `conductor/fleet.yaml` | **MODIFY** — add restrictions/guardrails per agent |
| `conductor/fleet_router.py` | **MODIFY** — add work_type parameter + hard filters |
| `conductor/fleet_handoff.py` | **MODIFY** — extend HandoffBrief with guardrail fields |
| `conductor/preflight.py` | **MODIFY** — wire TaskDispatcher |
| `conductor/oracle.py` | **MODIFY** — add 3 new detectors |
| `conductor/commands/fleet_cmd.py` | **MODIFY** — add dispatch/verify subcommands |
| `mcp_server.py` | **MODIFY** — add 3 new MCP tools |
| `tests/test_task_dispatcher.py` | **CREATE** — dispatcher tests |
| `tests/test_cross_verify.py` | **CREATE** — verifier tests |
| `tests/test_guardrailed_handoff.py` | **CREATE** — envelope tests |

## Verification

1. **Unit tests:** `python3 -m pytest tests/test_task_dispatcher.py tests/test_cross_verify.py tests/test_guardrailed_handoff.py -v`
2. **Integration:** `python3 -m pytest tests/test_fleet.py -v` (existing fleet tests still pass)
3. **CLI smoke test:** `python3 -m conductor fleet dispatch --work-type architecture --phase SHAPE` returns Claude as top recommendation with Gemini excluded
4. **Restriction enforcement:** `python3 -m conductor fleet dispatch --work-type boilerplate_generation --phase BUILD` returns Gemini/Codex eligible, Claude available
5. **Handoff round-trip:** Generate `GuardrailedHandoffBrief`, serialize, deserialize, verify all constraint fields preserved
6. **Cross-verify simulation:** Create a mock diff that violates `never_touch` and `conventions`, verify `CrossVerifier` catches violations
7. **Oracle check:** `python3 -m conductor doctor --strict` passes with new detectors loaded
8. **Full doctor:** `python3 -m conductor doctor` reports no regressions
9. **Existing tests:** `python3 -m pytest tests/ -v` — all existing tests pass unchanged
