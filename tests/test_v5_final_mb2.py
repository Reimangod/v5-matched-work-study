from __future__ import annotations

import copy

import pytest

from v5_final.method_native_interface import (
    METHOD_IDS,
    MethodNativeInterfaceError,
    MethodNativeRequest,
    MethodNativeResult,
    NativeExecutorIdentity,
    bind_result_to_request,
    protocol,
)


def _request(method_id: str) -> MethodNativeRequest:
    return MethodNativeRequest(
        queue_item_id="synthetic-queue-item",
        method_id=method_id,
        case_id="synthetic-case",
        state_preparation_id="state-v1:" + "1" * 64,
        problem_id="problem-v1:" + "2" * 64,
        source_checkpoint_digest="3" * 64,
        hamiltonian_digest="4" * 64,
        frozen_queue_digest="5" * 64,
        work_envelope="SYNTHETIC_ZERO_WORK",
        work_cap_digest="6" * 64,
        optimizer_policy_digest="7" * 64,
        acceptance_policy_digest="8" * 64,
        protocol_digest="9" * 64,
        rng_identity={"kind": "none", "reason": "serialization probe"},
        environment_identity={"kind": "synthetic", "threads": 1},
        environment_digest="a" * 64,
    )


def _executor(method_id: str) -> NativeExecutorIdentity:
    return NativeExecutorIdentity(
        method_id=method_id,
        classification="SYNTHETIC_INTERFACE_PROBE",
        entrypoint="v5_final.synthetic:never_execute",
        implementation_sha256="b" * 64,
        parent_repository_commit="c" * 40,
        ceo_adapt_vqe_commit="d" * 40,
    )


def _result(request: MethodNativeRequest) -> MethodNativeResult:
    return MethodNativeResult(
        request_id=request.request_id,
        terminal_status="INFRASTRUCTURE_ONLY",
        executor=_executor(request.method_id),
        parent_state_id=request.state_preparation_id,
        child_state_id=None,
        raw_semantic_events=(),
        work_ledger={"status": "NOT_STARTED", "total": {}},
        resource_recount={"status": "NOT_RUN"},
        transaction_record={"status": "NOT_STARTED"},
        failure_rollback_record=None,
        completeness_manifest={"complete": False, "reason": "not executed"},
        evidence_class="INFRASTRUCTURE_ONLY/NO_PERFORMANCE_EVIDENCE",
    )


def test_all_six_methods_round_trip_through_recording_interface() -> None:
    for method_id in METHOD_IDS:
        request = _request(method_id)
        rebuilt_request = MethodNativeRequest.from_dict(request.to_dict())
        result = _result(rebuilt_request)
        rebuilt_result = MethodNativeResult.from_dict(result.to_dict())
        bind_result_to_request(rebuilt_result, rebuilt_request)
        assert rebuilt_result.terminal_status == "INFRASTRUCTURE_ONLY"
        assert rebuilt_result.raw_semantic_events == ()
        assert rebuilt_result.completeness_manifest["complete"] is False


def test_interface_rejects_digest_tampering_and_cross_method_binding() -> None:
    request = _request(METHOD_IDS[0])
    tampered = copy.deepcopy(request.to_dict())
    tampered["work_envelope"] = "CHANGED"
    with pytest.raises(MethodNativeInterfaceError, match="digest or canonical"):
        MethodNativeRequest.from_dict(tampered)

    result = _result(request)
    other = _request(METHOD_IDS[1])
    with pytest.raises(MethodNativeInterfaceError, match="not bound"):
        bind_result_to_request(result, other)


def test_infrastructure_record_cannot_claim_execution_or_completeness() -> None:
    request = _request(METHOD_IDS[0])
    values = dict(
        request_id=request.request_id,
        terminal_status="INFRASTRUCTURE_ONLY",
        executor=_executor(request.method_id),
        parent_state_id=request.state_preparation_id,
        child_state_id=None,
        raw_semantic_events=(),
        work_ledger={"status": "NOT_STARTED"},
        resource_recount={"status": "NOT_RUN"},
        transaction_record={"status": "NOT_STARTED"},
        failure_rollback_record=None,
        completeness_manifest={"complete": True},
        evidence_class="INFRASTRUCTURE_ONLY",
    )
    with pytest.raises(MethodNativeInterfaceError, match="cannot contain events or be complete"):
        MethodNativeResult(**values)
    assert protocol()["algorithm_fields"] == []
    assert protocol()["candidate_execution"] == "NOT_AUTHORIZED_BY_THIS_PROTOCOL"
