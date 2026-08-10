"""Outcome-free H2/H4 preparation probe for all six actual executors."""

from __future__ import annotations

from contextlib import contextmanager
import json
from typing import Any, Iterator

from adaptvqe.algorithms.adapt_vqe import LinAlgAdapt

from .parent_native_executors import (
    METHOD_IDS,
    inspect_parent_execution_bindings,
    prepare_method_executor,
)
from .parent_native_runtime_factory import (
    QUEUE_PATH,
    build_queue_bound_runtime,
    build_s3_corrected_environment,
    project_queue_to_environment,
)


@contextmanager
def _outcome_guard() -> Iterator[dict[str, int]]:
    names = (
        "initialize",
        "run",
        "run_iteration",
        "get_state",
        "compute_state",
        "evaluate_energy",
        "evaluate_observable",
        "estimate_gradients",
        "estimate_hessian",
        "optimize",
    )
    originals = {name: getattr(LinAlgAdapt, name) for name in names}
    calls = {name: 0 for name in names}

    def blocked(name: str):
        def stop(*_: Any, **__: Any) -> Any:
            calls[name] += 1
            raise RuntimeError(f"S4 outcome guard blocked molecular kernel: {name}")

        return stop

    try:
        for name in names:
            setattr(LinAlgAdapt, name, blocked(name))
        yield calls
    finally:
        for name, value in originals.items():
            setattr(LinAlgAdapt, name, value)


def build() -> dict[str, Any]:
    environment = build_s3_corrected_environment()
    queue = project_queue_to_environment(
        json.loads(QUEUE_PATH.read_text()), environment
    )
    contexts = {}
    for case_id in (
        "h2-1.5-iteration-1",
        "h4-1.5-first-chemical-accuracy",
    ):
        source_item = next(
            item
            for item in queue["items"]
            if item["case_id"] == case_id
            and item["method_id"] == "immutable-ceo-star-source"
            and item["work_envelope"] == "LOW"
        )
        contexts[case_id] = build_queue_bound_runtime(
            source_item["queue_item_id"],
            queue_record=queue,
            environment_record=environment,
        )

    records = []
    with _outcome_guard() as calls:
        for case_id, context in contexts.items():
            cache: dict[str, Any] = {}
            for method_id in METHOD_IDS:
                item = next(
                    value
                    for value in queue["items"]
                    if value["case_id"] == case_id
                    and value["method_id"] == method_id
                    and value["work_envelope"] == "LOW"
                )
                prepared = prepare_method_executor(
                    context,
                    item,
                    preparation_cache=cache,
                )
                records.append(prepared.to_audit_dict())

    by_case_method = {
        (record["case_id"], record["method_id"]): record for record in records
    }
    contrasts = {}
    for case_id in contexts:
        fixed = by_case_method[
            (case_id, "v5-fixed-source-whitelist-no-replenishment")
        ]
        full = by_case_method[(case_id, "v5-sequential-with-rebuilding")]
        contrasts[case_id] = {
            "same_source_selection_digest": (
                fixed["execution_directives"]["selection_evidence"][
                    "selection_digest"
                ]
                == full["execution_directives"]["selection_evidence"][
                    "selection_digest"
                ]
            ),
            "same_initial_selected_candidates": (
                fixed["selected_candidate_ids"] == full["selected_candidate_ids"]
            ),
            "fixed_replenishment": fixed["execution_directives"][
                "replenishment_allowed"
            ],
            "full_replenishment": full["execution_directives"][
                "replenishment_allowed"
            ],
            "catalog_work_reduction_claimed": (
                fixed["execution_directives"][
                    "catalog_computation_reduction_claimed"
                ]
                or full["execution_directives"][
                    "catalog_computation_reduction_claimed"
                ]
            ),
        }
    return {
        "schema": "v5-final.s4-parent-native-executors-probe.v1",
        "methods": list(METHOD_IDS),
        "cases": list(contexts),
        "records": records,
        "parent_execution_bindings": inspect_parent_execution_bindings(),
        "fixed_vs_full_initial_contrast": contrasts,
        "molecular_outcome_kernel_calls": calls,
        "candidate_energy_evaluations": calls["evaluate_energy"],
        "optimizer_calls": calls["optimize"],
        "H2_H4_queue_executed": False,
        "projected_queue_written_or_authorized": False,
        "performance_evidence": False,
    }


def main() -> None:
    print(json.dumps(build(), sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
