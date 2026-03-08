# Agent Fleet Orchestration System

## Context

Every paid AI subscription (Claude Max, Gemini Pro, OpenAI Plus/Codex) has billing-period allotments that go partially unused. Tasks get routed to whichever agent happens to be open, not whichever is best suited. There's no visibility into utilization, no structured handoff when switching agents mid-task, and no mechanism to ensure every dollar spent delivers value. This plan builds the infrastructure to treat the full agent fleet as interlocking cogs — tracked, routed, and handed off systematically.

**Pain points addressed:** wasted capacity, wrong-agent-wrong-task, no visibility, context switching cost.

## Architecture

All new code lives in `~/Workspace/organvm-iv-taxis/tool-interaction-design/conductor/`. The system adds 5 new modules + 1 YAML config + modifications to 5 existing files.

### New Files

#### 1. `fleet.yaml` — Agent Fleet Registry
Declares every agent with subscription details, capabilities, and phase affinity.

```yaml
agents:
  claude:
    display_name: "Claude Code (Opus 4.6)"
    provider: anthropic
    subscription:
      tier: max
      billing_cycle: monthly
      allotment:
        messages_per_day: 45  # Opus messages
        context_window: 200000
    capabilities:
      strengths: [deep-coding, refactoring, architecture, testing, mcp-tools]
      weaknesses: [web-browsing-native, image-generation]
    phase_affinity:
      FRAME: 0.7
      SHAPE: 0.9
      BUILD: 1.0
      PROVE: 0.9
    sensitivity:
      can_see_secrets: true
      can_push_git: true
      can_run_shell: true
    active: true

  gemini:
    display_name: "Gemini CLI (2.5 Pro)"
    provider: google
    subscription:
      tier: pro
      billing_cycle: monthly
      allotment:
        requests_per_day: 25  # deep research
        context_window: 1000000
    capabilities:
      strengths: [deep-research, long-context, web-grounding, multi-modal]
      weaknesses: [file-editing-precision, git-safety]
    phase_affinity:
      FRAME: 1.0
      SHAPE: 0.8
      BUILD: 0.5
      PROVE: 0.6
    sensitivity:
      can_see_secrets: false
      can_push_git: false
      can_run_shell: true
    active: true

  codex:
    display_name: "Codex CLI (GPT-5.3)"
    provider: openai
    subscription:
      tier: plus
      billing_cycle: monthly
      allotment:
        messages_per_month: 750
        context_window: 200000
    capabilities:
      strengths: [parallel-agents, sandbox-execution, rapid-prototyping, multi-file-edits]
      weaknesses: [mcp-tool-depth, long-context-reasoning]
    phase_affinity:
      FRAME: 0.6
      SHAPE: 0.7
      BUILD: 0.9
      PROVE: 0.8
    sensitivity:
      can_see_secrets: true
      can_push_git: true
      can_run_shell: true
    active: true
```

Additional agents (goose, kimi, opencode) added as `active: false` stubs with minimal config.

#### 2. `fleet.py` — Core Data Model (~120 lines)
- Frozen dataclasses: `AgentAllotment`, `AgentCapabilities`, `AgentSensitivity`, `AgentSubscription`, `FleetAgent`
- `FleetRegistry` class: loads `fleet.yaml`, provides `get(name)`, `active_agents()`, `by_provider()`
- Pattern follows `policy.py` (frozen dataclass + YAML loader)

#### 3. `fleet_usage.py` — Usage Tracking (~150 lines)
- `UsageRecord` dataclass: agent, date, sessions, tokens_in, tokens_out, cost_usd
- `FleetUsageTracker` class:
  - Storage: `~/.conductor/fleet-usage/YYYY-MM/{agent}.jsonl` (append-only)
  - `record_session(agent, tokens_in, tokens_out, cost_usd)` — appends to JSONL
  - `get_period(agent, year, month)` → list of UsageRecord
  - `utilization_report(year, month)` → dict per agent with used/allotted/pct
  - `underutilized_agents(threshold=0.5)` → list of agents below threshold
  - `daily_snapshot()` → today's usage across all agents
- No async — plain synchronous file I/O (matches conductor patterns)

#### 4. `fleet_router.py` — Task-to-Agent Routing (~130 lines)
- `RouteScore` dataclass: agent, score, breakdown (dict of factor→value)
- `FleetRouter` class:
  - Constructor takes `FleetRegistry` + `FleetUsageTracker`
  - `recommend(phase, task_tags, sensitivity_required, context_size)` → sorted list of RouteScore
  - Scoring weights: phase_affinity=0.30, strength_match=0.20, utilization_pressure=0.20, context_fit=0.15, cost_efficiency=0.15
  - Hard filters: skip inactive agents, skip agents that can't meet sensitivity requirements
  - `utilization_pressure` = 1.0 - current_utilization (underused agents score higher)
  - `explain(route_score)` → human-readable string

