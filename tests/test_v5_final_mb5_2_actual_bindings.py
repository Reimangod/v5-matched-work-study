from __future__ import annotations

import json
from pathlib import Path

import pytest

from v5_final.mb5_1_production_backend_audit import fixture as fixture_v1
from v5_final.production_backends.common import CapRejected, digest
from v5_final.production_backends_v2 import ENTRYPOINTS_V2
from v5_final.production_backends_v2.common import (
    PersistentBoundaryRecorderV2,
    validate_request_v2,
)
from v5_final.production_kernel_bindings_v2 import FakeBehavioralKernelBindings


def fixture_v2(method_id: str, **updates: object) -> dict[str, object]:
    value = fixture_v1(method_id)
    value["schema"] = "v5-final.mb5-2-production-backend-request.v1"
    value["qubit_count"] = 4
    value["maximum_optimizer_iterations"] = 1
    value.update(updates)
    value["request_digest"] = digest(
        {key: item for key, item in value.items() if key != "request_digest"}
    )
    return value


def test_six_distinct_runtime_flows_call_behavioral_binding(tmp_path: Path) -> None:
    results = {}
    for index, (method_id, entrypoint) in enumerate(ENTRYPOINTS_V2.items()):
        results[method_id] = entrypoint(
            fixture_v2(method_id), ledger_path=tmp_path / f"{index}.jsonl"
        )
    assert len({entrypoint.__module__ for entrypoint in ENTRYPOINTS_V2.values()}) == 6
    assert all(result["binding_runtime_trace"] for result in results.values())
    assert all(result["scientific_candidate_energy_evaluations"] == 0 for result in results.values())
    assert all(result["synthetic_behavioral_work_only"] is True for result in results.values())
    assert results["immutable-ceo-star-source"]["binding_runtime_trace"][0]["operation"] == "full-physical-resource-recount"
    assert results["same-structure-reoptimization"]["raw_work_total"]["optimizer_starts"] == 1
    assert results["structural-magnitude-pruning"]["method_evidence"]["physical_generator_deleted"] is True
    assert results["v4.1-one-shot-joint-compression"]["method_evidence"]["frozen_sentinel_only"] is True
    assert results["v5-fixed-source-whitelist-no-replenishment"]["method_evidence"]["runtime_new_candidates_admitted"] is False
    assert results["v5-sequential-with-rebuilding"]["method_evidence"]["catalog_calls"] == 2


def test_cap_rejection_is_persisted_before_callable(tmp_path: Path) -> None:
    request = fixture_v2("immutable-ceo-star-source")
    request["componentwise_work_cap"]["resource_recounts"] = 0  # type: ignore[index]
    request["work_cap_digest"] = digest(request["componentwise_work_cap"])
    request["request_digest"] = digest({key: value for key, value in request.items() if key != "request_digest"})
    bound = validate_request_v2(request, "immutable-ceo-star-source")
    recorder = PersistentBoundaryRecorderV2(bound, "test.cap", tmp_path / "cap.jsonl")
    called = False

    def thunk() -> None:
        nonlocal called
        called = True

    with pytest.raises(CapRejected):
        recorder.invoke("full-physical-resource-recount", thunk)
    assert called is False
    persisted = [json.loads(line) for line in (tmp_path / "cap.jsonl").read_text().splitlines()]
    assert persisted[-1]["outcome"] == "rejected"
    assert persisted[-1]["evidence"]["call_executed"] is False


def test_failed_call_is_persistent_and_rolls_back(tmp_path: Path) -> None:
    result = ENTRYPOINTS_V2["same-structure-reoptimization"](
        fixture_v2("same-structure-reoptimization", fake_fail_operation="candidate-energy-evaluation"),
        ledger_path=tmp_path / "failure.jsonl",
    )
    assert result["transaction_record"]["status"] == "FAILED_CLOSED"
    assert result["rollback_record"]["exact"] is True
    assert any(event["outcome"] == "failed" for event in result["raw_boundary_events"])
    assert result["raw_work_total"]["energy_evaluations"] == 1


def test_hvp_counts_hvp_and_internal_gradient_work(tmp_path: Path) -> None:
    request = fixture_v2("same-structure-reoptimization")
    bound = validate_request_v2(request, "same-structure-reoptimization")
    recorder = PersistentBoundaryRecorderV2(bound, "test.hvp", tmp_path / "hvp.jsonl")
    fake = FakeBehavioralKernelBindings(recorder=recorder, catalog=[])
    fake.hessian_vector_product([0.1, 0.2], [0.0, 0.1], [1, 2])
    assert recorder.total["hvp_evaluations"] == 1
    assert recorder.total["gradient_vector_evaluations"] == 2
    assert recorder.total["gradient_component_equivalents"] == 4


def test_semantic_duplicate_uses_physical_state_identity(tmp_path: Path) -> None:
    request = fixture_v2("v5-sequential-with-rebuilding")
    bound = validate_request_v2(request, "v5-sequential-with-rebuilding")
    recorder = PersistentBoundaryRecorderV2(bound, "test.dedup", tmp_path / "dedup.jsonl")
    assert recorder.register_physical_state("candidate-a", "physical-state-v1:" + "1" * 64)
    assert not recorder.register_physical_state("different-id", "physical-state-v1:" + "1" * 64)
    assert recorder.total["search_states"] == 1
