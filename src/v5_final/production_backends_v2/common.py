"""Successor request validation, durable boundaries, and exact transactions."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from ..production_backends.common import (
    DRY_RUN_MODE,
    PRODUCTION_MODE,
    MOLECULAR_OPERATIONS,
    STRUCTURAL_OPERATIONS,
    WORK_COMPONENTS,
    CapRejected,
    ExactTransaction,
    ProductionBackendError,
    ValidatedRequest,
    digest,
    validate_request,
)
from ..s0_successor import ROOT
from ..production_kernel_bindings_v2 import (
    FakeBehavioralKernelBindings,
    KernelBindingProtocol,
)


SUCCESSOR_SCHEMA = "v5-final.mb5-2-production-backend-request.v1"
PRODUCTION_AUTHORIZATION_PATH = (
    ROOT / "artifacts/v5-final/pre-calibration/mb7-pre-calibration-go-v2.json"
)
OPERATION_COMPONENT = {
    **STRUCTURAL_OPERATIONS,
    **MOLECULAR_OPERATIONS,
}


def validate_request_v2(value: Mapping[str, Any], method_id: str) -> ValidatedRequest:
    request = dict(value)
    if request.get("schema") != SUCCESSOR_SCHEMA:
        raise ProductionBackendError("MB5.2 successor request schema mismatch")
    supplied = request.get("request_digest")
    body = dict(request)
    body.pop("request_digest", None)
    if supplied != digest(body):
        raise ProductionBackendError("successor request digest mismatch")
    mode = request.get("execution_mode")
    if mode == PRODUCTION_MODE:
        if not PRODUCTION_AUTHORIZATION_PATH.is_file():
            raise ProductionBackendError("MB7 v2 GO artifact is absent")
        authorization = json.loads(PRODUCTION_AUTHORIZATION_PATH.read_text())
        if authorization.get("decision") != "GO_H2_H4_CALIBRATION_ONLY":
            raise ProductionBackendError("MB7 v2 does not authorize H2/H4 calibration")
        expected_sha = hashlib.sha256(PRODUCTION_AUTHORIZATION_PATH.read_bytes()).hexdigest()
        if request.get("authorization_artifact_sha256") != expected_sha:
            raise ProductionBackendError("request is not bound to exact MB7 v2 GO")
    elif mode != DRY_RUN_MODE:
        raise ProductionBackendError("unregistered successor execution mode")

    # Reuse the already audited semantic validator without weakening it.  The
    # temporary view is always dry-run so the historical v1 authorization path
    # can never authorize successor production.
    legacy_view = dict(request)
    legacy_view["schema"] = "v5-final.mb5-1-production-backend-request.v1"
    legacy_view["execution_mode"] = DRY_RUN_MODE
    legacy_view.update(
        energy_blocking_sentinel=True,
        synthetic_structural_fixture=True,
        H2_H4_queue_bound=False,
        development_queue_bound=False,
        production_execution_authorized=False,
    )
    legacy_body = dict(legacy_view)
    legacy_body.pop("request_digest", None)
    legacy_view["request_digest"] = digest(legacy_body)
    validated = validate_request(legacy_view, method_id)
    return replace(
        validated,
        value=request,
        mode=mode,
        request_digest=supplied,
    )


class PersistentBoundaryRecorderV2:
    """Append-only, hash-linked call evidence with pre-call component caps."""

    def __init__(self, request: ValidatedRequest, producer: str, ledger_path: Path) -> None:
        self.request = request
        self.producer = producer
        self.ledger_path = ledger_path
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if self.ledger_path.exists() and self.ledger_path.stat().st_size:
            raise ProductionBackendError("new attempt requires an empty exclusive ledger path")
        self.total = {component: 0 for component in WORK_COMPONENTS}
        self.events: list[dict[str, Any]] = []
        self.seen_physical_states: set[str] = set()
        self._previous_digest: str | None = None

    def _delta(self, operation: str, units: int | None) -> dict[str, int]:
        if operation not in OPERATION_COMPONENT:
            raise ProductionBackendError(f"unregistered kernel operation: {operation}")
        amount = 1 if units is None else units
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ProductionBackendError("operation units must be a nonnegative integer")
        delta = {component: 0 for component in WORK_COMPONENTS}
        delta[OPERATION_COMPONENT[operation]] = amount
        if operation == "full-gradient-evaluation":
            delta["gradient_component_equivalents"] = amount
            delta["gradient_vector_evaluations"] = 1
        return delta

    def _append(self, operation: str, phase: str, outcome: str, delta: Mapping[str, int], evidence: Mapping[str, Any]) -> dict[str, Any]:
        event = {
            "sequence": len(self.events),
            "producer": self.producer,
            "operation": operation,
            "phase": phase,
            "outcome": outcome,
            "previous_event_digest": self._previous_digest,
            "delta": {component: int(delta.get(component, 0)) for component in WORK_COMPONENTS},
            "evidence": dict(evidence),
        }
        event["event_digest"] = digest(event)
        encoded = canonical_json_bytes(event).rstrip(b"\n") + b"\n"
        with self.ledger_path.open("ab") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        self.events.append(event)
        self._previous_digest = event["event_digest"]
        return event

    def _precheck(self, delta: Mapping[str, int]) -> None:
        exceeded = [
            component
            for component in WORK_COMPONENTS
            if self.total[component] + delta.get(component, 0) > self.request.cap[component]
        ]
        if exceeded:
            self._append(
                "cap-precheck",
                "precheck",
                "rejected",
                {},
                {"exceeded_components": exceeded, "call_executed": False},
            )
            raise CapRejected("operation would exceed cap before callable execution")

    def invoke(self, operation: str, thunk: Callable[[], Any], *, units: int | None = None, evidence: Mapping[str, Any] | None = None) -> Any:
        delta = self._delta(operation, units)
        self._precheck(delta)
        detail = dict(evidence or {})
        self._append(operation, "attempt-start", "started", {}, detail)
        try:
            value = thunk()
        except BaseException as error:
            for component in WORK_COMPONENTS:
                self.total[component] += delta[component]
            self._append(
                operation,
                "attempt-terminal",
                "failed",
                delta,
                {**detail, "exception_type": type(error).__name__, "exception_message": str(error)},
            )
            raise
        for component in WORK_COMPONENTS:
            self.total[component] += delta[component]
        self._append(operation, "attempt-terminal", "completed", delta, detail)
        return value

    def register_physical_state(self, candidate_id: str, proposed_physical_state_id: str) -> bool:
        if proposed_physical_state_id in self.seen_physical_states:
            self._append(
                "canonical-state-duplicate",
                "evidence",
                "completed",
                {},
                {"candidate_id": candidate_id, "deduplication_key": proposed_physical_state_id},
            )
            return False
        delta = {component: 0 for component in WORK_COMPONENTS}
        delta["search_states"] = 1
        self._precheck(delta)
        self.seen_physical_states.add(proposed_physical_state_id)
        for component in WORK_COMPONENTS:
            self.total[component] += delta[component]
        self._append(
            "unique-search-state-expansion",
            "attempt-terminal",
            "completed",
            delta,
            {"candidate_id": candidate_id, "deduplication_key": proposed_physical_state_id},
        )
        return True


def coefficients_and_indices(source: Mapping[str, Any]) -> tuple[list[float], list[int]]:
    generators = list(source["generators"])
    coefficients = [float(item.get("coefficient", 0.1)) for item in generators]
    indices = [int(item["pool_index"]) for item in generators]
    return coefficients, indices


def construct_bindings(
    request: ValidatedRequest,
    recorder: PersistentBoundaryRecorderV2,
    factory: Callable[[PersistentBoundaryRecorderV2, ValidatedRequest], KernelBindingProtocol]
    | None,
) -> KernelBindingProtocol:
    if factory is None:
        if request.mode != DRY_RUN_MODE:
            raise ProductionBackendError(
                "production execution requires dependency-injected actual bindings"
            )
        binding: KernelBindingProtocol = FakeBehavioralKernelBindings(
            recorder=recorder,
            catalog=request.source["structural_catalog"],
            fail_operation=request.value.get("fake_fail_operation"),
        )
    else:
        binding = factory(recorder, request)
    if not isinstance(binding, KernelBindingProtocol):
        raise ProductionBackendError("binding does not implement KernelBindingProtocol")
    if request.mode == PRODUCTION_MODE and binding.binding_kind != "PINNED_ACTUAL_CEO_DVG_KERNELS":
        raise ProductionBackendError("production mode rejects fake or proxy bindings")
    return binding


def finish_v2(
    request: ValidatedRequest,
    recorder: PersistentBoundaryRecorderV2,
    bindings: Any,
    *,
    selected_candidate_ids: Sequence[str],
    method_evidence: Mapping[str, Any],
    transaction_record: Mapping[str, Any],
    rollback_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    synthetic = bindings.binding_kind == "OUTCOME_FREE_BEHAVIORAL_FAKE"
    result = {
        "schema": "v5-final.mb5-2-production-backend-result.v1",
        "status": "OUTCOME_FREE_BEHAVIORAL_TRACE_COMPLETE" if synthetic else "PRODUCTION_ATTEMPT_TERMINAL",
        "canonical_method_id": request.method_id,
        "execution_mode": request.mode,
        "binding_kind": bindings.binding_kind,
        "request_digest": request.request_digest,
        "attempt_index": request.value["attempt_index"],
        "previous_attempt_digest": request.value["previous_attempt_digest"],
        "selected_candidate_ids": list(selected_candidate_ids),
        "raw_boundary_events": recorder.events,
        "raw_work_total": recorder.total,
        "binding_runtime_trace": bindings.trace,
        "unique_physical_state_count": len(recorder.seen_physical_states),
        "method_evidence": dict(method_evidence),
        "transaction_record": dict(transaction_record),
        "rollback_record": None if rollback_record is None else dict(rollback_record),
        "scientific_candidate_energy_evaluations": 0 if synthetic else recorder.total["energy_evaluations"],
        "synthetic_behavioral_work_only": synthetic,
        "H2_H4_queue_touched": False,
        "development_queue_touched": False,
        "performance_evidence": False if synthetic else None,
        "claim_boundary": "runtime binding behavior only; fake values are not molecular outcomes" if synthetic else "production result requires downstream queue-bound completeness audit",
    }
    result["result_digest"] = digest(result)
    return result


__all__ = [
    "DRY_RUN_MODE",
    "PRODUCTION_MODE",
    "ExactTransaction",
    "PersistentBoundaryRecorderV2",
    "ProductionBackendError",
    "coefficients_and_indices",
    "construct_bindings",
    "digest",
    "finish_v2",
    "validate_request_v2",
]
