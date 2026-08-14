"""Outcome-free integration probe for successor factory and execution services."""

from __future__ import annotations

import inspect
import json

from .parent_native_candidate_work_bindings import build_candidate_work_binding
from .parent_native_execution_control_probe import run_control_flow_probe
from .parent_native_execution_services import (
    ActualOptimizationBoundary,
    DurableWorkBoundary,
    ParentNativeExecutionServices,
    execute_frozen_item,
)
from .parent_native_runtime_factory_v2 import FALLBACK_PLAN_PATH


def main() -> None:
    plan = json.loads(FALLBACK_PLAN_PATH.read_text())
    records = []
    for case_id in (
        "h2-1.5-iteration-1",
        "h4-1.5-first-chemical-accuracy",
    ):
        for method_id in (
            "immutable-ceo-star-source",
            "same-structure-reoptimization",
            "structural-magnitude-pruning",
            "v4.1-one-shot-joint-compression",
            "v5-fixed-source-whitelist-no-replenishment",
            "v5-sequential-with-rebuilding",
        ):
            item = next(
                value
                for value in plan["items"]
                if value["case_id"] == case_id
                and value["method_id"] == method_id
                and value["work_envelope"] == "LOW"
            )
            context, prepared, binding = build_candidate_work_binding(item)
            records.append(
                {
                    "case_id": case_id,
                    "method_id": method_id,
                    "queue_item_id": item["queue_item_id"],
                    "actual_algorithm_type": type(context._actual_algorithm).__name__,
                    "actual_pool_type": type(context.pool).__name__,
                    "prepared_executor_type": type(prepared).__name__,
                    "candidate_work_binding": binding.to_dict(),
                    "release_called": False,
                }
            )
    print(
        json.dumps(
            {
                "schema": "v5-final.parent-native-execution-services-probe.v1",
                "records": records,
                "service_bindings": {
                    "prepared_execute_signature": str(
                        inspect.signature(ParentNativeExecutionServices.execute_prepared)
                    ),
                    "production_entrypoint_signature": str(
                        inspect.signature(execute_frozen_item)
                    ),
                    "durable_boundary": DurableWorkBoundary.__name__,
                    "actual_optimization_boundary": ActualOptimizationBoundary.__name__,
                },
                "outcome_free_control_flow": run_control_flow_probe(),
                "candidate_molecular_energy_evaluations": 0,
                "optimizer_calls": 0,
                "H2_H4_queue_executed": False,
                "performance_evidence": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
