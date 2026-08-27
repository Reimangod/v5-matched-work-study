from __future__ import annotations

from dataclasses import asdict
import hashlib
from pathlib import Path

import pytest

from v5_matched_work.atomic_artifacts import canonical_json_bytes
from v5_final.live_semantic_ledger import LiveSemanticLedgerError
from v5_final.method_native_hardening import (
    ExecutorBoundRecorder,
    build_attempt_segment_v2,
    build_chain_root_v2,
    build_completeness_manifest_v2,
    build_queue_binding_v2,
    publish_bound_result_exclusive,
    require_content_id,
    verify_attempt_chain_v2,
    verify_published_bound_result,
)
from v5_final.method_native_interface import (
    METHOD_IDS,
    MethodNativeInterfaceError,
    MethodNativeRequest,
    MethodNativeResult,
    NativeExecutorIdentity,
)
from v5_final.semantic_contract_v2 import WorkDelta


IMPLEMENTATION = Path(__file__).parents[1] / "src/v5_final/method_native_hardening.py"


def _digest(value) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _cap(**updates: int) -> WorkDelta:
    values = {
        "energy_evaluations": 2,
        "gradient_vector_evaluations": 2,
        "gradient_component_equivalents": 8,
        "hvp_evaluations": 2,
        "optimizer_starts": 2,
        "optimizer_iterations": 2,
        "resource_recounts": 2,
        "candidate_generations": 2,
        "search_states": 2,
        "rewrite_verifications": 2,
        "statevector_recomputations": 2,
    }
    values.update(updates)
    return WorkDelta(**values)


def _request(item: str, cap: WorkDelta) -> MethodNativeRequest:
    return MethodNativeRequest(
        queue_item_id=item,
        method_id=METHOD_IDS[0],
        case_id="synthetic-no-molecule",
        state_preparation_id="state-v1:" + "1" * 64,
        problem_id="problem-v1:" + "2" * 64,
        source_checkpoint_digest="3" * 64,
        hamiltonian_digest="4" * 64,
        frozen_queue_digest="5" * 64,
        work_envelope="SYNTHETIC_INFRASTRUCTURE_ONLY",
        work_cap_digest=_digest(asdict(cap)),
        optimizer_policy_digest="7" * 64,
        acceptance_policy_digest="8" * 64,
        protocol_digest="9" * 64,
        rng_identity={"status": "NOT_USED"},
        environment_identity={"status": "SYNTHETIC"},
        environment_digest="a" * 64,
    )


def _executor() -> NativeExecutorIdentity:
    return NativeExecutorIdentity(
        method_id=METHOD_IDS[0],
        classification="SYNTHETIC_INFRASTRUCTURE_ONLY",
        entrypoint="v5_final.method_native_hardening:synthetic_no_molecule",
        implementation_sha256=hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest(),
        parent_repository_commit="c" * 40,
        ceo_adapt_vqe_commit="d" * 40,
    )


def _recorder(
    request: MethodNativeRequest,
    cap: WorkDelta,
    *,
    first_sequence: int = 0,
) -> ExecutorBoundRecorder:
    return ExecutorBoundRecorder(
        request=request,
        executor=_executor(),
        implementation_path=IMPLEMENTATION,
        cap=cap,
        root_digest="0" * 64,
        first_sequence=first_sequence,
    )


def _queue_binding(items: list[str]):
    queue = {
        "schema": "v5-final.synthetic-hardening-queue.v1",
        "status": "FROZEN_PRE_OUTCOME_SYNTHETIC",
        "queue": [{"queue_item_id": item, "method_id": METHOD_IDS[0]} for item in items],
    }
    artifact_digest = _digest(queue)
    audit = {
        "schema": "v5-final.synthetic-queue-schema-audit.v1",
        "queue_artifact_sha256": artifact_digest,
        "checks": {"schema_known": True, "items_valid": True},
    }
    return build_queue_binding_v2(
        queue, artifact_sha256=artifact_digest, schema_audit=audit
    )


def test_ids_and_executor_implementation_require_exact_sha256() -> None:
    with pytest.raises(MethodNativeInterfaceError, match="SHA-256"):
        require_content_id("physical-state-v1:not-a-digest", "physical-state-v1", "state")
    cap = _cap()
    request = _request("q1", cap)
    invalid = NativeExecutorIdentity(
        method_id=METHOD_IDS[0],
        classification="SYNTHETIC",
        entrypoint="v5_final.method_native_hardening:synthetic_no_molecule",
        implementation_sha256="f" * 64,
        parent_repository_commit="c" * 40,
        ceo_adapt_vqe_commit="d" * 40,
    )
    with pytest.raises(MethodNativeInterfaceError, match="implementation digest"):
        ExecutorBoundRecorder(
            request=request,
            executor=invalid,
            implementation_path=IMPLEMENTATION,
            cap=cap,
            root_digest="0" * 64,
        )


def test_event_is_bound_to_exact_executor_identity() -> None:
    cap = _cap()
    request = _request("q1", cap)
    recorder = _recorder(request, cap)
    recorder.execute_kernel("full-physical-resource-recount", lambda: {"synthetic": True})
    event = recorder.events[0]
    assert event.producer == _executor().entrypoint
    assert event.evidence["native_executor_id"] == _executor().executor_id
    assert event.evidence["native_executor"] == _executor().to_dict()


