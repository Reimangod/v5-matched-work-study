"""V4.1 one-shot joint-compression production-backend flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import BoundaryRecorder, ExactTransaction, finish, validate_request


METHOD_ID = "v4.1-one-shot-joint-compression"


def execute(request: Mapping[str, Any]) -> dict[str, Any]:
    bound = validate_request(request, METHOD_ID)
    recorder = BoundaryRecorder(bound, "v5_final.method_native.v4_1_one_shot")
    transaction = ExactTransaction(bound.source["structural_state_digest"])
    representatives: dict[str, dict[str, Any]] = {}
    for candidate in bound.source["structural_catalog"]:
        if candidate.get("structurally_eligible") is not True:
            continue
        key = candidate.get("equivalence_class_id")
        if not isinstance(key, str) or not key:
            continue
        previous = representatives.get(key)
        if previous is None or candidate["candidate_id"] < previous["candidate_id"]:
            representatives[key] = candidate
    ordered = [representatives[key] for key in sorted(representatives)][:4]
    selected: list[str] = []
    for candidate in ordered:
        if recorder.register_physical_state(
            candidate["candidate_id"], candidate["proposed_physical_state_id"]
        ):
            recorder.structural(
                "rewrite-verification",
                {
                    "candidate_id": candidate["candidate_id"],
                    "predictor_used": False,
                    "FCI_used": False,
                },
            )
            selected.append(candidate["candidate_id"])
    transaction.stage(
        {
            "operation": "one-shot-joint-compression-pending",
            "selected_candidate_ids": selected,
        }
    )
    return finish(
        bound,
        recorder,
        selected_candidate_ids=selected,
        method_evidence={
            "one_candidate_per_equivalence_class": True,
            "maximum_candidates": 4,
            "canonical_order": True,
            "predictor_used": False,
            "candidate_energy_called": False,
        },
        transaction_record=transaction.commit(),
    )

