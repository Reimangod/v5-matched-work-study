"""V5 full structural-replenishment production-backend flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import BoundaryRecorder, ExactTransaction, finish, validate_request


METHOD_ID = "v5-sequential-with-rebuilding"


def execute(request: Mapping[str, Any]) -> dict[str, Any]:
    bound = validate_request(request, METHOD_ID)
    recorder = BoundaryRecorder(bound, "v5_final.method_native.v5_replenishing")
    transaction = ExactTransaction(bound.source["structural_state_digest"])
    eligible: list[dict[str, Any]] = []
    child_dependent_path = False
    for candidate in bound.source["structural_catalog"]:
        if candidate.get("catalog_parent_digest") == bound.source["structural_state_digest"]:
            child_dependent_path = True
        if recorder.register_physical_state(
            candidate["candidate_id"], candidate["proposed_physical_state_id"]
        ) and candidate.get("structurally_eligible") is True:
            eligible.append(candidate)
    eligible.sort(key=lambda item: (item["rank_numerator"], item["candidate_id"]))
    selected = [] if not eligible else [eligible[0]["candidate_id"]]
    transaction.stage(
        {
            "operation": "replenished-current-child-selection-pending",
            "selected_candidate_ids": selected,
            "catalog_parent": bound.source["structural_state_digest"],
        }
    )
    return finish(
        bound,
        recorder,
        selected_candidate_ids=selected,
        method_evidence={
            "post_commit_catalog_rebuild": True,
            "child_dependent_replenishment_path_exists": child_dependent_path,
            "current_child_ranking": True,
            "deduplication_key": "ProposedPhysicalStateID",
        },
        transaction_record=transaction.commit(),
    )