def test_candidate_generation_remains_but_cap_rejected_expansion_does_not_mutate() -> None:
    cap = _cap(search_states=0)
    request = _request("q1", cap)
    recorder = _recorder(request, cap)
    state = "physical-state-v1:" + "f" * 64
    assert recorder.register_candidate_state(
        candidate_id="synthetic-intent", proposed_physical_state_id=state
    ) == "CAP_REJECTED"
    assert [event.operation for event in recorder.events] == ["candidate-generation"]
    assert recorder.raw_total.candidate_generations == 1
    assert recorder.raw_total.search_states == 0
    assert recorder.close()["canonical_state_count"] == 0


def test_retry_lifecycle_has_unique_attempts_and_one_terminal_segment() -> None:
    cap = _cap()
    request = _request("q1", cap)
    executor = _executor()
    binding = _queue_binding(["q1"])
    root = build_chain_root_v2(binding)

    first_recorder = _recorder(request, cap)
    first_recorder.execute_kernel("optimizer-start", lambda: None)
    first = build_attempt_segment_v2(
        previous_digest=root["root_digest"],
        segment_index=0,
        attempt_id="method-attempt-v1:" + "a" * 64,
        attempt_ordinal=0,
        attempt_status="FAILED_ROLLED_BACK",
        item_terminal=False,
        request=request,
        executor=executor,
        events=first_recorder.events,
    )
    second_recorder = _recorder(request, cap, first_sequence=1)
    second_recorder.execute_kernel("full-physical-resource-recount", lambda: {"synthetic": True})
    second = build_attempt_segment_v2(
        previous_digest=first["segment_digest"],
        segment_index=1,
        attempt_id="method-attempt-v1:" + "b" * 64,
        attempt_ordinal=1,
        attempt_status="COMPLETED",
        item_terminal=True,
        request=request,
        executor=executor,
        events=second_recorder.events,
    )
    requests = {"q1": request}
    executors = {executor.executor_id: executor}
    manifest = build_completeness_manifest_v2(
        root=root,
        binding=binding,
        requests=requests,
        executors=executors,
        segments=[first, second],
    )
    assert manifest["complete"] is True
    assert manifest["attempt_count"] == 2
    assert manifest["candidate_energy_evaluations"] == 0

    forbidden_recorder = _recorder(request, cap, first_sequence=2)
    forbidden_recorder.execute_kernel("optimizer-start", lambda: None)
    forbidden = build_attempt_segment_v2(
        previous_digest=second["segment_digest"],
        segment_index=2,
        attempt_id="method-attempt-v1:" + "e" * 64,
        attempt_ordinal=2,
        attempt_status="FAILED_ROLLED_BACK",
        item_terminal=False,
        request=request,
        executor=executor,
        events=forbidden_recorder.events,
    )
    with pytest.raises(LiveSemanticLedgerError, match="after the item terminal"):
        verify_attempt_chain_v2(
            root=root,
            binding=binding,
            requests=requests,
            executors=executors,
            segments=[first, second, forbidden],
        )

    semantically_invalid = {**second, "item_terminal": False}
    semantically_invalid["segment_digest"] = _digest(
        {key: value for key, value in semantically_invalid.items() if key != "segment_digest"}
    )
    with pytest.raises(LiveSemanticLedgerError, match="terminal flag"):
        verify_attempt_chain_v2(
            root=root,
            binding=binding,
            requests=requests,
            executors=executors,
            segments=[first, semantically_invalid],
        )


def test_queue_binding_requires_a_successful_bound_schema_audit() -> None:
    queue = {
        "status": "FROZEN_PRE_OUTCOME_SYNTHETIC",
        "queue": [{"queue_item_id": "q1"}],
    }
    digest = _digest(queue)
    with pytest.raises(LiveSemanticLedgerError, match="schema audit"):
        build_queue_binding_v2(
            queue,
            artifact_sha256=digest,
            schema_audit={
                "queue_artifact_sha256": digest,
                "checks": {"schema_known": False},
            },
        )


def test_result_publication_forces_binding_and_is_exclusive(tmp_path: Path) -> None:
    cap = _cap()
    request = _request("q1", cap)
    executor = _executor()
    result = MethodNativeResult(
        request_id=request.request_id,
        terminal_status="INFRASTRUCTURE_ONLY",
        executor=executor,
        parent_state_id=request.state_preparation_id,
        child_state_id=None,
        raw_semantic_events=(),
        work_ledger={"status": "NOT_STARTED"},
        resource_recount={"status": "NOT_RUN"},
        transaction_record={"status": "NOT_STARTED"},
        failure_rollback_record=None,
        completeness_manifest={"complete": False, "reason": "not executed"},
        evidence_class="INFRASTRUCTURE_ONLY/NO_PERFORMANCE_EVIDENCE",
    )
    path = tmp_path / "bound-result.json"
    artifact = publish_bound_result_exclusive(path, request=request, result=result)
    rebuilt_request, rebuilt_result = verify_published_bound_result(artifact)
    assert rebuilt_request.request_id == request.request_id
    assert rebuilt_result.result_id == result.result_id
    with pytest.raises(FileExistsError):
        publish_bound_result_exclusive(path, request=request, result=result)

    other = _request("q2", cap)
    with pytest.raises(MethodNativeInterfaceError, match="not bound"):
        publish_bound_result_exclusive(
            tmp_path / "wrong.json", request=other, result=result
        )
