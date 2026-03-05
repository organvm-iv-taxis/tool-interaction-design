"""Tests for WorkflowExecutor proto-runtime behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

from conductor.executor import StepState, WorkflowExecutor


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


# ---------------------------------------------------------------------------
# Phase 1 tests: new primitives
# ---------------------------------------------------------------------------


def test_step_state_metadata_field() -> None:
    """StepState accepts metadata without crashing (Phase 0a fix)."""
    s = StepState(name="test", metadata={"key": "val"})
    assert s.metadata == {"key": "val"}
    assert s.iteration == 0
    assert s.max_iterations == 0


def test_fan_out_fan_in_collects_branches(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    state_path = tmp_path / "state.json"
    payload = {
        "version": "1.0",
        "examples": [{
            "name": "fan-test",
            "version": "1.0",
            "steps": [
                {
                    "name": "scatter",
                    "cluster": "web_search",
                    "type": "fan_out",
                    "branches": [
                        {"cluster": "a", "input": "branch-0-data"},
                        {"cluster": "b", "input": "branch-1-data"},
                        {"cluster": "c", "input": "branch-2-data"},
                    ],
                },
                {"name": "finish", "cluster": "sequential_thinking", "depends_on": ["scatter"]},
            ],
        }],
    }
    workflow_path.write_text(yaml.safe_dump(payload))
    executor = WorkflowExecutor(workflow_path=workflow_path, state_file=state_path)
    executor.start_workflow("fan-test", session_id="s-fan")

    result = executor.run_step("scatter")
    assert result["branches_completed"] == 3
    assert result["status"] == "CONTINUE"
    assert result["next_step"] == "finish"
    assert len(result["aggregated_output"]) == 3

    state = executor.load_state()
    assert state is not None
    assert state.steps["scatter__branch_0"].status == "COMPLETED"
    assert state.steps["scatter__branch_1"].status == "COMPLETED"
    assert state.steps["scatter__branch_2"].status == "COMPLETED"
    assert state.steps["scatter__fan_in"].status == "COMPLETED"


def test_loop_runs_until_condition(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    state_path = tmp_path / "state.json"
    payload = {
        "version": "1.0",
        "examples": [{
            "name": "loop-test",
            "version": "1.0",
            "steps": [
                {
                    "name": "counter",
                    "cluster": "sequential_thinking",
                    "type": "loop",
                    "max_iterations": 5,
                    "until": "gt(counter, 2)",
                },
            ],
        }],
    }
    workflow_path.write_text(yaml.safe_dump(payload))
    executor = WorkflowExecutor(workflow_path=workflow_path, state_file=state_path)
    executor.start_workflow("loop-test", session_id="s-loop")

    # Iteration 1: output=1, gt(counter,2) -> 1>2 false -> continue
    r1 = executor.run_step("counter", tool_output=1)
    assert r1["status"] == "LOOP_CONTINUE"
    assert r1["iteration"] == 1

    # Iteration 2: output=2, gt(counter,2) -> 2>2 false -> continue
    r2 = executor.run_step("counter", tool_output=2)
    assert r2["status"] == "LOOP_CONTINUE"
    assert r2["iteration"] == 2

    # Iteration 3: output=3, gt(counter,2) -> 3>2 true -> done
    r3 = executor.run_step("counter", tool_output=3)
    assert r3["status"] == "FINISHED"
    assert r3["iterations_completed"] == 3


def test_loop_respects_max_iterations(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    state_path = tmp_path / "state.json"
    payload = {
        "version": "1.0",
        "examples": [{
            "name": "loop-max",
            "version": "1.0",
            "steps": [
                {
                    "name": "spinner",
                    "cluster": "sequential_thinking",
                    "type": "loop",
                    "max_iterations": 3,
                    "until": "gt(spinner, 999)",  # never true
                },
            ],
        }],
    }
    workflow_path.write_text(yaml.safe_dump(payload))
    executor = WorkflowExecutor(workflow_path=workflow_path, state_file=state_path)
    executor.start_workflow("loop-max", session_id="s-loop-max")

    r1 = executor.run_step("spinner", tool_output=1)
    assert r1["status"] == "LOOP_CONTINUE"

    r2 = executor.run_step("spinner", tool_output=2)
    assert r2["status"] == "LOOP_CONTINUE"

    # Iteration 3 hits max_iterations
    r3 = executor.run_step("spinner", tool_output=3)
    assert r3["status"] == "FINISHED"
    assert r3["iterations_completed"] == 3


def test_on_error_retry(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    state_path = tmp_path / "state.json"
    payload = {
        "version": "1.0",
        "examples": [{
            "name": "retry-test",
            "version": "1.0",
            "steps": [
                {
                    "name": "flaky",
                    "cluster": "web_search",
                    "on_error": "retry(3)",
                },
                {"name": "done", "cluster": "sequential_thinking", "depends_on": ["flaky"]},
            ],
        }],
    }
    workflow_path.write_text(yaml.safe_dump(payload))
    executor = WorkflowExecutor(workflow_path=workflow_path, state_file=state_path)
    executor.start_workflow("retry-test", session_id="s-retry")

    # First attempt fails
    r1 = executor.run_step("flaky", tool_output={"__error__": True, "message": "timeout"})
    assert r1["status"] == "RETRY"
    assert r1["attempt"] == 1

    # Second attempt succeeds
    r2 = executor.run_step("flaky", tool_output="success-data")
    assert r2["status"] == "CONTINUE"
    assert r2["next_step"] == "done"


def test_on_error_skip(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    state_path = tmp_path / "state.json"
    payload = {
        "version": "1.0",
        "examples": [{
            "name": "skip-test",
            "version": "1.0",
            "steps": [
                {"name": "optional", "cluster": "web_search", "on_error": "skip"},
                {"name": "required", "cluster": "sequential_thinking"},
            ],
        }],
    }
    workflow_path.write_text(yaml.safe_dump(payload))
    executor = WorkflowExecutor(workflow_path=workflow_path, state_file=state_path)
    executor.start_workflow("skip-test", session_id="s-skip")

    r = executor.run_step("optional", tool_output={"__error__": True, "message": "not found"})
    assert r["status"] == "SKIPPED"
    assert r["next_step"] == "required"

    state = executor.load_state()
    assert state is not None
    assert state.steps["optional"].status == "SKIPPED"


def test_fallback_step(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    state_path = tmp_path / "state.json"
    payload = {
        "version": "1.0",
        "examples": [{
            "name": "fallback-test",
            "version": "1.0",
            "steps": [
                {
                    "name": "primary",
                    "cluster": "web_search",
                    "on_error": "fallback",
                    "fallback": "backup",
                },
                {"name": "backup", "cluster": "academic_research"},
                {"name": "finish", "cluster": "sequential_thinking", "depends_on": ["primary"]},
            ],
        }],
    }
    workflow_path.write_text(yaml.safe_dump(payload))
    executor = WorkflowExecutor(workflow_path=workflow_path, state_file=state_path)
    executor.start_workflow("fallback-test", session_id="s-fallback")

    r = executor.run_step("primary", tool_output={"__error__": True, "message": "service down"})
    assert r["status"] == "FALLBACK"
    assert r["fallback_step"] == "backup"

    state = executor.load_state()
    assert state is not None
    assert state.steps["primary"].status == "FAILED"
    assert state.current_step == "backup"


def test_emit_logs_event(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    state_path = tmp_path / "state.json"
    payload = {
        "version": "1.0",
        "examples": [{
            "name": "emit-test",
            "version": "1.0",
            "steps": [
                {"name": "collect", "cluster": "web_search", "input": "data"},
                {"name": "notify", "cluster": "sequential_thinking", "type": "emit", "depends_on": ["collect"]},
            ],
        }],
    }
    workflow_path.write_text(yaml.safe_dump(payload))
    executor = WorkflowExecutor(workflow_path=workflow_path, state_file=state_path)
    executor.start_workflow("emit-test", session_id="s-emit")

    executor.run_step("collect", tool_output="collected-data")

    with patch("conductor.executor.log_event") as mock_log:
        result = executor.run_step("notify")
        assert result["status"] == "FINISHED"
        # Check that log_event was called with the emit event type
        emit_calls = [c for c in mock_log.call_args_list if c[0][0] == "executor.emit"]
        assert len(emit_calls) == 1


def test_transforms_unique_sort_flatten(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    state_path = tmp_path / "state.json"
    payload = {
        "version": "1.0",
        "examples": [{
            "name": "transform-test",
            "version": "1.0",
            "steps": [
                {"name": "source", "cluster": "web_search"},
            ],
        }],
    }
    workflow_path.write_text(yaml.safe_dump(payload))
    executor = WorkflowExecutor(workflow_path=workflow_path, state_file=state_path)
    state = executor.start_workflow("transform-test", session_id="s-transform",
                                    global_input=[[1, 2], [2, 3], [3, 4]])

    # Test flatten
    val = executor._resolve_reference("input | flatten", state)
    assert val == [1, 2, 2, 3, 3, 4]

    # Test unique
    val = executor._resolve_reference("input | flatten | unique", state)
    assert val == [1, 2, 3, 4]

    # Test sort
    state.global_input = [3, 1, 4, 1, 5]
    val = executor._resolve_reference("input | unique | sort", state)
    assert val == [1, 3, 4, 5]

    # Test lines
    state.global_input = "line1\nline2\nline3"
    val = executor._resolve_reference("input | lines", state)
    assert val == ["line1", "line2", "line3"]

    # Test join
    state.global_input = ["a", "b", "c"]
    val = executor._resolve_reference("input | join(', ')", state)
    assert val == "a, b, c"

    # Test take
    state.global_input = [1, 2, 3, 4, 5]
    val = executor._resolve_reference("input | take(3)", state)
    assert val == [1, 2, 3]


def test_all_passed_requires_all_branches(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    state_path = tmp_path / "state.json"
    payload = {
        "version": "1.0",
        "examples": [{
            "name": "branch-check",
            "version": "1.0",
            "steps": [
                {
                    "name": "scatter",
                    "cluster": "web_search",
                    "type": "fan_out",
                    "branches": [
                        {"cluster": "a", "input": "data-0"},
                        {"cluster": "b", "input": "data-1"},
                    ],
                },
                {
                    "name": "gate",
                    "cluster": "sequential_thinking",
                    "depends_on": ["scatter"],
                    "condition": "all_passed(scatter)",
                },
            ],
        }],
    }
    workflow_path.write_text(yaml.safe_dump(payload))
    executor = WorkflowExecutor(workflow_path=workflow_path, state_file=state_path)
    executor.start_workflow("branch-check", session_id="s-branch")

    result = executor.run_step("scatter")
    assert result["status"] == "CONTINUE"
    assert result["next_step"] == "gate"

    # all_passed should be true since all branches completed
    state = executor.load_state()
    assert state is not None
    assert state.steps["scatter__branch_0"].status == "COMPLETED"
    assert state.steps["scatter__branch_1"].status == "COMPLETED"

    done = executor.run_step("gate")
    assert done["status"] == "FINISHED"
