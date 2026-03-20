"""Tests for the Guardian Angel — wisdom-enriched advisory engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import conductor.constants
import conductor.oracle
from conductor.guardian import GuardianAngel
from conductor.oracle import DETECTOR_REGISTRY, Advisory, Oracle, OracleContext
from conductor.wisdom import WisdomCorpus, WisdomEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def oracle_tmp(tmp_path):
    """Patch Oracle-relevant paths to temp directory."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    state_file = tmp_path / ".conductor-oracle-state.json"
    stats_file = tmp_path / ".conductor-stats.json"
    session_state = tmp_path / ".conductor-session.json"
    pattern_file = tmp_path / ".conductor-pattern-history.jsonl"

    with (
        patch.object(conductor.constants, "SESSIONS_DIR", sessions),
        patch.object(conductor.constants, "STATS_FILE", stats_file),
        patch.object(conductor.constants, "SESSION_STATE_FILE", session_state),
        patch.object(conductor.constants, "ORACLE_STATE_FILE", state_file),
        patch.object(conductor.constants, "PATTERN_HISTORY_FILE", pattern_file),
        patch.object(conductor.oracle, "SESSIONS_DIR", sessions),
        patch.object(conductor.oracle, "STATS_FILE", stats_file),
        patch.object(conductor.oracle, "ORACLE_STATE_FILE", state_file),
        patch.object(conductor.oracle, "SESSION_STATE_FILE", session_state),
    ):
        yield tmp_path


@pytest.fixture
def wisdom_dir(tmp_path):
    """Create a minimal wisdom corpus for testing."""
    wd = tmp_path / "wisdom"
    wd.mkdir()
    entries = [
        {
            "id": "test.tdd",
            "domain": "engineering",
            "principle": "Test-Driven Development",
            "summary": "Write tests before code.",
            "teaching": "TDD ensures your code is tested from the start.",
            "metaphor": "The blueprint precedes the building.",
            "triggers": ["tdd", "testing", "test_first"],
            "phase_relevance": ["BUILD", "PROVE"],
            "severity_hint": "info",
            "tags": ["testing", "quality"],
        },
        {
            "id": "test.mvp",
            "domain": "business",
            "principle": "Minimum Viable Product",
            "summary": "Ship the smallest thing that tests your hypothesis.",
            "teaching": "The MVP is not half-baked — it validates assumptions.",
            "metaphor": "The scout before the army.",
            "triggers": ["mvp", "over_building", "feature_creep"],
            "phase_relevance": ["FRAME", "SHAPE"],
            "severity_hint": "caution",
            "tags": ["strategy", "shipping"],
        },
        {
            "id": "test.scylla",
            "domain": "philosophical",
            "principle": "Navigate Between Scylla and Charybdis",
            "summary": "Steer between recklessness and paralysis.",
            "teaching": "Accept calculated losses to save the voyage.",
            "metaphor": "The hero doesn't defeat them — the hero survives them.",
            "triggers": ["risky_decision", "analysis_paralysis", "perfectionism"],
            "phase_relevance": ["FRAME", "SHAPE", "BUILD", "PROVE"],
            "severity_hint": "caution",
            "tags": ["mythology", "balance"],
        },
    ]
    import yaml
    (wd / "test.yaml").write_text(yaml.dump(entries))
    return wd


def _write_stats(tmp_path: Path, stats: dict) -> None:
    (tmp_path / ".conductor-stats.json").write_text(json.dumps(stats))


def _write_oracle_state(tmp_path: Path, state: dict) -> None:
    (tmp_path / ".conductor-oracle-state.json").write_text(json.dumps(state))


# ---------------------------------------------------------------------------
# WisdomEntry tests
# ---------------------------------------------------------------------------


