# Evaluation-to-Growth Report: `conductor` v1.0

**Date:** 2026-03-04
**Scope:** Full project review — conductor.py (1,308 lines), mcp_server.py (310 lines), router.py (588 lines), templates (3 files), generated artifacts
**Mode:** Autonomous | Markdown Report
**Framework:** Evaluation → Reinforcement → Risk Analysis → Growth

---

## Phase 1: Evaluation

### 1.1 Critique

#### Strengths

**S1 — Architecture-to-implementation coherence.** The three-layer model (Session/Governance/Product) maps cleanly from the plan's conceptual framing to actual code. Each layer has its own class (`SessionEngine`, `GovernanceRuntime`, `ProductExtractor`) with no leakage between concerns. This is the strongest structural decision — it means each layer can evolve independently.

**S2 — Phase state machine is correct and complete.** The `VALID_TRANSITIONS` dict at line 144-149 implements the exact diamond-shaped state graph from the plan, including reshape (SHAPE→FRAME) and fail-back (PROVE→BUILD). The `phase()` method enforces this strictly — you cannot skip phases or violate the lifecycle. This is the core pedagogical mechanism and it works.

**S3 — Real governance data, not mocks.** Layer 2 reads the actual `registry-v2.json` (101 repos) and `governance-rules.json` from the corpus. The `wip check` output immediately surfaced the real 55-CANDIDATE bottleneck — this proves the tool provides genuine operational insight, not theoretical output.

**S4 — Session logs are well-structured.** The YAML session log format (lines 427-437) captures phase durations, tools used, commits, warnings, and result. This is the raw material for Layer 3 pattern mining and is a genuinely mineable data format.

**S5 — Low dependency footprint.** Only PyYAML required. No framework, no ORM, no build system. The tool can run from any checkout with `python3 conductor.py`. MCP server adds the `mcp` package as an optional dependency. This is the right constraint for a tool that needs to be used daily without friction.

**S6 — Router passthrough preserves existing value.** Lines 1264-1280 delegate `route`, `capability`, `clusters`, `domains` back to router.py functions. This means conductor supersedes router.py as the entry point without losing any functionality.

**S7 — Template scaffolding is immediate.** `session start` creates the session directory and fills spec.md, plan.md, status.md with session metadata before the user types anything else. The templates exist as files, not abstractions — you can `cat` them, edit them, `git add` them.

#### Weaknesses

**W1 — `PhaseLog` dataclass is defined but never used.** Lines 152-163 define a `PhaseLog` dataclass with a `duration_minutes` property, but `Session.phase_logs` is typed as `list[dict]` (line 174), and all code manipulates raw dicts. The dataclass is dead code. This creates a false promise of type safety.

**W2 — Organ mapping is duplicated.** `ORGANS` dict at lines 78-87 duplicates `organvm_engine.organ_config.ORGANS`. The comment says "inline to avoid hard dependency" but this creates a maintenance burden — if an org name changes, two files need updating.

**W3 — `_all_repos()` returns a list, called multiple times.** In `wip_promote()`, `_all_repos()` is called 3 times (lines 613, 640, 650). Each call re-iterates the full registry. For 101 repos this is negligible, but it's a pattern that signals "I should be caching this."

**W4 — State machine transitions duplicated.** Lines 626-632 in `wip_promote()` redefine the promotion state machine transitions that already exist in `organvm_engine.governance.state_machine.TRANSITIONS`. This is the second duplication of organvm-engine logic.

**W5 — `stale` command makes N sequential API calls.** For 55 CANDIDATE repos, it runs 55 individual `gh api` calls (line 696-698), each with a 15s timeout. Worst case: 55 * 15 = 825 seconds. No batching, no parallelism, no caching.

**W6 — `_find_tool_cluster()` uses substring matching.** Line 396: `if tool_name.lower() in name.lower()` — searching for "edit" would match "NotebookEdit", "edit_block", "edit_file", etc. This will produce false positives and incorrect phase warnings.

**W7 — No tests.** Zero test files. The router.py CLAUDE.md acknowledges "No automated tests for router.py" and conductor inherits this gap. For a tool that enforces SDLC discipline, having no tests is a credibility problem.

**W8 — `wip_promote()` writes registry directly.** Line 660 writes to `registry-v2.json` without backup, validation, or confirmation. A typo in the repo name argument silently does nothing (falls through to "not found"), but a successful promotion is irreversible without `git checkout`.

