"""Fail-closed transport adapter for the frozen S11-v2 queue.

This module does not authorize an outcome kernel.  It binds queue-v2 items to
their immutable scientific predecessor, accepts only Verifier V2 preparation
records, and constructs the exact request/cap identity consumed by the parent
native persistent execution services.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .historical_artifact_audit import (
    artifact_is_immutable_git_blob,
    manifest_matches_artifact_commit,
)
from .parent_native_execution_services import ParentNativeExecutionServices
from .parent_native_persistent_runner import ParentNativePersistentRunner
from .parent_native_work_accounting import (
    OPERATION_COMPONENT,
    ZERO_DELTA_OPERATIONS,
    ParentNativeWorkRequest,
    operation_delta,
    work_cap_digest,
)
from .semantic_contract_v2 import WORK_COMPONENTS, WorkDelta
from .s0_successor import ROOT
from .verifier_v2 import DETERMINISTIC_COUNTER_FIELDS


QUEUE_V2 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v2"
    / "s11-v2-queue-v2.json"
)
QUEUE_V1 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v1"
    / "s11-v2-queue-v1.json"
)
DEVELOPMENT_PLAN_V4 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-queue-v4"
    / "development-plan-v4.json"
)
EXPECTED_QUEUE_DIGEST = (
    "c15a42b6e89fa72876d0293354b2eb52dc505d61386294ef7202280246c0271e"
)
METHOD_IDS = (
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
    "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression",
    "v5-fixed-source-whitelist-no-replenishment",
    "v5-sequential-with-rebuilding",
)
CONTROL_METHODS = {
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
}


class QueueV2NativeAdapterError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QueueV2NativeAdapterError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise QueueV2NativeAdapterError(f"noncanonical artifact: {path}")
    return value


def _embedded_digest(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return isinstance(observed, str) and observed == _digest(body)


def _candidate_ids(binding: Mapping[str, Any]) -> tuple[str, ...]:
    values = []
    for candidate in binding.get("candidate_set", ()):
        identifier = candidate.get("candidate_structural_id", candidate.get("candidate_id"))
        if not isinstance(identifier, str) or not identifier:
            raise QueueV2NativeAdapterError("predecessor candidate identity is incomplete")
        values.append(identifier)
    return tuple(values)


@dataclass(frozen=True)
class QueueV2NativeRequest:
    queue_digest: str
    item: dict[str, Any]
    predecessor_item: dict[str, Any]
    execution_item_v4: dict[str, Any]
    admitted_candidate_ids: tuple[str, ...]
    outcome_cap: WorkDelta

    @property
    def method_id(self) -> str:
        return str(self.item["method_id"])

    @property
    def work_request(self) -> ParentNativeWorkRequest:
        source = self.item["source_identity"]
        return ParentNativeWorkRequest(
            queue_item_id=str(self.item["queue_item_id"]),
            method_id=self.method_id,
            case_id=str(self.item["case_id"]),
            state_preparation_id=str(source["StatePreparationID"]),
            problem_id=str(source["ProblemID"]),
            hamiltonian_digest=str(source["Hamiltonian_digest"]),
            source_checkpoint_digest=str(source["source_checkpoint_digest"]),
            frozen_queue_digest=self.queue_digest,
            work_cap_digest=work_cap_digest(self.outcome_cap),
        )


@dataclass(frozen=True)
class PreparedQueueV2NativeRequest:
    request: QueueV2NativeRequest
    verifier_core_digest: str
    selected_candidate_ids: tuple[str, ...]
    deterministic_work_counters: dict[str, int]
    preparation_status: str

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "schema": "v5-final.s11-v2-native-adapter-preparation.v1",
            "queue_item_id": self.request.item["queue_item_id"],
            "method_id": self.request.method_id,
            "request_id": self.request.work_request.request_id,
            "preparation_engine": "VerifierV2",
            "preparation_status": self.preparation_status,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "deterministic_work_counters": self.deterministic_work_counters,
            "verifier_core_digest": self.verifier_core_digest,
            "candidate_energy_evaluations": 0,
            "optimizer_iterations": 0,
            "FCI_evaluations": 0,
            "outcome_execution_authorized": False,
        }


class QueueV2NativeAdapter:
    def __init__(
        self,
        *,
        queue: Mapping[str, Any] | None = None,
        predecessor: Mapping[str, Any] | None = None,
        execution_plan: Mapping[str, Any] | None = None,
    ) -> None:
        self.queue = dict(queue) if queue is not None else _load(QUEUE_V2)
        self.predecessor = (
            dict(predecessor) if predecessor is not None else _load(QUEUE_V1)
        )
        self.execution_plan = (
            dict(execution_plan)
            if execution_plan is not None
            else _load(DEVELOPMENT_PLAN_V4)
        )
        self._validate_queue()

    def _validate_queue(self) -> None:
        if (
            self.queue.get("schema") != "v5-final.s11-v2-fresh-90-item-queue.v2"
            or not _embedded_digest(self.queue, "queue_digest")
            or self.queue.get("queue_digest") != EXPECTED_QUEUE_DIGEST
            or self.queue.get("frozen_item_count") != 90
            or len(self.queue.get("items", ())) != 90
        ):
            raise QueueV2NativeAdapterError("queue v2 identity is invalid")
        if (
            not _embedded_digest(self.predecessor, "queue_digest")
            or len(self.predecessor.get("items", ())) != 90
            or not _embedded_digest(self.execution_plan, "plan_digest")
            or len(self.execution_plan.get("items", ())) != 90
        ):
            raise QueueV2NativeAdapterError("predecessor execution binding is invalid")
        predecessor_binding = self.queue.get("predecessor_queue", {})
        if (
            predecessor_binding.get("sha256") != _sha(QUEUE_V1)
            or predecessor_binding.get("queue_digest")
            != self.predecessor["queue_digest"]
            or self.queue.get("candidate_energy_evaluations") != 0
            or self.queue.get("optimizer_iterations") != 0
            or self.queue.get("FCI_evaluations") != 0
        ):
            raise QueueV2NativeAdapterError("queue predecessor or outcome boundary differs")
        if set(self.queue.get("complete_counter_schema", ())) != set(
            DETERMINISTIC_COUNTER_FIELDS
        ) | set(WORK_COMPONENTS):
            raise QueueV2NativeAdapterError("complete counter schema differs")
        if self.queue.get("method_order") != list(METHOD_IDS):
            raise QueueV2NativeAdapterError("method order differs")
        source_manifest = [
            {"path": path, "sha256": digest}
            for path, digest in self.queue.get("execution_source_sha256", {}).items()
        ]
        if not manifest_matches_artifact_commit(QUEUE_V2, source_manifest):
            raise QueueV2NativeAdapterError("frozen execution source manifest is invalid")
        if not artifact_is_immutable_git_blob(QUEUE_V2):
            raise QueueV2NativeAdapterError("queue v2 is not an immutable Git blob")
        seen: set[str] = set()
        for item in self.queue["items"]:
            identifier = item.get("queue_item_id")
            body = {key: value for key, value in item.items() if key != "queue_item_id"}
            if (
                identifier != "s11-v2-item-v2:" + _digest(body)
                or identifier in seen
                or item.get("terminal_status") != "NOT_STARTED"
                or item.get("authorization")
                != "NOT_AUTHORIZED_PENDING_P7_V4_ALL_GATES"
            ):
                raise QueueV2NativeAdapterError("queue item identity or status differs")
            seen.add(str(identifier))
            self._resolve(item)

    def _resolve(self, item: Mapping[str, Any]) -> QueueV2NativeRequest:
        predecessor_matches = [
            value
            for value in self.predecessor["items"]
            if value["queue_item_id"] == item.get("predecessor_queue_item_id")
        ]
        scientific_key = (
            item.get("case_id"),
            item.get("work_envelope"),
            item.get("method_id"),
        )
        execution_matches = [
            value
            for value in self.execution_plan["items"]
            if (
                value.get("case_id"),
                value.get("work_envelope"),
                value.get("method_id"),
            )
            == scientific_key
        ]
        if len(predecessor_matches) != 1 or len(execution_matches) != 1:
            raise QueueV2NativeAdapterError("queue item predecessor is absent or duplicated")
        predecessor = predecessor_matches[0]
        execution = execution_matches[0]
        if item.get("predecessor_queue_item_digest") != _digest(predecessor):
            raise QueueV2NativeAdapterError("predecessor item digest differs")
        source = item.get("source_identity", {})
        source_fields = (
            "source_checkpoint_digest",
            "source_checkpoint_sha256",
            "StatePreparationID",
            "ProblemID",
            "Hamiltonian_digest",
        )
        if any(source.get(field) != execution.get(field) for field in source_fields):
            raise QueueV2NativeAdapterError("source identity differs from execution predecessor")
        ids = _candidate_ids(execution["candidate_binding"])
        candidate = item.get("candidate_binding", {})
        if (
            candidate.get("candidate_count") != len(ids)
            or candidate.get("candidate_ids_digest") != _digest(list(ids))
            or candidate.get("candidate_binding_digest")
            != _digest(execution["candidate_binding"])
            or candidate.get("candidate_outcomes_used") is not False
        ):
            raise QueueV2NativeAdapterError("candidate binding differs")
        verifier_cap = item.get("verifier_componentwise_cap", {})
        if item.get("verifier_componentwise_cap_digest") != _digest(verifier_cap):
            raise QueueV2NativeAdapterError("verifier cap digest differs")
        outcome_record = item.get("outcome_work_cap", {})
        outcome = WorkDelta(**dict(outcome_record.get("componentwise_cap", {})))
        if (
            outcome_record.get("cap_digest") != work_cap_digest(outcome)
            or item.get("combined_live_ledger_cap_digest")
            != _digest(item.get("combined_live_ledger_cap"))
            or item.get("combined_all_counter_cap_digest")
            != _digest(item.get("combined_all_counter_cap"))
        ):
            raise QueueV2NativeAdapterError("outcome or combined cap digest differs")
        identity = item.get("method_executor_identity", {})
        if (
            identity.get("method_id") != item.get("method_id")
            or identity.get("shared_method_service_entrypoint")
            != "v5_final.parent_native_execution_services:ParentNativeExecutionServices.execute_prepared"
        ):
            raise QueueV2NativeAdapterError("method-native executor identity differs")
        return QueueV2NativeRequest(
            str(self.queue["queue_digest"]),
            dict(item),
            dict(predecessor),
            dict(execution),
            ids,
            outcome,
        )

    def request(self, queue_item_id: str) -> QueueV2NativeRequest:
        matches = [
            item for item in self.queue["items"]
            if item.get("queue_item_id") == queue_item_id
        ]
        if len(matches) != 1:
            raise QueueV2NativeAdapterError("queue v2 item is absent or duplicated")
        return self._resolve(matches[0])

    def first_request_for_method(self, method_id: str) -> QueueV2NativeRequest:
        if method_id not in METHOD_IDS:
            raise QueueV2NativeAdapterError("unregistered method")
        item = next(value for value in self.queue["items"] if value["method_id"] == method_id)
        return self._resolve(item)

    def consume_verifier_v2(
        self,
        request: QueueV2NativeRequest,
        result: Mapping[str, Any] | None,
    ) -> PreparedQueueV2NativeRequest:
        if request.method_id in CONTROL_METHODS:
            if result is not None or request.admitted_candidate_ids:
                raise QueueV2NativeAdapterError("control method must not invent candidates")
            return PreparedQueueV2NativeRequest(
                request,
                _digest({"method_id": request.method_id, "candidates": []}),
                (),
                {field: 0 for field in DETERMINISTIC_COUNTER_FIELDS},
                "CONTROL_WITHOUT_STRUCTURAL_CANDIDATE",
            )
        if not isinstance(result, Mapping) or not isinstance(result.get("core"), Mapping):
            raise QueueV2NativeAdapterError("Verifier V2 result is absent")
        core = dict(result["core"])
        if core.get("status") != "VERIFIED_READY_AWAITING_OUTCOME_AUTHORIZATION":
            raise QueueV2NativeAdapterError("Verifier V2 preparation is incomplete")
        counters = dict(core.get("deterministic_work_counters", {}))
        if set(counters) != set(DETERMINISTIC_COUNTER_FIELDS):
            raise QueueV2NativeAdapterError("Verifier V2 counter schema differs")
        if (
            counters["N_dense_expm"] != 0
            or counters["energy_evaluations"] != 0
            or counters["optimizer_iterations"] != 0
        ):
            raise QueueV2NativeAdapterError("Verifier V2 crossed the outcome boundary")
        cap = request.item["verifier_componentwise_cap"]
        if any(int(counters[field]) > int(cap[field]) for field in cap):
            raise QueueV2NativeAdapterError("Verifier V2 exceeded its frozen cap")
        selected = tuple(core.get("top_k_freeze", {}).get("selected_candidate_ids", ()))
        if not selected or not set(selected).issubset(request.admitted_candidate_ids):
            raise QueueV2NativeAdapterError("Verifier V2 selected an unbound candidate")
        authorization = core.get("authorization", {})
        if not authorization or not all(
            str(value).startswith("NOT_AUTHORIZED") for value in authorization.values()
        ):
            raise QueueV2NativeAdapterError("Verifier V2 authorization boundary differs")
        return PreparedQueueV2NativeRequest(
            request,
            _digest(core),
            selected,
            {key: int(value) for key, value in counters.items()},
            "VERIFIER_V2_PREPARED_OUTCOME_BLOCKED",
        )

    @staticmethod
    def precheck_outcome_release(
        prepared: PreparedQueueV2NativeRequest,
        *,
        recorder: Any,
        projected: WorkDelta,
    ) -> None:
        """Reject a cap before an executor can receive mutable state."""

        if prepared.to_audit_dict()["outcome_execution_authorized"] is not False:
            raise QueueV2NativeAdapterError("unexpected outcome authorization")
        recorder._precheck(projected, "queue-v2-native-adapter-release")


def audit_adapter_contract() -> dict[str, Any]:
    adapter = QueueV2NativeAdapter()
    requests = {
        method: adapter.first_request_for_method(method) for method in METHOD_IDS
    }
    registered_operations = set(OPERATION_COMPONENT) | set(ZERO_DELTA_OPERATIONS) | {
        "full-gradient-evaluation"
    }
    unknown_rejected = False
    try:
        operation_delta(
            "unregistered-adapter-operation",
            units=1,
            dimension=None,
            outcome="completed",
        )
    except Exception:
        unknown_rejected = True
    checks = {
        "queue_v2_exact": adapter.queue["queue_digest"] == EXPECTED_QUEUE_DIGEST,
        "all_90_requests_resolve": len(
            {adapter.request(item["queue_item_id"]).work_request.request_id for item in adapter.queue["items"]}
        )
        == 90,
        "all_six_methods_same_interface": set(requests) == set(METHOD_IDS)
        and len({type(value) for value in requests.values()}) == 1,
        "request_identity_is_queue_v2": all(
            value.work_request.frozen_queue_digest == EXPECTED_QUEUE_DIGEST
            and value.work_request.queue_item_id.startswith("s11-v2-item-v2:")
            for value in requests.values()
        ),
        "outcome_caps_bound": all(
            value.work_request.work_cap_digest == work_cap_digest(value.outcome_cap)
            for value in requests.values()
        ),
        "verifier_v2_only": adapter.queue["executor_code_binding"]["legacy_dense_verifier_allowed"]
        is False,
        "parent_native_services_bound": ParentNativeExecutionServices.__module__
        == "v5_final.parent_native_execution_services",
        "checkpoint_rollback_retry_bound": all(
            hasattr(ParentNativePersistentRunner, name)
            for name in ("open", "rollback_active_attempt", "start_retry")
        ),
        "operation_registry_nonempty": bool(registered_operations),
        "unregistered_operation_rejected": unknown_rejected,
        "candidate_outcomes_zero": all(
            item["candidate_energy_evaluations"]
            == item["optimizer_iterations"]
            == item["FCI_evaluations"]
            == 0
            for item in adapter.queue["items"]
        ),
    }
    if not all(checks.values()):
        raise QueueV2NativeAdapterError(
            [name for name, passed in checks.items() if not passed]
        )
    return {
        "status": "PASS_QUEUE_V2_NATIVE_ADAPTER_OUTCOME_BLOCKED",
        "checks": checks,
        "queue_digest": EXPECTED_QUEUE_DIGEST,
        "method_count": len(requests),
        "candidate_energy_evaluations": 0,
        "optimizer_iterations": 0,
        "FCI_evaluations": 0,
        "authorization": "NOT_AUTHORIZED_PENDING_P7_V5",
    }
