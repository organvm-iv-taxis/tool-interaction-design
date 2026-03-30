# Repository Guidelines

## Project Structure & Module Organization
- `conductor/`: core runtime (`cli.py`, `governance.py`, `doctor.py`, `plugins.py`, `observability.py`).
- `router.py`, `mcp_server.py`: top-level entrypoints packaged by `pyproject.toml`.
- `schemas/v1/`: JSON Schemas for domain docs and output/plugin contracts.
- `process/`: canonical delivery operating system (`contracts/`, `templates/`, `playbooks/`, `risk/`, `scorecards/`).
- `policies/`: policy bundles (`default.yaml`, `strict.yaml`, `relaxed.yaml`).
- `tests/`: pytest suite (`test_*.py`) for CLI, patchbay, plugins, policy, migrations, and contracts.
- `tools/`: maintenance scripts (`validate_schemas.py`, `release_guardrails.py`, `release.py`).

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create/activate local environment.
- `python -m pip install -e '.[dev]'`: install package and development dependencies.
- `./.venv/bin/python -m pytest -q`: run full test suite.
- `mypy --config-file mypy.ini`: run strict type checks on scoped modules.
- `python tools/release_guardrails.py`: enforce version/changelog consistency.
- `python tools/validate_schemas.py`: validate corpus/workflow docs against schemas.
- `python tools/validate_process_assets.py`: validate process templates, scorecards, and SOP assets.
- `./tools/run_quality_gate.sh`: run one-shot quality gate (tests, schemas, process assets, mypy, doctor, policy, observability).
- `python -m conductor doctor --workflow workflow-dsl.yaml --strict --apply`: diagnose and apply safe schema fixes.
- `python -m conductor plugins doctor --format json`: validate plugin manifests/provider loadability.
- `python -m conductor policy simulate --bundle strict --format json`: preview policy impact.
- `python -m conductor observability report --check`: export metrics and fail on warn/critical trend status.
- `python benchmarks/benchmark_routing.py --enforce --repeat 30`: verify routing SLA.

## Coding Style & Naming Conventions
- Python 3.11+ style, 4-space indentation, PEP 8, explicit type hints on public APIs.
- Use `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Keep modules focused; isolate IO/CLI handling from pure business logic.

## Testing Guidelines
- Framework: `pytest` (with optional `hypothesis` fuzz tests).
- Test files: `tests/test_<feature>.py`; test names: `test_<behavior>()`.
- Add/adjust tests for each behavior change, especially schema contracts and failure paths.
- User-facing failures must avoid tracebacks; assert this in subprocess tests.

## Commit & Pull Request Guidelines
- Prefer Conventional Commit style seen in history, e.g. `feat(schema): ...`, `fix(ci): ...`, `test(ci): ...`.
- Keep commits atomic by concern (runtime, schema/migration, policy/observability, CI/tests).
- PRs must include: summary, risk/impact, local commands run, and CI link.

## Change Recipes
- Runtime behavior change: update module + CLI surface + contract schema + tests in one atomic commit.
- New plugin/provider: add `schemas/v1/plugin_manifest.schema.json`-compatible manifest and run `conductor plugins doctor`.
- Release prep: `python tools/release.py prepare --part patch`, then run tests, guardrails, and tag.

## Failure Playbooks
- Schema failures: run `python tools/validate_schemas.py`, then `conductor doctor --apply`.
- Plugin failures/timeouts: run `conductor plugins doctor --strict`, inspect observability failure buckets.
- CI-only regressions: run `./.venv/bin/python -m pytest -q` and `mypy --config-file mypy.ini` locally before pushing.

## Security & Configuration Tips
- Key env vars: `ORGANVM_CORPUS_DIR`, `CONDUCTOR_POLICY_BUNDLE`, `CONDUCTOR_CLUSTER_FILE`.
- Do not commit generated local artifacts (for example `.conductor-observability*.json*`, temporary corpora).

<!-- ORGANVM:AUTO:START -->
## Agent Context (auto-generated — do not edit)

This repo participates in the **ORGAN-IV (Orchestration)** swarm.

### Active Subscriptions
- Event: `system.governance.update`

### Production Responsibilities
- **Produce** `conductor-session-lifecycle`
- **Produce** `tool-interaction-ontology`
- **Produce** `agent-coordination-protocol`

### External Dependencies
- **Consume** `orchestration-artifact`

### Governance Constraints
- Adhere to unidirectional flow: I→II→III
- Never commit secrets or credentials

*Last synced: 2026-03-26T19:39:27Z*
<!-- ORGANVM:AUTO:END -->

## Active Handoff Protocol

If `.conductor/active-handoff.md` exists, read it before starting work.
It contains constraints you must honor, files you must not modify, and
conventions you must follow. Violating these constraints will cause your
work to be rejected during cross-verification.

Key sections to obey:
- **Locked Constraints** — decisions you cannot override
- **Locked Files** — files you cannot modify
- **Conventions** — naming/style rules to follow exactly
- **Receiver Restrictions** — file patterns you must not touch
