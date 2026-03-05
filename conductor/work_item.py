"""Layer 2.5: Stateful Work Registry — persistent task management."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

from .constants import WORK_REGISTRY_FILE, atomic_write


@dataclass
class WorkItemRecord:
    """Persistent state for a work item."""
    id: str
    priority: str
    category: str
    organ: str
    repo: Optional[str]
    description: str
    suggested_command: str
    score: int
    status: str = "OPEN"  # OPEN, CLAIMED, RESOLVED, BLOCKED
    owner: Optional[str] = None
    claimed_at: Optional[float] = None
    resolved_at: Optional[float] = None
    session_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorkItemRecord:
        return cls(**d)


class WorkRegistry:
    """Manages the persistent work registry file."""

    def __init__(self):
        self.path = WORK_REGISTRY_FILE
        self.items: dict[str, WorkItemRecord] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                for item_id, item_data in data.get("items", {}).items():
                    self.items[item_id] = WorkItemRecord.from_dict(item_data)
            except (json.JSONDecodeError, TypeError, KeyError):
                # If corrupted, start fresh
                self.items = {}

    def save(self) -> None:
        data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "items": {item_id: item.to_dict() for item_id, item in self.items.items()}
        }
        atomic_write(self.path, json.dumps(data, indent=2))

    def sync(self, computed_items: list[Any]) -> None:
        """Merge dynamically computed items with persistent state."""
        # current keys in computed
        computed_keys = set()
        for item in computed_items:
            # Generate a stable ID based on organ, repo, category, and description
            item_id = hashlib_id(item.organ, item.repo or "", item.category, item.description)
            computed_keys.add(item_id)
            
            if item_id not in self.items:
                self.items[item_id] = WorkItemRecord(
                    id=item_id,
                    priority=item.priority,
                    category=item.category,
                    organ=item.organ,
                    repo=item.repo,
                    description=item.description,
                    suggested_command=item.suggested_command,
                    score=item.score,
                    metadata={"rationale": item.rationale}
                )
            else:
                # Update dynamic fields for existing items
                rec = self.items[item_id]
                rec.priority = item.priority
                rec.score = item.score
                rec.suggested_command = item.suggested_command
                rec.metadata["rationale"] = item.rationale

        # Cleanup RESOLVED items not in computed (optional, or keep history)
        # For now, if it's not in computed and it's OPEN, it might be stale
        to_remove = []
        for item_id, item in self.items.items():
            if item_id not in computed_keys and item.status == "OPEN":
                to_remove.append(item_id)
        
        for r in to_remove:
            del self.items[r]
            
        self.save()

    def claim(self, item_id: str, owner: str, session_id: Optional[str] = None) -> bool:
        if item_id not in self.items:
            return False
        rec = self.items[item_id]
        if rec.status != "OPEN":
            return False
        rec.status = "CLAIMED"
        rec.owner = owner
        rec.claimed_at = time.time()
        rec.session_id = session_id
        self.save()
        return True

    def resolve(self, item_id: str) -> bool:
        if item_id not in self.items:
            return False
        rec = self.items[item_id]
        rec.status = "RESOLVED"
        rec.resolved_at = time.time()
        self.save()
        return True

    def yield_item(self, item_id: str) -> bool:
        if item_id not in self.items:
            return False
        rec = self.items[item_id]
        if rec.status != "CLAIMED":
            return False
        rec.status = "OPEN"
        rec.owner = None
        rec.claimed_at = None
        rec.session_id = None
        self.save()
        return True


def hashlib_id(*args: str) -> str:
    import hashlib
    content = "|".join(args).encode()
    return hashlib.sha256(content).hexdigest()[:12]