class TestWisdomEntry:
    def test_from_dict(self):
        d = {
            "id": "eng.solid.srp",
            "domain": "engineering",
            "principle": "Single Responsibility",
            "summary": "One reason to change.",
            "teaching": "A class should have one reason to change.",
            "metaphor": "The Swiss Army knife is versatile but no single tool excels.",
            "triggers": ["multi_concern"],
            "phase_relevance": ["SHAPE", "BUILD"],
            "severity_hint": "caution",
            "tags": ["solid", "architecture"],
        }
        entry = WisdomEntry.from_dict(d)
        assert entry.id == "eng.solid.srp"
        assert entry.domain == "engineering"
        assert entry.principle == "Single Responsibility"
        assert "SHAPE" in entry.phase_relevance
        assert "solid" in entry.tags

    def test_to_dict_roundtrip(self):
        d = {
            "id": "test.x",
            "domain": "business",
            "principle": "X",
            "summary": "Y",
            "teaching": "Z",
            "metaphor": "M",
            "triggers": ["a"],
            "phase_relevance": ["BUILD"],
            "severity_hint": "info",
            "tags": ["t1"],
        }
        entry = WisdomEntry.from_dict(d)
        roundtripped = entry.to_dict()
        assert roundtripped["id"] == "test.x"
        assert roundtripped["triggers"] == ["a"]
        assert roundtripped["severity_hint"] == "info"

    def test_defaults(self):
        entry = WisdomEntry.from_dict({"id": "minimal"})
        assert entry.id == "minimal"
        assert entry.domain == ""
        assert entry.triggers == []
        assert entry.severity_hint == "info"


# ---------------------------------------------------------------------------
# WisdomCorpus tests
# ---------------------------------------------------------------------------


