# Full-Scope Dispatch Integration — Closing the Three Gaps

## Context

The dispatch engine is built and tested (620 tests, 3 MCP tools, CLI commands). What's missing is the ambient wiring that makes it operational without the user remembering to invoke anything.

Three gaps:
1. Claude doesn't check dispatch before starting work
2. Receiving agents (Gemini/Codex) don't see handoff constraints
3. Return-to-Claude doesn't trigger cross-verification

## Architecture: The Dispatch Loop

```
USER describes work
        │
        ▼
[1] PREFLIGHT checks dispatch ──► "This is boilerplate → dispatch to Codex"
        │                                    │
        ▼                                    ▼
  Claude does strategic work    [2] Handoff envelope written to:
        │                         .conductor/active-handoff.md
        │                         (symlinked into GEMINI.md / AGENTS.md)
        │                                    │
        │                                    ▼
        │                         User opens Codex/Gemini
        │                         Agent reads constraints automatically
        │                         Agent does the work
        │                                    │
        │                                    ▼
        │                         User returns to Claude
        │                                    │
        ▼                                    ▼
[3] PREFLIGHT detects unverified handoff ──► "Gemini completed work. Cross-verify required."
        │
        ▼
  Claude runs cross_verify against the envelope
  Reports violations or clears the handoff
```

## Gap 1: Claude Dispatch-Awareness

### Mechanism: Preflight dispatch guidance + CLAUDE.md directive

**A. Extend `preflight.py` — add dispatch scan**

Add a `_get_dispatch_guidance()` function that:
1. Reads the current session scope (if session exists)
2. Calls `TaskDispatcher.classify()` on the scope description
3. If the work type routes to a non-Claude agent, includes dispatch guidance in the preflight result

New fields on `PreflightResult`:
```python
dispatch_work_type: str | None = None
dispatch_recommended_agent: str | None = None
dispatch_guidance: str | None = None
```

The `_print_briefing()` function renders this as:
```
[DISPATCH] Work classified as: boilerplate_generation (mechanical)
[DISPATCH] Recommended agent: Codex CLI (score: 0.78)
[DISPATCH] Generate handoff: conductor fleet dispatch --work-type boilerplate_generation
```

**B. Extend `claude-prompt-gate.sh` — dispatch keyword detection**

Add dispatch detection alongside the existing phase-gate logic. When the user's prompt contains dispatch-triggering keywords during BUILD phase:

```bash
# Dispatch detection: if prompt describes mechanical work, suggest dispatch
dispatch_keywords = ['scaffold', 'boilerplate', 'stub', 'template', 'bulk', 'migrate naming']
if phase == 'BUILD' and any(kw in prompt for kw in dispatch_keywords):
    print(f'[DISPATCH] This may be dispatchable work. Check: conductor_fleet_dispatch')
```

**C. Add directive to CLAUDE.md**

Add a "Dispatch Protocol" section to `CLAUDE.md`:
```markdown
## Dispatch Protocol

Before starting BUILD-phase work, call `conductor_fleet_dispatch` with a description
of the task. If the recommended agent is NOT Claude:
1. Call `conductor_fleet_guardrailed_handoff` to generate an envelope
2. Present the envelope markdown to the user
3. Tell the user which agent to hand it to
4. Do NOT do the work yourself — reserve your tokens for strategic work

This is not optional. The system is designed for force multiplication: Claude handles
architecture, audit, governance. Mechanical work goes to the bench.
```

### Files changed:
- `conductor/preflight.py` — add `_get_dispatch_guidance()`, extend `PreflightResult`, extend `_print_briefing()`
- `hooks/claude-prompt-gate.sh` — add dispatch keyword detection
- `CLAUDE.md` — add Dispatch Protocol section

## Gap 2: Receiving Agents Auto-Read Handoff

### Mechanism: `.conductor/active-handoff.md` + context file injection

**A. Active handoff file**

When Claude generates a `GuardrailedHandoffBrief`, write it to a stable path:
```
.conductor/active-handoff.md
```

This replaces the timestamped `handoff-{timestamp}.md` as the canonical "current handoff" file. The timestamped files remain as the log. The `active-handoff.md` is the one receivers read.

Add to `fleet_handoff.py`:
```python
def write_active_handoff(brief: GuardrailedHandoffBrief, repo_path: Path) -> Path:
    """Write the active handoff to the canonical path receivers read."""
    handoff_dir = repo_path / ".conductor"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    out_path = handoff_dir / "active-handoff.md"
    out_path.write_text(format_markdown(brief))
    return out_path

def clear_active_handoff(repo_path: Path) -> None:
    """Clear the active handoff after verification passes."""
    path = repo_path / ".conductor" / "active-handoff.md"
    if path.exists():
        path.unlink()
```

The MCP tool `conductor_fleet_guardrailed_handoff` calls `write_active_handoff()` automatically.

**B. Inject into GEMINI.md**

Add to the bottom of `GEMINI.md`:
```markdown
## Active Handoff

If `.conductor/active-handoff.md` exists, READ IT FIRST before doing any work.
It contains constraints, locked files, conventions, and completed work from the
originating agent. You MUST honor all constraints listed there.

If the handoff says "CROSS-VERIFICATION REQUIRED", your self-assessment will
NOT be trusted. A different agent will verify your output.
```

**C. Inject into AGENTS.md**

Add the same section to `AGENTS.md` (read by Codex, OpenCode):
```markdown
## Active Handoff

If `.conductor/active-handoff.md` exists, read it before starting work.
It contains constraints you must honor, files you must not modify, and
conventions you must follow. Violating these constraints will cause your
work to be rejected during cross-verification.
```

