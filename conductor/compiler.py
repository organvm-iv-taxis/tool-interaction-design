"""Layer 3.5: Workflow Compiler — JIT generation of execution scores."""

from __future__ import annotations

import time
from typing import Any, Optional
from pathlib import Path

from .constants import WORKFLOW_DSL_PATH
from .executor import WorkflowExecutor, WorkflowState, StepState
from .work_item import hashlib_id

try:
    from router import RoutingEngine, Ontology
except ImportError:
    RoutingEngine = None  # type: ignore
    Ontology = None  # type: ignore


class WorkflowCompiler:
    """Compiles a RoutingEngine path into a runnable WorkflowState."""

    def __init__(self, engine: RoutingEngine, ontology: Ontology):
        self.engine = engine
        self.ontology = ontology
        self.executor = WorkflowExecutor(WORKFLOW_DSL_PATH)

    def compile_mission(
        self, 
        goal: str, 
        start_cluster: str, 
        end_cluster: str, 
        session_id: str,
        input_data: Optional[dict[str, Any]] = None
    ) -> WorkflowState:
        """Find the healthiest path and compile it into a stateful score."""
        
        # 1. Find the path using the health-aware RoutingEngine
        paths = self.engine.find_cluster_paths(start_cluster, end_cluster, max_paths=1)
        if not paths:
            raise ValueError(f"No path found between {start_cluster} and {end_cluster}")
        
        cluster_path = paths[0]
        
        # 2. Map clusters to specific tools
        steps: dict[str, StepState] = {}
        step_order: list[str] = []
        for i, cluster_id in enumerate(cluster_path):
            cluster = self.ontology.clusters.get(cluster_id)
            if not cluster:
                continue
                
            # Pick the best tool
            tool_name = cluster.tools[0] if cluster.tools else "unknown"
            for alt in self.engine.alternatives:
                if alt.cluster == cluster_id and alt.tools_ranked:
                    tool_name = alt.tools_ranked[0]
                    break
            
            # Descriptive step names: goal_slug + cluster_short
            goal_slug = goal.lower().replace(" ", "_")[:15].strip("_")
            step_name = f"{goal_slug}_{cluster_id}"
            if step_name in steps:
                step_name = f"{step_name}_{i}"

            steps[step_name] = StepState(
                name=step_name,
                status="PENDING",
            )
            step_order.append(step_name)

        # 3. Create the state
        workflow_name = f"synthetic-{hashlib_id(goal, start_cluster, end_cluster)}"
        state = WorkflowState(
            workflow_name=workflow_name,
            session_id=session_id,
            step_order=step_order,
            steps=steps,
            current_step=step_order[0] if step_order else None,
            status="ACTIVE",
        )
        
        # 3.5 Predictive Pre-Mortem Simulator
        self._simulate_and_harden(state, cluster_path)
        
        # 4. Inject into executor (persist it)
        self.executor.save_state(state)
        return state

    def _simulate_and_harden(self, state: WorkflowState, cluster_path: list[str]) -> None:
        """Shadow Trace: Assess path health and inject checkpoints if degraded."""
        # Calculate path health
        total_health = 0.0
        for cid in cluster_path:
            total_health += self.engine.get_cluster_health(cid)
        avg_health = total_health / len(cluster_path) if cluster_path else 1.0

        # If health is below threshold, rewrite score to include a checkpoint
        if avg_health < 0.85:
            # Find the weakest link
            weakest_idx = 0
            weakest_health = 1.0
            for i, cid in enumerate(cluster_path):
                h = self.engine.get_cluster_health(cid)
                if h < weakest_health:
                    weakest_health = h
                    weakest_idx = i

            target_step_name = f"step_{weakest_idx}_{cluster_path[weakest_idx]}"
            
            # Inject validation checkpoint before the weak link
            checkpoint_name = f"validation_checkpoint_before_{cluster_path[weakest_idx]}"
            state.steps[checkpoint_name] = StepState(
                name=checkpoint_name,
                status="PENDING",
                metadata={
                    "cluster": "governance_engine",
                    "tool": "conductor_doctor",
                    "description": f"Pre-mortem injected checkpoint due to degraded path health ({avg_health:.2f})",
                    "is_synthetic": True,
                    "is_checkpoint": True
                }
            )
            
            # Rewrite step order
            new_order = []
            for name in state.step_order:
                if name == target_step_name:
                    new_order.append(checkpoint_name)
                new_order.append(name)
            
            state.step_order = new_order
            state.current_step = new_order[0]
            state.metadata = {"shadow_trace_health": avg_health, "hardened": True}
        else:
            state.metadata = {"shadow_trace_health": avg_health, "hardened": False}

    def generate_description(self, state: WorkflowState) -> str:
        """Generate a human-readable summary of the compiled score."""
        lines = [f"Mission: {state.workflow_name}"]
        for name in state.step_order:
            step = state.steps[name]
            lines.append(f"  [{name}] -> {step.status}")
        return "\n".join(lines)