#### 5. `fleet_handoff.py` — Context Handoff (~100 lines)
- `HandoffBrief` dataclass: from_agent, to_agent, session_id, phase, summary, key_files, decisions, open_questions, timestamp
- `generate_handoff(session, from_agent, to_agent, summary)` → HandoffBrief
- `format_markdown(brief)` → string (injected into agent context files)
- `write_handoff(brief, repo_path)` → writes `.conductor/handoff-{timestamp}.md`
- `log_handoff(brief)` → appends to `~/.conductor/handoff-log.jsonl`

#### 6. `commands/fleet_cmd.py` — CLI Commands (~100 lines)
```
conductor fleet status              # Show all agents, active/inactive, today's usage
conductor fleet usage [--month M]   # Utilization report for billing period
conductor fleet recommend <phase>   # Route recommendation for current context
conductor fleet handoff <to-agent>  # Generate handoff brief from active session
```

### Modified Files

#### `constants.py` — Add 3 paths
```python
FLEET_YAML = CONDUCTOR_DIR / "fleet.yaml"
FLEET_USAGE_DIR = CONDUCTOR_DATA / "fleet-usage"
HANDOFF_LOG = CONDUCTOR_DATA / "handoff-log.jsonl"
```

#### `session.py` — Usage hook in `close()` (~7 lines)
After writing session-log.yaml, call `fleet_usage.record_session()` with the closing session's agent and duration. Guarded by try/except so fleet tracking never breaks session lifecycle.

#### `patchbay.py` — Fleet section in patch output
Add `_fleet_section()` that renders active agents + today's utilization into the patch text block. Called from `build_patch()`.

#### `parser.py` — Fleet subparser
Add `fleet` subcommand group with `status`, `usage`, `recommend`, `handoff` subcommands.

#### `mcp_server.py` — 2 new MCP tools
- `conductor_fleet_status` — returns fleet status + utilization (no params)
- `conductor_fleet_recommend` — returns routing recommendation (params: phase, task_tags, sensitivity)

## Shipping Strategy (3 Increments)

### Increment 1: Registry + Usage Tracking
**Files:** fleet.yaml, fleet.py, fleet_usage.py, constants.py changes, session.py hook
**Verify:** `conductor fleet status` shows agents; closing a session writes usage JSONL

### Increment 2: Agent Routing
**Files:** fleet_router.py, fleet_cmd.py (recommend), mcp_server.py (recommend tool)
**Verify:** `conductor fleet recommend BUILD` returns scored agent list

### Increment 3: Context Handoff
**Files:** fleet_handoff.py, fleet_cmd.py (handoff), mcp_server.py (status tool)
**Verify:** `conductor fleet handoff gemini` generates markdown brief with session context

## Verification

1. **Unit tests:** `tests/test_fleet.py` — registry loading, usage tracking, router scoring, handoff generation
2. **Integration:** Start a session with `--agent claude`, close it, verify JSONL written. Run `conductor fleet status` to see utilization. Run `conductor fleet recommend FRAME` to get routing suggestion.
3. **MCP:** Call `conductor_fleet_status` and `conductor_fleet_recommend` from Claude Code to verify tool dispatch.
4. **Cross-agent:** Start session in Claude (FRAME), generate handoff brief, open Gemini CLI, verify brief is readable.

## Critical Files

| File | Action |
|------|--------|
| `conductor/fleet.yaml` | CREATE |
| `conductor/fleet.py` | CREATE |
| `conductor/fleet_usage.py` | CREATE |
| `conductor/fleet_router.py` | CREATE |
| `conductor/fleet_handoff.py` | CREATE |
| `conductor/commands/fleet_cmd.py` | CREATE |
| `conductor/constants.py` | MODIFY (3 path constants) |
| `conductor/session.py` | MODIFY (usage hook in close) |
| `conductor/patchbay.py` | MODIFY (fleet section) |
| `conductor/parser.py` | MODIFY (fleet subparser) |
| `tool-interaction-design/mcp_server.py` | MODIFY (2 new tools) |

## Reuse

- `policy.py` pattern → frozen dataclass + YAML loader (fleet.py)
- `observability.log_event()` → all fleet operations
- `session.py` Session dataclass → handoff reads session state directly
- `patchbay.py` text formatting → fleet status section follows same pattern
- `constants.py` path conventions → CONDUCTOR_DATA / subdirectory
