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

from .constants import BASE, ConductorError, STATE_DIR, WORKFLOW_DSL_PATH, atomic_write
from .feedback import record_step_outcome
from .observability import log_event

_REFERENCE_PATTERN = re.compile(r"\$\{([^}]+)\}")

# Maturity levels for DSL primitives — loaded once from workflow-dsl.yaml spec.
# Primitives not listed here default to "alpha".
_PRIMITIVE_MATURITY: dict[str, str] = {}


def _load_primitive_maturity() -> dict[str, str]:
    """Load maturity annotations from the workflow DSL spec section."""
    global _PRIMITIVE_MATURITY
    if _PRIMITIVE_MATURITY:
        return _PRIMITIVE_MATURITY
    try:
        raw = yaml.safe_load(WORKFLOW_DSL_PATH.read_text()) or {}
        primitives = raw.get("spec", {}).get("primitives", {})
        for name, defn in primitives.items():
            if isinstance(defn, dict):
                _PRIMITIVE_MATURITY[name] = defn.get("maturity", "alpha")
    except Exception as exc:
        from .observability import log_event
        log_event("executor.maturity_load_error", {"error": str(exc)})
    return _PRIMITIVE_MATURITY


def _warn_if_alpha(primitive_name: str, step_name: str) -> None:
    """Log a warning when an alpha-maturity primitive is used."""
    maturity_map = _load_primitive_maturity()
    maturity = maturity_map.get(primitive_name, "alpha")
    if maturity == "alpha":
        log_event(
            "executor.alpha_primitive_warning",
            {
                "primitive": primitive_name,
                "step": step_name,
                "maturity": maturity,
                "message": (
                    f"Primitive '{primitive_name}' has alpha maturity. "
                    f"Behavior may be incomplete or differ from specification."
                ),
            },
        )


