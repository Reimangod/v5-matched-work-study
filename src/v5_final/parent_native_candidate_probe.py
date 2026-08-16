"""Outcome-free actual-parent probe for the typed candidate adapter."""

from __future__ import annotations

import json

import numpy as np

from dvg_obs_ceo.baseline import _load_upstream
from dvg_obs_ceo.resources import AnsatzStructure

from .parent_native_candidate_adapter import (
    build_typed_catalog,
    compose_parent_native_plan,
)


def main() -> None:
    _, dvg_ceo, _, _ = _load_upstream()
    pool = dvg_ceo(n=4)
    source = AnsatzStructure.create([2, 3], [0.3, -0.1], [2])
    catalog = build_typed_catalog(pool, source)
    candidate = next(
        item for item in catalog.candidates if item.kind == "mvp-to-ovp-sum"
    )
    plan = compose_parent_native_plan(
        pool=pool,
        source=source,
        catalog=catalog,
        candidates=(candidate,),
        gradient=np.zeros(2, dtype=np.float64),
        inverse_hessian=np.eye(2, dtype=np.float64),
        problem_id="problem-v1:" + "1" * 64,
        reference_state=(1, 1, 0, 0),
    )
    audit = plan.to_audit_dict()
    result = {
        "block_type": type(catalog.blocks[0]).__name__,
        "candidate_type": type(candidate).__name__,
        "candidate_is_mapping": hasattr(candidate, "get"),
        "candidate_count": catalog.generated_candidate_intent_count,
        "candidate_id": candidate.candidate_id,
        "equivalence_class_id": candidate.equivalence_class_id,
        "target_indices": audit["target_indices"],
        "target_iteration_counts": audit["target_iteration_counts"],
        "constraint_semantic_id": audit["constraint_semantic_id"],
        "constraint_numerical_id": audit["constraint_numerical_id"],
        "candidate_intent_id": audit["candidate_intent_ids"][0],
        "proposed_physical_state_id": audit["proposed_physical_state_id"],
        "proposed_state_preparation_id": audit[
            "proposed_state_preparation_id"
        ],
        "warm_start_dimension": len(audit["target_initial_coordinates_float64_hex"]),
        "inverse_hessian_dimension": len(
            audit["target_inverse_hessian_float64_hex"]
        ),
        "candidate_energy_evaluations": 0,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