**W9 — Session state is a single JSON file.** `.conductor-session.json` (line 66) means only one session can exist at a time. No concurrent sessions, no session history beyond the logs. The plan's session_id suggests uniqueness, but the implementation is a singleton.

**W10 — `enforce generate` produces static artifacts.** The generated rulesets (lines 738-757) are identical for all 8 orgs — same rules, just different org names. The governance-rules.json has per-organ requirements (e.g., III requires revenue fields, V requires min_essays) but none of this differentiation is reflected in the generated artifacts.

**W11 — `status.md` template has unfilled placeholders.** The template uses `{{ duration_minutes }}`, `{{ frame_duration }}`, etc. but `_scaffold_templates()` (line 263-283) only replaces 5 variables. The phase-specific placeholders remain as literal `{{ }}` strings in the scaffolded file. They're never filled because status.md is meant to be filled at close time, but the template replacement mechanism doesn't handle this.

**W12 — `asdict` imported but never used.** Line 41: `from dataclasses import asdict, dataclass, field` — `asdict` is unused.

#### Priority Areas (ranked)

1. **W7** — No tests (credibility + correctness risk)
2. **W6** — Substring tool matching (will produce wrong warnings)
3. **W8** — Unguarded registry writes (data integrity risk)
4. **W11** — Broken status.md template flow (UX confusion)
5. **W1/W12** — Dead code (cleanliness)
6. **W5** — Sequential API calls (performance)
7. **W10** — Undifferentiated enforcement artifacts (governance gap)

---

### 1.2 Logic Check

**LC1 — Session lifecycle has a gap between PROVE→DONE and close.** After `session phase done`, the session is marked SHIPPED but the state file still exists. The user must then run `session close` separately. This two-step exit is unforced — `phase done` could auto-close. However, the gap is defensible: it lets you add final notes to status.md before generating the log.

**LC2 — WIP limit of 3 CANDIDATE per organ is hardcoded but every organ currently exceeds it.** `MAX_CANDIDATE_PER_ORGAN = 3` (line 461) means `wip check` reports 5 violations on first run. This is technically correct (the system IS over WIP limit), but it means the limit is aspirational, not current. The tool will be noisy until ~40 repos are triaged. Risk: user learns to ignore the warnings.

**LC3 — `MAX_PUBLIC_PROCESS_PER_ORGAN = 1` is declared but never enforced.** Line 462 defines the constant, but `wip_promote()` only checks CANDIDATE limits (line 639). PUBLIC_PROCESS limit is a dead constant.

**LC4 — `registry sync` report-only, not auto-fix.** The plan says "auto-adds the 32 missing repos" but the implementation only reports the delta. No `--fix` flag exists. The plan and implementation disagree.

**LC5 — Phase logs can have duplicate phase entries.** If you go FRAME→SHAPE→FRAME (reshape), the `phase_logs` list will have two FRAME entries. The `close()` method's `phase_summary` dict (line 418-425) uses phase name as key, so the second FRAME overwrites the first. Duration data is lost for the initial FRAME.

---

### 1.3 Logos Review

**Argument clarity: Strong.** The docstring at lines 1-29 clearly states what each layer does and maps to the three goals (GROW, EFFICIENCY, COMMODIFY). The CLI help is self-documenting.

**Evidence quality: Mixed.** Layer 2 produces evidence-based output (real WIP counts, real registry delta). Layer 1 produces structural scaffolding. Layer 3 is thin — `mine_patterns` has hardcoded pattern names ("DEEP_RESEARCH", "QUICK_FRAME", "MARATHON_BUILD", "EAGER_CODER") that are if/else branches, not emergent patterns.

**Persuasive strength: Moderate.** The tool's most persuasive argument is `wip check` — showing 55 CANDIDATE repos instantly contextualizes the bottleneck problem. The session engine is persuasive as a ritual enforcer. The product extractor is the weakest argument — the process kit export is currently just template copies, which any user could do with `cp`.

**Enhancement recommendations:**
- Layer 3 needs more substance to justify "commodification" — pattern mining should produce actual named patterns with session counts, not hardcoded strings
- The MCP server `conductor_suggest` tool (keyword matching) is too naive to be genuinely useful — "build a test" would match both BUILD and TEST capabilities with no ranking