@dataclass
class StepState:
    name: str
    status: str = "PENDING"  # PENDING, RUNNING, CHECKPOINT, COMPLETED, FAILED, SKIPPED
    start_time: float = 0.0
    end_time: float = 0.0
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    iteration: int = 0
    max_iterations: int = 0


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
        self.default_state_file = state_file or (STATE_DIR / "workflows" / "_default.json")

    def _get_state_path(self, workflow_name: str | None = None) -> Path:
        """Return the specific path for a workflow's execution state.

        Validates that the active-workflow pointer is not stale. If the
        pointer references a workflow whose state file no longer exists,
        the pointer is cleaned up automatically.
        """
        if not workflow_name:
            active_link = STATE_DIR / "workflows" / "_active"
            if active_link.exists():
                candidate = active_link.read_text().strip()
                if candidate:
                    candidate_path = STATE_DIR / "workflows" / f"{candidate}.json"
                    if candidate_path.exists():
                        workflow_name = candidate
                    else:
                        # Stale pointer — clean it up
                        active_link.unlink(missing_ok=True)
                        log_event(
                            "executor.stale_pointer_cleaned",
                            {"stale_workflow": candidate, "pointer": str(active_link)},
                        )
            if not workflow_name:
                return self.default_state_file

        return STATE_DIR / "workflows" / f"{workflow_name}.json"

    def _set_active_workflow(self, workflow_name: str) -> None:
        wf_dir = STATE_DIR / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "_active").write_text(workflow_name)

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
                    "metadata": step.metadata,
                    "iteration": step.iteration,
                    "max_iterations": step.max_iterations,
                }
                for name, step in state.steps.items()
            },
        }
        atomic_write(path, json.dumps(payload, indent=2))

    def clear_state(self, workflow_name: str | None = None) -> None:
        path = self._get_state_path(workflow_name)
        path.unlink(missing_ok=True)
        active_link = STATE_DIR / "workflows" / "_active"
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
                # Check for fan_out branches: {step_name}__branch_*
                branch_steps = [
                    s for name, s in state.steps.items()
                    if name.startswith(f"{step_name}__branch_")
                ]
                if branch_steps:
                    if fn_name == "all_passed":
                        return all(s.status == "COMPLETED" for s in branch_steps)
                    return any(s.status == "COMPLETED" for s in branch_steps)
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
            t = transform.strip()
            if t == "text":
                if isinstance(value, (dict, list)):
                    value = json.dumps(value)
                else:
                    value = "" if value is None else str(value)
            elif t == "json":
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass
            elif t == "first" and isinstance(value, list):
                value = value[0] if value else None
            elif t == "last" and isinstance(value, list):
                value = value[-1] if value else None
            elif t == "count" and isinstance(value, (list, dict, str)):
                value = len(value)
            elif t == "lines":
                value = str(value).splitlines() if value is not None else []
            elif t == "flatten" and isinstance(value, list):
                flat: list[Any] = []
                for item in value:
                    if isinstance(item, list):
                        flat.extend(item)
                    else:
                        flat.append(item)
                value = flat
            elif t == "unique" and isinstance(value, list):
                seen: set[Any] = set()
                unique: list[Any] = []
                for item in value:
                    key = json.dumps(item, sort_keys=True) if isinstance(item, (dict, list)) else item
                    if key not in seen:
                        seen.add(key)
                        unique.append(item)
                value = unique
            elif t == "sort" and isinstance(value, list):
                try:
                    value = sorted(value)
                except TypeError:
                    pass
            elif t.startswith("filter(") and t.endswith(")") and isinstance(value, list):
                pred = t[7:-1].strip()
                pred = self._strip_quotes(pred)
                value = [item for item in value if pred in str(item)]
            elif t.startswith("join(") and t.endswith(")") and isinstance(value, list):
                sep = self._strip_quotes(t[5:-1].strip())
                value = sep.join(str(item) for item in value)
            elif t.startswith("take(") and t.endswith(")") and isinstance(value, list):
                try:
                    n = int(t[5:-1].strip())
                    value = value[:n]
                except ValueError:
                    pass

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

    def _fail_step(self, state: WorkflowState, step_name: str, error: str) -> None:
        """Mark a step as FAILED and record the error."""
        step = state.steps[step_name]
        step.status = "FAILED"
        step.error = error
        step.end_time = time.time()

    @staticmethod
    def _parse_error_strategy(strategy: str | None) -> tuple[str, int]:
        """Parse on_error strategy string. Returns (strategy_type, param)."""
        if not strategy:
            return ("fail", 0)
        s = strategy.strip().lower()
        match = re.fullmatch(r"retry\((\d+)\)", s)
        if match:
            return ("retry", int(match.group(1)))
        if s == "fallback":
            return ("fallback", 0)
        if s == "skip":
            return ("skip", 0)
        return ("fail", 0)

    def run_step(
        self,
        step_name: str,
        tool_output: Any = None,
        checkpoint_action: str | None = None,
        workflow_name: str | None = None,
    ) -> dict[str, Any]:
        """Advance the workflow by executing one step.

        Supported primitives: pipe, gate, checkpoint, fan_out/fan_in, loop,
        on_error/fallback, emit.
        """
        from .step_runners import get_runner

        state = self.load_state(workflow_name)
        if not state:
            raise ConductorError("No active workflow state found. Run start_workflow first.")

        workflow = self._get_workflow(state.workflow_name)
        if workflow is None:
            raise ConductorError(f"Workflow not found in spec: {state.workflow_name}")

        steps = self._step_map(workflow)
        if step_name not in state.steps:
            raise ConductorError(f"Step '{step_name}' not found in workflow '{state.workflow_name}'")

        step_spec = steps.get(step_name, {})

        if state.current_step and state.current_step != step_name:
            raise ConductorError(f"Current step is '{state.current_step}', not '{step_name}'")

        step = state.steps[step_name]

        if not self._dependencies_satisfied(state, step_name, steps):
            raise ConductorError(f"Dependencies are not satisfied for step '{step_name}'")

        # --- Oracle pre-step advisory ---
        oracle_pre_advisories: list[dict] = []
        try:
            from .oracle import Oracle, OracleContext
            _oracle = Oracle()
            _ctx = OracleContext(
                trigger="workflow_pre_step",
                workflow_step=step_name,
                workflow_name=state.workflow_name,
            )
            _pre_advs = _oracle.consult(_ctx, max_advisories=3)
            oracle_pre_advisories = [a.to_dict() for a in _pre_advs]
        except Exception as exc:
            log_event(
                "executor.oracle_pre_advisory_error",
                {
                    "workflow": state.workflow_name,
                    "step": step_name,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:200],
                },
            )

        # --- Checkpoint handling ---
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

        # --- Condition check ---
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

        # --- Primitive dispatch via strategy ---
        step_type = step_spec.get("type", "pipe")
        _warn_if_alpha(step_type, step_name)

        runner = get_runner(
            step_type, self, state, step_name, step_spec, workflow, steps, tool_output
        )
        result = runner.run()

        # --- Oracle post-step advisory (on successful completion) ---
        if result.get("status") in {"CONTINUE", "FINISHED"}:
            try:
                from .oracle import Oracle as PostOracle, OracleContext as PostCtx
                _post_oracle = PostOracle()
                _post_ctx = PostCtx(
                    trigger="workflow_post_step",
                    workflow_step=step_name,
                    workflow_name=state.workflow_name,
                )
                _post_advs = _post_oracle.consult(_post_ctx, max_advisories=2)
                if _post_advs:
                    result["oracle_advisories"] = [a.to_dict() for a in _post_advs]
            except Exception as exc:
                log_event(
                    "executor.oracle_post_advisory_error",
                    {
                        "workflow": state.workflow_name,
                        "step": step_name,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:200],
                    },
                )

        if oracle_pre_advisories:
            result.setdefault("oracle_pre_advisories", oracle_pre_advisories)

        return result

    def resume_workflow(
        self,
        workflow_name: str | None = None,
        from_step: str | None = None,
    ) -> dict[str, Any]:
        """Resume a failed/checkpoint workflow, optionally rewinding to a specific step.

        If ``from_step`` is provided, all steps from that point forward are reset
        to PENDING so the workflow can be re-executed from that point.
        """
        state = self.load_state(workflow_name)
        if not state:
            raise ConductorError("No workflow state found to resume.")

        workflow = self._get_workflow(state.workflow_name)
        if workflow is None:
            raise ConductorError(f"Workflow spec not found: {state.workflow_name}")

        steps = self._step_map(workflow)

        if from_step:
            if from_step not in state.steps:
                raise ConductorError(
                    f"Step '{from_step}' not found in workflow '{state.workflow_name}'"
                )
            # Reset from_step and all subsequent steps to PENDING
            rewind_idx = state.step_order.index(from_step) if from_step in state.step_order else 0
            reset_count = 0
            for step_name in state.step_order[rewind_idx:]:
                step = state.steps.get(step_name)
                if step:
                    step.status = "PENDING"
                    step.start_time = 0.0
                    step.end_time = 0.0
                    step.output = None
                    step.error = None
                    step.iteration = 0
                    state.bindings.pop(step_name, None)
                    state.checkpoint_actions.pop(step_name, None)
                    reset_count += 1
            # Also reset dynamically-injected steps (fan_out branches etc.)
            for step_name in list(state.steps.keys()):
                if step_name not in state.step_order:
                    continue
                if state.step_order.index(step_name) >= rewind_idx:
                    step = state.steps[step_name]
                    step.status = "PENDING"
                    step.start_time = 0.0
                    step.end_time = 0.0
                    step.output = None
                    step.error = None
                    step.iteration = 0
                    state.bindings.pop(step_name, None)
        else:
            # Just resume from where we stopped — reset current failed/checkpoint step
            reset_count = 0
            if state.current_step:
                step = state.steps.get(state.current_step)
                if step and step.status in {"FAILED", "CHECKPOINT"}:
                    step.status = "PENDING"
                    step.start_time = 0.0
                    step.end_time = 0.0
                    step.output = None
                    step.error = None
                    step.iteration = 0
                    reset_count = 1

        state.status = "ACTIVE"
        state.pending_checkpoint = None

        # Find next ready step
        state.current_step = self._find_next_ready_step(state, steps)
        if from_step and not state.current_step:
            # If rewinding didn't produce a ready step, point to from_step
            state.current_step = from_step

        self.save_state(state)
        log_event(
            "executor.workflow_resumed",
            {
                "workflow": state.workflow_name,
                "from_step": from_step,
                "current_step": state.current_step,
                "reset_count": reset_count,
            },
        )

        completed = sum(1 for s in state.steps.values() if s.status == "COMPLETED")
        return {
            "status": "RESUMED",
            "workflow": state.workflow_name,
            "current_step": state.current_step,
            "from_step": from_step,
            "progress": f"{completed}/{len(state.steps)}",
        }

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
