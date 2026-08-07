from __future__ import annotations

from dataclasses import asdict
import copy
import hashlib
from pathlib import Path

import pytest

from v5_matched_work.atomic_artifacts import canonical_json_bytes
from v5_final.method_native_hardening_v2 import (
    QUEUE_SCHEMA,
    PersistentRecorderV2,
    ResidualHardeningError,
    build_bound_result_artifact_v3,
    build_item_completeness_v3,
    build_transaction_record_v2,
    build_validated_queue_binding_v3,
    publish_bound_result_exclusive_v3,
    replay_persistent_ledger,
    resolve_executor_callable,
    verify_queue_binding_v3,
)
from v5_final.method_native_interface import (
    METHOD_IDS,
    MethodNativeInterfaceError,
    MethodNativeRequest,
    MethodNativeResult,
    NativeExecutorIdentity,
)
from v5_final.s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT
from v5_final.semantic_contract_v2 import WorkDelta


IMPLEMENTATION = ROOT / "src/v5_final/method_native_hardening_v2.py"
ATTEMPT_ID = "method-attempt-v1:" + "b" * 64


def _digest(value) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _queue() -> dict:
    return {
        "schema": "v5-final.method-native-frozen-queue.v3",
        "status": "FROZEN_PRE_OUTCOME",
        "queue": [
            {
                "queue_item_id": "synthetic-q1",
                "method_id": METHOD_IDS[0],
                "case_id": "synthetic-no-molecule",
            }
        ],
    }


def _binding() -> dict:
    queue = _queue()
    return build_validated_queue_binding_v3(queue, artifact_sha256=_digest(queue))


def _cap() -> WorkDelta:
    return WorkDelta(candidate_generations=1, search_states=0)


def _request(binding: dict | None = None) -> MethodNativeRequest:
    binding = binding or _binding()
    cap = _cap()
    return MethodNativeRequest(
        queue_item_id="synthetic-q1",
        method_id=METHOD_IDS[0],
        case_id="synthetic-no-molecule",
        state_preparation_id="state-v1:" + "1" * 64,
        problem_id="problem-v1:" + "2" * 64,
        source_checkpoint_digest="3" * 64,
        hamiltonian_digest="4" * 64,
        frozen_queue_digest=binding["binding_digest"],
        work_envelope="SYNTHETIC_CAP_REJECTION_ONLY",
        work_cap_digest=_digest(asdict(cap)),
        optimizer_policy_digest="7" * 64,
        acceptance_policy_digest="8" * 64,
        protocol_digest="9" * 64,
        rng_identity={"status": "NOT_USED"},
        environment_identity={"status": "SYNTHETIC_NO_MOLECULE"},
        environment_digest="a" * 64,
    )


def _executor(**changes) -> NativeExecutorIdentity:
    values = {
        "method_id": METHOD_IDS[0],
        "classification": "SYNTHETIC_INFRASTRUCTURE_ONLY",
        "entrypoint": "v5_final.method_native_hardening_v2:synthetic_no_molecule",
        "implementation_sha256": hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest(),
        "parent_repository_commit": PARENT_COMMIT,
        "ceo_adapt_vqe_commit": CEO_COMMIT,
    }
    values.update(changes)
    return NativeExecutorIdentity(**values)


def _records():
    binding = _binding()
    request = _request(binding)
    executor = _executor()
    recorder = PersistentRecorderV2(
        request=request,
        executor=executor,
        implementation_path=IMPLEMENTATION,
        attempt_id=ATTEMPT_ID,
        cap=_cap(),
        root_digest="0" * 64,
    )
    state = "physical-state-v1:" + "f" * 64
    assert recorder.register_candidate_state(
        candidate_id="synthetic-intent", proposed_physical_state_id=state
    ) == "CAP_REJECTED"
    ledger = recorder.close()
    transaction = build_transaction_record_v2(
        request=request,
        attempt_id=ATTEMPT_ID,
        ledger=ledger,
        terminal_status="CAP_EXHAUSTED",
    )
    completeness = build_item_completeness_v3(
        request=request,
        attempt_id=ATTEMPT_ID,
        ledger=ledger,
        queue_binding=binding,
        transaction=transaction,
    )
    result = MethodNativeResult(
        request_id=request.request_id,
        terminal_status="CAP_EXHAUSTED",
        executor=executor,
        parent_state_id=request.state_preparation_id,
        child_state_id=None,
        raw_semantic_events=tuple(ledger["events"]),
        work_ledger=ledger,
        resource_recount={"status": "NOT_RUN_CAP_EXHAUSTED"},
        transaction_record=transaction,
        failure_rollback_record=None,
        completeness_manifest=completeness,
        evidence_class="SYNTHETIC_INFRASTRUCTURE_ONLY/NO_MOLECULAR_ENERGY",
    )
    return binding, request, executor, ledger, transaction, completeness, result


