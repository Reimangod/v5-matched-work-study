from __future__ import annotations

import copy
import json

import pytest

from v5_final.mb5_1_production_backend_audit import OUTPUT, audit, fixture
from v5_final.production_backends import ENTRYPOINTS
from v5_final.production_backends.common import (
    OutcomeLeakageBlocked,
    ProductionBackendError,
    digest,
    validate_request,
    BoundaryRecorder,
)


def test_six_distinct_production_entrypoints_complete_only_outcome_free_dry_runs() -> None:
    assert len(ENTRYPOINTS) == 6
    modules = {entrypoint.__module__ for entrypoint in ENTRYPOINTS.values()}
    assert len(modules) == 6
    for method_id, entrypoint in ENTRYPOINTS.items():
        result = entrypoint(fixture(method_id))
        assert result["candidate_energy_evaluations"] == 0
        assert result["molecular_kernel_calls"] == 0
        assert result["H2_H4_queue_touched"] is False
        assert result["development_queue_touched"] is False
        assert result["performance_evidence"] is False


def test_energy_sentinel_blocks_at_exact_boundary_without_an_event() -> None:
    request = fixture("immutable-ceo-star-source")
    bound = validate_request(request, "immutable-ceo-star-source")
    recorder = BoundaryRecorder(bound, "v5_final.method_native.test")
    with pytest.raises(OutcomeLeakageBlocked, match="blocking sentinel"):
        recorder.molecular("candidate-energy-evaluation")
    assert recorder.events == []
    assert recorder.total["energy_evaluations"] == 0


def test_semantic_duplicate_and_replenishment_causal_difference() -> None:
    fixed = ENTRYPOINTS["v5-fixed-source-whitelist-no-replenishment"](
        fixture("v5-fixed-source-whitelist-no-replenishment")
    )
    full = ENTRYPOINTS["v5-sequential-with-rebuilding"](
        fixture("v5-sequential-with-rebuilding")
    )
    assert full["unique_physical_state_count"] == 3
    assert full["raw_work_total"]["candidate_generations"] == 4
    assert fixed["selected_candidate_ids"] == ["candidate-b"]
    assert full["selected_candidate_ids"] == ["candidate-new"]


def test_wrong_source_identity_and_fake_schema_fail_closed() -> None:
    request = fixture("immutable-ceo-star-source")
    request["source"]["Hamiltonian_digest"] = "0" * 64
    request["request_digest"] = digest(
        {key: value for key, value in request.items() if key != "request_digest"}
    )
    with pytest.raises(ProductionBackendError, match="source/Problem/Hamiltonian"):
        ENTRYPOINTS["immutable-ceo-star-source"](request)

    fake = fixture("immutable-ceo-star-source")
    fake["schema"] = "fake"
    fake["request_digest"] = digest(
        {key: value for key, value in fake.items() if key != "request_digest"}
    )
    with pytest.raises(ProductionBackendError, match="schema"):
        ENTRYPOINTS["immutable-ceo-star-source"](fake)


def test_failure_rolls_back_and_retry_is_linked() -> None:
    failure = fixture("same-structure-reoptimization")
    failure["failure_injection"] = "after-stage"
    failure["request_digest"] = digest(
        {key: value for key, value in failure.items() if key != "request_digest"}
    )
    failed = ENTRYPOINTS["same-structure-reoptimization"](failure)
    assert failed["rollback_record"]["exact"] is True
    retry = ENTRYPOINTS["same-structure-reoptimization"](
        fixture("same-structure-reoptimization", attempt_index=1)
    )
    assert retry["attempt_index"] == 1
    assert retry["previous_attempt_digest"] is not None


def test_committed_mb5_1_audit_rebuilds_exactly_and_stops_at_mb6_freeze() -> None:
    artifact = json.loads(OUTPUT.read_text())
    assert artifact["decision"] == "GO_MB6_OUTCOME_BLIND_QUEUE_FREEZE_ONLY"
    assert artifact["P0_capacity_status"] == "NO_GO_INSUFFICIENT_SAFE_DISK_CAPACITY"
    assert artifact["development_queue"]["not_started_count"] == 90
    assert artifact["development_queue"]["candidate_energy_evaluations"] == 0
    assert all(audit().values())
