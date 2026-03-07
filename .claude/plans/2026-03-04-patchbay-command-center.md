# Plan: The Patchbay — Conductor's Command Center

## Context

The conductor system (3 layers, 62 tests, v0.4.0) is built. But starting work means navigating between `conductor session`, `conductor wip`, `conductor audit`, `conductor patterns`, `router.py`, registry JSON, stats files, etc. There's no single "patch in" point. The user wants one location — the patchbay — where the puppeteer sees all strings and can pull any of them. Every session starts the same way: `conductor patch`.

The metaphor is from audio engineering. A patchbay is a panel of jacks. You walk up, see what's routed where, plug in cables, and start. You don't *live* in it — you read it, then act.

---

## Architecture

```
conductor patch
    |
    +-- SessionEngine    → active session / last closed
    +-- GovernanceRuntime → registry counts, WIP violations
    +-- WorkQueue (NEW)  → prioritized action items from registry state
    +-- ProductExtractor → lifetime stats, patterns
    +-- Ontology         → routing intelligence for current task
    |
    v
  Structured briefing (text or JSON)
```

Two new modules. Zero new dependencies. Read-only command (never mutates state).

---

## New Files

### 1. `conductor/workqueue.py` (~120 lines)

Computes a prioritized work queue from registry state. No stored file — computed fresh each invocation.

```python
@dataclass
class WorkItem:
    priority: str          # CRITICAL, HIGH, MEDIUM, LOW
    category: str          # wip_violation, stale, missing_ci, promotion_ready
    organ: str
    repo: str | None
    description: str
    suggested_command: str
    score: int             # sort key (higher = more urgent)

class WorkQueue:
    def __init__(self, gov: GovernanceRuntime): ...
    def compute(self, organ_filter: str | None = None) -> list[WorkItem]: ...
```

Scoring methods (in priority order):
| Method | Score | Trigger |
|--------|-------|---------|
| `_wip_violations()` | 100 | Organ exceeds CANDIDATE or PUBLIC_PROCESS limit |
| `_stale_candidates()` | 70 | CANDIDATE with `last_validated` > 30 days old |
| `_missing_infrastructure()` | 40 | Repo with empty `ci_workflow` or `documentation_status` = EMPTY |
| `_promotion_candidates()` | 20 | LOCAL repos with docs deployed (ready to promote) |

Each item includes a `suggested_command` — a runnable `conductor` invocation.

### 2. `conductor/patchbay.py` (~250 lines)

The command center. Composes all layers into a structured briefing.

```python
class Patchbay:
    def __init__(self, ontology=None, engine=None): ...

    def briefing(self, organ_filter=None) -> dict:
        """Full system briefing."""
        return {
            "timestamp": ...,
            "session": self._session_section(),
            "pulse": self._pulse_section(organ_filter),
            "queue": self._queue_section(organ_filter),
            "stats": self._stats_section(),
            "suggested_action": self._suggest_next(),
        }

    def format_text(self, data: dict) -> str: ...
    def format_json(self, data: dict) -> str: ...
```

Key design decisions:
- **No network calls.** Uses only local files (registry, session state, stats). Completes in <200ms.
- **Plain text output.** No `rich`, no `curses`. Output readable by both human and Claude Code.
- **Active session changes the view.** When a session is active, shows session context + routing suggestions instead of "suggested next action."

### 3. Modified Files

**`conductor/cli.py`** — Add `patch` subcommand:
```
conductor patch                  # Full briefing
conductor patch pulse            # System pulse only
conductor patch queue            # Work queue only
conductor patch stats            # Lifetime stats only
conductor patch --json           # Machine-readable output
conductor patch --organ III      # Filter to one organ
```

**`conductor/session.py`** — Extend `_update_stats()` to track:
- `streak`: consecutive SHIPPED sessions (resets on CLOSED)
- `last_session_id`: for "last closed" display
- `recent_sessions`: last 10 `{session_id, result, organ, duration_minutes}` entries

**`conductor/__init__.py`** — Export `Patchbay`, `WorkQueue`, `WorkItem`. Bump `__version__` to `"0.5.0"`.

**`mcp_server.py`** — Add `conductor_patch` tool returning JSON briefing.

---

## Terminal Output

