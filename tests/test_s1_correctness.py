from __future__ import annotations

import itertools

import pytest

from v5_matched_work.s1_correctness import (
    CorrectnessBaselineError,
    RuntimeEndpointProvenance,
    accepted_pareto_frontier,
    risk_semantics,
    source_relative_budget,
)


def _point(identifier: str, energy: float, cnot: int, parameters: int) -> dict:
    return {
        "id": identifier,
        "energy_increase_hartree": energy,
        "cnot_count": cnot,
        "cnot_depth": cnot,
        "total_depth": cnot,
        "parameter_count": parameters,
        "logical_block_count": parameters,
    }


def test_frontier_is_permutation_invariant_and_keeps_tradeoffs() -> None:
    values = [
        _point("energy", 1e-5, 20, 4),
        _point("resource", 8e-5, 10, 2),
        _point("dominated", 9e-5, 21, 5),
    ]
    expected = accepted_pareto_frontier(values)
    assert [item["id"] for item in expected] == ["energy", "resource"]
    for permutation in itertools.permutations(values):
        assert accepted_pareto_frontier(permutation) == expected


def test_frontier_fails_closed_on_nonfinite_or_duplicate() -> None:
    with pytest.raises(CorrectnessBaselineError):
        accepted_pareto_frontier([_point("bad", float("nan"), 1, 1)])
    with pytest.raises(CorrectnessBaselineError):
        accepted_pareto_frontier([_point("same", 0.0, 2, 2), _point("same", 1e-5, 1, 1)])


def test_budget_has_no_exact_reference_input() -> None:
    assert source_relative_budget(
        source_energy_hartree=-2.0,
        committed_energy_hartree=-1.99995,
        total_budget_hartree=1e-4,
    ) == pytest.approx(5e-5)


def test_endpoint_provenance_is_runtime_bound_and_zero_margin_is_not_risk_aware() -> None:
    value = RuntimeEndpointProvenance("candidate", "cnot_count", "0" * 64)
    assert value.runtime_selection_endpoint == "cnot_count"
    with pytest.raises(CorrectnessBaselineError):
        RuntimeEndpointProvenance("candidate", "rank-modulo-inference", "0" * 64)
    assert risk_semantics(0.0) == "risk-neutral-zero-uncertainty-margin"
