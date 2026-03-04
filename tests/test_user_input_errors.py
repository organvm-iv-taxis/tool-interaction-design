"""User-input error paths should not leak Python tracebacks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "conductor", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=20,
        env=merged_env,
    )


def test_missing_migration_input_has_no_traceback() -> None:
    result = run("migrate", "registry", "--input", "does-not-exist.json")
    assert result.returncode != 0
    assert "ERROR:" in result.stderr
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout


def test_unknown_repo_promote_has_no_traceback(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "registry-v2.json").write_text(json.dumps({"schema_version": "1", "organs": {}}))
    (corpus / "governance-rules.json").write_text(json.dumps({"schema_version": "1", "organ_requirements": {}}))

    result = run(
        "wip",
        "promote",
        "missing-repo",
        "PUBLIC_PROCESS",
        env={"ORGANVM_CORPUS_DIR": str(corpus)},
    )
    assert result.returncode != 0
    assert "ERROR:" in result.stderr
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout
