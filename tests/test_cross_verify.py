"""Tests for the CrossVerifier — violation detection, glob matching, convention checking."""

from __future__ import annotations

import pytest

from conductor.cross_verify import CrossVerifier, Violation, VerificationReport
from conductor.fleet_handoff import GuardrailedHandoffBrief


def _make_handoff(**kwargs) -> GuardrailedHandoffBrief:
    """Helper to create a minimal guardrailed handoff for testing."""
    defaults = dict(
        from_agent="claude",
        to_agent="gemini",
        session_id="test-001",
        phase="BUILD",
        organ="ORGAN-III",
        repo="test-repo",
        scope="test",
        summary="Test handoff",
    )
    defaults.update(kwargs)
    return GuardrailedHandoffBrief(**defaults)


class TestLockedFiles:
    def test_no_violation_when_no_locked_files(self):
        verifier = CrossVerifier()
        handoff = _make_handoff()
        report = verifier.verify(handoff, changed_files=["src/main.py"])
        assert report.passed
        assert len(report.violations) == 0

    def test_violation_on_locked_file(self):
        verifier = CrossVerifier()
        handoff = _make_handoff(files_locked=["schema.ts", "drizzle.config.ts"])
        report = verifier.verify(handoff, changed_files=["schema.ts", "src/app.ts"])
        assert not report.passed
        assert len(report.violations) == 1
        assert report.violations[0].rule == "file_locked"
        assert report.violations[0].file == "schema.ts"
        assert report.violations[0].severity == "error"

    def test_multiple_locked_violations(self):
        verifier = CrossVerifier()
        handoff = _make_handoff(files_locked=["a.ts", "b.ts"])
        report = verifier.verify(handoff, changed_files=["a.ts", "b.ts", "c.ts"])
        assert not report.passed
        assert len(report.violations) == 2


class TestNeverTouch:
    def test_glob_pattern_match(self):
        verifier = CrossVerifier()
        handoff = _make_handoff(
            receiver_restrictions={
                "restrictions": {"never_touch": ["*.config.ts", "package.json"]}
            }
        )
        report = verifier.verify(handoff, changed_files=["drizzle.config.ts"])
        assert not report.passed
        assert report.violations[0].rule == "never_touch"

    def test_package_json_blocked(self):
        verifier = CrossVerifier()
        handoff = _make_handoff(
            receiver_restrictions={
                "restrictions": {"never_touch": ["package.json"]}
            }
        )
        report = verifier.verify(handoff, changed_files=["package.json"])
        assert not report.passed

    def test_nested_path_matches_basename(self):
        verifier = CrossVerifier()
        handoff = _make_handoff(
            receiver_restrictions={
                "restrictions": {"never_touch": ["*.config.mjs"]}
            }
        )
        report = verifier.verify(handoff, changed_files=["src/astro.config.mjs"])
        assert not report.passed

    def test_no_match_passes(self):
        verifier = CrossVerifier()
        handoff = _make_handoff(
            receiver_restrictions={
                "restrictions": {"never_touch": ["package.json"]}
            }
        )
        report = verifier.verify(handoff, changed_files=["src/main.ts", "lib/utils.ts"])
        assert report.passed

    def test_env_glob_match(self):
        verifier = CrossVerifier()
        handoff = _make_handoff(
            receiver_restrictions={
                "restrictions": {"never_touch": [".env*"]}
            }
        )
        report = verifier.verify(handoff, changed_files=[".env.local"])
        assert not report.passed


class TestConventionChecks:
    def test_camelcase_in_orm_context_flagged(self):
        verifier = CrossVerifier()
        handoff = _make_handoff(conventions={"orm_naming": "snake_case"})
        diff = (
            "+++ b/src/service.ts\n"
            "+  const result = db.select().where(eq(users.brandId, id));\n"
        )
        report = verifier.verify(handoff, changed_files=["src/service.ts"], diff_content=diff)
        assert len(report.violations) == 1
        assert report.violations[0].rule == "convention_drift"
        assert report.violations[0].severity == "warning"

    def test_snake_case_in_orm_passes(self):
        verifier = CrossVerifier()
        handoff = _make_handoff(conventions={"orm_naming": "snake_case"})
        diff = (
            "+++ b/src/service.ts\n"
            "+  const result = db.select().where(eq(users.brand_id, id));\n"
        )
        report = verifier.verify(handoff, changed_files=["src/service.ts"], diff_content=diff)
        assert len(report.violations) == 0

    def test_no_orm_convention_no_check(self):
        verifier = CrossVerifier()
        handoff = _make_handoff(conventions={})
        diff = "+  db.select().where(eq(users.brandId, id));\n"
        report = verifier.verify(handoff, changed_files=[], diff_content=diff)
        assert report.passed


class TestVerificationReport:
    def test_report_to_dict(self):
        report = VerificationReport(
            violations=[Violation("never_touch", "test", "file.ts", "error")],
            passed=False,
            handoff_id="test-001",
            verifier_agent="claude",
        )
        d = report.to_dict()
        assert d["passed"] is False
        assert len(d["violations"]) == 1
        assert d["violations"][0]["rule"] == "never_touch"

    def test_summary_auto_generated(self):
        report = VerificationReport(
            violations=[
                Violation("never_touch", "a", "f1", "error"),
                Violation("convention_drift", "b", "", "warning"),
            ],
            passed=False,
        )
        assert "1 error" in report.summary
        assert "1 warning" in report.summary

    def test_passed_summary(self):
        report = VerificationReport(passed=True)
        assert "satisfied" in report.summary


class TestCombinedChecks:
    def test_locked_file_plus_convention_drift(self):
        verifier = CrossVerifier()
        handoff = _make_handoff(
            files_locked=["schema.ts"],
            conventions={"orm_naming": "snake_case"},
            receiver_restrictions={
                "restrictions": {"never_touch": ["package.json"]}
            },
        )
        diff = "+  db.update(users).set({ brandId: value });\n"
        report = verifier.verify(
            handoff,
            changed_files=["schema.ts", "package.json", "src/app.ts"],
            diff_content=diff,
        )
        assert not report.passed
        rules = {v.rule for v in report.violations}
        assert "file_locked" in rules
        assert "never_touch" in rules
        assert "convention_drift" in rules
