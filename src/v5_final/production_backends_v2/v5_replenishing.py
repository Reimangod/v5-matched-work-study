"""Full V5 child-dependent replenishment successor flow."""

from __future__ import annotations
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .common import ExactTransaction, PersistentBoundaryRecorderV2, coefficients_and_indices, construct_bindings, digest, finish_v2, validate_request_v2

METHOD_ID = "v5-sequential-with-rebuilding"

def execute(request: Mapping[str, Any], *, ledger_path: Path, binding_factory: Callable[..., Any] | None = None) -> dict[str, Any]:
    bound = validate_request_v2(request, METHOD_ID)
    recorder = PersistentBoundaryRecorderV2(bound, __name__, ledger_path)
    bindings = construct_bindings(bound, recorder, binding_factory)
    transaction = ExactTransaction(bound.source["structural_state_digest"])
    coefficients, indices = coefficients_and_indices(bound.source)
    selected: list[str] = []
    child_digest: str | None = None
    try:
        _, first_catalog = bindings.catalog(indices, coefficients, list(range(1, len(indices) + 1)), parent_digest=bound.source["structural_state_digest"])
        eligible = [item for item in first_catalog if item.get("structurally_eligible") is True and recorder.register_physical_state(item["candidate_id"], item["proposed_physical_state_id"])]
        eligible.sort(key=lambda item: (item["rank_numerator"], item["candidate_id"]))
        if eligible:
            selected.append(eligible[0]["candidate_id"])
            child_digest = digest({"parent": bound.source["structural_state_digest"], "candidate": selected[0]})
            bindings.optimize_bfgs(coefficients, indices, initial_inverse_hessian=None, maximum_iterations=int(bound.value.get("maximum_optimizer_iterations", 1)))
            _, child_catalog = bindings.catalog(indices, coefficients, list(range(1, len(indices) + 1)), parent_digest=child_digest)
            for item in child_catalog:
                recorder.register_physical_state(item["candidate_id"], item["proposed_physical_state_id"])
    except BaseException as error:
        rollback = transaction.rollback(type(error).__name__)
        return finish_v2(bound, recorder, bindings, selected_candidate_ids=selected, method_evidence={"child_dependent_replenishment": child_digest is not None, "failure": type(error).__name__}, transaction_record={"status": "FAILED_CLOSED"}, rollback_record=rollback)
    transaction.stage({"operation": "full-v5-replenishment", "selected": selected, "child_digest": child_digest})
    return finish_v2(bound, recorder, bindings, selected_candidate_ids=selected, method_evidence={"child_dependent_replenishment": child_digest is not None, "catalog_calls": sum(item["operation"] == "candidate-generation" for item in bindings.trace), "deduplication_key": "ProposedPhysicalStateID"}, transaction_record=transaction.commit())
