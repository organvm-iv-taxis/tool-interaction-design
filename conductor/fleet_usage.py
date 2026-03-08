"""Fleet usage tracking — append-only JSONL storage for agent utilization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .constants import STATE_DIR

FLEET_USAGE_DIR = STATE_DIR / "fleet-usage"


@dataclass
class UsageRecord:
    """A single session's usage entry."""

    agent: str
    date: str  # YYYY-MM-DD
    session_id: str
    duration_minutes: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    timestamp: str  # ISO 8601

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "date": self.date,
            "session_id": self.session_id,
            "duration_minutes": self.duration_minutes,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> UsageRecord:
        return cls(
            agent=str(d.get("agent", "unknown")),
            date=str(d.get("date", "")),
            session_id=str(d.get("session_id", "")),
            duration_minutes=int(d.get("duration_minutes", 0)),
            tokens_in=int(d.get("tokens_in", 0)),
            tokens_out=int(d.get("tokens_out", 0)),
            cost_usd=float(d.get("cost_usd", 0.0)),
            timestamp=str(d.get("timestamp", "")),
        )


class FleetUsageTracker:
    """Append-only usage tracking per agent per billing period."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or FLEET_USAGE_DIR

    def _agent_file(self, agent: str, year: int, month: int) -> Path:
        return self.base_dir / f"{year}-{month:02d}" / f"{agent}.jsonl"

    def record_session(
        self,
        agent: str,
        session_id: str = "",
        duration_minutes: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
    ) -> UsageRecord:
        """Append a usage record for a completed session."""
        now = datetime.now(timezone.utc)
        record = UsageRecord(
            agent=agent,
            date=now.strftime("%Y-%m-%d"),
            session_id=session_id,
            duration_minutes=duration_minutes,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            timestamp=now.isoformat(),
        )

        path = self._agent_file(agent, now.year, now.month)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(record.to_dict()) + "\n")

        return record

    def get_period(self, agent: str, year: int, month: int) -> list[UsageRecord]:
        """Load all usage records for an agent in a billing period."""
        path = self._agent_file(agent, year, month)
        if not path.exists():
            return []
        records: list[UsageRecord] = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(UsageRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError):
                continue
        return records

    def daily_snapshot(self, target_date: date | None = None) -> dict[str, dict[str, Any]]:
        """Today's usage across all agents."""
        if target_date is None:
            target_date = date.today()
        date_str = target_date.isoformat()
        result: dict[str, dict[str, Any]] = {}

        month_dir = self.base_dir / f"{target_date.year}-{target_date.month:02d}"
        if not month_dir.is_dir():
            return result

        for agent_file in month_dir.glob("*.jsonl"):
            agent_name = agent_file.stem
            sessions = 0
            total_tokens = 0
            total_cost = 0.0
            total_minutes = 0
            for line in agent_file.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("date") == date_str:
                    sessions += 1
                    total_tokens += rec.get("tokens_in", 0) + rec.get("tokens_out", 0)
                    total_cost += rec.get("cost_usd", 0.0)
                    total_minutes += rec.get("duration_minutes", 0)
            if sessions > 0:
                result[agent_name] = {
                    "sessions": sessions,
                    "total_tokens": total_tokens,
                    "total_cost_usd": round(total_cost, 4),
                    "total_minutes": total_minutes,
                }

        return result

    def utilization_report(
        self, year: int, month: int, fleet_agents: list | None = None
    ) -> dict[str, dict[str, Any]]:
        """Compute utilization percentage per agent for a billing period.

        If fleet_agents is provided (list of FleetAgent), allotment info is
        used to compute utilization percentages. Otherwise, raw counts only.
        """
        from .fleet import FleetAgent

        month_dir = self.base_dir / f"{year}-{month:02d}"
        report: dict[str, dict[str, Any]] = {}

        # Build allotment lookup
        allotments: dict[str, Any] = {}
        if fleet_agents:
            for fa in fleet_agents:
                allotments[fa.name] = fa.subscription.allotment

        # Collect all agents that have data
        agent_files: list[Path] = []
        if month_dir.is_dir():
            agent_files = list(month_dir.glob("*.jsonl"))

        for agent_file in agent_files:
            agent_name = agent_file.stem
            records = self.get_period(agent_name, year, month)
            total_sessions = len(records)
            total_tokens = sum(r.tokens_in + r.tokens_out for r in records)
            total_cost = sum(r.cost_usd for r in records)
            total_minutes = sum(r.duration_minutes for r in records)

            entry: dict[str, Any] = {
                "sessions": total_sessions,
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 4),
                "total_minutes": total_minutes,
            }

            # Compute utilization if allotment known
            allot = allotments.get(agent_name)
            if allot:
                if allot.messages_per_month > 0:
                    entry["utilization_pct"] = round(
                        total_sessions / allot.messages_per_month * 100, 1
                    )
                    entry["allotted"] = allot.messages_per_month
                    entry["allotment_unit"] = "messages/month"
                elif allot.messages_per_day > 0:
                    # Approximate: assume 30 days
                    monthly_allot = allot.messages_per_day * 30
                    entry["utilization_pct"] = round(
                        total_sessions / monthly_allot * 100, 1
                    )
                    entry["allotted"] = monthly_allot
                    entry["allotment_unit"] = "messages/month (est.)"
                elif allot.requests_per_day > 0:
                    monthly_allot = allot.requests_per_day * 30
                    entry["utilization_pct"] = round(
                        total_sessions / monthly_allot * 100, 1
                    )
                    entry["allotted"] = monthly_allot
                    entry["allotment_unit"] = "requests/month (est.)"

            report[agent_name] = entry

        return report

    def underutilized_agents(
        self, year: int, month: int, threshold: float = 50.0, fleet_agents: list | None = None
    ) -> list[str]:
        """Return agent names whose utilization is below threshold percent."""
        report = self.utilization_report(year, month, fleet_agents)
        return [
            name
            for name, data in report.items()
            if data.get("utilization_pct", 0) < threshold
        ]
