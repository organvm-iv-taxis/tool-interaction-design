# Conductor Auto-Start & Session Runway

**Date:** 2026-03-09
**Status:** SHIPPED
**Commit:** 8aba332

## What was built

1. **Multi-session support** — Sessions stored in `active-sessions/{agent}.json`. Different agents coexist. Legacy `session.json` becomes a symlink (backward compat). Auto-migration on first access.

2. **Preflight module** (`conductor/preflight.py`) — Core logic: `run_preflight()` infers organ/repo from cwd, checks active sessions + coordination claims, detects collisions, builds runway briefing (work queue, oracle advisory, fleet recommendation), auto-starts session.

3. **CLI** — `conductor preflight --agent claude --cwd $PWD [--json] [--no-start]`

4. **MCP tools** — `conductor_preflight`, `conductor_active_sessions`

5. **Hooks** — Claude hook (`claude-prompt-gate.sh`) now calls preflight when venv available. New `codex-preflight.sh` for non-Claude agents.

## Files changed

- 3 created: `preflight.py`, `commands/preflight_cmd.py`, `hooks/codex-preflight.sh`
- 7 modified: `constants.py`, `session.py`, `parser.py`, `commands/__init__.py`, `hooks/claude-prompt-gate.sh`, `mcp_server.py`
- 4 test fixtures updated for `ACTIVE_SESSIONS_DIR`
- 560 tests pass