def test_entrypoint_resolves_to_exact_callable_file_and_pinned_gitlinks() -> None:
    target, path = resolve_executor_callable(
        _executor(), implementation_path=IMPLEMENTATION, expected_method_id=METHOD_IDS[0]
    )
    assert callable(target)
    assert path == IMPLEMENTATION.resolve()

    other = ROOT / "src/v5_final/method_native_hardening.py"
    with pytest.raises(MethodNativeInterfaceError, match="source differs"):
        resolve_executor_callable(
            _executor(implementation_sha256=hashlib.sha256(other.read_bytes()).hexdigest()),
            implementation_path=other,
            expected_method_id=METHOD_IDS[0],
        )
    with pytest.raises(MethodNativeInterfaceError, match="does not resolve"):
        resolve_executor_callable(
            _executor(entrypoint="v5_final.method_native_hardening_v2:absent_callable"),
            implementation_path=IMPLEMENTATION,
            expected_method_id=METHOD_IDS[0],
        )
    with pytest.raises(MethodNativeInterfaceError, match="parent commit"):
        resolve_executor_callable(
            _executor(parent_repository_commit="e" * 40),
            implementation_path=IMPLEMENTATION,
            expected_method_id=METHOD_IDS[0],
        )


def test_queue_binding_executes_pinned_schema_and_rejects_false_inputs(tmp_path: Path) -> None:
    binding = _binding()
    verify_queue_binding_v3(binding)
    assert binding["queue_schema_audit"]["schema_error_count"] == 0
    assert binding["queue_schema_audit"]["valid"] is True

    invalid = _queue()
    invalid["queue"][0].pop("case_id")
    with pytest.raises(ResidualHardeningError, match="schema validation failed"):
        build_validated_queue_binding_v3(invalid, artifact_sha256=_digest(invalid))

    fake_schema = tmp_path / "fake.schema.json"
    fake_schema.write_text(QUEUE_SCHEMA.read_text())
    with pytest.raises(ResidualHardeningError, match="not the pinned schema"):
        build_validated_queue_binding_v3(
            _queue(), artifact_sha256=_digest(_queue()), schema_path=fake_schema
        )

    forged = copy.deepcopy(binding)
    forged["queue_schema_audit"]["validator"] = "caller.says.True"
    forged["queue_schema_audit"]["schema_audit_sha256"] = _digest(
        {key: value for key, value in forged["queue_schema_audit"].items() if key != "schema_audit_sha256"}
    )
    forged["queue_schema_audit_sha256"] = forged["queue_schema_audit"]["schema_audit_sha256"]
    forged["binding_digest"] = _digest(
        {key: value for key, value in forged.items() if key != "binding_digest"}
    )
    with pytest.raises(ResidualHardeningError, match="does not reproduce"):
        verify_queue_binding_v3(forged)


def test_cap_rejection_is_persistent_zero_work_and_replayable() -> None:
    _, request, executor, ledger, _, completeness, _ = _records()
    replay = replay_persistent_ledger(ledger, request=request, executor=executor)
    assert replay["rejection_count"] == 1
    assert replay["candidate_energy_evaluations"] == 0
    assert ledger["raw_counter_total"]["candidate_generations"] == 1
    assert ledger["raw_counter_total"]["search_states"] == 0
    assert ledger["canonical_state_count"] == 0
    assert completeness["rejection_ids"] == [ledger["rejections"][0]["rejection_id"]]

    deleted = copy.deepcopy(ledger)
    deleted["rejections"] = []
    deleted["rejection_count"] = 0
    deleted["ledger_digest"] = _digest(
        {key: value for key, value in deleted.items() if key != "ledger_digest"}
    )
    with pytest.raises(ResidualHardeningError, match="journal"):
        replay_persistent_ledger(deleted, request=request, executor=executor)

    altered = copy.deepcopy(ledger)
    altered["rejections"][0]["reason"] = "ALTERED"
    altered["rejections"][0]["rejection_id"] = "cap-rejection-v2:" + _digest(
        {
            key: value
            for key, value in altered["rejections"][0].items()
            if key != "rejection_id"
        }
    )
    altered["journal"][1]["record_id"] = altered["rejections"][0]["rejection_id"]
    altered["ledger_digest"] = _digest(
        {key: value for key, value in altered.items() if key != "ledger_digest"}
    )
    with pytest.raises(ResidualHardeningError, match="reason"):
        replay_persistent_ledger(altered, request=request, executor=executor)


def test_publication_revalidates_every_binding_and_is_exclusive(tmp_path: Path) -> None:
    binding, request, _, ledger, transaction, completeness, result = _records()
    values = {
        "request": request,
        "result": result,
        "implementation_path": IMPLEMENTATION,
        "queue_binding": binding,
        "ledger": ledger,
        "completeness": completeness,
        "transaction": transaction,
    }
    artifact = build_bound_result_artifact_v3(**values)
    assert artifact["binding"]["ledger_digest"] == ledger["ledger_digest"]
    output = tmp_path / "result.json"
    assert publish_bound_result_exclusive_v3(output, **values) == artifact
    with pytest.raises(FileExistsError):
        publish_bound_result_exclusive_v3(output, **values)

    wrong_transaction = copy.deepcopy(transaction)
    wrong_transaction["rollback_complete"] = True
    wrong_transaction["transaction_digest"] = _digest(
        {key: value for key, value in wrong_transaction.items() if key != "transaction_digest"}
    )
    with pytest.raises(ResidualHardeningError, match="does not reproduce"):
        build_bound_result_artifact_v3(**{**values, "transaction": wrong_transaction})

    wrong_binding = copy.deepcopy(binding)
    wrong_binding["expected_queue_count"] = 2
    wrong_binding["binding_digest"] = _digest(
        {key: value for key, value in wrong_binding.items() if key != "binding_digest"}
    )
    with pytest.raises(ResidualHardeningError, match="does not reproduce"):
        build_bound_result_artifact_v3(**{**values, "queue_binding": wrong_binding})