**D. Gitignore the active handoff**

Add `.conductor/active-handoff.md` to `.gitignore` — it's transient state, not committed.

### Files changed:
- `conductor/fleet_handoff.py` — add `write_active_handoff()` and `clear_active_handoff()`
- `mcp_server.py` — `fleet_guardrailed_handoff()` calls `write_active_handoff()` automatically
- `GEMINI.md` — add Active Handoff section
- `AGENTS.md` — add Active Handoff section
- `.gitignore` — add `.conductor/active-handoff.md`

## Gap 3: Return-to-Claude Verification

### Mechanism: Preflight detects pending verification + gate warning

**A. Extend preflight to check for unverified handoffs**

Add `_check_pending_verification()` to `preflight.py`:

1. Check if `.conductor/active-handoff.md` exists
2. If it does, read the `to_agent` field — this handoff hasn't been verified yet
3. Add a gate warning: "Unverified handoff from {from_agent} to {to_agent} exists. Run cross-verification before proceeding."
4. Add to `PreflightResult`:
```python
pending_verification: bool = False
pending_handoff_from: str | None = None
pending_handoff_to: str | None = None
```

**B. Extend `_print_briefing()` to render verification prompt**

```
[VERIFY] Pending handoff: claude → gemini (boilerplate_generation)
[VERIFY] Cross-verification required. Run: conductor_fleet_cross_verify
[VERIFY] Check the git diff against handoff constraints before proceeding.
```

**C. Add to CLAUDE.md Dispatch Protocol section**

```markdown
### Verification on Return

When preflight shows a pending verification, you MUST:
1. Run `git diff` to see what the dispatched agent changed
2. Call `conductor_fleet_cross_verify` with the changed files
3. If violations found, fix them before continuing
4. If passed, the active handoff is cleared automatically
```

**D. Auto-clear on verification pass**

When `fleet_cross_verify()` in `mcp_server.py` returns `passed: true`, call `clear_active_handoff()` to remove `.conductor/active-handoff.md`. This closes the loop — the next preflight won't show a pending verification.

### Files changed:
- `conductor/preflight.py` — add `_check_pending_verification()`, extend `PreflightResult`, extend `_print_briefing()`
- `mcp_server.py` — `fleet_cross_verify()` calls `clear_active_handoff()` on pass
- `CLAUDE.md` — add Verification on Return section

## Summary of All File Changes

| File | Action | Gap |
|------|--------|-----|
| `conductor/preflight.py` | **MODIFY** — dispatch guidance + pending verification check | 1, 3 |
| `conductor/fleet_handoff.py` | **MODIFY** — add `write_active_handoff()` + `clear_active_handoff()` | 2 |
| `mcp_server.py` | **MODIFY** — auto-write active handoff, auto-clear on verify pass | 2, 3 |
| `hooks/claude-prompt-gate.sh` | **MODIFY** — dispatch keyword detection | 1 |
| `CLAUDE.md` | **MODIFY** — add Dispatch Protocol + Verification on Return sections | 1, 3 |
| `GEMINI.md` | **MODIFY** — add Active Handoff section | 2 |
| `AGENTS.md` | **MODIFY** — add Active Handoff section | 2 |
| `.gitignore` | **MODIFY** — add active-handoff.md | 2 |
| `tests/test_preflight_dispatch.py` | **CREATE** — test dispatch guidance + verification detection | 1, 3 |
| `tests/test_active_handoff.py` | **CREATE** — test write/clear/read cycle | 2 |

## User's Daily Workflow After Integration

**Starting work (Claude):**
```
$ claude
[CONDUCTOR] Runway Briefing — IV/tool-interaction-design
[DISPATCH] Scope classified as: boilerplate_generation (mechanical)
[DISPATCH] Recommended: Codex CLI (0.78). Consider dispatching.
```

Claude sees this and says: "This work should go to Codex. Let me generate the handoff."
Claude calls `conductor_fleet_guardrailed_handoff` → envelope written to `.conductor/active-handoff.md`
Claude presents the envelope to the user.

**Dispatching (user switches to Codex):**
```
$ codex
```
Codex reads `AGENTS.md` → sees "If `.conductor/active-handoff.md` exists, read it first"
Codex reads the handoff → sees constraints, locked files, conventions
Codex does the work within constraints.

**Returning (user switches back to Claude):**
```
$ claude
[CONDUCTOR] Runway Briefing — IV/tool-interaction-design
[VERIFY] Pending handoff: claude → codex (boilerplate_generation)
[VERIFY] Cross-verification required before proceeding.
```

Claude sees the pending verification, runs `git diff`, calls `conductor_fleet_cross_verify`.
If passed → active handoff cleared, Claude proceeds with strategic work.
If violations → Claude fixes them, then clears.

**Net effect:** Claude's tokens go to architecture, audit, and verification. Codex/Gemini do the volume. The user's full bench is utilized. Claude stays in the game longer.

## Verification Plan

1. `python3 -m pytest tests/test_preflight_dispatch.py tests/test_active_handoff.py -v`
2. `python3 -m pytest tests/ -q` — full suite still green
3. CLI: `python3 -m conductor fleet dispatch --description "scaffold test stubs" --phase BUILD`
4. CLI: `python3 -m conductor preflight --agent claude --json` — check dispatch_guidance field
5. Write active handoff, verify file exists at `.conductor/active-handoff.md`
6. Run preflight again, verify pending_verification detected
7. Run cross-verify with clean files, verify active handoff cleared
8. Grep GEMINI.md and AGENTS.md for "active-handoff" directive
