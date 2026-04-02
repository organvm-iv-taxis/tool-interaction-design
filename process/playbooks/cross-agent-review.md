# Cross-Agent Review Playbook

## Purpose

Detect drift, collisions, and data corruption from concurrent or sequential multi-agent operations. Feed findings back into fleet.yaml to prevent recurrence.

## Entry Criteria

- 2+ agents have operated on the same repo or file within 24 hours
- OR a dispatch returned with `verification_policy: cross_agent_mandatory`
- OR a session close-out audit identified potential cross-agent conflicts

## Procedure

### Phase 1: Collect

1. **IDENTIFY AGENTS** — list all agents that touched the target repo/files in the review window. Use git log with author filtering:
   ```bash
   git log --since="24 hours ago" --format="%h %an %s" --all
   ```

2. **MAP FILE OVERLAP** — for each agent pair, identify files both touched:
   ```bash
   git diff --name-only <agent-A-first-commit>..<agent-A-last-commit>
   git diff --name-only <agent-B-first-commit>..<agent-B-last-commit>
   ```
   Intersection = overlap zone.

### Phase 2: Verify

3. **SEMANTIC CHECK** — for each agent's changes in the overlap zone:
   - Did the agent read the current file state before editing?
   - Did the agent act on an audit report rather than ground truth?
   - Did the agent's changes conflict with the other agent's intent?

4. **GOVERNANCE CHECK** — for each agent:
   - Verify no `never_decide` violations (check fleet.yaml restrictions against actual decisions made)
   - Verify no `never_touch` violations (check fleet.yaml restrictions against files modified)
   - Verify no sensitivity violations (agent pushed git without `can_push_git: true`)

5. **COMPLETION CHECK** — verify no agent:
   - Created GitHub issues for already-DONE items (grep for strikethrough/DONE)
   - Changed priorities without operator confirmation
   - Duplicated existing IRF entries

6. **COLLISION CHECK** — verify no ID collisions:
   - IRF IDs: `grep "^| IRF-" <file> | sort | uniq -d`
   - DONE IDs: `grep "^| DONE-" <file> | sort | uniq -d`
   - Concordance IDs: check for duplicate entries

### Phase 3: Record

7. **LOG FINDINGS** — for each novel failure pattern:
   - Add to the offending agent's `damage_modes` in `fleet.yaml`
   - Add mitigation to `prompt_fixes`
   - If pattern recurs 3+ times, upgrade to `never_decide` (structural block)

8. **UPDATE EXCLUSIONS** — if an agent proved unfit for a work type:
   - Add to `excluded_agents` in the relevant `work_types.yaml` entry

9. **PRODUCE REPORT** — structured summary:
   ```
   ## Cross-Agent Review: [repo] [date range]

   Agents: [list]
   Files overlapping: [count]

   ### Findings
   | # | Agent | Type | Severity | Description | Mitigation |

   ### Fleet Updates Made
   - fleet.yaml: [changes]
   - work_types.yaml: [changes]

   ### Remaining Risks
   - [any unresolved conflicts]
   ```

## Exit Criteria

- All file overlaps assessed (no uninspected overlap zones)
- All drift instances logged as damage_modes
- `fleet.yaml` updated with new damage_modes and prompt_fixes (if any)
- No unresolved governance violations
- Report produced and stored

## Outputs

| Output | Format | Location |
|--------|--------|----------|
| Review report | Markdown | Session log or `process/scorecards/` |
| Updated damage_modes | YAML | `fleet.yaml` |
| Updated prompt_fixes | YAML | `fleet.yaml` |
| Updated exclusions | YAML | `work_types.yaml` |

## Evolution Protocol

| Trigger | Action |
|---------|--------|
| Every cross-agent review | Feed damage_modes back into fleet.yaml |
| 3+ recurrences of same pattern | Graduate from damage_mode to never_decide |
| File-locking protocol violation | Enforce invariant #9 — no concurrent edits without coordination |
| New agent added to fleet | First 5 dispatches require cross-agent review regardless of verification_policy |

## Preferred Reviewers

Per fleet.yaml field evidence:
- **Codex** — zero false positives in portal audit (S51). Preferred for structured audits.
- **Claude** — strategic reasoning, governance awareness. Preferred for semantic/architectural review.
- **Gemini** — EXCLUDED from review work. `self_audit_trusted: false`, history of false completions.
