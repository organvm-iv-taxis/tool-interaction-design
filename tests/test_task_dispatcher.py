"""Tests for the TaskDispatcher — work type classification, restriction filtering, dispatch plans."""

from __future__ import annotations

import pytest


class TestWorkTypeClassification:
    def test_classify_architecture(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        assert dispatcher.classify("design the database schema") == "architecture"

    def test_classify_boilerplate(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        assert dispatcher.classify("scaffold CRUD endpoints for users") == "boilerplate_generation"

    def test_classify_research(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        assert dispatcher.classify("evaluate pricing for cloud APIs") == "research"

    def test_classify_mechanical_refactoring(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        assert dispatcher.classify("convert all naming convention to snake_case") == "mechanical_refactoring"

    def test_classify_audit(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        assert dispatcher.classify("run a security review of the auth module") == "audit"

    def test_classify_content(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        assert dispatcher.classify("write the README and CHANGELOG") == "content_generation"

    def test_classify_unclassified(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        assert dispatcher.classify("do something completely unrelated") == "unclassified"


class TestDispatchPlanRouting:
    def test_architecture_excludes_gemini(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        plan = dispatcher.plan("design module boundaries", phase="SHAPE")
        assert plan.work_type == "architecture"
        assert plan.cognitive_class == "strategic"

        agent_names = {s.agent for s in plan.ranked_agents}
        assert "claude" in agent_names
        assert "gemini" not in agent_names

        # Gemini should be in excluded list
        excluded_names = {e["agent"] for e in plan.excluded_agents}
        assert "gemini" in excluded_names

    def test_architecture_excludes_codex(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        plan = dispatcher.plan("select framework dependencies", phase="SHAPE")

        agent_names = {s.agent for s in plan.ranked_agents}
        # Codex max_cognitive_class is tactical, architecture is strategic
        assert "codex" not in agent_names

    def test_boilerplate_allows_claude_and_codex(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        plan = dispatcher.plan("scaffold test stubs", phase="BUILD")
        assert plan.work_type == "boilerplate_generation"
        assert plan.cognitive_class == "mechanical"

        agent_names = {s.agent for s in plan.ranked_agents}
        assert "claude" in agent_names
        assert "codex" in agent_names
        # Gemini excluded: BUILD affinity 0.5 < required 0.6
        assert "gemini" not in agent_names

    def test_research_excludes_gemini_by_cognitive_class(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        plan = dispatcher.plan("API evaluation and competitor analysis", phase="FRAME")
        assert plan.work_type == "research"
        # Research is strategic, Gemini is max mechanical
        agent_names = {s.agent for s in plan.ranked_agents}
        assert "gemini" not in agent_names

    def test_explicit_work_type_override(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        # Even though description sounds like research, explicit override to boilerplate
        plan = dispatcher.plan(
            "research the API docs",
            phase="BUILD",
            work_type="boilerplate_generation",
        )
        assert plan.work_type == "boilerplate_generation"

    def test_claude_ranks_first_for_architecture(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        plan = dispatcher.plan("design the API contract", phase="SHAPE")
        assert plan.recommended == "claude"

    def test_verification_policy_propagated(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        plan = dispatcher.plan("scaffold CRUD endpoints", phase="BUILD")
        assert plan.verification_policy == "cross_agent_mandatory"

    def test_dispatch_plan_to_dict(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        plan = dispatcher.plan("design schema", phase="SHAPE")
        d = plan.to_dict()
        assert "work_type" in d
        assert "ranked_agents" in d
        assert "excluded_agents" in d
        assert isinstance(d["ranked_agents"], list)

    def test_unclassified_returns_all_agents(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        plan = dispatcher.plan("xyzzy foobar", phase="BUILD")
        assert plan.work_type == "unclassified"
        # Unclassified should not apply work type filters
        assert len(plan.ranked_agents) >= 3

    def test_exclusion_reasons_are_specific(self):
        from conductor.task_dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher()
        plan = dispatcher.plan("design module boundaries", phase="SHAPE")
        gemini_excl = next(
            (e for e in plan.excluded_agents if e["agent"] == "gemini"),
            None,
        )
        assert gemini_excl is not None
        assert "cognitive_class" in gemini_excl["reason"] or "never_decide" in gemini_excl["reason"]
