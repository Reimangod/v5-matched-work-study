from __future__ import annotations

import copy
import json

import pytest

from v5_final.mb4_2_owner_protocol_freeze import OUTPUT as FREEZE_OUTPUT
from v5_final.mb5_outcome_free_executor_audit import audit, synthetic_fixture
from v5_final.outcome_free_method_executors import (
    ENTRYPOINTS,
    OutcomeFreeExecutorError,
)


def _request(method_id: str) -> dict:
    freeze = json.loads(FREEZE_OUTPUT.read_text())
    return synthetic_fixture(
        method_id,
        freeze["protocol_digests"][method_id],
        freeze["freeze_digest"],
    )


def test_six_entrypoints_execute_only_synthetic_structural_semantics() -> None:
    assert len(ENTRYPOINTS) == 6
    for method_id, entrypoint in ENTRYPOINTS.items():
        result = entrypoint(_request(method_id))
        assert result["canonical_method_id"] == method_id
        assert result["semantic_counters"] == {
            "candidate_energy_evaluations": 0,
            "molecular_kernel_calls": 0,
            "H2_H4_queue_events": 0,
            "development_queue_events": 0,
        }
        assert result["development_queue_touched"] is False
        assert result["H2_H4_execution_touched"] is False
        assert result["production_execution_authorized"] is False
        assert result["performance_evidence"] is False


def test_fixed_whitelist_and_rebuild_differ_only_by_replenishment_eligibility() -> None:
    fixed_id = "v5-fixed-source-whitelist-no-replenishment"
    rebuild_id = "v5-sequential-with-rebuilding"
    fixed = ENTRYPOINTS[fixed_id](_request(fixed_id))
    rebuild = ENTRYPOINTS[rebuild_id](_request(rebuild_id))
    assert fixed["legacy_queue_method_id"] == "v5-sequential-without-rebuilding"
    assert fixed["selected_candidate_ids"] == ["candidate-b"]
    assert fixed["stale_candidate_ids"] == ["candidate-stale"]
    assert rebuild["selected_candidate_ids"] == ["candidate-new"]


def test_magnitude_and_v4_1_protocol_details_are_executable_without_outcomes() -> None:
    magnitude_id = "structural-magnitude-pruning"
    magnitude = ENTRYPOINTS[magnitude_id](_request(magnitude_id))
    assert magnitude["selected_candidate_ids"] == ["generator-b"]
    assert magnitude["child_generators"] == ["generator-a", "generator-c"]
    assert magnitude["resource_recount"]["resource_reduction_success"] is False
    assert all(value == 0 for value in magnitude["resource_recount"]["reduction"].values())

    v4_id = "v4.1-one-shot-joint-compression"
    v4 = ENTRYPOINTS[v4_id](_request(v4_id))
    assert v4["selected_candidate_ids"] == [
        "candidate-new",
        "candidate-a",
        "candidate-b",
        "candidate-d",
    ]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.__setitem__("energy", -1), "outcome-bearing"),
        (lambda value: value.__setitem__("Hamiltonian_digest", "1" * 64), "outcome-bearing"),
        (lambda value: value.__setitem__("molecular_case_id", "H2"), "outcome-bearing"),
        (
            lambda value: value.__setitem__("execution_mode", "PRODUCTION"),
            "outcome-free synthetic",
        ),
        (
            lambda value: value.__setitem__("candidate_energy_evaluations", 1),
            "candidate energy count",
        ),
        (
            lambda value: value.__setitem__("protocol_digest", "0" * 64),
            "differs from the owner freeze",
        ),
        (
            lambda value: value.__setitem__("protocol_freeze_digest", "0" * 64),
            "does not bind",
        ),
    ],
)
def test_outcome_or_unbound_requests_fail_closed(mutation, message: str) -> None:
    method_id = "immutable-ceo-star-source"
    request = copy.deepcopy(_request(method_id))
    mutation(request)
    with pytest.raises(OutcomeFreeExecutorError, match=message):
        ENTRYPOINTS[method_id](request)


def test_mb5_audit_stops_at_mb6_queue_freeze_only() -> None:
    checks = audit()
    assert all(checks.values())