---

### 1.4 Pathos Review

**Current emotional tone:** Professional-utilitarian. The output formatting (indented, boxed with `═` headers) is clean and readable. Tool names like "conductor" and phase names like "FRAME/SHAPE/BUILD/PROVE" carry the musical metaphor without being precious about it.

**Audience connection:** The tool addresses a specific pain point — the gap between having an architecture (289K words of documentation) and having a daily practice. The session ritual is the emotional hook: "start your work here, and the system guides you."

**Engagement level:** Medium. The tool is functional but doesn't celebrate progress. There's no "you've completed 10 sessions" counter, no "your ship rate improved from 60% to 80%", no streak tracking. The session close output is purely factual.

**Recommendations:**
- Add a cumulative stats line to `session close` ("Session #N | Lifetime: X sessions, Y hours, Z% ship rate")
- `wip check` could show a pipeline visualization instead of just a table

---

### 1.5 Ethos Review

**Perceived expertise: High** for Layer 2 (real governance data, real state machines, real registry integration). **Low** for Layer 3 (pattern mining is toy-grade, process kit is just templates).

**Trustworthiness signals present:**
- Reads from actual system of record (registry-v2.json)
- Enforces real state machine transitions
- Warns on phase violations
- Generates standard GitHub artifacts (rulesets, Actions, Issue Forms)

**Trustworthiness signals missing:**
- No tests (biggest trust gap)
- No version number or changelog
- No `--version` flag
- `enforce generate` has a TODO in the output (`echo 'TODO: Add commitlint'`)
- `wip_promote` writes without confirmation or backup

**Credibility recommendations:**
- Add tests (even 10 would transform credibility)
- Remove TODOs from generated artifacts
- Add `--confirm` prompt to destructive operations (`wip promote`, `registry sync --fix`)

---

## Phase 2: Reinforcement

### 2.1 Synthesis

| Finding | Resolution |
|---------|------------|
| LC3: `MAX_PUBLIC_PROCESS_PER_ORGAN` unused | Either enforce it in `wip_promote()` or remove the constant |
| LC5: Duplicate phase entries overwrite | Use a list of phase dicts in session log instead of dict keyed by name; or merge durations for same-named phases |
| W1: `PhaseLog` dataclass unused | Either use it (replace raw dicts in `Session.phase_logs`) or delete it |
| W12: `asdict` unused import | Remove |
| W6: Substring tool matching | Use exact match against normalized tool names, or match against cluster membership directly |
| LC4: `registry sync` doesn't auto-add | Either add `--fix` flag or update the plan to say "report-only" — don't let plan and code disagree |
| W11: status.md unfilled placeholders | Either (a) fill them at `session close` time, or (b) remove phase-specific placeholders from the template since status.md is meant to be human-edited |

---

## Phase 3: Risk Analysis

### 3.1 Blind Spots

**BS1 — No integration with actual git workflow.** The session engine tracks phases and logs tools, but never creates a branch, never commits, never opens a PR. The plan's SHAPE phase says "git checkout -b feat/<organ>/<slug>" and the BUILD phase says "git add + git commit" — none of this is wired up. The session is a parallel metadata layer disconnected from the git timeline.

**BS2 — `session log-tool` requires manual invocation.** There's no hook, no automatic detection. The tool-logging mechanism only works if you remember to call `conductor session log-tool <name>` after every tool use. In practice, nobody will do this. The plan envisions this being automatic ("phase WARNS when you reach for a tool from a different phase") but the implementation requires opt-in discipline — the exact thing the tool is supposed to provide.

**BS3 — No connection to the existing organvm MCP server.** The organvm-mcp-server already has 16 tools for registry, seeds, graph, health, and context. The conductor MCP server (5 tools) overlaps with some of these (WIP status vs system health) but doesn't compose with them. Two independent MCP servers serving partially overlapping data about the same system.

**BS4 — The tool doesn't reference the tool-surface-integration.yaml at runtime.** The `PHASE_CLUSTERS` dict (lines 117-135) is a hardcoded copy of data from `research/digested/2026-03-03-tool-surface-integration.yaml`. If the ontology changes (clusters added/removed), the YAML and the Python will drift. The router.py loads ontology.yaml dynamically, but conductor's phase mapping is static.

