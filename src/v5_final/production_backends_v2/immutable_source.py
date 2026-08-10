"""Immutable CEO* source successor flow."""

from __future__ import annotations
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .common import ExactTransaction, PersistentBoundaryRecorderV2, coefficients_and_indices, construct_bindings, finish_v2, validate_request_v2

METHOD_ID = "immutable-ceo-star-source"

def execute(request: Mapping[str, Any], *, ledger_path: Path, binding_factory: Callable[..., Any] | None = None) -> dict[str, Any]:
    bound = validate_request_v2(request, METHOD_ID)
    recorder = PersistentBoundaryRecorderV2(bound, __name__, ledger_path)
    bindings = construct_bindings(bound, recorder, binding_factory)
    transaction = ExactTransaction(bound.source["structural_state_digest"])
    coefficients, indices = coefficients_and_indices(bound.source)
    try:
        resources = bindings.resource_recount(coefficients, indices, int(bound.value.get("qubit_count", 4)))
    except BaseException as error:
        rollback = transaction.rollback(type(error).__name__)
        return finish_v2(bound, recorder, bindings, selected_candidate_ids=[], method_evidence={"candidate_construction": "NOT_PERFORMED", "failure": type(error).__name__}, transaction_record={"status": "FAILED_CLOSED"}, rollback_record=rollback)
    return finish_v2(bound, recorder, bindings, selected_candidate_ids=[], method_evidence={"candidate_construction": "NOT_PERFORMED", "source_structure_preserved": True, "resources": dict(resources)}, transaction_record=transaction.commit())
