"""Immutable CEO* source production-backend flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import BoundaryRecorder, ExactTransaction, finish, validate_request


METHOD_ID = "immutable-ceo-star-source"


def execute(request: Mapping[str, Any]) -> dict[str, Any]:
    bound = validate_request(request, METHOD_ID)
    recorder = BoundaryRecorder(bound, "v5_final.method_native.immutable_source")
    transaction = ExactTransaction(bound.source["structural_state_digest"])
    recorder.structural(
        "full-physical-resource-recount",
        {"reason": "record exact immutable source circuit without constructing a child"},
    )
    return finish(
        bound,
        recorder,
        selected_candidate_ids=[],
        method_evidence={
            "candidate_construction": "NOT_PERFORMED",
            "child_state": "NOT_CREATED",
            "source_structure_preserved": True,
        },
        transaction_record=transaction.commit(),
    )

