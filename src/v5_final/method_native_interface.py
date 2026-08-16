"""Shared recording interface for distinct method-native molecular executors.

This module standardizes identity and serialization only.  It deliberately
contains no candidate construction, selection, optimization, or acceptance
algorithm.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Mapping, Sequence

from v5_matched_work.atomic_artifacts import canonical_json_bytes


METHOD_IDS = (
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
    "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression",
    "v5-sequential-without-rebuilding",
    "v5-sequential-with-rebuilding",
)
TERMINAL_STATUSES = {
    "INFRASTRUCTURE_ONLY",
    "SOURCE_RECORDED",
    "COMPLETED",
    "REJECTED",
    "CAP_EXHAUSTED",
    "FAILED_ROLLED_BACK",
}
EXECUTED_STATUSES = TERMINAL_STATUSES - {"INFRASTRUCTURE_ONLY"}


class MethodNativeInterfaceError(ValueError):
    pass


def _content_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + ":" + hashlib.sha256(canonical_json_bytes(dict(payload))).hexdigest()


def _require_digest(value: str, label: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise MethodNativeInterfaceError(f"{label} must be a lowercase SHA-256 digest")


def _require_content_id(value: str, prefix: str, label: str) -> None:
    if not value.startswith(prefix + ":"):
        raise MethodNativeInterfaceError(f"{label} has the wrong identity namespace")
    _require_digest(value.split(":", 1)[1], label)


def _require_git_oid(value: str, label: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise MethodNativeInterfaceError(f"{label} must be a lowercase 40-hex Git object ID")


def _mapping(value: Mapping[str, Any], label: str, *, nonempty: bool = True) -> dict[str, Any]:
    result = dict(value)
    if nonempty and not result:
        raise MethodNativeInterfaceError(f"{label} cannot be empty")
    try:
        canonical_json_bytes(result)
    except (TypeError, ValueError) as error:
        raise MethodNativeInterfaceError(f"{label} is not canonical JSON data") from error
    return result


@dataclass(frozen=True)
class MethodNativeRequest:
    queue_item_id: str
    method_id: str
    case_id: str
    state_preparation_id: str
    problem_id: str
    source_checkpoint_digest: str
    hamiltonian_digest: str
    frozen_queue_digest: str
    work_envelope: str
    work_cap_digest: str
    optimizer_policy_digest: str
    acceptance_policy_digest: str
    protocol_digest: str
    rng_identity: Mapping[str, Any]
    environment_identity: Mapping[str, Any]
    environment_digest: str

    def __post_init__(self) -> None:
        if not self.queue_item_id or not self.case_id:
            raise MethodNativeInterfaceError("queue item and case identity are required")
        if self.method_id not in METHOD_IDS:
            raise MethodNativeInterfaceError("unregistered method ID")
        _require_content_id(self.state_preparation_id, "state-v1", "StatePreparationID")
        _require_content_id(self.problem_id, "problem-v1", "ProblemID")
        for value, label in (
            (self.source_checkpoint_digest, "source checkpoint"),
            (self.hamiltonian_digest, "Hamiltonian"),
            (self.frozen_queue_digest, "frozen queue"),
            (self.work_cap_digest, "work cap"),
            (self.optimizer_policy_digest, "optimizer policy"),
            (self.acceptance_policy_digest, "acceptance policy"),
            (self.protocol_digest, "protocol"),
            (self.environment_digest, "environment"),
        ):
            _require_digest(value, label)
        if not self.work_envelope:
            raise MethodNativeInterfaceError("work envelope is required")
        _mapping(self.rng_identity, "RNG identity")
        _mapping(self.environment_identity, "environment identity")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "v5-final.method-native-request.v1",
            "queue_item_id": self.queue_item_id,
            "method_id": self.method_id,
            "case_id": self.case_id,
            "StatePreparationID": self.state_preparation_id,
            "ProblemID": self.problem_id,
            "source_checkpoint_digest": self.source_checkpoint_digest,
            "Hamiltonian_digest": self.hamiltonian_digest,
            "frozen_queue_digest": self.frozen_queue_digest,
            "work_envelope": self.work_envelope,
            "work_cap_digest": self.work_cap_digest,
            "optimizer_policy_digest": self.optimizer_policy_digest,
            "acceptance_policy_digest": self.acceptance_policy_digest,
            "protocol_digest": self.protocol_digest,
            "rng_identity": dict(self.rng_identity),
            "environment_identity": dict(self.environment_identity),
            "environment_digest": self.environment_digest,
        }

    @property
    def request_id(self) -> str:
        return _content_id("method-native-request-v1", self.payload())

    def to_dict(self) -> dict[str, Any]:
        return self.payload() | {"request_id": self.request_id}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MethodNativeRequest":
        if value.get("schema") != "v5-final.method-native-request.v1":
            raise MethodNativeInterfaceError("method-native request schema mismatch")
        request = cls(
            queue_item_id=value["queue_item_id"],
            method_id=value["method_id"],
            case_id=value["case_id"],
            state_preparation_id=value["StatePreparationID"],
            problem_id=value["ProblemID"],
            source_checkpoint_digest=value["source_checkpoint_digest"],
            hamiltonian_digest=value["Hamiltonian_digest"],
            frozen_queue_digest=value["frozen_queue_digest"],
            work_envelope=value["work_envelope"],
            work_cap_digest=value["work_cap_digest"],
            optimizer_policy_digest=value["optimizer_policy_digest"],
            acceptance_policy_digest=value["acceptance_policy_digest"],
            protocol_digest=value["protocol_digest"],
            rng_identity=dict(value["rng_identity"]),
            environment_identity=dict(value["environment_identity"]),
            environment_digest=value["environment_digest"],
        )
        if request.to_dict() != dict(value):
            raise MethodNativeInterfaceError("request digest or canonical content mismatch")
        return request


@dataclass(frozen=True)
class NativeExecutorIdentity:
    method_id: str
    classification: str
    entrypoint: str
    implementation_sha256: str
    parent_repository_commit: str
    ceo_adapt_vqe_commit: str

    def __post_init__(self) -> None:
        if self.method_id not in METHOD_IDS or not self.classification or ":" not in self.entrypoint:
            raise MethodNativeInterfaceError("executor method, classification, and entrypoint are required")
        _require_digest(self.implementation_sha256, "executor implementation")
        _require_git_oid(self.parent_repository_commit, "parent repository commit")
        _require_git_oid(self.ceo_adapt_vqe_commit, "CEO* commit")

    def payload(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "classification": self.classification,
            "entrypoint": self.entrypoint,
            "implementation_sha256": self.implementation_sha256,
            "parent_repository_commit": self.parent_repository_commit,
            "ceo_adapt_vqe_commit": self.ceo_adapt_vqe_commit,
        }

    @property
    def executor_id(self) -> str:
        return _content_id("method-native-executor-v1", self.payload())

    def to_dict(self) -> dict[str, Any]:
        return self.payload() | {"executor_id": self.executor_id}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "NativeExecutorIdentity":
        executor = cls(**{key: value[key] for key in (
            "method_id", "classification", "entrypoint", "implementation_sha256",
            "parent_repository_commit", "ceo_adapt_vqe_commit",
        )})
        if executor.to_dict() != dict(value):
            raise MethodNativeInterfaceError("executor digest or canonical content mismatch")
        return executor


@dataclass(frozen=True)
class MethodNativeResult:
    request_id: str
    terminal_status: str
    executor: NativeExecutorIdentity
    parent_state_id: str
    child_state_id: str | None
    raw_semantic_events: tuple[Mapping[str, Any], ...]
    work_ledger: Mapping[str, Any]
    resource_recount: Mapping[str, Any]
    transaction_record: Mapping[str, Any]
    failure_rollback_record: Mapping[str, Any] | None
    completeness_manifest: Mapping[str, Any]
    evidence_class: str

    def __post_init__(self) -> None:
        _require_content_id(self.request_id, "method-native-request-v1", "method-native request")
        if self.terminal_status not in TERMINAL_STATUSES:
            raise MethodNativeInterfaceError("unregistered terminal status")
        _require_content_id(self.parent_state_id, "state-v1", "parent state")
        if self.child_state_id is not None:
            _require_content_id(self.child_state_id, "state-v1", "child state")
        if not self.evidence_class:
            raise MethodNativeInterfaceError("evidence class is required")
        events = tuple(_mapping(event, "raw semantic event") for event in self.raw_semantic_events)
        sequences = [event.get("sequence") for event in events]
        if sequences and sequences != list(range(sequences[0], sequences[0] + len(sequences))):
            raise MethodNativeInterfaceError("raw semantic event sequence is not contiguous")
        work = _mapping(self.work_ledger, "work ledger")
        resources = _mapping(self.resource_recount, "resource recount")
        transaction = _mapping(self.transaction_record, "transaction record")
        completeness = _mapping(self.completeness_manifest, "completeness manifest")
        if not isinstance(completeness.get("complete"), bool):
            raise MethodNativeInterfaceError("completeness manifest needs a boolean complete field")
        if self.failure_rollback_record is not None:
            _mapping(self.failure_rollback_record, "failure/rollback record")
        if self.terminal_status == "INFRASTRUCTURE_ONLY":
            if events or completeness["complete"]:
                raise MethodNativeInterfaceError("infrastructure-only records cannot contain events or be complete")
            if self.child_state_id is not None:
                raise MethodNativeInterfaceError("infrastructure-only records cannot claim a child state")
        elif not events:
            raise MethodNativeInterfaceError("executed terminal records require raw semantic events")
        if self.terminal_status == "FAILED_ROLLED_BACK" and self.failure_rollback_record is None:
            raise MethodNativeInterfaceError("failed rollback status requires rollback evidence")
        if self.executor.method_id not in METHOD_IDS:
            raise MethodNativeInterfaceError("result executor method is invalid")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "v5-final.method-native-result.v1",
            "request_id": self.request_id,
            "terminal_status": self.terminal_status,
            "executor": self.executor.to_dict(),
            "parent_state_id": self.parent_state_id,
            "child_state_id": self.child_state_id,
            "raw_semantic_events": [dict(event) for event in self.raw_semantic_events],
            "work_ledger": dict(self.work_ledger),
            "resource_recount": dict(self.resource_recount),
            "transaction_record": dict(self.transaction_record),
            "failure_rollback_record": None if self.failure_rollback_record is None else dict(self.failure_rollback_record),
            "completeness_manifest": dict(self.completeness_manifest),
            "evidence_class": self.evidence_class,
        }

    @property
    def result_id(self) -> str:
        return _content_id("method-native-result-v1", self.payload())

    def to_dict(self) -> dict[str, Any]:
        return self.payload() | {"result_id": self.result_id}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MethodNativeResult":
        if value.get("schema") != "v5-final.method-native-result.v1":
            raise MethodNativeInterfaceError("method-native result schema mismatch")
        result = cls(
            request_id=value["request_id"],
            terminal_status=value["terminal_status"],
            executor=NativeExecutorIdentity.from_dict(value["executor"]),
            parent_state_id=value["parent_state_id"],
            child_state_id=value.get("child_state_id"),
            raw_semantic_events=tuple(dict(event) for event in value["raw_semantic_events"]),
            work_ledger=dict(value["work_ledger"]),
            resource_recount=dict(value["resource_recount"]),
            transaction_record=dict(value["transaction_record"]),
            failure_rollback_record=(
                None if value.get("failure_rollback_record") is None
                else dict(value["failure_rollback_record"])
            ),
            completeness_manifest=dict(value["completeness_manifest"]),
            evidence_class=value["evidence_class"],
        )
        if result.to_dict() != dict(value):
            raise MethodNativeInterfaceError("result digest or canonical content mismatch")
        return result


def bind_result_to_request(result: MethodNativeResult, request: MethodNativeRequest) -> None:
    if result.request_id != request.request_id:
        raise MethodNativeInterfaceError("result is not bound to its request")
    if result.executor.method_id != request.method_id:
        raise MethodNativeInterfaceError("executor method differs from request method")
    for event in result.raw_semantic_events:
        required = {
            "queue_item_id": request.queue_item_id,
            "method_id": request.method_id,
            "case_id": request.case_id,
            "state_preparation_id": request.state_preparation_id,
            "problem_id": request.problem_id,
        }
        if any(event.get(key) != expected for key, expected in required.items()):
            raise MethodNativeInterfaceError("raw event identity differs from its request")


def protocol() -> dict[str, Any]:
    result = {
        "schema": "v5-final.method-native-interface-protocol.v1",
        "purpose": "shared identity and recording format only; no shared algorithm",
        "method_ids": list(METHOD_IDS),
        "request_identity": [
            "queue item", "method", "case", "StatePreparationID", "ProblemID",
            "source checkpoint", "Hamiltonian", "frozen queue", "work cap",
            "optimizer policy", "acceptance policy", "RNG", "environment",
        ],
        "result_records": [
            "terminal status", "exact executor identity", "parent and child state",
            "raw semantic events", "work ledger", "resource recount", "transaction",
            "failure rollback", "completeness manifest",
        ],
        "algorithm_fields": [],
        "candidate_execution": "NOT_AUTHORIZED_BY_THIS_PROTOCOL",
        "claim_boundary": "serialization and identity infrastructure only; no molecular or performance evidence",
    }
    result["protocol_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return result
