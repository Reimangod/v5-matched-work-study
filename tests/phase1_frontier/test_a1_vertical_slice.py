from __future__ import annotations

import json

import pytest

from phase1_frontier.a1_vertical_slice import (
    A1KernelBoundary,
    A1_RESULT,
    audit_result,
)


def test_kernel_boundary_counts_completed_and_failed_calls_at_the_boundary() -> None:
    boundary = A1KernelBoundary()
    assert boundary.invoke("candidate-energy-evaluation", lambda: -1.0) == -1.0
    with pytest.raises(RuntimeError, match="injected"):
        boundary.invoke(
            "full-gradient-evaluation",
            lambda: (_ for _ in ()).throw(RuntimeError("injected")),
            dimension=3,
        )
    assert boundary.totals() == {
        "candidate-energy-evaluation": 1,
        "full-gradient-evaluation": 3,
    }
    assert [event.outcome for event in boundary.events] == ["completed", "failed"]


def test_A1_artifact_audits_and_keeps_E3_and_FCI_closed() -> None:
    assert A1_RESULT.is_file()
    record = json.loads(A1_RESULT.read_text(encoding="utf-8"))
    assert record["E3_candidate_outcomes"] == 0
    assert record["FCI_evaluations"] == 0
    assert record["engineering_transaction"][
        "scientific_compression_acceptance_claimed"
    ] is False
    assert audit_result()["passed"] is True


def test_A1_executed_exactly_one_singleton_and_one_K2_joint_with_two_starts() -> None:
    record = json.loads(A1_RESULT.read_text(encoding="utf-8"))
    assert [target["target_class"] for target in record["targets"]] == [
        "singleton",
        "joint-K2",
    ]
    assert [len(target["candidate_ids"]) for target in record["targets"]] == [1, 2]
    for target in record["targets"]:
        assert [start["start"] for start in target["starts"]] == [
            "mapped-warm-start",
            "zero-target-coordinate",
        ]
        assert all(
            start["raw_counter_totals"][
                "independent-full-gradient-certification"
            ]
            > 0
            for start in target["starts"]
        )


def test_A1_failure_probes_are_exact_and_retry_the_same_request() -> None:
    record = json.loads(A1_RESULT.read_text(encoding="utf-8"))
    failures = record["failure_probes"]
    assert failures["optimizer_failure_injected"] is True
    assert failures["optimizer_failure_exact_rollback"] is True
    assert failures["artifact_write_failure_injected"] is True
    assert failures["artifact_write_failure_exact_rollback"] is True
    assert failures["same_request_retry_id"] == "a1-retry-request"
    assert failures["same_request_retry_authorized_after_exact_rollback"] is True
