# Dissection: Claude Session Artifacts for tool-interaction-design

**Date**: 2026-03-06
**Context**: The `tool-interaction-design` project was moved from `~/Workspace/tool-interaction-design/` into `~/Workspace/organvm-iv-taxis/tool-interaction-design/`. This created a split: old session data lives under the original path-based project key, while new sessions use the new path. The user wants a full inventory and atomic breakdown for sorting/analysis.

---

## Directory 1: Old Projects Cache

**Path**: `/Users/4jp/.claude/projects/-Users-4jp-Workspace-tool-interaction-design/`
**Total**: 94 files, 38MB
**Date range**: Mar 4–5, 2026

### Atomic Units

#### A. Configuration (1 file)

| # | File | Size | Content |
|---|------|------|---------|
| A1 | `hooks.json` | 213B | `user_prompt_submit` hook running `conductor patch` — **STALE**: points to old path `~/Workspace/tool-interaction-design/` |

#### B. Session Transcripts (10 JSONL files)

Each is a full conversation log (messages, tool calls, responses).

| # | Session UUID | Size | Lines | Notes |
|---|-------------|------|-------|-------|
| B1 | `1000ff4c` | 6.7MB | 1,373 | Largest session — heavy subagent use |
| B2 | `28710771` | 756KB | 189 | Medium session, no subagent dir |
| B3 | `28a0927a` | 4.7MB | 1,048 | Heavy session — 18 tool results, 6 subagents |
| B4 | `48b84e44` | 42KB | 30 | Tiny session — likely aborted/short |
| B5 | `5887dbad` | 6.0MB | 1,025 | Heavy — 11 subagents, 6 tool results |
| B6 | `63b56ab7` | 2.5MB | 402 | Medium — 7 subagents, 2 tool results |
| B7 | `a2bd4599` | 1.2MB | 212 | Medium — 4 subagents, 4 tool results |
| B8 | `b1eccb5d` | 1.5MB | 311 | Medium, no subagent dir |
| B9 | `df790903` | 2.5MB | 502 | Medium — 1 subagent, 1 tool result |
| B10 | `e22acba7` | 1.2MB | 303 | Medium — 12 subagents (many compacted), 2 tool results |

#### C. Subagent Logs (44 JSONL files across 8 sessions)

Subagent transcripts nested under `{session-uuid}/subagents/`. Two naming patterns:
- `agent-a{hex}.jsonl` — full subagent transcript
- `agent-acompact-{hex}.jsonl` — compacted/summarized subagent transcript

| Session | Full Agents | Compacted | Total |
|---------|-------------|-----------|-------|
| `63b56ab7` | 5 | 2 | 7 |
| `5887dbad` | 6 | 3 (+ 2 compacted) | 11 |
| `1000ff4c` | 3 | 1 | 4 |
| `df790903` | 0 | 1 | 1 |
| `28a0927a` | 5 | 1 | 6 |
| `a2bd4599` | 4 | 0 | 4 |
| `e22acba7` | 4 | 8 | 12 |
| Total | 27 | 16 | 45* |

*One over 44 due to counting method — verify exact.

#### D. Tool Results (39 TXT files across 6 sessions)

Captured outputs from MCP/system tool invocations. Two naming patterns:
- `toolu_{base62}.txt` — standard tool result
- `{shortid}.txt` — compact naming (e.g., `bubcum1jl.txt`, `b221rtilx.txt`, `bkno5ugsy.txt`)

| Session | Tool Results |
|---------|-------------|
| `63b56ab7` | 2 |
| `5887dbad` | 6 |
| `1000ff4c` | 4 |
| `df790903` | 1 |
| `28a0927a` | 18 |
| `a2bd4599` | 4 |
| `e22acba7` | 2 |
| Total | 37 |

---

## Directory 2: Plans Archive

**Path**: `/Users/4jp/.claude/plans/tool-interaction-design/`
**Total**: 8 files, 131KB
**Date range**: Mar 4–5, 2026

| # | File | Size | Lines | Topic |
|---|------|------|-------|-------|
| P1 | `2026-03-04-tool-interaction-design-exploration-synthesis.md` | 44KB | 1,140 | Full system architecture analysis — 4-layer stack, 12 domains, 64 clusters, 578 tools |
| P2 | `2026-03-04-tool-interaction-design-mcp-exploration.md` | 11KB | 242 | MCP server infrastructure audit — 6 tools, gaps, test coverage |
| P3 | `effervescent-pondering-fountain.md` | 9KB | 179 | System activation plan — router tests, routing density, MCP registration, research pipeline |
| P4 | `twinkly-greeting-marble.md` | 10KB | 269 | Patchbay command center design — unified `conductor patch` entry point |
| P5 | `twinkly-greeting-marble-agent-ab7e83fcf34021c6b.md` | 19KB | 410 | Convergence architecture — cross-referencing 4 documents into unified design |
| P6 | `drifting-twirling-gosling.md` | 13KB | 245 | Executor completion + health signals + Oracle advisory + growth loop |
| P7 | `starry-growing-mountain.md` | 12KB | 213 | Project maturity review — 14,249 Python LOC, 396 tests, 25 modules |
| P8 | `golden-sparking-whale.md` | 13KB | 260 | Guardian Angel expansion — Oracle as wisdom/advisory layer |

