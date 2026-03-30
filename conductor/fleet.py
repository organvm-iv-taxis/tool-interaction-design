"""Fleet Agent Registry — data model and YAML loader for the agent fleet."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


FLEET_YAML = Path(__file__).parent / "fleet.yaml"


@dataclass(frozen=True)
class AgentAllotment:
    """Subscription allotment limits for an agent."""

    context_window: int = 0
    messages_per_day: int = 0
    messages_per_month: int = 0
    requests_per_day: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentAllotment:
        return cls(
            context_window=int(d.get("context_window", 0)),
            messages_per_day=int(d.get("messages_per_day", 0)),
            messages_per_month=int(d.get("messages_per_month", 0)),
            requests_per_day=int(d.get("requests_per_day", 0)),
        )


@dataclass(frozen=True)
class AgentCapabilities:
    """Declared strengths and weaknesses."""

    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentCapabilities:
        return cls(
            strengths=tuple(d.get("strengths", [])),
            weaknesses=tuple(d.get("weaknesses", [])),
        )


@dataclass(frozen=True)
class AgentSensitivity:
    """Security and access constraints."""

    can_see_secrets: bool = False
    can_push_git: bool = False
    can_run_shell: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentSensitivity:
        return cls(
            can_see_secrets=bool(d.get("can_see_secrets", False)),
            can_push_git=bool(d.get("can_push_git", False)),
            can_run_shell=bool(d.get("can_run_shell", False)),
        )


@dataclass(frozen=True)
class AgentRestrictions:
    """Hard constraints on what an agent must not do."""

    never_touch: tuple[str, ...] = ()
    never_decide: tuple[str, ...] = ()
    max_cognitive_class: str = "strategic"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentRestrictions:
        return cls(
            never_touch=tuple(d.get("never_touch", [])),
            never_decide=tuple(d.get("never_decide", [])),
            max_cognitive_class=str(d.get("max_cognitive_class", "strategic")),
        )


@dataclass(frozen=True)
class AgentGuardrails:
    """Operational guardrails for agent behavior."""

    self_audit_trusted: bool = True
    max_files_before_checkpoint: int = 50
    handoff_envelope_required: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentGuardrails:
        return cls(
            self_audit_trusted=bool(d.get("self_audit_trusted", True)),
            max_files_before_checkpoint=int(d.get("max_files_before_checkpoint", 50)),
            handoff_envelope_required=bool(d.get("handoff_envelope_required", False)),
        )


@dataclass(frozen=True)
class AgentSubscription:
    """Subscription tier and billing details."""

    tier: str = "free"
    billing_cycle: str = "monthly"
    allotment: AgentAllotment = field(default_factory=AgentAllotment)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentSubscription:
        return cls(
            tier=str(d.get("tier", "free")),
            billing_cycle=str(d.get("billing_cycle", "monthly")),
            allotment=AgentAllotment.from_dict(d.get("allotment", {})),
        )


@dataclass(frozen=True)
class FleetAgent:
    """A single agent in the fleet."""

    name: str
    display_name: str
    provider: str
    subscription: AgentSubscription
    capabilities: AgentCapabilities
    phase_affinity: dict[str, float]
    sensitivity: AgentSensitivity
    restrictions: AgentRestrictions
    guardrails: AgentGuardrails
    active: bool

    @classmethod
    def from_dict(cls, name: str, d: dict[str, Any]) -> FleetAgent:
        return cls(
            name=name,
            display_name=str(d.get("display_name", name)),
            provider=str(d.get("provider", "unknown")),
            subscription=AgentSubscription.from_dict(d.get("subscription", {})),
            capabilities=AgentCapabilities.from_dict(d.get("capabilities", {})),
            phase_affinity=dict(d.get("phase_affinity", {})),
            sensitivity=AgentSensitivity.from_dict(d.get("sensitivity", {})),
            restrictions=AgentRestrictions.from_dict(d.get("restrictions", {})),
            guardrails=AgentGuardrails.from_dict(d.get("guardrails", {})),
            active=bool(d.get("active", False)),
        )


class FleetRegistry:
    """Loads and queries the fleet agent registry."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or FLEET_YAML
        self._agents: dict[str, FleetAgent] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = yaml.safe_load(self.path.read_text()) or {}
        for name, agent_data in data.get("agents", {}).items():
            self._agents[name] = FleetAgent.from_dict(name, agent_data)

    def get(self, name: str) -> FleetAgent | None:
        return self._agents.get(name)

    def active_agents(self) -> list[FleetAgent]:
        return [a for a in self._agents.values() if a.active]

    def all_agents(self) -> list[FleetAgent]:
        return list(self._agents.values())

    def by_provider(self, provider: str) -> list[FleetAgent]:
        return [a for a in self._agents.values() if a.provider == provider]
