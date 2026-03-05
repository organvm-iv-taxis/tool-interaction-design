"""Step runner strategies for the workflow executor.

Each runner handles execution of a specific DSL primitive (pipe, fan_out, loop, emit).
The WorkflowExecutor dispatches to the appropriate runner based on step type.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from .constants import ConductorError
from .feedback import record_step_outcome
from .observability import log_event

if TYPE_CHECKING:
    from .executor import StepState, WorkflowExecutor, WorkflowState


class StepRunner(Protocol):
    """Protocol for step execution strategies."""

    def run(self) -> dict[str, Any]: ...


def _advance_or_finish(
    executor: WorkflowExecutor,
    state: WorkflowState,
    workflow: dict[str, Any],
    steps: dict[str, dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    """Common logic: find next step or mark workflow finished."""
    next_step = executor._find_next_ready_step(state, steps)
    if next_step:
        state.current_step = next_step
        next_spec = steps.get(next_step, {})
        result: dict[str, Any] = {
            "status": "CONTINUE",
            "next_step": next_step,
            "checkpoint": bool(next_spec.get("checkpoint")),
            "input": executor._resolve_step_input(state, workflow, next_step),
        }
        result.update(extra)
    else:
        state.current_step = None
        state.status = "COMPLETED"
        result = {"status": "FINISHED"}
        result.update(extra)
    return result


@dataclass
class EmitRunner:
    """Runs an emit step (side-effect only, logs event)."""

    executor: WorkflowExecutor
    state: WorkflowState
    step_name: str
    step_spec: dict[str, Any]
    workflow: dict[str, Any]
    steps: dict[str, dict[str, Any]]
    tool_output: Any

    def run(self) -> dict[str, Any]:
        step = self.state.steps[self.step_name]
        step.status = "RUNNING"
        step.start_time = time.time()
        resolved_input = self.executor._resolve_step_input(self.state, self.workflow, self.step_name)
        output = resolved_input if self.tool_output is None else self.tool_output
        step.output = output
        step.status = "COMPLETED"
        step.end_time = time.time()
        self.state.bindings[self.step_name] = output
        log_event(
            "executor.emit",
            {"workflow": self.state.workflow_name, "step": self.step_name, "payload": output},
        )
        result = _advance_or_finish(self.executor, self.state, self.workflow, self.steps)
        self.executor.save_state(self.state)
        return result


@dataclass
class FanOutRunner:
    """Runs a fan_out step: executes branches sequentially and aggregates."""

    executor: WorkflowExecutor
    state: WorkflowState
    step_name: str
    step_spec: dict[str, Any]
    workflow: dict[str, Any]
    steps: dict[str, dict[str, Any]]

    def run(self) -> dict[str, Any]:
        from .executor import StepState

        branches = self.step_spec.get("branches", [])
        if not isinstance(branches, list) or not branches:
            raise ConductorError(f"fan_out step '{self.step_name}' must have a 'branches' list")

        self.state.steps[self.step_name].status = "RUNNING"
        self.state.steps[self.step_name].start_time = time.time()
        branch_outputs: list[Any] = []

        for i, branch in enumerate(branches):
            branch_name = f"{self.step_name}__branch_{i}"
            branch_input = branch.get("input") if isinstance(branch, dict) else None

            self.state.steps[branch_name] = StepState(name=branch_name)
            if branch_name not in self.state.step_order:
                idx = self.state.step_order.index(self.step_name) + 1 + i
                self.state.step_order.insert(idx, branch_name)

            self.state.steps[branch_name].status = "RUNNING"
            self.state.steps[branch_name].start_time = time.time()
            resolved = (
                self.executor._resolve_value(branch_input, self.state)
                if branch_input
                else self.executor._pipe_input(self.state, self.step_name)
            )
            self.state.steps[branch_name].output = resolved
            self.state.steps[branch_name].status = "COMPLETED"
            self.state.steps[branch_name].end_time = time.time()
            self.state.bindings[branch_name] = resolved
            branch_outputs.append(resolved)

        # Fan-in: aggregate
        fan_in_name = f"{self.step_name}__fan_in"
        self.state.steps[fan_in_name] = StepState(name=fan_in_name)
        self.state.steps[fan_in_name].status = "COMPLETED"
        self.state.steps[fan_in_name].start_time = time.time()
        self.state.steps[fan_in_name].end_time = time.time()
        self.state.steps[fan_in_name].output = branch_outputs
        self.state.bindings[fan_in_name] = branch_outputs

        # Complete parent step
        self.state.steps[self.step_name].output = branch_outputs
        self.state.steps[self.step_name].status = "COMPLETED"
        self.state.steps[self.step_name].end_time = time.time()
        self.state.bindings[self.step_name] = branch_outputs

        result = _advance_or_finish(
            self.executor,
            self.state,
            self.workflow,
            self.steps,
            branches_completed=len(branches),
            aggregated_output=branch_outputs,
        )
        self.executor.save_state(self.state)
        log_event(
            "executor.fan_out_completed",
            {"workflow": self.state.workflow_name, "step": self.step_name, "branches": len(branches)},
        )
        return result


@dataclass
class LoopRunner:
    """Runs a loop step until condition is met or max_iterations reached."""

    executor: WorkflowExecutor
    state: WorkflowState
    step_name: str
    step_spec: dict[str, Any]
    workflow: dict[str, Any]
    steps: dict[str, dict[str, Any]]
    tool_output: Any

    def run(self) -> dict[str, Any]:
        max_iter = int(self.step_spec.get("max_iterations", 10))
        until_condition = self.step_spec.get("until")
        step = self.state.steps[self.step_name]
        step.max_iterations = max_iter

        step.status = "RUNNING"
        step.start_time = step.start_time or time.time()

        resolved_input = self.executor._resolve_step_input(self.state, self.workflow, self.step_name)
        output = resolved_input if self.tool_output is None else self.tool_output

        step.iteration += 1
        step.output = output
        self.state.bindings[self.step_name] = output
        step.metadata["last_iteration"] = step.iteration

        # Check termination
        done = step.iteration >= max_iter
        if not done and until_condition:
            done = self.executor._condition_passes(self.state, until_condition)

        if not done:
            self.executor.save_state(self.state)
            return {
                "status": "LOOP_CONTINUE",
                "step": self.step_name,
                "iteration": step.iteration,
                "max_iterations": max_iter,
                "output": output,
            }

        # Loop complete
        step.status = "COMPLETED"
        step.end_time = time.time()

        result = _advance_or_finish(
            self.executor,
            self.state,
            self.workflow,
            self.steps,
            iterations_completed=step.iteration,
        )
        self.executor.save_state(self.state)
        log_event(
            "executor.loop_completed",
            {"workflow": self.state.workflow_name, "step": self.step_name, "iterations": step.iteration},
        )
        return result


@dataclass
class PipeRunner:
    """Runs a standard pipe/gate step with on_error support."""

    executor: WorkflowExecutor
    state: WorkflowState
    step_name: str
    step_spec: dict[str, Any]
    workflow: dict[str, Any]
    steps: dict[str, dict[str, Any]]
    tool_output: Any

    def run(self) -> dict[str, Any]:
        from .executor import StepState

        step = self.state.steps[self.step_name]
        step.status = "RUNNING"
        step.start_time = step.start_time or time.time()
        resolved_input = self.executor._resolve_step_input(self.state, self.workflow, self.step_name)

        on_error = self.step_spec.get("on_error")
        strategy_type, strategy_param = self.executor._parse_error_strategy(on_error)

        # Handle error marker
        if isinstance(self.tool_output, dict) and self.tool_output.get("__error__"):
            return self._handle_error(step, resolved_input, strategy_type, strategy_param)

        output = resolved_input if self.tool_output is None else self.tool_output
        step.status = "COMPLETED"
        step.end_time = time.time()
        step.output = output
        self.state.bindings[self.step_name] = output

        result = _advance_or_finish(self.executor, self.state, self.workflow, self.steps)
        self.executor.save_state(self.state)
        record_step_outcome(
            self.step_spec.get("cluster"),
            True,
            workflow_name=self.state.workflow_name,
            step_name=self.step_name,
        )
        log_event(
            "executor.step_completed",
            {
                "workflow": self.state.workflow_name,
                "step": self.step_name,
                "next_step": self.state.current_step,
            },
        )
        return result

    def _handle_error(
        self,
        step: StepState,
        resolved_input: Any,
        strategy_type: str,
        strategy_param: int,
    ) -> dict[str, Any]:
        from .executor import StepState as _StepState

        error_msg = str(self.tool_output.get("message", "Step failed"))

        if strategy_type == "retry" and step.iteration < strategy_param:
            step.iteration += 1
            step.status = "PENDING"
            self.executor.save_state(self.state)
            return {
                "status": "RETRY",
                "step": self.step_name,
                "attempt": step.iteration,
                "max_attempts": strategy_param,
                "input": resolved_input,
            }

        if strategy_type == "skip":
            self.executor._mark_step_skipped(self.state, self.step_name)
            result = _advance_or_finish(
                self.executor,
                self.state,
                self.workflow,
                self.steps,
                step=self.step_name,
                reason=error_msg,
            )
            if result["status"] == "CONTINUE":
                result["status"] = "SKIPPED"
                result["step"] = self.step_name
                result["reason"] = error_msg
            self.executor.save_state(self.state)
            return result

        if strategy_type == "fallback":
            fallback_step = self.step_spec.get("fallback")
            if fallback_step and fallback_step in self.steps:
                self.executor._fail_step(self.state, self.step_name, error_msg)
                self.state.bindings[self.step_name] = None
                if fallback_step not in self.state.step_order:
                    idx = self.state.step_order.index(self.step_name) + 1
                    self.state.step_order.insert(idx, fallback_step)
                if fallback_step not in self.state.steps:
                    self.state.steps[fallback_step] = _StepState(name=fallback_step)
                self.state.current_step = fallback_step
                self.executor.save_state(self.state)
                log_event(
                    "executor.fallback_triggered",
                    {
                        "workflow": self.state.workflow_name,
                        "step": self.step_name,
                        "fallback": fallback_step,
                    },
                )
                return {
                    "status": "FALLBACK",
                    "failed_step": self.step_name,
                    "fallback_step": fallback_step,
                    "error": error_msg,
                    "input": self.executor._resolve_step_input(
                        self.state, self.workflow, fallback_step
                    ),
                }

        # Default: fail the workflow
        self.executor._fail_step(self.state, self.step_name, error_msg)
        record_step_outcome(
            self.step_spec.get("cluster"),
            False,
            workflow_name=self.state.workflow_name,
            step_name=self.step_name,
        )
        self.state.current_step = None
        self.state.status = "FAILED"
        self.executor.save_state(self.state)
        return {"status": "FAILED", "step": self.step_name, "error": error_msg}


# Runner registry: step type -> runner class
STEP_RUNNERS: dict[str, type] = {
    "emit": EmitRunner,
    "fan_out": FanOutRunner,
    "loop": LoopRunner,
    "pipe": PipeRunner,
    "gate": PipeRunner,
}


def get_runner(
    step_type: str,
    executor: WorkflowExecutor,
    state: WorkflowState,
    step_name: str,
    step_spec: dict[str, Any],
    workflow: dict[str, Any],
    steps: dict[str, dict[str, Any]],
    tool_output: Any = None,
) -> StepRunner:
    """Create the appropriate runner for a step type."""
    runner_cls = STEP_RUNNERS.get(step_type, PipeRunner)
    kwargs: dict[str, Any] = {
        "executor": executor,
        "state": state,
        "step_name": step_name,
        "step_spec": step_spec,
        "workflow": workflow,
        "steps": steps,
    }
    # Only runners that accept tool_output
    if runner_cls in (PipeRunner, LoopRunner, EmitRunner):
        kwargs["tool_output"] = tool_output
    return runner_cls(**kwargs)
