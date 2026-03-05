"""Workflow DSL Prototype Executor.

Interprets workflow definitions and persists execution state so sessions can
execute a concrete "score" instead of using the DSL as validation-only docs.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .constants import BASE, ConductorError, atomic_write
from .observability import log_event

_REFERENCE_PATTERN = re.compile(r"\$\{([^}]+)\}")


@dataclass
class StepState:
    name: str
    status: str = "PENDING"  # PENDING, RUNNING, CHECKPOINT, COMPLETED, FAILED, SKIPPED
    start_time: float = 0.0
    end_time: float = 0.0
    output: Any = None
    error: str | None = None


@dataclass
class WorkflowState:
    workflow_name: str
    session_id: str
    step_order: list[str] = field(default_factory=list)
    steps: dict[str, StepState] = field(default_factory=dict)
    current_step: str | None = None
    global_input: Any = None
    bindings: dict[str, Any] = field(default_factory=dict)
    checkpoint_actions: dict[str, str] = field(default_factory=dict)
    status: str = "ACTIVE"  # ACTIVE, CHECKPOINT, COMPLETED, FAILED
    pending_checkpoint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkflowExecutor:
    """Interprets and executes (prototypically) a Workflow DSL."""

    def __init__(self, workflow_path: Path, state_file: Path | None = None):
        self.workflow_path = workflow_path
        self.spec = self._load_spec()
        # Default fallback, but methods now prefer workflow-specific files
        self.default_state_file = state_file or (BASE / ".conductor-workflow-state.json")

    def _get_state_path(self, workflow_name: str | None = None) -> Path:
        """Return the specific path for a workflow's execution state."""
        if not workflow_name:
            # Check if there's a link to an 'active' workflow
            active_link = BASE / ".conductor-active-workflow"
            if active_link.exists():
                workflow_name = active_link.read_text().strip()
            else:
                return self.default_state_file
        
        return BASE / f".conductor-workflow-{workflow_name}.json"

    def _set_active_workflow(self, workflow_name: str) -> None:
        (BASE / ".conductor-active-workflow").write_text(workflow_name)

    def _load_spec(self) -> dict[str, Any]:
        if not self.workflow_path.exists():
            raise ConductorError(f"Workflow DSL file not found: {self.workflow_path}")
        payload = yaml.safe_load(self.workflow_path.read_text()) or {}
        if not isinstance(payload, dict):
            raise ConductorError("Workflow DSL must be a YAML object.")
        return payload

    def _workflows(self) -> list[dict[str, Any]]:
        workflows = self.spec.get("workflows")
        if isinstance(workflows, list):
            return [w for w in workflows if isinstance(w, dict)]
        examples = self.spec.get("examples")
        if isinstance(examples, list):
            return [w for w in examples if isinstance(w, dict)]
        if isinstance(self.spec.get("name"), str) and isinstance(self.spec.get("steps"), list):
            return [self.spec]
        return []

    def list_workflows(self) -> list[str]:
        names = [str(w.get("name")) for w in self._workflows() if w.get("name")]
        return sorted(set(names))

    def _get_workflow(self, workflow_name: str) -> dict[str, Any] | None:
        for workflow in self._workflows():
            if workflow.get("name") == workflow_name:
                return workflow
        return None

    @staticmethod
    def _step_map(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
        mapping: dict[str, dict[str, Any]] = {}
        for step in workflow.get("steps", []):
            if isinstance(step, dict) and isinstance(step.get("name"), str):
                mapping[step["name"]] = step
        return mapping

    def load_state(self, workflow_name: str | None = None) -> WorkflowState | None:
        path = self._get_state_path(workflow_name)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            raw_steps = data.get("steps", {})
            steps = {
                name: StepState(**sdata)
                for name, sdata in raw_steps.items()
                if isinstance(sdata, dict)
            }
            return WorkflowState(
                workflow_name=str(data["workflow_name"]),
                session_id=str(data["session_id"]),
                step_order=[str(s) for s in data.get("step_order", list(steps.keys()))],
                steps=steps,
                current_step=data.get("current_step"),
                global_input=data.get("global_input"),
                bindings=data.get("bindings", {}),
                checkpoint_actions=data.get("checkpoint_actions", {}),
                status=str(data.get("status", "ACTIVE")),
                pending_checkpoint=data.get("pending_checkpoint"),
                metadata=data.get("metadata", {}),
            )
        except Exception as exc:
            log_event("executor.load_state_failed", {"error": str(exc), "path": str(path)})
            return None

    def save_state(self, state: WorkflowState) -> None:
        path = self._get_state_path(state.workflow_name)
        self._set_active_workflow(state.workflow_name)
        payload = {
            "workflow_name": state.workflow_name,
            "session_id": state.session_id,
            "step_order": state.step_order,
            "current_step": state.current_step,
            "global_input": state.global_input,
            "bindings": state.bindings,
            "checkpoint_actions": state.checkpoint_actions,
            "status": state.status,
            "pending_checkpoint": state.pending_checkpoint,
            "metadata": state.metadata,
            "steps": {
                name: {
                    "name": step.name,
                    "status": step.status,
                    "start_time": step.start_time,
                    "end_time": step.end_time,
                    "output": step.output,
                    "error": step.error,
                }
                for name, step in state.steps.items()
            },
        }
        atomic_write(path, json.dumps(payload, indent=2))

    def clear_state(self, workflow_name: str | None = None) -> None:
        path = self._get_state_path(workflow_name)
        path.unlink(missing_ok=True)
        active_link = BASE / ".conductor-active-workflow"
        if active_link.exists() and (not workflow_name or active_link.read_text().strip() == workflow_name):
            active_link.unlink()

    def _dependencies_satisfied(self, state: WorkflowState, step_name: str, steps: dict[str, dict[str, Any]]) -> bool:
        step = steps.get(step_name, {})
        deps = step.get("depends_on", [])
        if not isinstance(deps, list):
            return True
        for dep in deps:
            dep_name = str(dep)
            dep_state = state.steps.get(dep_name)
            if dep_state is None or dep_state.status not in {"COMPLETED", "SKIPPED"}:
                return False
        return True

    @staticmethod
    def _strip_quotes(value: str) -> str:
        raw = value.strip()
        if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
            return raw[1:-1]
        return raw

    @staticmethod
    def _is_empty_value(value: Any) -> bool:
        return value is None or value == "" or value == [] or value == {}

    @staticmethod
    def _split_condition_args(raw: str) -> list[str]:
        args: list[str] = []
        current: list[str] = []
        depth = 0
        in_quote: str | None = None
        for ch in raw:
            if in_quote:
                current.append(ch)
                if ch == in_quote:
                    in_quote = None
                continue
            if ch in {"'", '"'}:
                in_quote = ch
                current.append(ch)
                continue
            if ch == "(":
                depth += 1
                current.append(ch)
                continue
            if ch == ")":
                depth = max(0, depth - 1)
                current.append(ch)
                continue
            if ch == "," and depth == 0:
                args.append("".join(current).strip())
                current = []
                continue
            current.append(ch)
        if current:
            args.append("".join(current).strip())
        return [arg for arg in args if arg]

    def _resolve_condition_value(self, expression: str, state: WorkflowState) -> Any:
        expr = expression.strip()
        if expr.startswith("${") and expr.endswith("}"):
            return self._resolve_reference(expr[2:-1], state)
        return self._resolve_reference(expr, state)

    def _condition_passes(self, state: WorkflowState, condition: Any) -> bool:
        if condition is None:
            return True
        if isinstance(condition, bool):
            return condition
        if not isinstance(condition, str):
            return bool(condition)

        text = condition.strip()
        if not text:
            return True

        match = re.fullmatch(r"([a-zA-Z_][a-zA-Z0-9_]*)\((.*)\)", text)
        if not match:
            # Fallback: resolve as truthy reference/expression
            value = self._resolve_condition_value(text, state)
            return bool(value)

        fn_name = match.group(1).lower()
        args = self._split_condition_args(match.group(2))

        if fn_name in {"success", "failure", "approval", "all_passed", "any_passed"}:
            if not args:
                return False
            step_name = self._strip_quotes(args[0])
            step = state.steps.get(step_name)
            if fn_name == "success":
                return step is not None and step.status == "COMPLETED"
            if fn_name == "failure":
                return step is not None and step.status == "FAILED"
            if fn_name in {"all_passed", "any_passed"}:
                # Parallel branch aggregation is represented by parent step completion in this prototype.
                return step is not None and step.status == "COMPLETED"
            action = state.checkpoint_actions.get(step_name, "").lower()
            return action in {"approve", "modify"}

        if fn_name == "exists":
            if not args:
                return False
            value = self._resolve_condition_value(args[0], state)
            return not self._is_empty_value(value)

        if fn_name == "empty":
            if not args:
                return False
            value = self._resolve_condition_value(args[0], state)
            return self._is_empty_value(value)

        if fn_name == "gt":
            if len(args) < 2:
                return False
            lhs = self._resolve_condition_value(args[0], state)
            rhs_raw = self._strip_quotes(args[1])
            try:
                lhs_value = float(lhs)
                rhs_value = float(rhs_raw)
            except (TypeError, ValueError):
                return False
            return lhs_value > rhs_value

        if fn_name == "contains":
            if len(args) < 2:
                return False
            container = self._resolve_condition_value(args[0], state)
            needle = self._strip_quotes(args[1])
            if isinstance(container, str):
                return needle in container
            if isinstance(container, list):
                return needle in [str(item) for item in container]
            if isinstance(container, dict):
                return needle in container or needle in [str(v) for v in container.values()]
            return False

        if fn_name == "matches":
            if len(args) < 2:
                return False
            value = self._resolve_condition_value(args[0], state)
            pattern = self._strip_quotes(args[1])
            try:
                return re.search(pattern, "" if value is None else str(value)) is not None
            except re.error:
                return False

        return bool(self._resolve_condition_value(text, state))

    def _mark_step_skipped(self, state: WorkflowState, step_name: str) -> None:
        step = state.steps[step_name]
        if step.status in {"COMPLETED", "FAILED", "SKIPPED"}:
            return
        step.status = "SKIPPED"
        step.end_time = time.time()
        state.bindings[step_name] = None

    def _find_next_ready_step(self, state: WorkflowState, steps: dict[str, dict[str, Any]]) -> str | None:
        for step_name in state.step_order:
            step_state = state.steps.get(step_name)
            if step_state is None:
                continue
            if step_state.status in {"COMPLETED", "FAILED", "SKIPPED"}:
                continue
            if self._dependencies_satisfied(state, step_name, steps):
                condition = steps.get(step_name, {}).get("condition")
                if not self._condition_passes(state, condition):
                    self._mark_step_skipped(state, step_name)
                    continue
                return step_name
        return None

    def start_workflow(self, workflow_name: str, session_id: str, global_input: Any = None) -> WorkflowState:
        workflow = self._get_workflow(workflow_name)
        if workflow is None:
            raise ConductorError(f"Workflow not found: {workflow_name}")

        step_order = [step["name"] for step in workflow.get("steps", []) if isinstance(step, dict) and step.get("name")]
        if not step_order:
            raise ConductorError(f"Workflow '{workflow_name}' has no executable steps.")

        state = WorkflowState(
            workflow_name=workflow_name,
            session_id=session_id,
            step_order=step_order,
            global_input=global_input,
        )

        for step_name in step_order:
            state.steps[step_name] = StepState(name=step_name)

        steps = self._step_map(workflow)
        state.current_step = self._find_next_ready_step(state, steps)

        self.save_state(state)
        log_event(
            "executor.workflow_started",
            {
                "workflow": workflow_name,
                "session": session_id,
                "first_step": state.current_step,
            },
        )
        return state

    @staticmethod
    def _walk_path(value: Any, path: str) -> Any:
        cursor = value
        remaining = path
        while remaining:
            if remaining.startswith("["):
                end_idx = remaining.find("]")
                if end_idx == -1:
                    return None
                index_str = remaining[1:end_idx]
                if not isinstance(cursor, list):
                    return None
                try:
                    cursor = cursor[int(index_str)]
                except (ValueError, IndexError):
                    return None
                remaining = remaining[end_idx + 1 :]
                if remaining.startswith("."):
                    remaining = remaining[1:]
                continue

            dot_idx = remaining.find(".")
            bracket_idx = remaining.find("[")
            if dot_idx == -1 and bracket_idx == -1:
                key = remaining
                remaining = ""
            elif dot_idx != -1 and (bracket_idx == -1 or dot_idx < bracket_idx):
                key = remaining[:dot_idx]
                remaining = remaining[dot_idx + 1 :]
            else:
                key = remaining[:bracket_idx]
                remaining = remaining[bracket_idx:]

            if not isinstance(cursor, dict):
                return None
            cursor = cursor.get(key)

        return cursor

    def _resolve_reference(self, expression: str, state: WorkflowState) -> Any:
        raw = expression.strip()
        parts = [part.strip() for part in raw.split("|")]
        reference = parts[0]
        transforms = parts[1:]

        if reference == "input":
            value = state.global_input
        elif reference.startswith("input."):
            value = self._walk_path(state.global_input, reference[len("input.") :])
        else:
            step_name, _, remainder = reference.partition(".")
            value = state.bindings.get(step_name)
            if remainder:
                value = self._walk_path(value, remainder)

        for transform in transforms:
            if transform == "text":
                if isinstance(value, (dict, list)):
                    value = json.dumps(value)
                else:
                    value = "" if value is None else str(value)
            elif transform == "json":
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass
            elif transform == "first" and isinstance(value, list):
                value = value[0] if value else None
            elif transform == "last" and isinstance(value, list):
                value = value[-1] if value else None
            elif transform == "count" and isinstance(value, (list, dict, str)):
                value = len(value)

        return value

    def _resolve_value(self, value: Any, state: WorkflowState) -> Any:
        if isinstance(value, str):
            match = _REFERENCE_PATTERN.fullmatch(value.strip())
            if match:
                return self._resolve_reference(match.group(1), state)

            def _replace_ref(match_obj: re.Match[str]) -> str:
                resolved = self._resolve_reference(match_obj.group(1), state)
                if isinstance(resolved, (dict, list)):
                    return json.dumps(resolved)
                return "" if resolved is None else str(resolved)

            return _REFERENCE_PATTERN.sub(_replace_ref, value)

        if isinstance(value, dict):
            return {k: self._resolve_value(v, state) for k, v in value.items()}

        if isinstance(value, list):
            return [self._resolve_value(item, state) for item in value]

        return value

    def _pipe_input(self, state: WorkflowState, step_name: str) -> Any:
        if step_name not in state.step_order:
            return None
        idx = state.step_order.index(step_name)
        for prev in reversed(state.step_order[:idx]):
            prev_state = state.steps.get(prev)
            if prev_state and prev_state.status == "COMPLETED":
                return prev_state.output
        return None

    def _resolve_step_input(self, state: WorkflowState, workflow: dict[str, Any], step_name: str) -> Any:
        steps = self._step_map(workflow)
        step = steps.get(step_name, {})
        if "input" in step:
            return self._resolve_value(step.get("input"), state)
        return self._pipe_input(state, step_name)

    def run_step(
        self,
        step_name: str,
        tool_output: Any = None,
        checkpoint_action: str | None = None,
        workflow_name: str | None = None,
    ) -> dict[str, Any]:
        """Advance the workflow by executing one step.

        `pipe` behavior: when output is omitted, the step receives previous completed
        output (or resolved `input`) and persists that value as output.
        `checkpoint` behavior: checkpointed steps pause until explicit action.
        """
        state = self.load_state(workflow_name)
        if not state:
            raise ConductorError("No active workflow state found. Run start_workflow first.")

        workflow = self._get_workflow(state.workflow_name)
        if workflow is None:
            raise ConductorError(f"Workflow not found in spec: {state.workflow_name}")

        steps = self._step_map(workflow)
        if step_name not in state.steps or step_name not in steps:
            raise ConductorError(f"Step '{step_name}' not found in workflow '{state.workflow_name}'")

        if state.current_step and state.current_step != step_name:
            raise ConductorError(f"Current step is '{state.current_step}', not '{step_name}'")

        step = state.steps[step_name]
        step_spec = steps[step_name]

        if not self._dependencies_satisfied(state, step_name, steps):
            raise ConductorError(f"Dependencies are not satisfied for step '{step_name}'")

        requires_checkpoint = bool(step_spec.get("checkpoint"))
        if requires_checkpoint:
            action = checkpoint_action.lower() if checkpoint_action else None
            if action is None:
                step.status = "CHECKPOINT"
                state.status = "CHECKPOINT"
                state.pending_checkpoint = step_name
                state.current_step = step_name
                self.save_state(state)
                return {
                    "status": "CHECKPOINT",
                    "step": step_name,
                    "allowed_actions": ["approve", "modify", "abort"],
                    "input": self._resolve_step_input(state, workflow, step_name),
                }
            if action not in {"approve", "modify", "abort"}:
                raise ConductorError("checkpoint_action must be one of: approve, modify, abort")
            if action == "abort":
                step.status = "FAILED"
                step.error = "Checkpoint aborted by human"
                step.end_time = time.time()
                state.checkpoint_actions[step_name] = "abort"
                state.current_step = None
                state.pending_checkpoint = None
                state.status = "FAILED"
                self.save_state(state)
                log_event("executor.step_aborted", {"workflow": state.workflow_name, "step": step_name})
                return {"status": "ABORTED", "step": step_name}

            state.checkpoint_actions[step_name] = action
            state.pending_checkpoint = None
            state.status = "ACTIVE"

        condition = step_spec.get("condition")
        if not self._condition_passes(state, condition):
            self._mark_step_skipped(state, step_name)
            next_step_after_skip = self._find_next_ready_step(state, steps)
            if next_step_after_skip:
                state.current_step = next_step_after_skip
                next_spec = steps[next_step_after_skip]
                result = {
                    "status": "SKIPPED",
                    "step": step_name,
                    "next_step": next_step_after_skip,
                    "checkpoint": bool(next_spec.get("checkpoint")),
                    "input": self._resolve_step_input(state, workflow, next_step_after_skip),
                }
            else:
                state.current_step = None
                state.status = "COMPLETED"
                result = {"status": "FINISHED"}
            self.save_state(state)
            return result

        step.status = "RUNNING"
        step.start_time = step.start_time or time.time()
        resolved_input = self._resolve_step_input(state, workflow, step_name)
        output = resolved_input if tool_output is None else tool_output

        step.status = "COMPLETED"
        step.end_time = time.time()
        step.output = output
        state.bindings[step_name] = output

        next_step = self._find_next_ready_step(state, steps)
        if next_step:
            state.current_step = next_step
            next_spec = steps[next_step]
            result = {
                "status": "CONTINUE",
                "next_step": next_step,
                "checkpoint": bool(next_spec.get("checkpoint")),
                "input": self._resolve_step_input(state, workflow, next_step),
            }
        else:
            state.current_step = None
            state.status = "COMPLETED"
            result = {"status": "FINISHED"}

        self.save_state(state)
        log_event(
            "executor.step_completed",
            {
                "workflow": state.workflow_name,
                "step": step_name,
                "next_step": state.current_step,
            },
        )
        return result

    def get_current_step_context(self, workflow_name: str | None = None) -> dict[str, Any]:
        state = self.load_state(workflow_name)
        if not state:
            return {"active": False}

        workflow = self._get_workflow(state.workflow_name)
        if workflow is None:
            return {
                "active": True,
                "workflow": state.workflow_name,
                "status": state.status,
                "error": "workflow_spec_missing",
            }

        step_name = state.current_step
        if not step_name:
            return {
                "active": True,
                "workflow": state.workflow_name,
                "status": state.status,
                "current_step": None,
            }

        step_spec = self._step_map(workflow).get(step_name, {})
        return {
            "active": True,
            "workflow": state.workflow_name,
            "status": state.status,
            "current_step": step_name,
            "cluster": step_spec.get("cluster"),
            "tool": step_spec.get("tool"),
            "checkpoint": bool(step_spec.get("checkpoint")),
            "depends_on": step_spec.get("depends_on", []),
            "input": self._resolve_step_input(state, workflow, step_name),
        }

    def get_briefing(self, workflow_name: str | None = None) -> dict[str, Any]:
        """Briefing payload used by patchbay and MCP surfaces."""
        state = self.load_state(workflow_name)
        if not state:
            return {"active": False}

        total_steps = len(state.steps)
        completed_steps = sum(1 for step in state.steps.values() if step.status == "COMPLETED")
        context = self.get_current_step_context(workflow_name)

        return {
            "active": True,
            "workflow": state.workflow_name,
            "session_id": state.session_id,
            "current_step": state.current_step,
            "status": state.status,
            "pending_checkpoint": state.pending_checkpoint,
            "progress": f"{completed_steps}/{total_steps}",
            "current_context": context,
            "suggested_tool_call": self.get_suggested_tool_call(workflow_name) if state.current_step else None,
        }

    def get_suggested_tool_call(self, workflow_name: str | None = None) -> dict[str, Any] | None:
        """Suggest the concrete MCP tool call for the current step."""
        state = self.load_state(workflow_name)
        if not state or not state.current_step:
            return None

        workflow = self._get_workflow(state.workflow_name)
        if not workflow:
            return None

        step_spec = self._step_map(workflow).get(state.current_step, {})
        tool_name = step_spec.get("tool")
        if not tool_name:
            return None

        # Resolve arguments
        raw_args = step_spec.get("arguments", {})
        resolved_args = self._resolve_value(raw_args, state)

        # Special handling for common tools
        # If 'input' is in arguments, it's already resolved. 
        # If not, and the tool is known to take an input, we might inject it.
        
        return {
            "step": state.current_step,
            "tool": tool_name,
            "arguments": resolved_args,
            "explanation": step_spec.get("description", f"Execute {tool_name} for step {state.current_step}"),
        }
