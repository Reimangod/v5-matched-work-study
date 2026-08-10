"""Physical single-generator deletion successor flow."""

from __future__ import annotations
from collections.abc import Callable, Mapping
import hashlib
from pathlib import Path
from typing import Any

from .common import ExactTransaction, PersistentBoundaryRecorderV2, construct_bindings, finish_v2, validate_request_v2

METHOD_ID = "structural-magnitude-pruning"

def execute(request: Mapping[str, Any], *, ledger_path: Path, binding_factory: Callable[..., Any] | None = None) -> dict[str, Any]:
    bound = validate_request_v2(request, METHOD_ID)
    recorder = PersistentBoundaryRecorderV2(bound, __name__, ledger_path)
    bindings = construct_bindings(bound, recorder, binding_factory)
    transaction = ExactTransaction(bound.source["structural_state_digest"])
    chosen = min(bound.source["generators"], key=lambda item: (item["magnitude_rank"], item["generator_id"]))
    candidate_id = "single-coordinate-delete:" + chosen["generator_id"]
    physical_id = "physical-state-v1:" + hashlib.sha256((bound.source["structural_state_digest"] + "|" + chosen["generator_id"]).encode()).hexdigest()
    recorder.register_physical_state(candidate_id, physical_id)
    remaining = [item for item in bound.source["generators"] if item["generator_id"] != chosen["generator_id"]]
    coefficients = [float(item.get("coefficient", 0.1)) for item in remaining]
    indices = [int(item["pool_index"]) for item in remaining]
    transaction.stage({"physical_state_id": physical_id, "generators": [item["generator_id"] for item in remaining], "coefficient_zeroing_only": False})
    try:
        bindings.verify_rewrite(
            {"candidate_id": candidate_id, "physical_generator_deleted": True}, [], []
        )
        bindings.optimize_bfgs(coefficients, indices, initial_inverse_hessian=None, maximum_iterations=int(bound.value.get("maximum_optimizer_iterations", 1)))
        resources = bindings.resource_recount(coefficients, indices, int(bound.value.get("qubit_count", 4)))
    except BaseException as error:
        rollback = transaction.rollback(type(error).__name__)
        return finish_v2(bound, recorder, bindings, selected_candidate_ids=[candidate_id], method_evidence={"physical_generator_deleted": True, "coefficient_zeroing_only": False, "failure": type(error).__name__}, transaction_record={"status": "FAILED_CLOSED"}, rollback_record=rollback)
    before = bound.source["resources_before"]
    reduction = any(resources[key] < before[key] for key in before)
    return finish_v2(bound, recorder, bindings, selected_candidate_ids=[candidate_id], method_evidence={"physical_generator_deleted": True, "coefficient_zeroing_only": False, "full_circuit_rebuild_and_recount": True, "resource_reduction_success": reduction, "zero_resource_reduction_is_success": False}, transaction_record=transaction.commit())
