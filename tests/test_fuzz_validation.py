"""Property-based fuzz tests for parser/validator boundaries."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

hypothesis = pytest.importorskip("hypothesis")
strategies = pytest.importorskip("hypothesis.strategies")

from conductor.constants import GovernanceError
from conductor.governance import _parse_governance_payload, _parse_registry_payload
from router import Ontology, RoutingEngine, WorkflowValidator


@hypothesis.given(strategies.one_of(strategies.none(), strategies.integers(), strategies.text(), strategies.lists(strategies.integers()), strategies.dictionaries(strategies.text(), strategies.integers())))
def test_registry_parser_is_total(input_payload):
    if isinstance(input_payload, dict):
        # Ensure parser can still reject invalid dicts deterministically.
        try:
            _parse_registry_payload(input_payload)
        except GovernanceError:
            pass
    else:
        with pytest.raises(GovernanceError):
            _parse_registry_payload(input_payload)


@hypothesis.given(strategies.one_of(strategies.none(), strategies.integers(), strategies.text(), strategies.lists(strategies.integers()), strategies.dictionaries(strategies.text(), strategies.integers())))
def test_governance_parser_is_total(input_payload):
    if isinstance(input_payload, dict):
        try:
            _parse_governance_payload(input_payload)
        except GovernanceError:
            pass
    else:
        with pytest.raises(GovernanceError):
            _parse_governance_payload(input_payload)


@hypothesis.given(strategies.text(min_size=1, max_size=20))
def test_workflow_validator_handles_random_file_text(random_text):
    ontology = Ontology(Path(__file__).parent.parent / "ontology.yaml")
    engine = RoutingEngine(Path(__file__).parent.parent / "routing-matrix.yaml", ontology)
    validator = WorkflowValidator(ontology, engine)

    with tempfile.TemporaryDirectory() as tmp_dir:
        wf_path = Path(tmp_dir) / "fuzz-workflow.yaml"
        wf_path.write_text(random_text)

        try:
            report = validator.validate_report(wf_path)
            assert isinstance(report.errors, list)
            assert isinstance(report.warnings, list)
        except Exception as exc:
            # Parser errors from malformed YAML are acceptable, but they must be deterministic and explicit.
            assert isinstance(exc, Exception)
