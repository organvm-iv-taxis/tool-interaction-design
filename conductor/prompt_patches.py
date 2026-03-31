"""Prompt patch engine — violation-driven constraint evolution.

Each violation generates a prompt patch — a constraint rule injected into
future handoff envelopes. Patches have a lifecycle:
  draft → active → proven → retired

Amplifications are the positive counterpart: proven techniques suggested
(not mandated) for future dispatches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .constants import STATE_DIR


PROMPT_PATCHES_DIR = STATE_DIR / "prompt-patches"


@dataclass
class PromptPatch:
    """A constraint rule injected into future handoff envelopes."""

    id: str
    created_from: str  # dispatch ID that spawned this patch
    rule: str
    agents: list[str] = field(default_factory=lambda: ["*"])
    repos: list[str] = field(default_factory=lambda: ["*"])
    work_types: list[str] = field(default_factory=lambda: ["*"])
    model_version_tested: str = ""
    lifecycle_status: str = "active"  # draft | active | proven | retired
    times_injected: int = 0
    recurrences: int = 0

    @property
    def recurrence_rate(self) -> float:
        if self.times_injected == 0:
            return 0.0
        return self.recurrences / self.times_injected

    @property
    def should_promote(self) -> bool:
        return self.times_injected >= 3 and self.recurrences == 0

    def matches(self, agent: str, repo: str, work_type: str) -> bool:
        if self.lifecycle_status == "retired":
            return False
        agent_match = "*" in self.agents or agent in self.agents
        repo_match = "*" in self.repos or repo in self.repos
        wt_match = "*" in self.work_types or work_type in self.work_types
        return agent_match and repo_match and wt_match

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_from": self.created_from,
            "rule": self.rule,
            "agents": self.agents,
            "repos": self.repos,
            "work_types": self.work_types,
            "model_version_tested": self.model_version_tested,
            "lifecycle_status": self.lifecycle_status,
            "times_injected": self.times_injected,
            "recurrences": self.recurrences,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PromptPatch:
        return cls(
            id=str(d.get("id", "")),
            created_from=str(d.get("created_from", "")),
            rule=str(d.get("rule", "")),
            agents=list(d.get("agents", ["*"])),
            repos=list(d.get("repos", ["*"])),
            work_types=list(d.get("work_types", ["*"])),
            model_version_tested=str(d.get("model_version_tested", "")),
            lifecycle_status=str(d.get("lifecycle_status", "active")),
            times_injected=int(d.get("times_injected", 0)),
            recurrences=int(d.get("recurrences", 0)),
        )


@dataclass
class Amplification:
    """Positive counterpart to patches — proven techniques suggested for dispatch."""

    id: str
    created_from: str
    technique: str
    agents: list[str] = field(default_factory=lambda: ["*"])
    work_types: list[str] = field(default_factory=lambda: ["*"])
    injection_mode: str = "suggestion"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_from": self.created_from,
            "technique": self.technique,
            "agents": self.agents,
            "work_types": self.work_types,
            "injection_mode": self.injection_mode,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Amplification:
        return cls(
            id=str(d.get("id", "")),
            created_from=str(d.get("created_from", "")),
            technique=str(d.get("technique", "")),
            agents=list(d.get("agents", ["*"])),
            work_types=list(d.get("work_types", ["*"])),
            injection_mode=str(d.get("injection_mode", "suggestion")),
        )


class PatchStore:
    """YAML-backed storage for prompt patches."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or PROMPT_PATCHES_DIR

    def save(self, patch: PromptPatch) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self.base_dir / f"{patch.id}.yaml"
        path.write_text(yaml.dump(patch.to_dict(), default_flow_style=False, sort_keys=False))
        return path

    def load(self, patch_id: str) -> PromptPatch | None:
        path = self.base_dir / f"{patch_id}.yaml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text())
        if not data:
            return None
        return PromptPatch.from_dict(data)

    def list_active(self) -> list[PromptPatch]:
        if not self.base_dir.exists():
            return []
        patches = []
        for f in sorted(self.base_dir.glob("PP-*.yaml")):
            data = yaml.safe_load(f.read_text())
            if data:
                p = PromptPatch.from_dict(data)
                if p.lifecycle_status in ("active", "proven"):
                    patches.append(p)
        return patches


def patches_for_dispatch(
    store: PatchStore,
    agent: str,
    repo: str,
    work_type: str,
) -> list[PromptPatch]:
    """Return all active patches matching the dispatch context."""
    return [p for p in store.list_active() if p.matches(agent, repo, work_type)]
