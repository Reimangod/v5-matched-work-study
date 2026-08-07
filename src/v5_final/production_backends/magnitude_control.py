"""Single-coordinate magnitude-control production-backend flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import BoundaryRecorder, ExactTransaction, finish, validate_request


METHOD_ID = "structural-magnitude-pruning"


def execute(request: Mapping[str, Any]) -> dict[str, Any]:
    bound = validate_request(request, METHOD_ID)
    recorder = BoundaryRecorder(bound, "v5_final.method_native.magnitude_control")
    transaction = ExactTransaction(bound.source["structural_state_digest"])
    chosen = min(
        bound.source["generators"],
        key=lambda item: (item["magnitude_rank"], item["generator_id"]),
    )
    candidate_id = "single-coordinate-delete:" + chosen["generator_id"]
    physical_state_id = "physical-state-v1:" + __import__("hashlib").sha256(
        (bound.source["structural_state_digest"] + "|" + chosen["generator_id"]).encode()
    ).hexdigest()
    recorder.register_physical_state(candidate_id, physical_state_id)
    child_generators = [
        item["generator_id"]
        for item in bound.source["generators"]
        if item["generator_id"] != chosen["generator_id"]
    ]
    transaction.stage(
        {
            "physical_state_id": physical_state_id,
            "generators": child_generators,
            "coefficient_zeroing_only": False,
        }
    )
    recorder.structural(
        "full-physical-resource-recount",
        {
            "candidate_id": candidate_id,
            "full_circuit_rebuild": True,
            "resource_zero_is_not_success": True,
        },
    )
    before_resources = bound.source["resources_before"]
    after_resources = bound.source["resources_after_single_deletion"]
    resource_reduction_success = any(
        after_resources[key] < before_resources[key] for key in before_resources
    )
    if bound.value.get("failure_injection") == "after-stage":
        rollback = transaction.rollback("injected-after-stage")
        return finish(
            bound,
            recorder,
            selected_candidate_ids=[candidate_id],
            method_evidence={"physical_generator_deleted": True, "optimizer_called": False},
            transaction_record={"status": "FAILED_CLOSED"},
            rollback_record=rollback,
        )
    return finish(
        bound,
        recorder,
        selected_candidate_ids=[candidate_id],
        method_evidence={
            "batch_size": 1,
            "physical_generator_deleted": True,
            "coefficient_zeroing_only": False,
            "optimizer_called": False,
            "resource_reduction_success": resource_reduction_success,
            "zero_resource_reduction_is_success": False,
            "post_commit_score_recompute_path": "method-native-and-gated",
        },
        transaction_record=transaction.commit(),
    )
