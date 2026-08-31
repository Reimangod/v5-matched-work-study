"""Frozen-sentinel V4.1 one-shot successor flow."""

from __future__ import annotations
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .common import ExactTransaction, PersistentBoundaryRecorderV2, coefficients_and_indices, construct_bindings, finish_v2, validate_request_v2

METHOD_ID = "v4.1-one-shot-joint-compression"

def execute(request: Mapping[str, Any], *, ledger_path: Path, binding_factory: Callable[..., Any] | None = None) -> dict[str, Any]:
    bound = validate_request_v2(request, METHOD_ID)
    recorder = PersistentBoundaryRecorderV2(bound, __name__, ledger_path)
    bindings = construct_bindings(bound, recorder, binding_factory)
    transaction = ExactTransaction(bound.source["structural_state_digest"])
    representatives: dict[str, dict[str, Any]] = {}
    for candidate in bound.source["structural_catalog"]:
        if candidate.get("structurally_eligible") is not True:
            continue
        key = candidate.get("equivalence_class_id")
        if isinstance(key, str) and (key not in representatives or candidate["candidate_id"] < representatives[key]["candidate_id"]):
            representatives[key] = candidate
    frozen = [representatives[key] for key in sorted(representatives)][:4]
    selected: list[str] = []
    try:
        for candidate in frozen:
            if recorder.register_physical_state(candidate["candidate_id"], candidate["proposed_physical_state_id"]):
                bindings.verify_rewrite(candidate, [], [])
                selected.append(candidate["candidate_id"])
        coefficients, indices = coefficients_and_indices(bound.source)
        bindings.optimize_bfgs(coefficients, indices, initial_inverse_hessian=None, maximum_iterations=int(bound.value.get("maximum_optimizer_iterations", 1)))
    except BaseException as error:
        rollback = transaction.rollback(type(error).__name__)
        return finish_v2(bound, recorder, bindings, selected_candidate_ids=selected, method_evidence={"frozen_sentinel_only": True, "failure": type(error).__name__}, transaction_record={"status": "FAILED_CLOSED"}, rollback_record=rollback)
    transaction.stage({"operation": "v4.1-one-shot", "frozen_sentinels": selected})
    return finish_v2(bound, recorder, bindings, selected_candidate_ids=selected, method_evidence={"frozen_sentinel_only": True, "maximum_candidates": 4, "predictor_used": False, "FCI_used": False}, transaction_record=transaction.commit())
