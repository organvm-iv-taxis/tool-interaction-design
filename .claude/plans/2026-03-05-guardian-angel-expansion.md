# Guardian Angel Expansion: The Oracle Becomes Omniscient

## Context

The user originally described five pain points: undisciplined in software procedures, approaching development as a rhetorician, naivete causing trouble, getting lost in a labyrinth of unknowns, and needing to grow/commodify/demystify process. The Conductor OS has addressed these with a phase-gated lifecycle (FRAME/SHAPE/BUILD/PROVE), WIP governance, 23-detector Oracle advisory engine, pattern mining, process kit exports, and a patchbay command center.

Now the user wants to expand the Oracle into a **true Guardian Angel** — "an expert of tradition, master of history, business titan, wise magician sage as an omnipotent guide... someone to whisper in my ear, guide me from Scylla and Charybdis, inform me of the tried and true methods, steer me from disaster, teach me, make me feel safe."

The existing Oracle is an **analytics engine** — it observes behavior and warns. The Guardian Angel adds a **wisdom layer** — it carries canonical knowledge, teaches principles, maps risk-reward landscapes, and grows with the user.

---

## Pain Point Audit: What's Solved, What's Missing

| Pain Point | Existing Solution | Gap |
|---|---|---|
| Undisciplined procedures | Phase-gated lifecycle, locked transitions, per-phase tool activation | **None** — well addressed |
| Rhetorician with theory | Templates (spec.md/plan.md), workflow DSL, concrete artifact tracking | **None** — forces material output |
| Naivete causes trouble | Oracle advisories at session/phase/close, WIP limits, governance gates | **Partial** — warns about patterns but doesn't TEACH canonical knowledge |
| Lost in labyrinth | Patchbay briefing, ontology/routing, cluster-based navigation | **Partial** — maps tool landscape but not conceptual knowledge |
| Grow & commodify process | Pattern mining, process kit export, fleet dashboard, Gemini extension | **Partial** — mines patterns but doesn't connect to canonical best practices |

**Core gap**: The Oracle knows WHAT you're doing wrong but doesn't know WHY the right way exists. It lacks a curated knowledge base of canonical software engineering, business, and philosophical wisdom.

---

## Implementation Plan

### Step 1: Wisdom Corpus — the knowledge foundation

**Create `conductor/wisdom/` package** — a static, curated knowledge base that the Oracle draws from contextually.

**New files:**
- `conductor/wisdom/__init__.py` — `WisdomEntry` dataclass + `WisdomCorpus` loader with in-memory cache
- `conductor/wisdom/engineering.yaml` — ~40 entries: SOLID, TDD, 12-factor, CI/CD, test pyramid, semantic versioning, design patterns, anti-patterns (God Object, Premature Optimization, Big Bang), phase-specific practices
- `conductor/wisdom/business.yaml` — ~20 entries: MVP/MLP, ship speed vs polish, 80/20, effort-vs-impact, sunk cost, portfolio strategy, flywheel effects
- `conductor/wisdom/philosophical.yaml` — ~15 entries: Scylla & Charybdis, Daedalus, Solve et Coagula, counterpoint, wabi-sabi, mise en place, alchemical metaphors

**WisdomEntry structure:**
```python
@dataclass
class WisdomEntry:
    id: str                    # "solid.single_responsibility"
    domain: str                # "engineering" | "business" | "philosophical"
    principle: str             # "Single Responsibility Principle"
    summary: str               # One-line description
    teaching: str              # 2-3 sentences: WHY this matters
    metaphor: str              # Rich philosophical framing
    triggers: list[str]        # When to surface: ["scope_complex", "multi_concern"]
    phase_relevance: list[str] # ["SHAPE", "BUILD"]
    severity_hint: str         # Default severity
    tags: list[str]            # For filtering
```

**WisdomCorpus API:**
- `query(triggers, phase, domain, limit)` — match wisdom entries to current context
- `get_by_id(entry_id)` — direct lookup
- `random_insight(phase)` — serendipitous wisdom for narrative enrichment
- Lazy-loads YAML, caches in memory (~75 entries, <10ms load)

**Modify:** `conductor/constants.py` — add `WISDOM_DIR = BASE / "conductor" / "wisdom"`

---

### Step 2: Mastery Ledger — tracking growth

**Extend Oracle state file** (`.conductor-oracle-state.json`) with a `mastery` section:

