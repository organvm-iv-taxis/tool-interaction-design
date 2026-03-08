# Plan: Activate the Conductor as the Interaction Buffer

**Date**: 2026-03-07
**Status**: IMPLEMENTED

## What Was Done

### Step 1: Fix Conductor Startup
- Modified `conductor/schemas.py` and `conductor/contracts.py` to degrade gracefully when `jsonschema` is not installed (skip validation instead of raising errors)
- `python3 -m conductor patch --json` now produces valid JSON output

### Step 2: Add MCP Tools for Session Lifecycle
- Added 3 new MCP tools to `mcp_server.py`:
  - `conductor_session_start` — wraps SessionEngine.start()
  - `conductor_session_transition` — wraps SessionEngine.phase() (hard gate enforcement)
  - `conductor_gate_check` — wraps GuardianAngel.counsel(gate_mode=True)
- Registered in `~/.claude/mcp.json`

### Step 3: Add Claude Code Hook for Ambient Phase Awareness
- Created `hooks/claude-prompt-gate.sh` — reads session.json, emits phase context
- Detects implementation keywords during FRAME/SHAPE and emits [GATE] warning
- Registered in `~/.claude/settings.json` as UserPromptSubmit hook

### Step 4: Add Oracle Detectors for Process Anti-Patterns
- Added 5 new detectors to `conductor/oracle.py`:
  - `no_session` — blocks when no session exists (gate_action="block")
  - `phase_skip` — warns when session phase doesn't match intent (gate_action="warn")
  - `context_switching` — warns when 3+ organs in last 5 sessions
  - `infrastructure_gravity` — cautions when >70% of sessions target META/IV
  - `session_fragmentation` — cautions when last 5 sessions all under 5 minutes
- Added threshold constants to `conductor/constants.py`
- Registered in DETECTOR_REGISTRY and wired into consult()

### Step 5: Update CLAUDE.md Session Protocol
- Updated `~/Workspace/CLAUDE.md` with Conductor-first session protocol
- Updated `~/Workspace/meta-organvm/CLAUDE.md` with Conductor instructions
- Created `~/.claude/mcp.json` to register the Conductor MCP server

## Files Modified
- `conductor/schemas.py` — graceful degradation
- `conductor/contracts.py` — graceful degradation
- `conductor/constants.py` — anti-pattern thresholds
- `conductor/oracle.py` — 5 new detectors
- `mcp_server.py` — 3 new MCP tools + dispatch
- `hooks/claude-prompt-gate.sh` — new hook script
- `~/.claude/settings.json` — hook registration
- `~/.claude/mcp.json` — MCP server registration
- `~/Workspace/CLAUDE.md` — session protocol
- `~/Workspace/meta-organvm/CLAUDE.md` — session protocol

## Verification Results
1. `python3 -m conductor patch --json` ✅ produces valid JSON
2. `conductor session start --organ III --repo peer-audited --scope "test"` ✅ creates session
3. `conductor session phase build` from FRAME ✅ FAILS (hard gate works)
4. FRAME→SHAPE→BUILD ✅ succeeds
5. MCP tools registered and functional ✅
6. Hook reads session state and outputs phase context ✅
7. Oracle detectors fire: no_session ✅, phase_skip ✅
