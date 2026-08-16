"""Outcome-free actual rewrite/matrix/resource parity probe."""

from __future__ import annotations

import json

import numpy as np

from dvg_obs_ceo.baseline import _load_upstream
from dvg_obs_ceo.resources import (
    AnsatzStructure,
    evaluate_full_circuit_resources,
    paper_era_backend,
)

from .parent_native_candidate_adapter import (
    build_typed_catalog,
    compose_parent_native_plan,
)
from .parent_native_rewrite import prepare_rewrite_for_optimizer


def main() -> None:
    _, dvg_ceo, _, _ = _load_upstream()
    pool = dvg_ceo(n=4)
    source = AnsatzStructure.create(
        [4, 2, 3, 0],
        [0.2, 0.3, -0.1, 0.4],
        [3, 4],
    )
    catalog = build_typed_catalog(pool, source)
    mvp_block = next(block for block in catalog.blocks if block.family == "MVP")
    candidate = next(
        item
        for item in catalog.candidates
        if item.source_block_id == mvp_block.block_id
        and item.kind == "mvp-to-ovp-sum"
    )
    plan = compose_parent_native_plan(
        pool=pool,
        source=source,
        catalog=catalog,
        candidates=(candidate,),
        gradient=np.zeros(len(source.indices), dtype=np.float64),
        inverse_hessian=np.eye(len(source.indices), dtype=np.float64),
        problem_id="problem-v1:" + "2" * 64,
        reference_state=(1, 1, 0, 0),
    )
    prepared = prepare_rewrite_for_optimizer(
        pool=pool,
        source=source,
        parent_plan=plan,
    )
    audit = prepared.to_audit_dict()
    h2 = AnsatzStructure.create([4], [-0.18820719206269798], [1])
    h2_first = evaluate_full_circuit_resources(pool, h2, paper_era_backend())
    h2_second = evaluate_full_circuit_resources(pool, h2, paper_era_backend())
    result = {
        "rewrite": audit,
        "rewrite_applied_before_optimizer_arguments": (
            audit["optimizer_arguments"]["indices"] == audit["target_indices"]
            and audit["target_indices"] != audit["source_indices"]
        ),
        "optimizer_called": False,
        "candidate_energy_evaluations": 0,
        "known_h2_parent_parity": {
            "first": audit_h2(h2_first),
            "second": audit_h2(h2_second),
            "exact_match": h2_first == h2_second,
        },
    }
    print(json.dumps(result, sort_keys=True))


def audit_h2(value: object) -> dict[str, int]:
    snapshot = value.snapshot
    return {
        "cnot_count": int(snapshot.cnot_count),
        "cnot_depth": int(snapshot.cnot_depth),
        "total_depth": int(snapshot.total_depth),
        "parameter_count": int(snapshot.parameter_count),
        "logical_block_count": int(snapshot.logical_block_count),
    }


if __name__ == "__main__":
    main()
