"""V5 fixed-source-whitelist/no-replenishment successor flow."""

from __future__ import annotations
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .common import ExactTransaction, PersistentBoundaryRecorderV2, coefficients_and_indices, construct_bindings, finish_v2, validate_request_v2

METHOD_ID = "v5-fixed-source-whitelist-no-replenishment"

def execute(request: Mapping[str, Any], *, ledger_path: Path, binding_factory: Callable[..., Any] | None = None) -> dict[str, Any]:
    bound = validate_request_v2(request, METHOD_ID)
    recorder = PersistentBoundaryRecorderV2(bound, __name__, ledger_path)
    bindings = construct_bindings(bound, recorder, binding_factory)
    transaction = ExactTransaction(bound.source["structural_state_digest"])
    whitelist = list(bound.source.get("source_candidate_whitelist", []))
    if not whitelist or len(whitelist) != len(set(whitelist)):
        raise ValueError("unique frozen source whitelist required")
    coefficients, indices = coefficients_and_indices(bound.source)
    try:
        _, runtime_catalog = bindings.catalog(indices, coefficients, list(range(1, len(indices) + 1)), parent_digest=bound.source["structural_state_digest"])
        catalog = {item["candidate_id"]: item for item in runtime_catalog}
        eligible = [catalog[item] for item in whitelist if item in catalog and catalog[item].get("structurally_eligible") is True]
        eligible.sort(key=lambda item: (item["rank_numerator"], item["candidate_id"]))
        selected = [] if not eligible else [eligible[0]["candidate_id"]]
        for candidate in eligible:
            recorder.register_physical_state(candidate["candidate_id"], candidate["proposed_physical_state_id"])
        bindings.optimize_bfgs(coefficients, indices, initial_inverse_hessian=None, maximum_iterations=int(bound.value.get("maximum_optimizer_iterations", 1)))
    except BaseException as error:
        rollback = transaction.rollback(type(error).__name__)
        return finish_v2(bound, recorder, bindings, selected_candidate_ids=[], method_evidence={"replenishment_allowed": False, "failure": type(error).__name__}, transaction_record={"status": "FAILED_CLOSED"}, rollback_record=rollback)
    transaction.stage({"operation": "fixed-whitelist", "selected": selected})
    return finish_v2(bound, recorder, bindings, selected_candidate_ids=selected, method_evidence={"replenishment_allowed": False, "whitelist_only_selection": all(item in whitelist for item in selected), "runtime_new_candidates_admitted": False}, transaction_record=transaction.commit())
