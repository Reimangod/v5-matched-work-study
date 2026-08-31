"""V5 fixed-source-whitelist/no-replenishment production-backend flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import BoundaryRecorder, ExactTransaction, finish, validate_request


METHOD_ID = "v5-fixed-source-whitelist-no-replenishment"


def execute(request: Mapping[str, Any]) -> dict[str, Any]:
    bound = validate_request(request, METHOD_ID)
    recorder = BoundaryRecorder(bound, "v5_final.method_native.v5_fixed_whitelist")
    transaction = ExactTransaction(bound.source["structural_state_digest"])
    whitelist = bound.source.get("source_candidate_whitelist")
    if not isinstance(whitelist, list) or not whitelist or len(whitelist) != len(set(whitelist)):
        raise ValueError("fixed-whitelist backend requires a unique frozen source whitelist")
    catalog = {item["candidate_id"]: item for item in bound.source["structural_catalog"]}
    for item in catalog.values():
        recorder.register_physical_state(item["candidate_id"], item["proposed_physical_state_id"])
    survivors = [
        catalog[candidate_id]
        for candidate_id in whitelist
        if candidate_id in catalog and catalog[candidate_id].get("structurally_eligible") is True
    ]
    survivors.sort(key=lambda item: (item["rank_numerator"], item["candidate_id"]))
    selected = [] if not survivors else [survivors[0]["candidate_id"]]
    forbidden_new = [candidate_id for candidate_id in catalog if candidate_id not in whitelist]
    transaction.stage(
        {
            "operation": "fixed-source-whitelist-selection-pending",
            "selected_candidate_ids": selected,
            "source_whitelist_digest": __import__("hashlib").sha256(
                "\n".join(whitelist).encode()
            ).hexdigest(),
        }
    )
    return finish(
        bound,
        recorder,
        selected_candidate_ids=selected,
        method_evidence={
            "current_runtime_catalog_built": True,
            "catalog_computation_reduction_claimed": False,
            "replenishment_allowed": False,
            "new_candidates_filtered": sorted(forbidden_new),
            "whitelist_only_selection": all(item in whitelist for item in selected),
        },
        transaction_record=transaction.commit(),
    )