```python
"mastery": {
    "encountered": {"wisdom_id": {"first_seen": "...", "times_shown": N, "last_shown": "..."}},
    "internalized": {"wisdom_id": {"at": "...", "evidence": "..."}},
    "growth_areas": ["wisdom_id_1", "wisdom_id_2"],
    "mastery_score": 0.0
}
```

**Add to `conductor/oracle.py`** (Oracle class):
- `_load_mastery()` / `_save_mastery()` — read/write mastery section
- `_record_wisdom_shown(wisdom_id)` — increment encounter counter
- `_check_internalization(wisdom_id)` — detect behavioral change (e.g., TDD internalized if last 3 sessions had tests)
- `get_mastery_report()` — public API returning growth state

---

### Step 3: Guardian Angel Engine — the wisdom wrapper

**New file: `conductor/guardian.py`** — wraps Oracle with the seven Guardian Angel capabilities.

```python
class GuardianAngel:
    def __init__(self, oracle: Oracle | None = None):
        self.oracle = oracle or Oracle()
        self.corpus = WisdomCorpus()

    def counsel(self, context, *, max_advisories=8, include_wisdom=True) -> list[Advisory]:
        """Enhanced consult: Oracle detectors + wisdom enrichment + mastery tracking."""

    def whisper(self, action_description: str, context=None) -> Advisory | None:
        """Lightweight ambient guidance — returns None if no warning needed."""

    def teach(self, topic: str) -> dict:
        """On-demand: look up a principle, explain pedagogically, show user's history with it."""

    def landscape(self, decision: str, context=None) -> dict:
        """Map risk-reward poles for a decision with personalized positioning."""

    def growth_report(self) -> dict:
        """Full growth report: mastered, practicing, trajectory."""
```

**How `counsel()` works:**
1. Calls `oracle.consult()` for all existing detector advisories
2. Enriches each advisory with matching wisdom entries (adds `teaching` + `metaphor`)
3. Generates 1-2 standalone wisdom advisories from corpus based on phase/context
4. Skips wisdom already internalized (mastery ledger check)
5. Records wisdom shown (mastery tracking)
6. Returns combined, sorted advisory list

**How `whisper()` works:**
- Fast path: checks action description against wisdom triggers
- Returns a single advisory with contextual warning + wisdom reference, or None
- Designed to be called frequently with minimal overhead

---

### Step 4: Extend Advisory and OracleProfile dataclasses

**In `conductor/oracle.py`**, add backward-compatible fields:

```python
# Advisory — new fields
wisdom_id: str = ""            # Reference to WisdomEntry
teaching: str = ""             # Pedagogical explanation
mastery_note: str = ""         # "You've encountered this 5 times..."

# OracleProfile — new fields
mastery_score: float = 0.0
principles_encountered: int = 0
principles_internalized: int = 0
top_growth_areas: list[str] = field(default_factory=list)
learning_velocity: str = "starting"  # starting | growing | plateau | mastering
```

---

### Step 5: New Detectors (wisdom-powered)

Add to `DETECTOR_REGISTRY` in `conductor/oracle.py`:

| Detector | Category | Phase | Purpose |
|---|---|---|---|
| `canonical_practice` | wisdom | context | Surface engineering principles relevant to current phase/behavior |
| `business_insight` | business | context | MVP/shipping/effort wisdom based on project state |
| `mastery_progress` | growth | stateless | Growth trajectory updates and celebration |

Each follows existing pattern: register in `DETECTOR_REGISTRY`, implement `_detect_*()` method, return `list[Advisory]`.

**`canonical_practice`**: Queries `WisdomCorpus` with triggers derived from current phase + behavioral signals (no tests → TDD, complex scope → SRP, long build → small commits). Skips internalized wisdom.

**`business_insight`**: Checks project age, promotion state, session count — surfaces MVP thinking for new repos, shipping urgency for stuck CANDIDATEs, portfolio balancing for organ-heavy users.

**`mastery_progress`**: Compares mastery ledger snapshots, celebrates milestones ("You've internalized 5 principles"), identifies stalled growth areas.

---

### Step 6: CLI and MCP Integration

**CLI** (modify `conductor/cli.py` and `conductor/commands/oracle_cmd.py`):