**BS5 — No mechanism for the 50-session learning claim.** The plan says "After ~50 sessions, the SDLC is internalized." The tool tracks session count nowhere. There's no progression system, no "you used FRAME tools during BUILD 0 times this week vs 3 times last week." The pedagogical promise has no measurement behind it.

### 3.2 Shatter Points

**SP1 — Registry corruption via `wip_promote`.** Severity: HIGH. The `wip_promote()` method mutates the in-memory registry dict (line 656) then writes the entire registry back (line 660). If the process is interrupted mid-write, or if another process modifies the registry concurrently, data is lost. No file locking, no atomic write, no backup.

**SP2 — 1,308-line single file will resist contribution.** Severity: MEDIUM. All three layers, the CLI parser, and all data constants live in one file. A contributor wanting to improve pattern mining must read past the session engine and governance runtime. The file will grow with every feature. By 2,000 lines it becomes a deterrent.

**SP3 — `stale` command can take 15+ minutes.** Severity: MEDIUM. 55 sequential `gh api` calls with 15s timeouts each. On slow networks or with rate limiting, this blocks the terminal. No progress indicator, no `--limit` flag, no caching of results.

**SP4 — Process kit is not standalone.** Severity: MEDIUM. The exported process kit references `conductor.py` in its CLAUDE.md and README, but doesn't include conductor.py. A recipient gets templates but no engine. The "Free tier" product isn't self-contained.

**SP5 — Session state file on filesystem has no corruption recovery.** Severity: LOW. If `.conductor-session.json` is malformed (partial write, manual edit gone wrong), `session status` and all session commands will crash with a JSON parse error. No graceful degradation, no "session state corrupted, would you like to reset?"

**SP6 — MCP server `suggest` tool is a keyword match.** Severity: LOW. "I need to deploy my test results to production" matches DEPLOY, TEST, and GENERATE — with no ranking between them. The suggestion list will be a grab-bag for any complex sentence. Users will learn it's unreliable and stop using it.

---

## Phase 4: Growth

### 4.1 Bloom (Emergent Insights)

**E1 — The session log format is more valuable than the CLI.** The YAML session log (organ, repo, scope, phase durations, tools, warnings, result) is a portable, queryable data format that works regardless of whether the CLI exists. If you published the log schema alone, other tools could emit compatible logs. The schema IS the product; the CLI is one implementation.

**E2 — Phase-cluster mapping could be user-configurable.** Different practitioners have different workflows. A machine learning engineer's BUILD phase needs `jupyter_notebooks` prominently; a frontend developer's PROVE phase needs `browser_playwright`. The hardcoded `PHASE_CLUSTERS` dict should be a YAML file that users can customize — and sharing custom phase configs becomes another product tier.

**E3 — `conductor audit` could feed back into session planning.** Right now, audit output goes to stdout and disappears. If audit findings generated Issue suggestions (`"Create issue: ORGAN-III has 11 CANDIDATE repos requiring triage"`), the audit would close the loop into action. Audit → Issues → Sessions → Audit.

**E4 — The "three-prompt rule" from the research is not implemented.** The tool-surface-integration.yaml specifies "if 3 AI iterations don't work, rewrite spec" as a BUILD constraint. This would be a genuinely novel feature: a tool that counts how many times Claude retries a task and escalates to "this spec is wrong." No other dev tool does this.

**E5 — Session logs could become a content source for ORGAN-V (Logos).** The pattern mining output (named patterns, phase averages, ship rates) could automatically draft essays for the public-process publication pipeline. "What I learned from 100 conductor sessions" writes itself from aggregated session data.

**E6 — Git hooks could solve BS2 (manual tool logging).** A post-commit hook that detects "conductor session active" and auto-increments the commit count for the current phase. A pre-push hook that checks "is the session in PROVE phase?" These hooks would make the session lifecycle a git-native constraint rather than a parallel metadata layer.

### 4.2 Evolve (Implementation Plan)

Based on all findings, here is the prioritized implementation plan:

#### P0 — Correctness (fix what's broken)

