"""Outcome-free behavioral probe for six production control-flow branches."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import numpy as np

from .parent_native_execution_services import ParentNativeExecutionServices
from .parent_native_execution_services import (
    _outcome_checkpoint,
    _outcome_checkpoint_path,
    _work_request,
    recover_frozen_item_result,
)
from .parent_native_persistent_runner import ParentNativePersistentRunner, make_attempt_id
from .parent_native_work_accounting import work_cap_digest
from .semantic_contract_v2 import WorkDelta
from v5_matched_work.atomic_artifacts import write_json_exclusive


@dataclass
class _Runtime:
    ansatz: Any
    energy_hartree: float
    gradient: np.ndarray
    inverse_hessian: np.ndarray
    statevector: np.ndarray
    metadata: dict[str, Any]
    validations: int = 0

    def validate(self) -> None:
        self.validations += 1


def _structure(label: str) -> Any:
    return SimpleNamespace(
        label=label,
        indices=(1,),
        coefficients=(0.1,),
        cumulative_parameter_counts=(1,),
    )


def _attempt(label: str, accepted: bool) -> dict[str, Any]:
    return {
        "accepted": accepted,
        "acceptance": {"method_control_accepted": accepted},
        "optimizer": {"iterations": 1},
        "energy_hartree": -1.0 - 0.01 * len(label),
        "independent_energy_hartree": -1.0 - 0.01 * len(label),
        "state_fidelity": 1.0,
        "gradient_infinity_norm": 0.0,
        "structure": _structure(label),
        "parameters": np.asarray((0.1,)),
        "inverse_hessian": np.eye(1),
        "gradient": np.zeros(1),
        "statevector": np.asarray((1.0 + 0.0j,)),
        "resources": {
            "structure_digest": "resource:" + label,
            "cnot_count": 0,
            "cnot_depth": 0,
            "total_depth": 0,
            "parameter_count": 1,
            "logical_block_count": 1,
        },
        "time_series": [],
    }


def _executor(method: str) -> Any:
    runtime = _Runtime(
        ansatz=_structure("source"),
        energy_hartree=-1.0,
        gradient=np.zeros(1),
        inverse_hessian=np.eye(1),
        statevector=np.asarray((1.0 + 0.0j,)),
        metadata={
            "resource_structure_digest": "resource:source",
            "budget_reference_energy_hartree": -1.0,
        },
    )
    context = SimpleNamespace(
        runtime=runtime,
        source_resources={
            "structure_digest": "resource:source",
            "cnot_count": 1,
            "cnot_depth": 1,
            "total_depth": 1,
            "parameter_count": 1,
            "logical_block_count": 1,
        },
    )
    candidate = SimpleNamespace(candidate_id="candidate:first")
    plan = SimpleNamespace(
        candidates=(candidate,), proposed_state_preparation_spec=object()
    )
    rewrite = SimpleNamespace(target=_structure("first"), target_inverse_hessian=np.eye(1))
    magnitude = SimpleNamespace(
        candidate_id="magnitude:first",
        target=_structure("first"),
        position=0,
    )
    structural = method in {
        "v4.1-one-shot-joint-compression",
        "v5-fixed-source-whitelist-no-replenishment",
        "v5-sequential-with-rebuilding",
    }
    return SimpleNamespace(
        method_id=method,
        context=context,
        prepared_rewrites=(rewrite,) if structural else (),
        candidate_plans=(plan,) if structural else (),
        magnitude_deletion=magnitude if method == "structural-magnitude-pruning" else None,
    )


def run_control_flow_probe() -> dict[str, Any]:
    records: dict[str, Any] = {}
    methods = (
        "immutable-ceo-star-source",
        "same-structure-reoptimization",
        "structural-magnitude-pruning",
        "v4.1-one-shot-joint-compression",
        "v5-fixed-source-whitelist-no-replenishment",
        "v5-sequential-with-rebuilding",
    )
    for method in methods:
        executor = _executor(method)
        service = ParentNativeExecutionServices(
            item={}, plan={}, runner=object(), boundary=object(), algorithm=object()
        )
        optimization_trace: list[str] = []
        dynamic_trace: list[str] = []
        outcomes = (
            [_attempt("same", True)]
            if method == "same-structure-reoptimization"
            else [_attempt("first", True), _attempt("second", False)]
            if method == "structural-magnitude-pruning"
            else [_attempt("first", True)]
        )

        def optimize(**values: Any) -> dict[str, Any]:
            optimization_trace.append(values["target"].label)
            return outcomes.pop(0)

        def magnitude_dynamic(*_: Any) -> Any:
            dynamic_trace.append("magnitude-rebuild")
            return (
                "magnitude:second",
                _structure("second"),
                np.eye(1),
            ) if len(dynamic_trace) == 1 else None

        def v5_dynamic(current: Any, *_: Any) -> Any:
            dynamic_trace.append(current.method_id)
            return (), (), {"selected_attempt_count": 0}

        with (
            patch(
                "v5_final.parent_native_execution_services._optimize_and_decide",
                side_effect=optimize,
            ),
            patch(
                "v5_final.parent_native_execution_services._dynamic_magnitude_preparation",
                side_effect=magnitude_dynamic,
            ),
            patch(
                "v5_final.parent_native_execution_services._dynamic_v5_preparation",
                side_effect=v5_dynamic,
            ),
            patch(
                "v5_final.parent_native_execution_services._plan_physical_id",
                return_value="physical-state-v3:" + "1" * 64,
            ),
        ):
            result = service.execute_prepared(executor)
        records[method] = {
            "terminal_status": result["terminal_status"],
            "stopping_reason": result["stopping_reason"],
            "accepted_candidate_ids": result["accepted_candidate_ids"],
            "optimization_trace": optimization_trace,
            "dynamic_trace": dynamic_trace,
            "runtime_validation_count": executor.context.runtime.validations,
        }

    checks = {
        "immutable_executes_no_optimizer": records["immutable-ceo-star-source"][
            "optimization_trace"
        ]
        == [],
        "same_structure_commits_reoptimization": records[
            "same-structure-reoptimization"
        ]["runtime_validation_count"]
        == 1,
        "magnitude_rebuilds_after_commit": records[
            "structural-magnitude-pruning"
        ]["optimization_trace"]
        == ["first", "second"]
        and records["structural-magnitude-pruning"]["dynamic_trace"]
        == ["magnitude-rebuild"],
        "v4_is_one_shot": records["v4.1-one-shot-joint-compression"][
            "dynamic_trace"
        ]
        == [],
        "fixed_rebuilds_but_preserves_fixed_method_identity": records[
            "v5-fixed-source-whitelist-no-replenishment"
        ]["dynamic_trace"]
        == ["v5-fixed-source-whitelist-no-replenishment"],
        "full_v5_rebuilds_from_committed_child": records[
            "v5-sequential-with-rebuilding"
        ]["dynamic_trace"]
        == ["v5-sequential-with-rebuilding"],
    }
    if not all(checks.values()):
        raise RuntimeError("outcome-free production control-flow proof failed")
    checkpoint_recovery = _checkpoint_recovery_probe()
    return {
        "schema": "v5-final.parent-native-execution-control-probe.v1",
        "binding_kind": "OUTCOME_FREE_BEHAVIORAL_FAKE",
        "scientific_candidate_energy_evaluations": 0,
        "performance_evidence": False,
        "records": records,
        "checks": checks,
        "outcome_checkpoint_recovery": checkpoint_recovery,
    }


def _checkpoint_recovery_probe() -> dict[str, Any]:
    cap = WorkDelta(
        energy_evaluations=2,
        gradient_vector_evaluations=1,
        gradient_component_equivalents=2,
        hvp_evaluations=0,
        optimizer_starts=1,
        optimizer_iterations=1,
        statevector_recomputations=0,
        resource_recounts=0,
        candidate_generations=0,
        search_states=0,
        rewrite_verifications=0,
    )
    item = {
        "queue_item_id": "synthetic-queue-item",
        "method_id": "same-structure-reoptimization",
        "case_id": "synthetic-case",
        "StatePreparationID": "state-v1:" + "1" * 64,
        "ProblemID": "problem-v1:" + "2" * 64,
        "Hamiltonian_digest": "3" * 64,
        "source_checkpoint_digest": "4" * 64,
        "work_cap_digest": work_cap_digest(cap),
        "componentwise_work_cap": asdict(cap),
    }
    plan = {"plan_digest": "5" * 64}
    request = _work_request(item, plan)
    with tempfile.TemporaryDirectory(prefix="v5-outcome-recovery-") as directory:
        root = Path(directory) / "raw"
        result = Path(directory) / "result.json"
        runner = ParentNativePersistentRunner.create(
            root,
            request=request,
            cap=cap,
            attempt_id=make_attempt_id(request, ordinal=1, nonce="synthetic"),
        )
        recorder = runner.resume_work_recorder()
        recorder.invoke(
            "candidate-energy-evaluation",
            lambda: -1.0,
            evidence={"synthetic_behavioral": True},
        )
        runner.persist_new_work_events(recorder.events)
        payload = {
            "queue_item_id": item["queue_item_id"],
            "method_id": item["method_id"],
            "case_id": item["case_id"],
            "result": {
                "terminal_status": "ACCEPTED",
                "stopping_reason": "SYNTHETIC_ACCEPTED",
            },
            "work_total": asdict(recorder.total),
            "telemetry": [],
            "synthetic_behavioral": True,
        }
        checkpoint = _outcome_checkpoint(request, payload)
        write_json_exclusive(_outcome_checkpoint_path(root), checkpoint)
        first = recover_frozen_item_result(
            plan=plan,
            item=item,
            raw_ledger_root=root,
            result_output=result,
        )
        second = recover_frozen_item_result(
            plan=plan,
            item=item,
            raw_ledger_root=root,
            result_output=result,
        )
        return {
            "checkpoint_before_terminal_recovered_without_kernel_rerun": first == second,
            "terminal_status": first["recovered"]["terminal"]["terminal_status"],
            "outcome_digest_bound": first["recovered"]["terminal"][
                "outcome_digest"
            ]
            == checkpoint["outcome_digest"],
            "synthetic_candidate_energy_events": 1,
            "molecular_candidate_energy_events": 0,
        }


if __name__ == "__main__":
    import json

    print(json.dumps(run_control_flow_probe(), sort_keys=True))