```
conductor oracle counsel              # Guardian Angel enhanced consult
conductor oracle teach <topic>        # On-demand teaching
conductor oracle landscape <decision> # Risk-reward mapping
conductor oracle whisper <action>     # Quick guidance check
conductor oracle mastery              # Growth report
conductor oracle corpus [search]      # Browse/search wisdom corpus
```

**MCP** (modify `mcp_server.py`) — 5 new tools:

```
conductor_guardian_counsel    # Full counsel with wisdom
conductor_guardian_whisper    # Ambient guidance
conductor_guardian_teach      # On-demand teaching
conductor_guardian_landscape  # Risk-reward mapping
conductor_guardian_mastery    # Growth report
```

---

### Step 7: Session Integration

**Modify `conductor/session.py`** — replace Oracle calls with GuardianAngel:

- `start()`: `guardian.counsel()` instead of `oracle.consult()` — includes phase-appropriate wisdom for session start
- `phase()`: `guardian.counsel()` with gate_mode — includes canonical practice advice for the target phase
- `close()`: `guardian.counsel()` — includes mastery progress update + retrospective wisdom

GuardianAngel composes with Oracle, so all existing detector behavior is preserved.

---

### Step 8: Patchbay Integration

**Modify `conductor/patchbay.py`** — add Guardian Angel section to briefing:

- Current mastery score + learning velocity
- Top 3 growth areas
- One contextual wisdom insight
- Recent mastery milestones (if any)

---

### Step 9: Tests

**New file: `tests/test_guardian.py`**
- `TestWisdomEntry` — dataclass construction, YAML loading
- `TestWisdomCorpus` — query by triggers, phase, domain; get_by_id; random_insight; empty/malformed corpus handling
- `TestGuardianAngel` — counsel wraps consult; whisper returns None when safe; teach returns pedagogical content; landscape maps poles; growth_report structure
- `TestMasteryLedger` — record_wisdom_shown, check_internalization, mastery_score computation, persistence across instances

**Extend `tests/test_oracle.py`**:
- New Advisory/OracleProfile fields backward-compatible
- New detectors in DETECTOR_REGISTRY
- `canonical_practice`, `business_insight`, `mastery_progress` detector unit tests

---

## Critical Files

| File | Action | Purpose |
|---|---|---|
| `conductor/wisdom/__init__.py` | CREATE | WisdomEntry + WisdomCorpus loader |
| `conductor/wisdom/engineering.yaml` | CREATE | ~40 canonical engineering entries |
| `conductor/wisdom/business.yaml` | CREATE | ~20 business wisdom entries |
| `conductor/wisdom/philosophical.yaml` | CREATE | ~15 philosophical wisdom entries |
| `conductor/guardian.py` | CREATE | GuardianAngel engine (counsel, whisper, teach, landscape) |
| `conductor/oracle.py` | MODIFY | Mastery ledger methods, 3 new detectors, extended dataclasses |
| `conductor/constants.py` | MODIFY | Add WISDOM_DIR constant |
| `conductor/cli.py` | MODIFY | New oracle subcommands (counsel, teach, landscape, whisper, mastery, corpus) |
| `conductor/commands/oracle_cmd.py` | MODIFY | Dispatch for new subcommands |
| `mcp_server.py` | MODIFY | 5 new Guardian Angel MCP tools |
| `conductor/session.py` | MODIFY | Swap oracle → guardian at 3 integration points |
| `conductor/patchbay.py` | MODIFY | Add Guardian Angel section to briefing |
| `conductor/__init__.py` | MODIFY | Export GuardianAngel, WisdomCorpus |
| `tests/test_guardian.py` | CREATE | Full test suite for wisdom + guardian |
| `tests/test_oracle.py` | MODIFY | Tests for new detectors + backward compat |

---

## Verification

1. **Unit tests**: `python3 -m pytest tests/test_guardian.py tests/test_oracle.py -v`
2. **Existing tests pass**: `python3 -m pytest tests/ -v` — no regressions
3. **CLI smoke test**: `python3 -m conductor oracle counsel` — returns wisdom-enriched advisories
4. **CLI teach**: `python3 -m conductor oracle teach tdd` — returns pedagogical response
5. **CLI mastery**: `python3 -m conductor oracle mastery` — returns growth report
6. **Doctor check**: `python3 -m conductor doctor --strict` — no new issues
7. **Corpus validation**: `python3 -c "from conductor.wisdom import WisdomCorpus; c = WisdomCorpus(); print(len(c._entries))"` — prints ~75