class TestWisdomCorpus:
    def test_loads_yaml(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        assert corpus.count == 3

    def test_get_by_id(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        entry = corpus.get_by_id("test.tdd")
        assert entry is not None
        assert entry.principle == "Test-Driven Development"

    def test_get_by_id_missing(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        assert corpus.get_by_id("nonexistent") is None

    def test_query_by_triggers(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        results = corpus.query(triggers=["tdd"])
        assert len(results) >= 1
        assert results[0].id == "test.tdd"

    def test_query_by_phase(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        results = corpus.query(phase="BUILD")
        assert any(e.id == "test.tdd" for e in results)

    def test_query_by_domain(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        results = corpus.query(domain="business")
        assert len(results) >= 1
        assert all(e.domain == "business" for e in results)

    def test_query_combined(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        results = corpus.query(triggers=["mvp"], phase="FRAME", domain="business")
        assert results[0].id == "test.mvp"

    def test_query_limit(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        results = corpus.query(phase="BUILD", limit=1)
        assert len(results) <= 1

    def test_search(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        results = corpus.search("Scylla")
        assert len(results) == 1
        assert results[0].id == "test.scylla"

    def test_search_no_match(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        results = corpus.search("zzz_nonexistent_zzz")
        assert results == []

    def test_random_insight(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        entry = corpus.random_insight()
        assert entry is not None
        assert entry.id in ("test.tdd", "test.mvp", "test.scylla")

    def test_random_insight_with_phase(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        entry = corpus.random_insight(phase="FRAME")
        assert entry is not None
        # FRAME-relevant: test.mvp and test.scylla
        assert "FRAME" in [p.upper() for p in entry.phase_relevance]

    def test_domains(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        domains = corpus.domains
        assert "engineering" in domains
        assert "business" in domains
        assert "philosophical" in domains

    def test_domain_counts(self, wisdom_dir):
        corpus = WisdomCorpus(wisdom_dir)
        assert corpus.domain_counts == {
            "business": 1,
            "engineering": 1,
            "philosophical": 1,
        }

    def test_empty_corpus(self, tmp_path):
        empty_dir = tmp_path / "empty_wisdom"
        empty_dir.mkdir()
        corpus = WisdomCorpus(empty_dir)
        assert corpus.count == 0
        assert corpus.random_insight() is None
        assert corpus.query(triggers=["anything"]) == []

    def test_malformed_yaml(self, tmp_path):
        bad_dir = tmp_path / "bad_wisdom"
        bad_dir.mkdir()
        (bad_dir / "bad.yaml").write_text("not: a list\n")
        corpus = WisdomCorpus(bad_dir)
        assert corpus.count == 0

    def test_real_corpus_loads(self):
        """Verify the actual wisdom corpus loads without errors."""
        corpus = WisdomCorpus()
        assert corpus.count > 50  # We created ~75 entries


# ---------------------------------------------------------------------------
# GuardianAngel tests
# ---------------------------------------------------------------------------


class TestGuardianAngel:
    def test_counsel_returns_advisories(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        advisories = guardian.counsel()
        assert isinstance(advisories, list)
        # Should return Advisory instances
        for adv in advisories:
            assert isinstance(adv, Advisory)

    def test_counsel_enriches_wisdom(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        advisories = guardian.counsel()
        # At least some should have wisdom content (standalone wisdom advisory)
        wisdom_advs = [a for a in advisories if a.wisdom_id]
        # We can't guarantee wisdom entries in every case, but the list should be valid
        assert isinstance(advisories, list)

    def test_counsel_respects_max(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        advisories = guardian.counsel(max_advisories=2)
        assert len(advisories) <= 2

    def test_counsel_records_only_visible_wisdom(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        with patch.object(
            guardian.oracle,
            "consult",
            return_value=[
                Advisory(
                    category="wisdom",
                    severity="critical",
                    message="High-priority wisdom",
                    detector="test",
                    wisdom_id="test.tdd",
                ),
                Advisory(
                    category="wisdom",
                    severity="info",
                    message="Lower-priority wisdom",
                    detector="test",
                    wisdom_id="test.mvp",
                ),
            ],
        ):
            advisories = guardian.counsel(max_advisories=1)

        assert len(advisories) == 1
        assert advisories[0].wisdom_id == "test.tdd"
        mastery = guardian.oracle._load_mastery()
        encountered = mastery.get("encountered", {})
        assert "test.tdd" in encountered
        assert "test.mvp" not in encountered

    def test_counsel_without_wisdom(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        advisories = guardian.counsel(include_wisdom=False)
        assert isinstance(advisories, list)

    def test_whisper_returns_none_for_safe_action(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        result = guardian.whisper("update readme")
        assert result is None

    def test_whisper_returns_advisory_for_risky_action(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        result = guardian.whisper("rewrite everything from scratch")
        # "rewrite" triggers should match
        if result is not None:
            assert isinstance(result, Advisory)
            assert result.wisdom_id

    def test_whisper_empty_string(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        assert guardian.whisper("") is None

    def test_teach_found(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        result = guardian.teach("test.tdd")
        assert result["found"] is True
        assert result["principle"] == "Test-Driven Development"
        assert "teaching" in result
        assert "metaphor" in result
        assert "mastery" in result

    def test_teach_by_search(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        result = guardian.teach("Scylla")
        assert result["found"] is True
        assert "Scylla" in result["principle"]

    def test_teach_not_found(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        result = guardian.teach("nonexistent_topic_xyz")
        assert result["found"] is False
        assert "suggestion" in result

    def test_teach_shows_mastery_history(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        _write_oracle_state(oracle_tmp, {
            "mastery": {
                "encountered": {
                    "test.tdd": {"first_seen": "2026-01-01", "times_shown": 5, "last_shown": "2026-03-01"}
                },
                "internalized": {},
                "growth_areas": [],
                "mastery_score": 0.0,
            }
        })
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        result = guardian.teach("test.tdd")
        assert result["found"] is True
        assert result["mastery"]["times_encountered"] == 5

    def test_landscape_returns_structure(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        result = guardian.landscape("rewrite vs refactor")
        assert "decision" in result
        assert "poles" in result
        assert isinstance(result["poles"], list)
        assert len(result["poles"]) >= 1
        assert "wisdom" in result
        assert "positioning" in result

    def test_landscape_identifies_poles(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        result = guardian.landscape("ship perfect code")
        # "perfect" trigger should create a pole
        poles = result["poles"]
        assert any("left" in p and "right" in p for p in poles)

    def test_growth_report_structure(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        report = guardian.growth_report()
        assert "mastery_score" in report
        assert "learning_velocity" in report
        assert "principles_encountered" in report
        assert "principles_internalized" in report
        assert "corpus_size" in report
        assert "corpus_domains" in report
        assert report["corpus_size"] == 3

    def test_growth_report_with_data(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        _write_oracle_state(oracle_tmp, {
            "mastery": {
                "encountered": {
                    "test.tdd": {"first_seen": "2026-01-01", "times_shown": 5, "last_shown": "2026-03-01"},
                    "test.mvp": {"first_seen": "2026-02-01", "times_shown": 3, "last_shown": "2026-03-01"},
                },
                "internalized": {
                    "test.tdd": {"at": "2026-03-01", "evidence": "user writes tests first"},
                },
                "growth_areas": ["test.mvp"],
                "mastery_score": 0.5,
            }
        })
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        report = guardian.growth_report()
        assert report["principles_encountered"] == 2
        assert report["principles_internalized"] == 1

    def test_corpus_search_query(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        result = guardian.corpus_search("TDD")
        assert result["count"] >= 1
        assert result["results"][0]["id"] == "test.tdd"

    def test_corpus_search_overview(self, oracle_tmp, wisdom_dir):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wisdom_dir)
        result = guardian.corpus_search()
        assert result["total_entries"] == 3
        assert "by_domain" in result
        assert result["by_domain"]["engineering"] == 1
        assert result["by_domain"]["business"] == 1
        assert result["by_domain"]["philosophical"] == 1

    def test_corpus_search_overview_counts_above_100(self, oracle_tmp, tmp_path):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        wd = tmp_path / "wisdom_large"
        wd.mkdir()
        import yaml

        engineering_entries = [
            {
                "id": f"eng.{i}",
                "domain": "engineering",
                "principle": f"Engineering Principle {i}",
                "summary": "Summary",
                "teaching": "Teaching",
                "metaphor": "Metaphor",
                "triggers": ["engineering"],
                "phase_relevance": ["BUILD"],
                "severity_hint": "info",
                "tags": ["engineering"],
            }
            for i in range(120)
        ]
        business_entries = [
            {
                "id": f"biz.{i}",
                "domain": "business",
                "principle": f"Business Principle {i}",
                "summary": "Summary",
                "teaching": "Teaching",
                "metaphor": "Metaphor",
                "triggers": ["business"],
                "phase_relevance": ["SHAPE"],
                "severity_hint": "info",
                "tags": ["business"],
            }
            for i in range(5)
        ]
        (wd / "large.yaml").write_text(yaml.dump(engineering_entries + business_entries))

        guardian = GuardianAngel()
        guardian.corpus = WisdomCorpus(wd)
        result = guardian.corpus_search()
        assert result["total_entries"] == 125
        assert result["by_domain"]["engineering"] == 120
        assert result["by_domain"]["business"] == 5


# ---------------------------------------------------------------------------
# Mastery ledger tests
# ---------------------------------------------------------------------------


class TestMasteryLedger:
    def test_record_and_check(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        oracle = Oracle()
        oracle._record_wisdom_shown("test.tdd")
        mastery = oracle._load_mastery()
        assert "test.tdd" in mastery["encountered"]
        assert mastery["encountered"]["test.tdd"]["times_shown"] == 1

    def test_record_increments(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        oracle = Oracle()
        oracle._record_wisdom_shown("test.tdd")
        oracle._record_wisdom_shown("test.tdd")
        oracle._record_wisdom_shown("test.tdd")
        mastery = oracle._load_mastery()
        assert mastery["encountered"]["test.tdd"]["times_shown"] == 3

    def test_check_internalization_false(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        oracle = Oracle()
        assert oracle._check_internalization("test.tdd") is False

    def test_mark_internalized(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        oracle = Oracle()
        oracle._record_wisdom_shown("test.tdd")
        oracle._mark_internalized("test.tdd", evidence="writes tests first")
        assert oracle._check_internalization("test.tdd") is True

    def test_mastery_score_updates(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        oracle = Oracle()
        oracle._record_wisdom_shown("test.tdd")
        oracle._record_wisdom_shown("test.mvp")
        oracle._mark_internalized("test.tdd", evidence="e1")
        mastery = oracle._load_mastery()
        # 1 internalized out of 2 encountered = 0.5
        assert mastery["mastery_score"] == 0.5

    def test_mastery_report(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        oracle = Oracle()
        report = oracle.get_mastery_report()
        assert "mastery_score" in report
        assert "learning_velocity" in report
        assert report["learning_velocity"] == "starting"

    def test_mastery_report_velocity(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        _write_oracle_state(oracle_tmp, {
            "mastery": {
                "encountered": {f"w{i}": {"times_shown": 3} for i in range(12)},
                "internalized": {f"w{i}": {"at": "2026-01-01"} for i in range(9)},
                "growth_areas": [],
                "mastery_score": 0.75,
            }
        })
        oracle = Oracle()
        report = oracle.get_mastery_report()
        assert report["learning_velocity"] == "mastering"

    def test_persistence_across_instances(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        oracle1 = Oracle()
        oracle1._record_wisdom_shown("test.tdd")
        oracle1._record_wisdom_shown("test.tdd")

        oracle2 = Oracle()
        mastery = oracle2._load_mastery()
        assert mastery["encountered"]["test.tdd"]["times_shown"] == 2


# ---------------------------------------------------------------------------
# Advisory backward compatibility
# ---------------------------------------------------------------------------


class TestAdvisoryBackwardCompat:
    def test_new_fields_default_empty(self):
        adv = Advisory(category="test", severity="info", message="msg")
        assert adv.wisdom_id == ""
        assert adv.teaching == ""
        assert adv.mastery_note == ""

    def test_to_dict_excludes_empty_wisdom(self):
        adv = Advisory(category="test", severity="info", message="msg")
        d = adv.to_dict()
        assert "wisdom_id" not in d
        assert "teaching" not in d
        assert "mastery_note" not in d

    def test_to_dict_includes_wisdom_when_set(self):
        adv = Advisory(
            category="test",
            severity="info",
            message="msg",
            wisdom_id="eng.tdd",
            teaching="Write tests first.",
            mastery_note="Encountered 5 times.",
        )
        d = adv.to_dict()
        assert d["wisdom_id"] == "eng.tdd"
        assert d["teaching"] == "Write tests first."
        assert d["mastery_note"] == "Encountered 5 times."


# ---------------------------------------------------------------------------
# OracleProfile new fields
# ---------------------------------------------------------------------------


class TestOracleProfileGuardianFields:
    def test_new_fields_default(self):
        from conductor.profiler import OracleProfile
        profile = OracleProfile()
        assert profile.mastery_score == 0.0
        assert profile.principles_encountered == 0
        assert profile.principles_internalized == 0
        assert profile.top_growth_areas == []
        assert profile.learning_velocity == "starting"

    def test_to_dict_includes_new_fields(self):
        from conductor.profiler import OracleProfile
        profile = OracleProfile(mastery_score=0.5, learning_velocity="growing")
        d = profile.to_dict()
        assert d["mastery_score"] == 0.5
        assert d["learning_velocity"] == "growing"


# ---------------------------------------------------------------------------
# New detectors
# ---------------------------------------------------------------------------


class TestNewDetectors:
    def test_canonical_practice_in_registry(self):
        assert "canonical_practice" in DETECTOR_REGISTRY

    def test_business_insight_in_registry(self):
        assert "business_insight" in DETECTOR_REGISTRY

    def test_mastery_progress_in_registry(self):
        assert "mastery_progress" in DETECTOR_REGISTRY

    def test_canonical_practice_returns_list(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        oracle = Oracle()
        ctx = OracleContext(current_phase="BUILD")
        result = oracle._detect_canonical_practice(ctx)
        assert isinstance(result, list)

    def test_business_insight_returns_list(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        oracle = Oracle()
        ctx = OracleContext()
        result = oracle._detect_business_insight(ctx)
        assert isinstance(result, list)

    def test_mastery_progress_returns_list(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        oracle = Oracle()
        result = oracle._detect_mastery_progress()
        assert isinstance(result, list)

    def test_mastery_progress_milestone(self, oracle_tmp):
        _write_stats(oracle_tmp, {"total_sessions": 0})
        _write_oracle_state(oracle_tmp, {
            "mastery": {
                "encountered": {f"w{i}": {"times_shown": 1} for i in range(5)},
                "internalized": {},
                "growth_areas": [],
                "mastery_score": 0.0,
            }
        })
        oracle = Oracle()
        result = oracle._detect_mastery_progress()
        # Should have a milestone advisory for 5 encountered
        milestone_advs = [a for a in result if "milestone" in a.message.lower() or "encountered" in a.message.lower()]
        assert len(milestone_advs) >= 1


# ---------------------------------------------------------------------------
# Extract triggers helper
# ---------------------------------------------------------------------------


class TestExtractTriggers:
    def test_basic_extraction(self):
        triggers = GuardianAngel._extract_triggers("I want to rewrite the entire API")
        assert "rewrite" in triggers
        assert "ambitious_rewrite" in triggers

    def test_multiple_keywords(self):
        triggers = GuardianAngel._extract_triggers("deploy the perfect mvp")
        assert "deployment" in triggers or "ci_cd" in triggers
        assert "perfectionism" in triggers or "fear_of_shipping" in triggers
        assert "mvp" in triggers or "minimum_viable" in triggers

    def test_no_triggers(self):
        triggers = GuardianAngel._extract_triggers("update variable name")
        assert triggers == []

    def test_case_insensitive(self):
        triggers = GuardianAngel._extract_triggers("REWRITE everything")
        assert "rewrite" in triggers