### Plan Chronology & Dependency Graph

```
Mar 4 AM:  P1 (exploration) + P2 (MCP audit) → P3 (activation plan)
Mar 4 AM:  P4 (patchbay design) + P5 (convergence synthesis)
Mar 5:     P6 (executor/health) → P7 (maturity review) → P8 (guardian angel)
```

### Naming Convention Issues
- P1, P2: Properly dated (`2026-03-04-{slug}.md`)
- P3–P8: Use Claude's random animal names instead of dated convention
- P5: Agent sub-plan with correct suffix pattern (`-agent-{id}.md`)

---

## Directory 3: Current Project Cache

**Path**: `/Users/4jp/.claude/projects/-Users-4jp-Workspace-organvm-iv-taxis-tool-interaction-design/`
**Total**: 31 files, 5.9MB
**Date**: Mar 6, 2026 (this session only)

| Category | Count | Notes |
|----------|-------|-------|
| Session JSONL | 1 | `5ddd3d18...jsonl` (278KB, this session) |
| Subagent logs | 27 | 3 full + 24 compacted |
| Subagent meta | 3 | `.meta.json` files (23B each) |
| Tool results | 2 | 3.7MB MCP Docker output + 739KB search result |
| **No hooks.json** | — | Missing — not carried over from old project |

---

## Implementation Plan

### Step 1: Migrate old session data into current project directory

Move all 10 session JSONL files + their subagent/tool-result subdirectories from the old path into the current project directory so Claude treats them as current.

```
SOURCE: ~/.claude/projects/-Users-4jp-Workspace-tool-interaction-design/
TARGET: ~/.claude/projects/-Users-4jp-Workspace-organvm-iv-taxis-tool-interaction-design/

Move:
  {uuid}.jsonl              (10 files)
  {uuid}/subagents/         (8 session dirs with 44 subagent logs)
  {uuid}/tool-results/      (37 tool result files)
```

After move, delete the old directory (only `hooks.json` remains, which is stale).

### Step 2: Create hooks.json in current project directory

```
TARGET: ~/.claude/projects/-Users-4jp-Workspace-organvm-iv-taxis-tool-interaction-design/hooks.json
```

```json
{
  "hooks": {
    "user_prompt_submit": [
      {
        "matcher": "",
        "command": "cd /Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design && python3 -m conductor patch 2>/dev/null || true"
      }
    ]
  }
}
```

### Step 3: Rename undated plans to convention

In `~/.claude/plans/tool-interaction-design/`:

| Current | Proposed |
|---------|----------|
| `effervescent-pondering-fountain.md` | `2026-03-04-system-activation-plan.md` |
| `twinkly-greeting-marble.md` | `2026-03-04-patchbay-command-center.md` |
| `twinkly-greeting-marble-agent-ab7e83fcf34021c6b.md` | `2026-03-04-convergence-architecture-agent-ab7e83fc.md` |
| `drifting-twirling-gosling.md` | `2026-03-05-executor-health-oracle.md` |
| `starry-growing-mountain.md` | `2026-03-05-project-maturity-review.md` |
| `golden-sparking-whale.md` | `2026-03-05-guardian-angel-expansion.md` |

### Step 4: Copy all 8 plans into project repo

```
SOURCE: ~/.claude/plans/tool-interaction-design/*.md
TARGET: ~/Workspace/organvm-iv-taxis/tool-interaction-design/.claude/plans/
```

Create `.claude/plans/` in the project repo and copy all 8 renamed plan files there. These become version-controlled per plan file discipline.

### Step 5: Delete old project directory

After confirming all files migrated successfully:
```
rm -rf ~/.claude/projects/-Users-4jp-Workspace-tool-interaction-design/
```

---

## Verification

1. `ls ~/.claude/projects/-Users-4jp-Workspace-organvm-iv-taxis-tool-interaction-design/*.jsonl | wc -l` returns 11 (10 migrated + 1 current)
2. `cat ~/.claude/projects/-Users-4jp-Workspace-organvm-iv-taxis-tool-interaction-design/hooks.json` shows updated path
3. `ls ~/.claude/plans/tool-interaction-design/` shows all 8 files with `2026-03-0{4,5}-` prefixes
4. `ls ~/Workspace/organvm-iv-taxis/tool-interaction-design/.claude/plans/` shows all 8 plan copies
5. `python3 -m conductor patch` succeeds from the project directory
6. Old project directory no longer exists
