"""Wisdom Corpus — curated canonical knowledge for the Guardian Angel.

Loads YAML entries lazily, caches in memory. Provides query API for
matching wisdom to context (triggers, phase, domain).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

WISDOM_DIR = Path(__file__).parent


@dataclass
class WisdomEntry:
    """A single piece of canonical wisdom."""

    id: str                         # "solid.single_responsibility"
    domain: str                     # "engineering" | "business" | "philosophical"
    principle: str                  # "Single Responsibility Principle"
    summary: str                    # One-line description
    teaching: str                   # 2-3 sentences: WHY this matters
    metaphor: str                   # Rich philosophical framing
    triggers: list[str]             # When to surface: ["scope_complex", "multi_concern"]
    phase_relevance: list[str]      # ["SHAPE", "BUILD"]
    severity_hint: str = "info"     # Default severity
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WisdomEntry:
        return cls(
            id=d["id"],
            domain=d.get("domain", ""),
            principle=d.get("principle", ""),
            summary=d.get("summary", ""),
            teaching=d.get("teaching", ""),
            metaphor=d.get("metaphor", ""),
            triggers=d.get("triggers", []),
            phase_relevance=d.get("phase_relevance", []),
            severity_hint=d.get("severity_hint", "info"),
            tags=d.get("tags", []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain,
            "principle": self.principle,
            "summary": self.summary,
            "teaching": self.teaching,
            "metaphor": self.metaphor,
            "triggers": self.triggers,
            "phase_relevance": self.phase_relevance,
            "severity_hint": self.severity_hint,
            "tags": self.tags,
        }


class WisdomCorpus:
    """Lazy-loading, in-memory cache of wisdom entries from YAML files."""

    def __init__(self, wisdom_dir: Path | None = None) -> None:
        self._dir = wisdom_dir or WISDOM_DIR
        self._entries: list[WisdomEntry] = []
        self._loaded = False
        self._by_id: dict[str, WisdomEntry] = {}

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        for yaml_file in sorted(self._dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(yaml_file.read_text())
                if not isinstance(data, list):
                    continue
                for item in data:
                    if isinstance(item, dict) and "id" in item:
                        entry = WisdomEntry.from_dict(item)
                        self._entries.append(entry)
                        self._by_id[entry.id] = entry
            except (OSError, yaml.YAMLError):
                continue

    def query(
        self,
        *,
        triggers: list[str] | None = None,
        phase: str | None = None,
        domain: str | None = None,
        tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[WisdomEntry]:
        """Match wisdom entries to current context. Returns highest-relevance first."""
        self._ensure_loaded()
        scored: list[tuple[float, WisdomEntry]] = []

        for entry in self._entries:
            score = 0.0

            if domain and entry.domain == domain:
                score += 1.0

            if phase and phase.upper() in [p.upper() for p in entry.phase_relevance]:
                score += 2.0

            if triggers:
                trigger_matches = sum(1 for t in triggers if t in entry.triggers)
                score += trigger_matches * 3.0

            if tags:
                tag_matches = sum(1 for t in tags if t in entry.tags)
                score += tag_matches * 1.5

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: -x[0])
        return [entry for _, entry in scored[:limit]]

    def get_by_id(self, entry_id: str) -> WisdomEntry | None:
        """Direct lookup by entry ID."""
        self._ensure_loaded()
        return self._by_id.get(entry_id)

    def random_insight(self, phase: str | None = None) -> WisdomEntry | None:
        """Return a serendipitous wisdom entry, optionally filtered by phase."""
        self._ensure_loaded()
        if not self._entries:
            return None

        import hashlib
        import time
        # Deterministic-ish "random" based on current hour (stable within an hour)
        seed = hashlib.sha256(f"{time.time() // 3600}".encode()).hexdigest()
        index = int(seed[:8], 16)

        candidates = self._entries
        if phase:
            phase_upper = phase.upper()
            filtered = [e for e in self._entries if phase_upper in [p.upper() for p in e.phase_relevance]]
            if filtered:
                candidates = filtered

        return candidates[index % len(candidates)]

    def search(self, query: str) -> list[WisdomEntry]:
        """Search entries by keyword across principle, summary, and tags."""
        self._ensure_loaded()
        query_lower = query.lower()
        results = []
        for entry in self._entries:
            searchable = f"{entry.principle} {entry.summary} {' '.join(entry.tags)} {entry.id}".lower()
            if query_lower in searchable:
                results.append(entry)
        return results

    @property
    def count(self) -> int:
        self._ensure_loaded()
        return len(self._entries)

    @property
    def domains(self) -> list[str]:
        self._ensure_loaded()
        return sorted(set(e.domain for e in self._entries))
