"""Same-structure reoptimization production-backend flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import BoundaryRecorder, ExactTransaction, finish, validate_request


METHOD_ID = "same-structure-reoptimization"


def execute(request: Mapping[str, Any]) -> dict[str, Any]:
    bound = validate_request(request, METHOD_ID)
    recorder = BoundaryRecorder(bound, "v5_final.method_native.same_structure")
    transaction = ExactTransaction(bound.source["structural_state_digest"])
    recorder.evidence(
        "optimizer-lifecycle-prepared",
        {
            "structure_preserved": True,
            "optimizer_policy_digest": bound.value["optimizer_policy_digest"],
            "optimizer_kernel_called": False,
        },
    )
    transaction.stage(
        {
            "source": bound.source["structural_state_digest"],
            "generators": [item["generator_id"] for item in bound.source["generators"]],
            "operation": "same-structure-reoptimization-pending",
        }
    )
    if bound.value.get("failure_injection") == "after-stage":
        rollback = transaction.rollback("injected-after-stage")
        return finish(
            bound,
            recorder,
            selected_candidate_ids=[],
            method_evidence={"optimizer_kernel_called": False, "structure_preserved": True},
            transaction_record={"status": "FAILED_CLOSED"},
            rollback_record=rollback,
        )
    return finish(
        bound,
        recorder,
        selected_candidate_ids=[],
        method_evidence={
            "optimizer_kernel_called": False,
            "structure_preserved": True,
            "production_optimizer_path": "bound-but-gated-until-MB8-CAL",
        },
        transaction_record=transaction.commit(),
    )

