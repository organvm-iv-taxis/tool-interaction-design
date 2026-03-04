"""CLI tests for newly added governance/plugin/observability flows."""

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
        timeout=30,
        env=merged_env,
    )


def _write_corpus(corpus: Path) -> None:
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "registry-v2.json").write_text(
        json.dumps(
            {
                "version": "2.0",
                "organs": {
                    "ORGAN-III": {
                        "repositories": [
                            {"name": "r1", "promotion_status": "CANDIDATE"},
                            {"name": "r2", "promotion_status": "CANDIDATE"},
                            {"name": "r3", "promotion_status": "CANDIDATE"},
                            {"name": "r4", "promotion_status": "PUBLIC_PROCESS"},
                        ]
                    }
                },
            }
        )
    )
    (corpus / "governance-rules.json").write_text(
        json.dumps({"version": "1.0", "organ_requirements": {}})
    )


def test_policy_simulate_json_uses_requested_bundle(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    _write_corpus(corpus)

    result = run(
        "policy",
        "simulate",
        "--bundle",
        "strict",
        "--format",
        "json",
        env={"ORGANVM_CORPUS_DIR": str(corpus)},
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["bundle"] == "strict"
    assert payload["limits"]["max_candidate_per_organ"] == 2
    assert payload["summary"]["violations_total"] >= 1


def test_observability_report_writes_json(tmp_path) -> None:
    output = tmp_path / "obs-report.json"
    result = run("observability", "report", "--format", "json", "--output", str(output))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "metrics" in payload
    assert "trends" in payload
    written = json.loads(output.read_text())
    assert "generated_at" in written


def test_doctor_apply_migrates_schema_version(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    _write_corpus(corpus)

    result = run(
        "doctor",
        "--workflow",
        "workflow-dsl.yaml",
        "--format",
        "json",
        "--apply",
        env={"ORGANVM_CORPUS_DIR": str(corpus)},
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "applied_fixes" in payload
    registry = json.loads((corpus / "registry-v2.json").read_text())
    governance = json.loads((corpus / "governance-rules.json").read_text())
    assert registry["schema_version"] == "1"
    assert governance["schema_version"] == "1"


def test_plugins_doctor_json_contract_shape() -> None:
    result = run("plugins", "doctor", "--format", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert set(payload.keys()) >= {"ok", "summary", "providers"}
