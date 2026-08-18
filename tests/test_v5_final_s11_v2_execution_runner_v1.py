from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from v5_final.parent_native_persistent_runner import (
    ParentNativePersistentRunner,
    make_attempt_id,
    replay_raw_ledger,
)
from v5_final.s11_v2_execution_runner_v1 import (
    S11V2ExecutionRunnerError,
    _execute_authorized_item,
    _item_paths,
    _queue_index,
    _queue_v2_dynamic_scope,
    _result_artifact,
    _runtime_environment,
    _source_binding,
    _terminal_prefix,
    _write_dispatch,
    execute_queue_item_v1,
)
from v5_final.s11_v2_native_preparation_runtime_v1 import (
    CumulativeVerifierLedger,
    VerifierComponentwiseCapRejected,
)
from v5_final.s11_v2_queue_native_adapter import QueueV2NativeAdapter


class _Recorder:
    def __init__(self):
        self.events = []

    def _append(self, **values):
        self.events.append(SimpleNamespace(**values))


class _RawRunner:
    def __init__(self):
        self.persisted = 0

    def persist_new_work_events(self, events):
        self.persisted = len(events)


def test_public_entrypoint_refuses_absent_readiness_before_adapter_or_kernel(
    tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_execution_runner_v1 as subject

    monkeypatch.setattr(subject, "audit_p7_v5", lambda **kwargs: {})
    monkeypatch.setattr(subject, "READINESS_V2", tmp_path / "absent.json")
    touched = {"adapter": False}

    def adapter():
        touched["adapter"] = True
        raise AssertionError("adapter must remain unreachable")

    monkeypatch.setattr(subject, "QueueV2NativeAdapter", adapter)
    with pytest.raises(S11V2ExecutionRunnerError, match="readiness v8 GO is absent"):
        execute_queue_item_v1("unused", production_root=tmp_path / "production")
    assert touched["adapter"] is False


def test_dynamic_scope_restores_frozen_hooks_and_records_verifier_cap(tmp_path, monkeypatch) -> None:
    from v5_final import s11_v2_execution_runner_v1 as subject

    recorder = _Recorder()
    raw = _RawRunner()
    boundary = SimpleNamespace(recorder=recorder, runner=raw)
    frozen_v5 = subject.services._dynamic_v5_preparation
    frozen_magnitude = subject.services._dynamic_magnitude_preparation
    monkeypatch.setattr(
        subject,
        "prepare_dynamic_v5_v1",
        lambda **kwargs: (_ for _ in ()).throw(
            VerifierComponentwiseCapRejected("frozen verifier cap")
        ),
    )
    with _queue_v2_dynamic_scope(
        queue_item={},
        verifier_ledger=object(),
        boundary=boundary,
        maximum_rounds=2,
    ):
        with pytest.raises(Exception, match="frozen verifier cap"):
            subject.services._dynamic_v5_preparation(object(), boundary)
    assert subject.services._dynamic_v5_preparation is frozen_v5
    assert subject.services._dynamic_magnitude_preparation is frozen_magnitude
    assert len(recorder.events) == 1
    assert recorder.events[0].operation == "cap-rejection"
    assert recorder.events[0].outcome == "cap-rejected"
    assert raw.persisted == 1


def test_result_maps_raw_terminal_and_binds_empty_verifier_ledger(tmp_path) -> None:
    adapter = QueueV2NativeAdapter()
    request = adapter.first_request_for_method("same-structure-reoptimization")
    raw_root = tmp_path / "raw"
    attempt = make_attempt_id(request.work_request, ordinal=1, nonce="test")
    runner = ParentNativePersistentRunner.create(
        raw_root,
        request=request.work_request,
        cap=request.outcome_cap,
        attempt_id=attempt,
    )
    runner.finish("ALGORITHM_REJECTED", rejection_reason="TEST_REJECTION")
    verifier = CumulativeVerifierLedger(
        tmp_path / "verifier", cap=request.item["verifier_componentwise_cap"]
    )
    result = _result_artifact(
        request=request,
        raw_root=raw_root,
        verifier_ledger=verifier,
        outcome_checkpoint=None,
    )
    assert result["terminal_status"] == "ALGORITHM_REJECTED"
    assert result["N_dense_expm"] == 0
    assert result["FCI_evaluations"] == 0


@dataclass
class _Runtime:
    metadata: dict

    def snapshot(self):
        return SimpleNamespace(snapshot_digest="runtime-snapshot")

    def restore(self, snapshot):
        return None


def test_internal_authorized_runner_is_durable_and_recovery_does_not_reexecute(
    tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_execution_runner_v1 as subject

    adapter = QueueV2NativeAdapter()
    request = adapter.first_request_for_method("immutable-ceo-star-source")
    runtime = _Runtime(metadata={})
    context = SimpleNamespace(
        runtime=runtime,
        _actual_algorithm=SimpleNamespace(
            molecule=SimpleNamespace(fci_energy=None, ccsd_energy=None)
        ),
    )
    calls = {"build": 0, "execute": 0}

    monkeypatch.setattr(
        subject, "preflight_development_binding_v1", lambda *a, **k: None
    )

    def build(*args, **kwargs):
        calls["build"] += 1
        return context

    class Executor:
        def execute(self, service):
            calls["execute"] += 1
            return {
                "terminal_status": "ACCEPTED",
                "stopping_reason": "IMMUTABLE_SOURCE_CONTROL",
            }

    monkeypatch.setattr(subject, "build_queue_bound_development_runtime_v1", build)
    monkeypatch.setattr(
        subject,
        "prepare_initial_executor_v1",
        lambda **kwargs: (
            Executor(),
            SimpleNamespace(
                to_audit_dict=lambda: {"outcome_execution_authorized": False}
            ),
        ),
    )
    monkeypatch.setattr(
        subject.services,
        "_component_snapshot_digest",
        lambda runtime: {
            "ansatz": "1" * 64,
            "parameters": "2" * 64,
            "optimizer_inverse_hessian": "3" * 64,
            "resources": "4" * 64,
            "ledger_transaction": "5" * 64,
        },
    )
    production = tmp_path / "production"
    first = _execute_authorized_item(
        adapter=adapter,
        request=request,
        production_root=production,
        readiness_digest="6" * 64,
    )
    second = _execute_authorized_item(
        adapter=adapter,
        request=request,
        production_root=production,
        readiness_digest="6" * 64,
    )
    assert first == second
    assert first["terminal_status"] == "COMPLETED"
    assert calls == {"build": 1, "execute": 1}
    index = _queue_index(adapter, request.item["queue_item_id"])
    paths = _item_paths(production, index, request)
    assert paths["result"].is_file()
    assert paths["receipt"].is_file()
    assert paths["raw"].is_dir()


def test_nonprimitive_failure_rolls_back_without_false_work_or_terminal(
    tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_execution_runner_v1 as subject

    adapter = QueueV2NativeAdapter()
    request = adapter.first_request_for_method("immutable-ceo-star-source")
    monkeypatch.setattr(subject, "preflight_development_binding_v1", lambda *a, **k: None)
    monkeypatch.setattr(
        subject,
        "build_queue_bound_development_runtime_v1",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pre-context failure")),
    )
    with pytest.raises(S11V2ExecutionRunnerError, match="explicit additive incident"):
        _execute_authorized_item(
            adapter=adapter,
            request=request,
            production_root=tmp_path,
            readiness_digest="6" * 64,
        )
    paths = _item_paths(tmp_path, _queue_index(adapter, request.item["queue_item_id"]), request)
    records = sorted(paths["raw"].glob("*.json"))
    assert any(path.name.endswith("attempt-rollback.json") for path in records)
    assert not any(path.name.endswith("kernel-event.json") for path in records)
    assert not any(path.name.endswith("terminal.json") for path in records)


def test_rolled_back_item_cannot_retry_without_additive_authorization(
    tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_execution_runner_v1 as subject

    adapter = QueueV2NativeAdapter()
    request = adapter.first_request_for_method("immutable-ceo-star-source")
    paths = _item_paths(
        tmp_path, _queue_index(adapter, request.item["queue_item_id"]), request
    )
    attempt = make_attempt_id(request.work_request, ordinal=1, nonce="failed")
    runner = ParentNativePersistentRunner.create(
        paths["raw"],
        request=request.work_request,
        cap=request.outcome_cap,
        attempt_id=attempt,
    )
    snapshots = {
        name: str(index) * 64
        for index, name in enumerate(
            (
                "ansatz",
                "parameters",
                "optimizer_inverse_hessian",
                "resources",
                "ledger_transaction",
            ),
            start=1,
        )
    }
    runner.rollback_active_attempt(
        component_digests_before=snapshots,
        component_digests_after=snapshots,
        reason="TEST_ENGINEERING_FAILURE",
    )
    before = tuple(paths["raw"].iterdir())
    monkeypatch.setattr(subject, "preflight_development_binding_v1", lambda *a, **k: None)

    with pytest.raises(S11V2ExecutionRunnerError, match="retry authorization"):
        _execute_authorized_item(
            adapter=adapter,
            request=request,
            production_root=tmp_path,
            readiness_digest="6" * 64,
        )
    assert tuple(paths["raw"].iterdir()) == before


def test_item022_retry_rejects_before_runtime_or_verifier(
    tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_execution_runner_v1 as subject

    adapter = QueueV2NativeAdapter()
    request = adapter.request(subject.ITEM022_QUEUE_ID)
    paths = _item_paths(tmp_path, 22, request)
    runner = ParentNativePersistentRunner.create(
        paths["raw"],
        request=request.work_request,
        cap=request.outcome_cap,
        attempt_id=make_attempt_id(request.work_request, ordinal=1, nonce="incident"),
    )
    snapshots = {
        name: str(index) * 64
        for index, name in enumerate(
            (
                "ansatz",
                "parameters",
                "optimizer_inverse_hessian",
                "resources",
                "ledger_transaction",
            ),
            start=1,
        )
    }
    runner.rollback_active_attempt(
        component_digests_before=snapshots,
        component_digests_after=snapshots,
        reason="S11V2NativePreparationError",
    )
    authorization = {
        "schema": "v5-final.s11-v2-item022-same-item-retry-authorization.v1",
        "observed": {"corrected_relation_aware_upper_bound": 452},
    }
    monkeypatch.setattr(
        subject, "_audit_retry_authorization", lambda *args, **kwargs: authorization
    )
    touched = {"preflight": 0, "build": 0, "prepare": 0}
    monkeypatch.setattr(
        subject,
        "preflight_development_binding_v1",
        lambda *args, **kwargs: touched.__setitem__(
            "preflight", touched["preflight"] + 1
        ),
    )
    monkeypatch.setattr(
        subject,
        "build_queue_bound_development_runtime_v1",
        lambda *args, **kwargs: touched.__setitem__("build", touched["build"] + 1),
    )
    monkeypatch.setattr(
        subject,
        "prepare_initial_executor_v1",
        lambda *args, **kwargs: touched.__setitem__(
            "prepare", touched["prepare"] + 1
        ),
    )
    result = _execute_authorized_item(
        adapter=adapter,
        request=request,
        production_root=tmp_path,
        readiness_digest="6" * 64,
        retry_authorization=authorization,
    )
    assert result["terminal_status"] == "CAP_REJECTED"
    assert result["candidate_energy_evaluations"] == 0
    assert result["raw_work_total"]["optimizer_starts"] == 0
    assert result["raw_work_total"]["statevector_recomputations"] == 0
    assert result["verifier_work_total"]["N_symbolic_checks"] == 0
    assert result["N_dense_expm"] == 0
    assert result["FCI_evaluations"] == 0
    assert result["raw_work_operation_units"] == {"cap-rejection": 0}
    # The immutable source-binding preflight is allowed; molecular runtime
    # construction and Verifier V2 preparation are not.
    assert touched == {"preflight": 1, "build": 0, "prepare": 0}


def test_item023_retry_rejects_before_runtime_or_verifier(
    tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_execution_runner_v1 as subject

    adapter = QueueV2NativeAdapter()
    request = adapter.request(subject.ITEM023_QUEUE_ID)
    paths = _item_paths(tmp_path, 23, request)
    runner = ParentNativePersistentRunner.create(
        paths["raw"],
        request=request.work_request,
        cap=request.outcome_cap,
        attempt_id=make_attempt_id(request.work_request, ordinal=1, nonce="incident"),
    )
    snapshots = {
        name: str(index) * 64
        for index, name in enumerate(
            (
                "ansatz",
                "parameters",
                "optimizer_inverse_hessian",
                "resources",
                "ledger_transaction",
            ),
            start=1,
        )
    }
    runner.rollback_active_attempt(
        component_digests_before=snapshots,
        component_digests_after=snapshots,
        reason="RelationAwareSymbolicPrecheckError",
    )
    authorization = {
        "schema": "v5-final.s11-v2-item023-same-item-retry-authorization.v1",
        "observed": {"corrected_relation_aware_upper_bound": 452},
    }
    monkeypatch.setattr(
        subject, "_audit_retry_authorization", lambda *args, **kwargs: authorization
    )
    touched = {"preflight": 0, "build": 0, "prepare": 0}
    monkeypatch.setattr(
        subject,
        "preflight_development_binding_v1",
        lambda *args, **kwargs: touched.__setitem__(
            "preflight", touched["preflight"] + 1
        ),
    )
    monkeypatch.setattr(
        subject,
        "build_queue_bound_development_runtime_v1",
        lambda *args, **kwargs: touched.__setitem__("build", touched["build"] + 1),
    )
    monkeypatch.setattr(
        subject,
        "prepare_initial_executor_v1",
        lambda *args, **kwargs: touched.__setitem__(
            "prepare", touched["prepare"] + 1
        ),
    )
    result = _execute_authorized_item(
        adapter=adapter,
        request=request,
        production_root=tmp_path,
        readiness_digest="6" * 64,
        retry_authorization=authorization,
    )
    assert result["terminal_status"] == "CAP_REJECTED"
    assert result["candidate_energy_evaluations"] == 0
    assert result["raw_work_total"]["optimizer_starts"] == 0
    assert result["raw_work_total"]["statevector_recomputations"] == 0
    assert result["verifier_work_total"]["N_symbolic_checks"] == 0
    assert result["N_dense_expm"] == 0
    assert result["FCI_evaluations"] == 0
    assert result["raw_work_operation_units"] == {"cap-rejection": 0}
    assert touched == {"preflight": 1, "build": 0, "prepare": 0}


def test_authorized_retry_appends_attempt_without_replacing_rollback(
    tmp_path, monkeypatch
) -> None:
    from v5_final import s11_v2_execution_runner_v1 as subject

    adapter = QueueV2NativeAdapter()
    request = adapter.first_request_for_method("immutable-ceo-star-source")
    paths = _item_paths(
        tmp_path, _queue_index(adapter, request.item["queue_item_id"]), request
    )
    first_attempt = make_attempt_id(request.work_request, ordinal=1, nonce="failed")
    runner = ParentNativePersistentRunner.create(
        paths["raw"],
        request=request.work_request,
        cap=request.outcome_cap,
        attempt_id=first_attempt,
    )
    snapshots = {
        name: str(index) * 64
        for index, name in enumerate(
            (
                "ansatz",
                "parameters",
                "optimizer_inverse_hessian",
                "resources",
                "ledger_transaction",
            ),
            start=1,
        )
    }
    runner.rollback_active_attempt(
        component_digests_before=snapshots,
        component_digests_after=snapshots,
        reason="TEST_ENGINEERING_FAILURE",
    )
    runtime = _Runtime(metadata={})
    context = SimpleNamespace(
        runtime=runtime,
        _actual_algorithm=SimpleNamespace(
            molecule=SimpleNamespace(fci_energy=None, ccsd_energy=None)
        ),
    )

    class Executor:
        def execute(self, service):
            return {"terminal_status": "ACCEPTED", "stopping_reason": "TEST"}

    monkeypatch.setattr(subject, "ITEM002_QUEUE_ID", request.item["queue_item_id"])
    monkeypatch.setattr(subject, "preflight_development_binding_v1", lambda *a, **k: None)
    monkeypatch.setattr(subject, "_audit_retry_authorization", lambda *a, **k: {})
    monkeypatch.setattr(
        subject, "build_queue_bound_development_runtime_v1", lambda *a, **k: context
    )
    monkeypatch.setattr(
        subject,
        "prepare_initial_executor_v1",
        lambda **kwargs: (
            Executor(),
            SimpleNamespace(
                to_audit_dict=lambda: {"outcome_execution_authorized": False}
            ),
        ),
    )
    monkeypatch.setattr(
        subject.services,
        "_component_snapshot_digest",
        lambda runtime: snapshots,
    )
    result = _execute_authorized_item(
        adapter=adapter,
        request=request,
        production_root=tmp_path,
        readiness_digest="6" * 64,
        retry_authorization={"authorization_digest": "7" * 64},
    )
    replay = replay_raw_ledger(
        paths["raw"],
        request=request.work_request,
        cap=request.outcome_cap,
        require_terminal=True,
    )
    assert result["terminal_status"] == "COMPLETED"
    assert replay.attempt_ids[0] == first_attempt
    assert len(replay.attempt_ids) == 2
    assert replay.rolled_back_attempt_ids == (first_attempt,)


def test_runtime_environment_rejects_thread_drift(monkeypatch) -> None:
    monkeypatch.setenv("OMP_NUM_THREADS", "1")
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "2")
    monkeypatch.setenv("MKL_NUM_THREADS", "2")
    with pytest.raises(S11V2ExecutionRunnerError, match="threads_exact"):
        _runtime_environment()


def test_source_binding_rejects_kernel_drift(monkeypatch) -> None:
    adapter = QueueV2NativeAdapter()
    from v5_final import s11_v2_execution_runner_v1 as subject

    monkeypatch.setattr(subject, "_sha", lambda path: "0" * 64)
    with pytest.raises(S11V2ExecutionRunnerError, match="kernel source"):
        _source_binding(adapter)


def test_dispatch_is_exclusive_and_binds_process_environment_and_sources(
    tmp_path, monkeypatch
) -> None:
    adapter = QueueV2NativeAdapter()
    request = adapter.request(adapter.queue["items"][0]["queue_item_id"])
    paths = _item_paths(tmp_path, 0, request)
    monkeypatch.setattr(
        "v5_final.s11_v2_execution_runner_v1._free_bytes", lambda: 50 * 1024**3
    )
    environment = {"frozen_environment_digest": "e" * 64}
    sources = {"kernel_bundle_digest": "k" * 64, "adapter_sha256": "a" * 64}
    first = _write_dispatch(
        adapter=adapter,
        request=request,
        paths=paths,
        queue_index=0,
        readiness_digest="r" * 64,
        environment=environment,
        source_binding=sources,
    )
    second = _write_dispatch(
        adapter=adapter,
        request=request,
        paths=paths,
        queue_index=0,
        readiness_digest="r" * 64,
        environment=environment,
        source_binding=sources,
    )
    assert first == second
    assert first["process"]["pid"] > 0
    assert first["process"]["pgid"] > 0
    assert first["process"]["exact_command"]


def test_terminal_prefix_rejects_work_after_first_gap(tmp_path) -> None:
    adapter = QueueV2NativeAdapter()
    request = adapter.request(adapter.queue["items"][1]["queue_item_id"])
    paths = _item_paths(tmp_path, 1, request)
    paths["dispatch"].parent.mkdir(parents=True)
    paths["dispatch"].write_text("{}")
    with pytest.raises(S11V2ExecutionRunnerError, match="after the first queue gap"):
        _terminal_prefix(
            adapter=adapter,
            production_root=tmp_path,
            readiness_digest="r" * 64,
        )
