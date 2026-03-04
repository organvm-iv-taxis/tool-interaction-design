#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

if [[ -x "$ROOT_DIR/.venv/bin/mypy" ]]; then
  MYPY_BIN="$ROOT_DIR/.venv/bin/mypy"
else
  MYPY_BIN="mypy"
fi

if [[ -d .ci-corpus ]]; then
  export ORGANVM_CORPUS_DIR="$ROOT_DIR/.ci-corpus"
fi

echo "==> pytest"
"$PYTHON_BIN" -m pytest -q

echo "==> schema validation"
"$PYTHON_BIN" tools/validate_schemas.py

echo "==> process validation"
"$PYTHON_BIN" tools/validate_process_assets.py

echo "==> mypy"
"$MYPY_BIN" --config-file mypy.ini

echo "==> release guardrails"
"$PYTHON_BIN" tools/release_guardrails.py

echo "==> conductor doctor"
"$PYTHON_BIN" -m conductor doctor --workflow workflow-dsl.yaml --strict

echo "==> strict policy simulation"
"$PYTHON_BIN" -m conductor policy simulate --bundle strict --format json >/tmp/conductor-policy-sim.json

echo "==> observability trend check"
"$PYTHON_BIN" -m conductor observability report --check

echo "quality gate passed"
