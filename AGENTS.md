# Repository Guidelines

## Project Structure & Module Organization
- `conductor/`: main package (CLI, governance runtime, policy, schemas, doctor, observability).
- `router.py` and `mcp_server.py`: top-level modules used by CLI/tests and packaged via `pyproject.toml`.
- `tests/`: pytest suite (`test_*.py`) covering CLI, routing, policy, migrations, observability, and E2E flows.
- `schemas/v1/`: JSON Schemas for `registry`, `governance`, and `workflow` documents.
- `policies/`: environment policy bundles (`default`, `strict`, `relaxed`).
- `benchmarks/`: routing SLA benchmark script.
- `tools/`: quality/release utilities (schema validation, release guardrails).
- Runtime/output dirs: `sessions/`, `generated/`, `exports/`.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create/activate local environment.
- `python -m pip install -e '.[dev]'`: install package and development dependencies.
- `pytest -q`: run full test suite.
- `mypy --config-file mypy.ini`: run strict type checks on scoped modules.
- `python tools/release_guardrails.py`: enforce version/changelog consistency.
- `python tools/validate_schemas.py`: validate corpus/workflow docs against schemas.
- `python -m conductor doctor --workflow workflow-dsl.yaml --strict`: run integrity checks.
- `python benchmarks/benchmark_routing.py --enforce --repeat 30`: verify routing SLA.

## Coding Style & Naming Conventions
- Python 3.11+ style, 4-space indentation, PEP 8, explicit type hints on public APIs.
- Use `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Keep modules focused and side-effect free where possible (especially validation/runtime code paths).

## Testing Guidelines
- Framework: `pytest` (with optional `hypothesis` fuzz tests).
- Test files: `tests/test_<feature>.py`; test names: `test_<behavior>()`.
- Add/adjust tests for every behavior change, especially CLI output modes and schema validation paths.

## Commit & Pull Request Guidelines
- Prefer Conventional Commit style seen in history, e.g. `feat(schema): ...`, `fix(ci): ...`, `test(ci): ...`.
- Keep commits atomic by concern (runtime, schema/migration, policy/observability, CI/tests).
- PRs should include: summary, risk/impact notes, commands run locally, and CI status link.

## Security & Configuration Tips
- Key env vars: `ORGANVM_CORPUS_DIR`, `CONDUCTOR_POLICY_BUNDLE`, `CONDUCTOR_CLUSTER_FILE`.
- Do not commit generated local artifacts (for example `.conductor-observability*.json*`, temporary corpora).
