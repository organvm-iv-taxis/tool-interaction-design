# Agent Onboarding Playbook

## Purpose

Bring an agent from wishlist to active status through installation, field testing, and evidence-based capability profiling.

## Entry Criteria

- Agent is identified for onboarding (CLI, IDE, or API-based)
- `fleet.yaml` entry exists with `active: false` (create if absent)
- Operator has decided to invest testing time in this agent

## Procedure

### Phase 1: Install

1. **INSTALL** — verify the agent's CLI is accessible or API is reachable:
   - CLI agents: `which <agent-name>` or install via Homebrew/pipx
   - API agents: verify API key or OAuth flow
   - IDE agents: verify headless/CLI mode exists (if not, document as `mode: ide-only`)
   - Bot agents (Jules): verify GitHub bot is authorized on target repos

2. **RECORD** — set `installed: true` in `fleet.yaml`

### Phase 2: Profile

3. **INITIAL PROFILE** — set preliminary capability estimates based on documentation:
   - `strengths` and `weaknesses` from the agent's own docs
   - `phase_affinity` estimates (conservative — use 0.5 for unknown phases)
   - `sensitivity` based on agent's permissions model
   - `mode` — coding, research, or ide-only

### Phase 3: Field Test

4. **FIELD TEST** — dispatch 3 standardized tasks to the agent. Each task must:
   - Use a non-critical repo (preferably a `contrib--*` workspace)
   - Be the same task given to all onboarding candidates for comparability
   - Be cross-verified by Claude or Codex after completion

   **Standard test battery:**

   | Test | Cognitive Class | Task | Expected Output |
   |------|----------------|------|-----------------|
   | T1: Mechanical | mechanical | Rename all snake_case variables to camelCase in a 50-line file | Clean rename, no semantic changes |
   | T2: Tactical | tactical | Write 5 unit tests for an existing function | Tests pass, edge cases covered |
   | T3: Strategic | strategic | Design a module boundary for a new feature | Coherent architecture, no governance violations |

   Agents with `max_cognitive_class: mechanical` skip T2 and T3.
   Agents with `max_cognitive_class: tactical` skip T3.

5. **RECORD RESULTS** — for each test, document:
   - Pass/fail
   - Time to completion
   - Files changed
   - Damage modes observed (even minor ones)
   - Prompt adjustments required

### Phase 4: Activate

6. **SET FIELD RATING** — score 1-10 based on test battery results:
   - 9-10: Exceptional — self-governing, catches bugs, minimal prompt adjustment
   - 7-8: Good — reliable within scope, occasional prompt fix needed
   - 5-6: Adequate — works but requires heavy guardrailing
   - 3-4: Problematic — more rework than value, restrict to narrow scope
   - 1-2: Dangerous — active harm, do not activate

7. **SET COGNITIVE CEILING** — `max_cognitive_class` is the highest test tier passed cleanly:
   - T1 only → `mechanical`
   - T1 + T2 → `tactical`
   - T1 + T2 + T3 → `strategic`

8. **CONFIGURE GUARDRAILS** — based on test results:
   - `self_audit_trusted` — only `true` if the agent correctly identified its own errors
   - `never_touch` — files the agent corrupted or mishandled
   - `never_decide` — decision categories where the agent made wrong calls
   - `handoff_envelope_required` — `true` for any agent with field_rating < 8
   - `max_files_before_checkpoint` — lower for less trusted agents

9. **ACTIVATE** — set `active: true` in `fleet.yaml`

10. **ANNOUNCE** — update `FLEET.md`:
    - Add to Fleet Summary table
    - Add damage modes to Damage Mode Registry
    - Add to Routing Quick Reference
    - Remove from Activation Checklist

## Exit Criteria

- `field_rating` is set (not null)
- At least 1 `damage_mode` documented (or explicit "none observed" in notes)
- `max_cognitive_class` determined by field test evidence
- `FLEET.md` updated with new agent's profile
- `best_for` populated with proven task categories

## Outputs

| Output | Format | Location |
|--------|--------|----------|
| Updated agent entry | YAML | `fleet.yaml` |
| Updated reference doc | Markdown | `FLEET.md` |
| Field test results | JSON | `.conductor/fleet-usage/<agent>/onboarding.json` |

## Evolution Protocol

| Trigger | Action |
|---------|--------|
| 25 dispatches to an onboarded agent | Re-evaluate field_rating |
| 10+ successful dispatches at next cognitive tier | Consider promoting max_cognitive_class |
| 2+ incidents at current tier | Demote max_cognitive_class |
| Agent releases major version update | Re-run field test battery |