### No active session:
```
  PATCHBAY                                          2026-03-04 14:22 UTC
  ======================================================================

  SESSION: none active
  Last closed: 2026-03-03-III-auth-middleware-a3f2c1 (SHIPPED, 47m)

  PULSE
  --------------------------------------------------------------------
  ORGAN         REPOS  CAND  PUB   GRAD  ARCH   FLAGS
  I  Theoria      20    11    4     0     3     CAND>3
  II Poiesis      30    22    2     0     4     CAND>3
  III Ergon       27    11   13     0     2     CAND>3, PUB>1
  IV Taxis         7     5    2     0     0     CAND>3
  V  Logos         2     1    1     0     0
  VI Koinonia      6     0    6     0     0
  VII Kerygma      4     0    0     4     0
  META             7     5    1     0     1     CAND>3
  --------------------------------------------------------------------
  5 organs over WIP limit | 55 CANDIDATE system-wide

  QUEUE (top 5 of 15)
  --------------------------------------------------------------------
  !!  ORGAN-II: 22 CANDIDATE (limit 3) — triage required
      -> conductor audit --organ II
  !!  ORGAN-III: 11 CANDIDATE (limit 3)
      -> conductor audit --organ III
  !   repo-x: stale CANDIDATE (last validated 45d ago)
      -> conductor wip promote repo-x PUBLIC_PROCESS
  .   repo-y: LOCAL, docs deployed — ready for CANDIDATE
      -> conductor wip promote repo-y CANDIDATE
  .   repo-z: missing CI workflow
      -> add ci-python.yml
  --------------------------------------------------------------------

  STATS
  --------------------------------------------------------------------
  Sessions: 14 | Hours: 11.2 | Ship rate: 71% | Streak: 3

  NEXT ACTION
  --------------------------------------------------------------------
  Triage ORGAN-II CANDIDATE backlog (22 repos, largest overage).
  -> conductor session start --organ II --repo <pick> --scope "triage"
```

### Active session:
```
  PATCHBAY                                          2026-03-04 14:22 UTC
  ======================================================================

  SESSION: ACTIVE
  --------------------------------------------------------------------
  2026-03-04-III-auth-middleware-a3f2c1
  ORGAN-III | classroom-rpg-aetheria | "Add auth middleware"
  Phase: BUILD (23m) | Role: Implementer + Tester
  Clusters: claude_code_core, code_execution, code_quality_cli, git_core
  FRAME(8m) -> SHAPE(12m) -> BUILD(23m*)
  -> Next: conductor session phase prove

  PULSE (abbreviated)
  --------------------------------------------------------------------
  System: 111 repos | 5 organs over WIP | ORGAN-III: CAND>3, PUB>1

  STATS
  --------------------------------------------------------------------
  Sessions: 14 | Hours: 11.2 | Ship rate: 71% | Streak: 3
```

---

## Auto-Patch Integration (multi-assistant)

The patchbay should auto-brief on session start, and work across AI assistants (Claude Code, Cursor, Windsurf, Copilot, etc.).

### Layer A: Workspace instruction file

Add to `/Users/4jp/Workspace/CLAUDE.md` (and any future `.cursorrules`, `AGENTS.md`, etc.):

```markdown
## Session Start Protocol

Before beginning any work session in this workspace, run:
    python3 -m conductor patch --json
Read the output to understand system state, active sessions, and work queue.
Use this context to inform your responses and suggestions.
```

This is assistant-agnostic — any AI that reads the workspace instruction file will execute the same command. The `--json` flag ensures structured output that any assistant can parse.

### Layer B: Claude Code hook

Configure a Claude Code `user_prompt_submit` hook in project settings that runs the patchbay on first prompt of a conversation. File: `/Users/4jp/.claude/projects/-Users-4jp-Workspace-tool-interaction-design/hooks.json`:

```json
{
  "hooks": {
    "user_prompt_submit": [
      {
        "matcher": "",
        "command": "python3 -m conductor patch 2>/dev/null || true"
      }
    ]
  }
}
```

This prints the text briefing before Claude Code processes the first message. The `|| true` ensures it never blocks if conductor isn't installed.

### Layer C: Shell alias (human-facing)

Add to user's shell config (via chezmoi):
```zsh
alias patch="python3 -m conductor patch"
alias pj="python3 -m conductor patch --json"
```

So the human can type `patch` at any terminal to get the briefing.

---

## Build Sequence

1. **`workqueue.py`** — WorkItem dataclass + WorkQueue class with 4 scoring methods
2. **`patchbay.py`** — Patchbay class composing all layers, text + JSON formatters
3. **`cli.py`** — Add `patch` subcommand with pulse/queue/stats sub-views, `--json`, `--organ`
4. **`session.py`** — Extend `_update_stats()` for streak, last_session_id, recent_sessions
5. **`__init__.py`** — Exports + version bump
6. **`mcp_server.py`** — Add `conductor_patch` MCP tool
7. **`tests/test_patchbay.py`** — 12+ tests covering briefing, queue scoring, formatting, stats
8. **Workspace CLAUDE.md** — Add Session Start Protocol section
9. **Claude Code hooks** — Configure `user_prompt_submit` hook for auto-patch

---

## Verification

```bash
# Unit tests
source .venv/bin/activate && python -m pytest tests/ -v

# Manual: full briefing with real registry
python -m conductor patch

# Manual: queue for one organ
python -m conductor patch queue --organ III

# Manual: JSON pipe
python -m conductor patch --json | python -m json.tool

# Manual: active session context
python -m conductor session start --organ III --repo test --scope "test" --no-branch
python -m conductor patch
python -m conductor session close
```
