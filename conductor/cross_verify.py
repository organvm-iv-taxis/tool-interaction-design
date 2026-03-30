"""Cross-verification — check that agent output conforms to handoff constraints.

When an agent's guardrails declare self_audit_trusted: false, its output must
be verified by a different agent before acceptance. This module provides the
structural checks (file restriction violations, convention drift, constraint
breaches) that complement the verifying agent's semantic review.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .fleet_handoff import GuardrailedHandoffBrief


@dataclass
class Violation:
    """A single constraint violation found during cross-verification."""

    rule: str       # "never_touch", "file_locked", "convention_drift", "constraint_broken"
    detail: str     # Human-readable description
    file: str       # Affected file path (empty string if not file-specific)
    severity: str   # "error" | "warning"


@dataclass
class VerificationReport:
    """Result of cross-verifying an agent's output against handoff constraints."""

    violations: list[Violation] = field(default_factory=list)
    passed: bool = True
    checked_at: str = ""
    handoff_id: str = ""
    verifier_agent: str = ""
    summary: str = ""

    def __post_init__(self) -> None:
        if not self.checked_at:
            self.checked_at = datetime.now(timezone.utc).isoformat()
        if not self.summary:
            if self.passed:
                self.summary = "All constraints satisfied."
            else:
                errors = sum(1 for v in self.violations if v.severity == "error")
                warns = sum(1 for v in self.violations if v.severity == "warning")
                self.summary = f"{errors} error(s), {warns} warning(s) found."

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checked_at": self.checked_at,
            "handoff_id": self.handoff_id,
            "verifier_agent": self.verifier_agent,
            "summary": self.summary,
            "violations": [
                {"rule": v.rule, "detail": v.detail, "file": v.file, "severity": v.severity}
                for v in self.violations
            ],
        }


class CrossVerifier:
    """Verify agent output against guardrailed handoff constraints."""

    def verify(
        self,
        handoff: GuardrailedHandoffBrief,
        changed_files: list[str],
        diff_content: str = "",
        verifier_agent: str = "",
    ) -> VerificationReport:
        """Check that changed files and diff conform to handoff constraints.

        Args:
            handoff: The guardrailed handoff envelope from the originating agent.
            changed_files: List of file paths that the receiving agent modified.
            diff_content: Optional unified diff content for convention checking.
            verifier_agent: Name of the agent performing verification.

        Returns:
            VerificationReport with any violations found.
        """
        violations: list[Violation] = []

        # 1. Check locked files
        violations.extend(self._check_locked_files(handoff.files_locked, changed_files))

        # 2. Check receiver restrictions (never_touch patterns)
        restr = handoff.receiver_restrictions.get("restrictions", {})
        never_touch = restr.get("never_touch", [])
        violations.extend(self._check_never_touch(never_touch, changed_files))

        # 3. Check conventions against diff content
        if diff_content and handoff.conventions:
            violations.extend(self._check_conventions(handoff.conventions, diff_content))

        passed = not any(v.severity == "error" for v in violations)

        return VerificationReport(
            violations=violations,
            passed=passed,
            handoff_id=handoff.session_id,
            verifier_agent=verifier_agent,
        )

    @staticmethod
    def _check_locked_files(
        locked: list[str], changed: list[str]
    ) -> list[Violation]:
        """Check that no locked files were modified."""
        violations = []
        locked_set = set(locked)
        for f in changed:
            if f in locked_set:
                violations.append(Violation(
                    rule="file_locked",
                    detail=f"Modified locked file: {f}",
                    file=f,
                    severity="error",
                ))
        return violations

    @staticmethod
    def _check_never_touch(
        patterns: list[str], changed: list[str]
    ) -> list[Violation]:
        """Check that no files match never_touch glob patterns."""
        violations = []
        for f in changed:
            basename = f.rsplit("/", 1)[-1] if "/" in f else f
            for pattern in patterns:
                if fnmatch.fnmatch(basename, pattern) or fnmatch.fnmatch(f, pattern):
                    violations.append(Violation(
                        rule="never_touch",
                        detail=f"Modified restricted file matching '{pattern}': {f}",
                        file=f,
                        severity="error",
                    ))
                    break
        return violations

    @staticmethod
    def _check_conventions(
        conventions: dict[str, str], diff_content: str
    ) -> list[Violation]:
        """Check diff content for convention violations.

        Currently supports:
        - orm_naming: "snake_case" — flags camelCase identifiers in ORM contexts
        """
        violations = []

        if conventions.get("orm_naming") == "snake_case":
            # Look for camelCase in added lines that reference ORM operations
            orm_patterns = [".where(", ".values(", ".set(", ".insert(", ".update("]
            added_lines = [
                line[1:] for line in diff_content.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            ]
            camel_re = re.compile(r"[a-z][A-Z]")
            for line in added_lines:
                if any(p in line for p in orm_patterns) and camel_re.search(line):
                    violations.append(Violation(
                        rule="convention_drift",
                        detail=f"Possible camelCase in ORM context (expected snake_case): {line.strip()[:100]}",
                        file="",
                        severity="warning",
                    ))

        return violations
