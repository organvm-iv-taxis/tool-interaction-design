"""Prompt template versioning and metadata tracking."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .constants import STATE_DIR, ConductorError, atomic_write

PROMPT_REGISTRY_DIR = STATE_DIR / "prompts"


@dataclass
class PromptTemplate:
    id: str
    name: str
    version: str  # semver
    content: str
    model_compatibility: list[str]  # e.g., ["claude-opus-4-6", "gpt-4"]
    tags: list[str]
    created_at: float
    updated_at: float
    performance_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "content": self.content,
            "model_compatibility": self.model_compatibility,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "performance_notes": self.performance_notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PromptTemplate:
        return cls(
            id=d["id"],
            name=d["name"],
            version=d["version"],
            content=d["content"],
            model_compatibility=d.get("model_compatibility", []),
            tags=d.get("tags", []),
            created_at=d.get("created_at", 0),
            updated_at=d.get("updated_at", 0),
            performance_notes=d.get("performance_notes", ""),
        )


_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _parse_semver(version: str) -> tuple[int, int, int]:
    m = _SEMVER_RE.match(version)
    if not m:
        raise ConductorError(f"Invalid semver: {version}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _next_minor(version: str) -> str:
    """Bump minor version: 1.0.0 -> 1.1.0."""
    major, minor, _ = _parse_semver(version)
    return f"{major}.{minor + 1}.0"


class PromptRegistry:
    """Version-controlled prompt template store in .conductor/prompts/."""

    def __init__(self, registry_dir: Optional[Path] = None) -> None:
        self.registry_dir = registry_dir or PROMPT_REGISTRY_DIR
        self.registry_dir.mkdir(parents=True, exist_ok=True)

    def _prompt_dir(self, name: str) -> Path:
        return self.registry_dir / name

    def _version_file(self, name: str, version: str) -> Path:
        return self._prompt_dir(name) / f"v{version}.json"

    def _latest_version(self, name: str) -> Optional[str]:
        """Find the latest version for a prompt name."""
        prompt_dir = self._prompt_dir(name)
        if not prompt_dir.exists():
            return None
        versions: list[str] = []
        for f in prompt_dir.glob("v*.json"):
            ver_str = f.stem[1:]  # strip leading 'v'
            try:
                _parse_semver(ver_str)
                versions.append(ver_str)
            except ConductorError:
                continue
        if not versions:
            return None
        versions.sort(key=lambda v: _parse_semver(v))
        return versions[-1]

    def register(
        self,
        name: str,
        content: str,
        model_compat: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        performance_notes: str = "",
    ) -> PromptTemplate:
        """Register a new prompt template (or a new version of an existing one)."""
        if not name or not content:
            raise ConductorError("Prompt name and content are required.")

        latest = self._latest_version(name)
        if latest is None:
            version = "1.0.0"
        else:
            version = _next_minor(latest)

        now = time.time()
        template_id = f"{name}@{version}"
        template = PromptTemplate(
            id=template_id,
            name=name,
            version=version,
            content=content,
            model_compatibility=model_compat or ["claude-opus-4-6"],
            tags=tags or [],
            created_at=now,
            updated_at=now,
            performance_notes=performance_notes,
        )

        prompt_dir = self._prompt_dir(name)
        prompt_dir.mkdir(parents=True, exist_ok=True)
        version_file = self._version_file(name, version)
        atomic_write(version_file, json.dumps(template.to_dict(), indent=2))

        return template

    def get(self, name: str, version: Optional[str] = None) -> PromptTemplate:
        """Get a prompt template by name and optionally version."""
        if version is None:
            version = self._latest_version(name)
        if version is None:
            raise ConductorError(f"Prompt template not found: {name}")

        version_file = self._version_file(name, version)
        if not version_file.exists():
            raise ConductorError(f"Prompt template version not found: {name}@{version}")

        data = json.loads(version_file.read_text())
        return PromptTemplate.from_dict(data)

    def list_prompts(self) -> list[PromptTemplate]:
        """List the latest version of every prompt template."""
        results: list[PromptTemplate] = []
        if not self.registry_dir.exists():
            return results
        for prompt_dir in sorted(self.registry_dir.iterdir()):
            if not prompt_dir.is_dir():
                continue
            name = prompt_dir.name
            latest = self._latest_version(name)
            if latest:
                try:
                    results.append(self.get(name, latest))
                except ConductorError:
                    continue
        return results

    def search(
        self,
        tag: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[PromptTemplate]:
        """Search prompt templates by tag and/or model compatibility."""
        all_prompts = self.list_prompts()
        results: list[PromptTemplate] = []
        for pt in all_prompts:
            if tag and tag not in pt.tags:
                continue
            if model and model not in pt.model_compatibility:
                continue
            results.append(pt)
        return results
