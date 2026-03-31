"""Tests for prompt patch lifecycle — create, inject, track recurrence."""

from __future__ import annotations

from pathlib import Path

from conductor.prompt_patches import (
    PromptPatch,
    Amplification,
    PatchStore,
    patches_for_dispatch,
)


def test_patch_creation():
    patch = PromptPatch(
        id="PP-2026-0330-001",
        created_from="D-2026-0330-001",
        rule="Include exact filesystem path of referenced documents.",
        agents=["gemini"],
        repos=["*"],
        work_types=["*"],
        model_version_tested="gemini-3-flash-preview",
    )
    assert patch.lifecycle_status == "active"
    assert patch.times_injected == 0
    d = patch.to_dict()
    assert d["rule"].startswith("Include")
    restored = PromptPatch.from_dict(d)
    assert restored.id == "PP-2026-0330-001"


def test_patch_store_round_trip(tmp_path):
    store = PatchStore(base_dir=tmp_path / "prompt-patches")
    patch = PromptPatch(
        id="PP-2026-0330-001",
        created_from="D-2026-0330-001",
        rule="Test rule",
        agents=["gemini"],
    )
    store.save(patch)
    loaded = store.load("PP-2026-0330-001")
    assert loaded is not None
    assert loaded.rule == "Test rule"


def test_patch_injection_tracking(tmp_path):
    store = PatchStore(base_dir=tmp_path / "prompt-patches")
    patch = PromptPatch(
        id="PP-001",
        created_from="D-001",
        rule="Test",
        agents=["gemini"],
    )
    store.save(patch)

    # Record 3 injections
    for _ in range(3):
        patch.times_injected += 1
    store.save(patch)

    loaded = store.load("PP-001")
    assert loaded.times_injected == 3


def test_patch_recurrence_rate(tmp_path):
    store = PatchStore(base_dir=tmp_path / "prompt-patches")
    patch = PromptPatch(
        id="PP-001",
        created_from="D-001",
        rule="Test",
        agents=["gemini"],
        times_injected=5,
        recurrences=1,
    )
    store.save(patch)
    assert patch.recurrence_rate == 1 / 5


def test_patch_proven_promotion():
    patch = PromptPatch(
        id="PP-001",
        created_from="D-001",
        rule="Test",
        agents=["gemini"],
        times_injected=5,
        recurrences=0,
    )
    assert patch.should_promote  # 5 injections, 0 recurrences
    patch.lifecycle_status = "proven"
    assert patch.lifecycle_status == "proven"


def test_patches_for_dispatch(tmp_path):
    store = PatchStore(base_dir=tmp_path / "prompt-patches")
    store.save(PromptPatch(id="PP-001", created_from="D-001", rule="Gemini rule 1", agents=["gemini"]))
    store.save(PromptPatch(id="PP-002", created_from="D-002", rule="All agents rule", agents=["*"]))
    store.save(PromptPatch(id="PP-003", created_from="D-003", rule="Codex rule", agents=["codex"]))
    store.save(PromptPatch(id="PP-004", created_from="D-004", rule="Retired", agents=["gemini"], lifecycle_status="retired"))

    matches = patches_for_dispatch(store, agent="gemini", repo="any", work_type="any")
    ids = [p.id for p in matches]
    assert "PP-001" in ids  # agent match
    assert "PP-002" in ids  # wildcard match
    assert "PP-003" not in ids  # wrong agent
    assert "PP-004" not in ids  # retired


def test_amplification_creation():
    amp = Amplification(
        id="AMP-2026-0330-001",
        created_from="D-2026-0330-004",
        technique="Codex spawns named sub-agents for multi-repo work",
        agents=["codex"],
        work_types=["multi_repo_parallel"],
    )
    assert amp.injection_mode == "suggestion"
    d = amp.to_dict()
    assert d["technique"].startswith("Codex")
