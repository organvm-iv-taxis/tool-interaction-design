"""Persistent risk register for tracking project-level risks."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .constants import RISK_REGISTRY_FILE, atomic_write
from .observability import log_event

VALID_PROBABILITIES = {"low", "medium", "high"}
VALID_IMPACTS = {"low", "medium", "high"}
VALID_STATUSES = {"open", "mitigating", "resolved", "accepted"}


@dataclass
class Risk:
    id: str
    description: str
    probability: str  # low, medium, high
    impact: str  # low, medium, high
    mitigation: str
    owner: str
    status: str  # open, mitigating, resolved, accepted
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Risk:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})

    @property
    def severity_score(self) -> int:
        """Numeric severity: probability * impact (low=1, medium=2, high=3)."""
        scale = {"low": 1, "medium": 2, "high": 3}
        return scale.get(self.probability, 1) * scale.get(self.impact, 1)


class RiskRegistry:
    """Persistent risk register stored in .conductor/risks.json."""

    def __init__(self) -> None:
        self.risks: dict[str, Risk] = {}
        self._load()

    def _load(self) -> None:
        if RISK_REGISTRY_FILE.exists():
            try:
                data = json.loads(RISK_REGISTRY_FILE.read_text())
                for rid, rdata in data.get("risks", {}).items():
                    self.risks[rid] = Risk.from_dict(rdata)
            except (json.JSONDecodeError, TypeError, KeyError):
                self.risks = {}

    def _save(self) -> None:
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "risks": {rid: r.to_dict() for rid, r in self.risks.items()},
        }
        atomic_write(RISK_REGISTRY_FILE, json.dumps(payload, indent=2))

    def add(
        self,
        description: str,
        probability: str,
        impact: str,
        mitigation: str,
        owner: str,
    ) -> Risk:
        """Add a new risk and persist."""
        probability = probability.lower()
        impact = impact.lower()
        if probability not in VALID_PROBABILITIES:
            raise ValueError(f"Invalid probability '{probability}'. Must be one of: {', '.join(sorted(VALID_PROBABILITIES))}")
        if impact not in VALID_IMPACTS:
            raise ValueError(f"Invalid impact '{impact}'. Must be one of: {', '.join(sorted(VALID_IMPACTS))}")

        risk_id = f"RISK-{uuid.uuid4().hex[:8].upper()}"
        risk = Risk(
            id=risk_id,
            description=description,
            probability=probability,
            impact=impact,
            mitigation=mitigation,
            owner=owner,
            status="open",
            created_at=time.time(),
        )
        self.risks[risk_id] = risk
        self._save()
        log_event("risk.add", {"id": risk_id, "probability": probability, "impact": impact})
        return risk

    def resolve(self, risk_id: str) -> bool:
        """Mark a risk as resolved. Returns True on success."""
        if risk_id not in self.risks:
            return False
        self.risks[risk_id].status = "resolved"
        self._save()
        log_event("risk.resolve", {"id": risk_id})
        return True

    def list_risks(self, status: Optional[str] = None) -> list[Risk]:
        """List risks, optionally filtered by status."""
        risks = list(self.risks.values())
        if status:
            status_lower = status.lower()
            risks = [r for r in risks if r.status == status_lower]
        return sorted(risks, key=lambda r: -r.severity_score)

    def to_markdown(self) -> str:
        """Render the risk register as a Markdown table."""
        lines = [
            "# Risk Register",
            "",
            "| ID | Description | P | I | Score | Status | Owner | Mitigation |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for risk in sorted(self.risks.values(), key=lambda r: -r.severity_score):
            lines.append(
                f"| {risk.id} | {risk.description} | {risk.probability} | {risk.impact} "
                f"| {risk.severity_score} | {risk.status} | {risk.owner} | {risk.mitigation} |"
            )
        return "\n".join(lines)
