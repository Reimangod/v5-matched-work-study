"""Outcome-free actual H2/H4 proof for the MB6-v3 runtime successor."""

from __future__ import annotations

import json

from .parent_native_runtime_factory_v2 import (
    ENVIRONMENT_PATH,
    FALLBACK_PLAN_PATH,
    build_queue_bound_runtime_v2,
)


def main() -> None:
    plan = json.loads(FALLBACK_PLAN_PATH.read_text())
    records = []
    for case_id in (
        "h2-1.5-iteration-1",
        "h4-1.5-first-chemical-accuracy",
    ):
        item = next(
            value
            for value in plan["items"]
            if value["case_id"] == case_id
            and value["method_id"] == "immutable-ceo-star-source"
            and value["work_envelope"] == "LOW"
        )
        runtime = build_queue_bound_runtime_v2(item["queue_item_id"])
        records.append(
            {
                "case_id": case_id,
                "queue_item_id": runtime.queue_item_id,
                "plan_digest": runtime.plan_digest,
                "ProblemID": runtime.problem_id,
                "Hamiltonian_digest": runtime.hamiltonian_digest,
                "StatePreparationID": runtime.state_preparation_id,
                "source_statevector_sha256": runtime.source_statevector_sha256,
                "source_resources": runtime.source_resources,
                "actual_algorithm_type": type(runtime._actual_algorithm).__name__,
                "actual_pool_type": type(runtime.pool).__name__,
            }
        )
    print(
        json.dumps(
            {
                "schema": "v5-final.parent-native-runtime-factory-v2-probe.v1",
                "environment_path": str(ENVIRONMENT_PATH),
                "records": records,
                "candidate_molecular_energy_evaluations": 0,
                "H2_H4_queue_executed": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
