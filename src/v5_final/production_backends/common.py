"""Shared identity, cap, ledger, transaction, and authorization infrastructure.

No candidate construction, ranking, selection, pruning, optimizer lifecycle, or
acceptance algorithm lives here.  Those semantics remain in six separate
method modules.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from ..mb4_2_owner_protocol_freeze import (
    CANONICAL_METHOD_IDS,
    LEGACY_QUEUE_METHOD_IDS,
    OUTPUT as OWNER_FREEZE_OUTPUT,
)
from ..s0_successor import ROOT


DRY_RUN_MODE = "MB5_1_OUTCOME_FREE_PRODUCTION_BINDING_DRY_RUN"
PRODUCTION_MODE = "PRODUCTION_MOLECULAR_EXECUTION"
WORK_COMPONENTS = (
    "energy_evaluations",
    "gradient_vector_evaluations",
    "gradient_component_equivalents",
    "hvp_evaluations",
    "optimizer_starts",
    "optimizer_iterations",
    "resource_recounts",
    "candidate_generations",
    "search_states",
    "rewrite_verifications",
    "statevector_recomputations",
)
STRUCTURAL_OPERATIONS = {
    "candidate-generation": "candidate_generations",
    "unique-search-state-expansion": "search_states",
    "rewrite-verification": "rewrite_verifications",
    "full-physical-resource-recount": "resource_recounts",
}
MOLECULAR_OPERATIONS = {
    "source-energy-evaluation": "energy_evaluations",
    "candidate-energy-evaluation": "energy_evaluations",
    "full-gradient-evaluation": "gradient_vector_evaluations",
    "gradient-component-evaluation": "gradient_component_equivalents",
    "hessian-vector-product": "hvp_evaluations",
    "optimizer-start": "optimizer_starts",
    "optimizer-iteration": "optimizer_iterations",
    "statevector-recomputation": "statevector_recomputations",
}
PRODUCTION_AUTHORIZATION_PATH = (
    ROOT / "artifacts/v5-final/pre-calibration/mb7-production-binding-go-v1.json"
)


class ProductionBackendError(RuntimeError):
    pass


class OutcomeLeakageBlocked(ProductionBackendError):
    pass


class CapRejected(ProductionBackendError):
    pass


class ProductionNotAuthorized(ProductionBackendError):
    pass


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ProductionBackendError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _validate_authorization(value: Mapping[str, Any]) -> None:
    if not PRODUCTION_AUTHORIZATION_PATH.is_file():
        raise ProductionNotAuthorized(
            "MB7 production-binding GO artifact does not exist; molecular kernels remain closed"
        )
    artifact = json.loads(PRODUCTION_AUTHORIZATION_PATH.read_text())
    if artifact.get("decision") != "GO_H2_H4_CALIBRATION_ONLY":
        raise ProductionNotAuthorized("MB7 artifact does not authorize H2/H4 calibration")
    if value.get("authorization_artifact_sha256") != hashlib.sha256(
        PRODUCTION_AUTHORIZATION_PATH.read_bytes()
    ).hexdigest():
        raise ProductionNotAuthorized("request does not bind the exact MB7 authorization artifact")


def _validate_source(value: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(value)
    require_digest(source.get("source_checkpoint_digest"), "source checkpoint")
    require_digest(source.get("structural_state_digest"), "structural state")
    generators = source.get("generators")
    if not isinstance(generators, list) or not generators:
        raise ProductionBackendError("source generators must be a nonempty list")
    generator_ids = [record.get("generator_id") for record in generators]
    if len(generator_ids) != len(set(generator_ids)) or any(
        not isinstance(item, str) or not item for item in generator_ids
    ):
        raise ProductionBackendError("source generator IDs must be unique and nonempty")
    for record in generators:
        if not isinstance(record.get("pool_index"), int):
            raise ProductionBackendError("each source generator needs an integer pool index")
        if not isinstance(record.get("magnitude_rank"), int) or record["magnitude_rank"] < 0:
            raise ProductionBackendError("magnitude ranks must be exact nonnegative integers")
    candidates = source.get("structural_catalog")
    if not isinstance(candidates, list):
        raise ProductionBackendError("source structural catalog must be a list")
    candidate_ids = [record.get("candidate_id") for record in candidates]
    if len(candidate_ids) != len(set(candidate_ids)) or any(
        not isinstance(item, str) or not item for item in candidate_ids
    ):
        raise ProductionBackendError("candidate IDs must be unique and nonempty")
    physical_ids = [record.get("proposed_physical_state_id") for record in candidates]
    if any(
        not isinstance(item, str) or not item.startswith("physical-state-v1:")
        for item in physical_ids
    ):
        raise ProductionBackendError("every candidate needs a canonical physical-state identity")
    resource_fields = (
        "cnot_count",
        "cnot_depth",
        "total_depth",
        "parameter_count",
        "logical_block_count",
    )
    for field_name in ("resources_before", "resources_after_single_deletion"):
        resources = source.get(field_name)
        if not isinstance(resources, Mapping) or set(resources) != set(resource_fields):
            raise ProductionBackendError(f"{field_name} is incomplete")
        if any(
            isinstance(resources[field], bool)
            or not isinstance(resources[field], int)
            or resources[field] < 0
            for field in resource_fields
        ):
            raise ProductionBackendError("resource records must contain nonnegative integers")
    canonical_json_bytes(source)
    return source


@dataclass(frozen=True)
class ValidatedRequest:
    value: dict[str, Any]
    method_id: str
    mode: str
    source: dict[str, Any]
    cap: dict[str, int]
    request_digest: str

    @property
    def is_dry_run(self) -> bool:
        return self.mode == DRY_RUN_MODE


def validate_request(value: Mapping[str, Any], method_id: str) -> ValidatedRequest:
    request = dict(value)
    if request.get("schema") != "v5-final.mb5-1-production-backend-request.v1":
        raise ProductionBackendError("MB5.1 request schema mismatch")
    if method_id not in CANONICAL_METHOD_IDS or request.get("canonical_method_id") != method_id:
        raise ProductionBackendError("request was routed to the wrong production backend")
    if request.get("legacy_queue_method_id") != LEGACY_QUEUE_METHOD_IDS[method_id]:
        raise ProductionBackendError("legacy queue method alias is incorrect")
    mode = request.get("execution_mode")
    if mode not in {DRY_RUN_MODE, PRODUCTION_MODE}:
        raise ProductionBackendError("execution mode is not registered")
    freeze = json.loads(OWNER_FREEZE_OUTPUT.read_text())
    if request.get("owner_freeze_digest") != freeze["freeze_digest"]:
        raise ProductionBackendError("request does not bind the committed owner freeze")
    if request.get("protocol_digest") != freeze["protocol_digests"][method_id]:
        raise ProductionBackendError("request protocol differs from the frozen method protocol")
    identity = request.get("identity")
    if not isinstance(identity, Mapping):
        raise ProductionBackendError("production identity is required")
    for field in (
        "StatePreparationID_digest",
        "ProblemID_digest",
        "Hamiltonian_digest",
        "environment_digest",
        "dependency_lock_sha256",
    ):
        require_digest(identity.get(field), field)
    source = _validate_source(request.get("source", {}))
    if any(
        source.get(field) != identity[field]
        for field in (
            "StatePreparationID_digest",
            "ProblemID_digest",
            "Hamiltonian_digest",
        )
    ):
        raise ProductionBackendError("source/Problem/Hamiltonian identity mismatch")
    cap = request.get("componentwise_work_cap")
    if not isinstance(cap, Mapping) or set(cap) != set(WORK_COMPONENTS):
        raise ProductionBackendError("componentwise work cap is incomplete")
    cap_value: dict[str, int] = {}
    for component in WORK_COMPONENTS:
        amount = cap[component]
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ProductionBackendError("componentwise work caps must be nonnegative integers")
        cap_value[component] = amount
    if request.get("work_cap_digest") != digest(cap_value):
        raise ProductionBackendError("componentwise work cap digest mismatch")
    for field in ("optimizer_policy_digest", "acceptance_policy_digest"):
        require_digest(request.get(field), field)
    if request.get("candidate_energy_evaluations_before") != 0:
        raise ProductionBackendError("candidate energy count must be zero before MB5.1 dry-run")
    attempt_index = request.get("attempt_index")
    if isinstance(attempt_index, bool) or not isinstance(attempt_index, int) or attempt_index < 0:
        raise ProductionBackendError("attempt index must be a nonnegative integer")
    previous_attempt = request.get("previous_attempt_digest")
    retry_reason = request.get("retry_reason")
    if attempt_index == 0:
        if previous_attempt is not None or retry_reason is not None:
            raise ProductionBackendError("initial attempt cannot claim retry provenance")
    else:
        require_digest(previous_attempt, "previous attempt")
        if not isinstance(retry_reason, str) or not retry_reason:
            raise ProductionBackendError("linked retry requires a nonempty reason")
    if mode == DRY_RUN_MODE:
        required = {
            "energy_blocking_sentinel": True,
            "synthetic_structural_fixture": True,
            "H2_H4_queue_bound": False,
            "development_queue_bound": False,
            "production_execution_authorized": False,
        }
        if any(request.get(key) is not expected for key, expected in required.items()):
            raise ProductionBackendError("outcome-free dry-run boundary is incomplete")
    else:
        _validate_authorization(request)
    supplied_digest = request.get("request_digest")
    body = dict(request)
    body.pop("request_digest", None)
    expected_digest = digest(body)
    if supplied_digest != expected_digest:
        raise ProductionBackendError("request digest mismatch")
    return ValidatedRequest(request, method_id, mode, source, cap_value, expected_digest)


class BoundaryRecorder:
    """Precheck component caps at the exact call boundary and retain raw events."""

    def __init__(self, request: ValidatedRequest, producer: str) -> None:
        self.request = request
        self.producer = producer
        self.total = {component: 0 for component in WORK_COMPONENTS}
        self.events: list[dict[str, Any]] = []
        self.seen_physical_states: set[str] = set()

    def _precheck(self, delta: Mapping[str, int]) -> None:
        if any(self.total[key] + delta.get(key, 0) > self.request.cap[key] for key in WORK_COMPONENTS):
            raise CapRejected("operation would exceed the componentwise work cap before execution")

    def _append(
        self,
        operation: str,
        delta: Mapping[str, int],
        evidence: Mapping[str, Any],
        *,
        outcome: str = "completed",
    ) -> None:
        self._precheck(delta)
        for component in WORK_COMPONENTS:
            self.total[component] += delta.get(component, 0)
        event = {
            "sequence": len(self.events),
            "producer": self.producer,
            "operation": operation,
            "outcome": outcome,
            "delta": {component: delta.get(component, 0) for component in WORK_COMPONENTS},
            "evidence": dict(evidence),
        }
        event["event_digest"] = digest(event)
        self.events.append(event)

    def evidence(self, operation: str, evidence: Mapping[str, Any]) -> None:
        self._append(operation, {}, evidence)

    def structural(
        self, operation: str, evidence: Mapping[str, Any], *, units: int = 1
    ) -> None:
        if operation not in STRUCTURAL_OPERATIONS or units <= 0:
            raise ProductionBackendError("unregistered structural kernel boundary")
        self._append(operation, {STRUCTURAL_OPERATIONS[operation]: units}, evidence)

    def register_physical_state(
        self, candidate_id: str, proposed_physical_state_id: str
    ) -> bool:
        self.structural(
            "candidate-generation",
            {
                "candidate_id": candidate_id,
                "proposed_physical_state_id": proposed_physical_state_id,
            },
        )
        if proposed_physical_state_id in self.seen_physical_states:
            self.evidence(
                "canonical-state-duplicate",
                {
                    "candidate_id": candidate_id,
                    "deduplication_key": proposed_physical_state_id,
                },
            )
            return False
        self._precheck({"search_states": 1})
        self.seen_physical_states.add(proposed_physical_state_id)
        self.structural(
            "unique-search-state-expansion",
            {
                "candidate_id": candidate_id,
                "deduplication_key": proposed_physical_state_id,
            },
        )
        return True

    def molecular(self, operation: str) -> None:
        if operation not in MOLECULAR_OPERATIONS:
            raise ProductionBackendError("unregistered molecular kernel boundary")
        if self.request.is_dry_run:
            raise OutcomeLeakageBlocked(
                f"blocking sentinel refused molecular kernel boundary: {operation}"
            )
        raise ProductionBackendError(
            "production kernel calls require PinnedCEOProductionKernelBindings at MB8-CAL"
        )


class ExactTransaction:
    def __init__(self, source_digest: str) -> None:
        self.source_digest = require_digest(source_digest, "transaction source")
        self.working_digest = self.source_digest
        self.closed = False

    def stage(self, payload: Mapping[str, Any]) -> None:
        if self.closed:
            raise ProductionBackendError("closed transaction cannot stage")
        self.working_digest = digest(dict(payload))

    def rollback(self, reason: str) -> dict[str, Any]:
        if self.closed:
            raise ProductionBackendError("transaction already closed")
        before = self.source_digest
        self.working_digest = self.source_digest
        self.closed = True
        return {
            "status": "ROLLED_BACK_EXACTLY",
            "reason": reason,
            "source_digest_before": before,
            "source_digest_after": self.working_digest,
            "exact": before == self.working_digest,
        }

    def commit(self) -> dict[str, Any]:
        if self.closed:
            raise ProductionBackendError("transaction already closed")
        self.closed = True
        return {
            "status": "COMMITTED",
            "source_digest_before": self.source_digest,
            "child_digest": self.working_digest,
        }


def finish(
    request: ValidatedRequest,
    recorder: BoundaryRecorder,
    *,
    selected_candidate_ids: Sequence[str],
    method_evidence: Mapping[str, Any],
    transaction_record: Mapping[str, Any],
    rollback_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if any(recorder.total[component] for component in (
        "energy_evaluations",
        "gradient_vector_evaluations",
        "gradient_component_equivalents",
        "hvp_evaluations",
        "optimizer_starts",
        "optimizer_iterations",
        "statevector_recomputations",
    )):
        raise OutcomeLeakageBlocked("MB5.1 result contains molecular work")
    result = {
        "schema": "v5-final.mb5-1-production-backend-dry-run-result.v1",
        "status": "OUTCOME_FREE_PRODUCTION_BINDING_DRY_RUN_COMPLETE",
        "canonical_method_id": request.method_id,
        "legacy_queue_method_id": LEGACY_QUEUE_METHOD_IDS[request.method_id],
        "execution_mode": request.mode,
        "request_digest": request.request_digest,
        "attempt_index": request.value["attempt_index"],
        "previous_attempt_digest": request.value["previous_attempt_digest"],
        "selected_candidate_ids": list(selected_candidate_ids),
        "raw_boundary_events": recorder.events,
        "raw_work_total": recorder.total,
        "unique_physical_state_count": len(recorder.seen_physical_states),
        "method_evidence": dict(method_evidence),
        "transaction_record": dict(transaction_record),
        "rollback_record": None if rollback_record is None else dict(rollback_record),
        "candidate_energy_evaluations": 0,
        "molecular_kernel_calls": 0,
        "H2_H4_queue_touched": False,
        "development_queue_touched": False,
        "performance_evidence": False,
        "claim_boundary": (
            "production call graph and method-native structural control flow only; no molecular outcome"
        ),
    }
    result["result_digest"] = digest(result)
    return result
