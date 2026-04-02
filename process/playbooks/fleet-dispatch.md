# Fleet Dispatch Playbook

## Purpose

Route cognitive work to the optimal agent with guardrailed handoff, verified return, and tracked receipt.

## Entry Criteria

- Work description exists (natural language)
- Current conductor phase is known (FRAME/SHAPE/BUILD/PROVE)
- Active session with organ/repo context
- `fleet.yaml` is loaded and agents are available

## Procedure

1. **CLASSIFY** — `TaskDispatcher.classify(description)` determines `work_type` and `cognitive_class`. If misclassified, override with explicit `work_type` parameter.

2. **ROUTE** — `FleetRouter.recommend(phase, context_size, tags)` produces ranked agents. The router hard-filters by:
   - `max_cognitive_class` — agents below the required class are excluded
   - `never_decide` — agents prohibited from this decision category are excluded
   - `sensitivity` — agents lacking required permissions (git push, shell, secrets) are excluded
   - `phase_affinity` — agents below the required threshold for the current phase are excluded

3. **VERIFY EXCLUSIONS** — review the `excluded_agents` list in the dispatch plan. Each exclusion has a reason. If the recommended agent is unexpected, check the exclusion reasons for the preferred agent.

4. **GENERATE ENVELOPE** — create a `HandoffBrief` containing:
   - Scope (what to do, what not to do)
   - Key files (exact paths, never descriptions — per Gemini prompt_fix)
   - Decisions already made (to prevent re-deciding)
   - Warnings (agent-specific from `damage_modes`)
   - Open questions (for the receiving agent to clarify with operator)

5. **INJECT CONSTRAINTS** — append agent-specific `prompt_fixes` from `fleet.yaml` into the envelope. These are non-negotiable instructions derived from field-tested failures.

6. **DISPATCH** — present the envelope markdown to the operator for relay to the target agent. Claude does not execute the work — the operator copies the envelope to the target agent's session.

7. **AWAIT RETURN** — monitor for completion. If no return within the session:
   - Log status as `timeout` in the dispatch receipt
   - Flag for cross-verification in the next session

8. **CROSS-VERIFY** — if `verification_policy` is:
   - `self_sufficient` — accept the agent's own verification
   - `cross_agent_mandatory` — route to a different agent (preferably Codex) for verification
   - `independent` — the verifier must not have been the builder

9. **LOG** — record a dispatch receipt to `handoff-log.jsonl` and update per-agent usage in `fleet-usage/`.

## Exit Criteria

- Work is verified per the verification policy
- Dispatch receipt logged with final status
- Usage metrics updated for billing-period tracking
- If damage modes were discovered, `fleet.yaml` is updated

## Outputs

| Output | Format | Location |
|--------|--------|----------|
| Completed work | Files, commits | Target repo |
| Dispatch receipt | JSON | `.conductor/handoff-log.jsonl` |
| Cross-verification report | Text | Session log |
| Fleet usage delta | JSON | `.conductor/fleet-usage/` |

## Tracking

| Instrument | What It Records | Cadence |
|-----------|-----------------|---------|
| `handoff-log.jsonl` | Every dispatch event (agent, work_type, status, duration) | Per dispatch |
| `fleet-usage/` | Per-agent daily usage against allotment | Per dispatch |
| `fleet.yaml` damage_modes | Novel failure patterns discovered during dispatch | On failure |
| `fleet.yaml` field_rating | Aggregate agent quality score | Per 10 dispatches |

## Evolution Protocol

| Trigger | Action |
|---------|--------|
| Every 10 dispatches to an agent | Review damage_modes and update field_rating |
| Every cross-agent review | Update prompt_fixes and consider never_decide additions |
| Quarterly | Review work_types.yaml for classification accuracy |
| Novel damage mode discovered | Add to fleet.yaml immediately, update FLEET.md |
| 3+ recurrences of same damage mode | Graduate from damage_mode to never_decide (structural enforcement) |

## CLI Reference

```bash
# Classify and route
python3 -m conductor fleet dispatch --description "your work description"

# With explicit phase
python3 -m conductor fleet dispatch --description "..." --phase BUILD

# Generate handoff envelope
python3 -m conductor fleet handoff

# Cross-verify after return
python3 -m conductor fleet verify --files path/to/changed/files
```