| ID | Finding | Action | File | Lines |
|----|---------|--------|------|-------|
| P0.1 | W1 | Delete `PhaseLog` dataclass (dead code) | conductor.py | 152-163 |
| P0.2 | W12 | Remove unused `asdict` import | conductor.py | 41 |
| P0.3 | LC3 | Enforce `MAX_PUBLIC_PROCESS_PER_ORGAN` in `wip_promote()` or delete constant | conductor.py | 462, 638-653 |
| P0.4 | LC5 | Merge duplicate phase durations in `close()` instead of overwriting | conductor.py | 418-425 |
| P0.5 | W6 | Fix `_find_tool_cluster()` to use exact match or cluster membership | conductor.py | 391-398 |
| P0.6 | W11 | Remove unfillable `{{ }}` placeholders from status.md template OR auto-fill at close | templates/status.md | 15-16 |

#### P1 — Integrity (prevent damage)

| ID | Finding | Action | File |
|----|---------|--------|------|
| P1.1 | SP1/W8 | Add atomic write (write to .tmp, rename) + backup for registry writes | conductor.py |
| P1.2 | SP5 | Add try/except around session state JSON loading with recovery prompt | conductor.py |
| P1.3 | W8 | Add `--yes` flag and confirmation prompt to `wip promote` | conductor.py |

#### P2 — Tests (credibility)

| ID | Action | Priority |
|----|--------|----------|
| P2.1 | Test session lifecycle: start → phase transitions → close → verify log | HIGH |
| P2.2 | Test state machine: all valid transitions, all invalid transitions rejected | HIGH |
| P2.3 | Test WIP enforcement: promote past limit → blocked | MEDIUM |
| P2.4 | Test phase-cluster tool warnings | MEDIUM |
| P2.5 | Test template scaffolding produces valid markdown | LOW |

#### P3 — Architecture (prevent sprawl)

| ID | Finding | Action |
|----|---------|--------|
| P3.1 | SP2 | Split conductor.py into `conductor/{session.py, governance.py, product.py, cli.py, constants.py}` |
| P3.2 | W2/W4 | Make organvm-engine an optional import; fall back to inline constants only when it's not installed |
| P3.3 | BS4 | Load `PHASE_CLUSTERS` from a YAML config file instead of hardcoding |
| P3.4 | BS3 | Merge conductor MCP tools into the existing organvm-mcp-server or establish clear boundaries |

#### P4 — Capability (add value)

| ID | Finding | Action |
|----|---------|--------|
| P4.1 | BS1/E6 | Add git integration: `session start` creates branch, `session close` commits breadcrumb |
| P4.2 | LC4 | Add `registry sync --fix` to auto-add missing repos with sensible defaults |
| P4.3 | W10 | Read organ-specific requirements from governance-rules.json into generated rulesets |
| P4.4 | E3 | `audit --create-issues` flag to auto-create GitHub Issues from findings |
| P4.5 | SP3 | Batch `gh api` calls in `stale` using GraphQL or `--paginate` |
| P4.6 | E4 | Implement the three-prompt rule as a BUILD phase constraint |

#### P5 — Product (make it sellable)

| ID | Finding | Action |
|----|---------|--------|
| P5.1 | SP4 | Include a standalone conductor-lite.py in the process kit export |
| P5.2 | E1 | Publish session log schema as a specification document |
| P5.3 | E2 | Make phase-cluster mapping a `.conductor.yaml` config file |
| P5.4 | E5 | Add `patterns --export-essay` to generate draft essays from session data |
| P5.5 | BS5 | Add cumulative stats tracking and progression milestones |

---

## Summary

| Dimension | Grade | Key Issue |
|-----------|-------|-----------|
| **Architecture** | B+ | Clean three-layer separation, but monolithic file and hardcoded configs will resist growth |
| **Correctness** | B- | Dead code (PhaseLog, asdict), unused constant (MAX_PUBLIC_PROCESS), duplicate phase overwrite bug |
| **Governance integration** | A- | Reads real data, enforces real state machines, surfaces real bottlenecks |
| **Session engine** | B | State machine works, but no git integration, no automatic tool logging, no learning measurement |
| **Product layer** | C+ | Template copying, toy pattern mining, keyword-match suggest — not yet at "sellable" quality |
| **Risk posture** | C | No tests, unguarded registry writes, no confirmation prompts, no atomic file operations |
| **Overall** | B- | A solid v0.1 foundation with the right architecture. Needs the P0-P2 fixes to earn trust, P3 to scale, P4-P5 to deliver on its three promises. |

The single most impactful next step: **P0 (correctness fixes) + P2.1-P2.2 (core tests)**. Everything else builds on a correct, tested foundation.
