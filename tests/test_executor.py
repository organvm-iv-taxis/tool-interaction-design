"""Tests for WorkflowExecutor proto-runtime behavior."""

from __future__ import annotations

from pathlib import Path

import yaml

from conductor.executor import WorkflowExecutor


def _write_workflow(path: Path) -> None:
    payload = {
        "version": "1.0",
        "examples": [
            {
                "name": "proto-pipe-checkpoint",
                "version": "1.0",
                "steps": [
                    {
                        "name": "collect",
                        "cluster": "web_search",
                        "input": "${input.topic}",
                        "checkpoint": True,
                    },
                    {
                        "name": "synthesize",
                        "cluster": "sequential_thinking",
                    },
                ],
            }
        ],
    }
    path.write_text(yaml.safe_dump(payload))


def test_executor_uses_examples_and_runs_checkpoint_then_pipe(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    state_path = tmp_path / "state.json"
    _write_workflow(workflow_path)

    executor = WorkflowExecutor(workflow_path=workflow_path, state_file=state_path)
    state = executor.start_workflow(
        workflow_name="proto-pipe-checkpoint",
        session_id="session-123",
        global_input={"topic": "agent orchestration"},
    )

    assert state.current_step == "collect"
    assert executor.list_workflows() == ["proto-pipe-checkpoint"]

    gate = executor.run_step("collect")
    assert gate["status"] == "CHECKPOINT"
    assert gate["step"] == "collect"
    assert gate["allowed_actions"] == ["approve", "modify", "abort"]
    assert gate["input"] == "agent orchestration"

    after_approve = executor.run_step(
        "collect",
        checkpoint_action="approve",
        tool_output={"facts": ["a", "b"]},
    )
    assert after_approve["status"] == "CONTINUE"
    assert after_approve["next_step"] == "synthesize"
    assert after_approve["input"] == {"facts": ["a", "b"]}

    finished = executor.run_step("synthesize")
    assert finished["status"] == "FINISHED"

    briefing = executor.get_briefing()
    assert briefing["active"] is True
    assert briefing["status"] == "COMPLETED"
    assert briefing["progress"] == "2/2"


def test_executor_condition_skips_blocked_step_and_advances(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    state_path = tmp_path / "state.json"
    payload = {
        "version": "1.0",
        "examples": [
            {
                "name": "condition-skip",
                "version": "1.0",
                "steps": [
                    {"name": "collect", "cluster": "web_search", "input": "${input.n}"},
                    {
                        "name": "gate",
                        "cluster": "sequential_thinking",
                        "depends_on": ["collect"],
                        "condition": "gt(collect, 10)",
                    },
                    {"name": "finish", "cluster": "sequential_thinking", "depends_on": ["collect"]},
                ],
            }
        ],
    }
    workflow_path.write_text(yaml.safe_dump(payload))

    executor = WorkflowExecutor(workflow_path=workflow_path, state_file=state_path)
    executor.start_workflow("condition-skip", session_id="session-456", global_input={"n": 3})

    first = executor.run_step("collect")
    assert first["status"] == "CONTINUE"
    assert first["next_step"] == "finish"

    state = executor.load_state()
    assert state is not None
    assert state.steps["gate"].status == "SKIPPED"

    done = executor.run_step("finish")
    assert done["status"] == "FINISHED"


def test_executor_approval_condition_uses_checkpoint_action(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    state_path = tmp_path / "state.json"
    payload = {
        "version": "1.0",
        "examples": [
            {
                "name": "approval-gate",
                "version": "1.0",
                "steps": [
                    {"name": "review", "cluster": "sequential_thinking", "checkpoint": True},
                    {
                        "name": "deploy",
                        "cluster": "vercel_platform",
                        "depends_on": ["review"],
                        "condition": "approval(review)",
                    },
                ],
            }
        ],
    }
    workflow_path.write_text(yaml.safe_dump(payload))

    executor = WorkflowExecutor(workflow_path=workflow_path, state_file=state_path)
    executor.start_workflow("approval-gate", session_id="session-789")

    gate = executor.run_step("review")
    assert gate["status"] == "CHECKPOINT"

    after_approve = executor.run_step("review", checkpoint_action="approve")
    assert after_approve["status"] == "CONTINUE"
    assert after_approve["next_step"] == "deploy"

    done = executor.run_step("deploy")
    assert done["status"] == "FINISHED"
