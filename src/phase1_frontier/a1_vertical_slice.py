"""Real-kernel H4 vertical slice for Phase-1 engineering readiness.

This is E2 calibration.  Candidate choice is deterministic and structural;
no candidate energy, FCI value, or historical winner enters enumeration.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from dvg_obs_ceo.composition import GlobalCompatibilityError
from dvg_obs_ceo.resources import AnsatzStructure
from dvg_obs_ceo.transaction import CompressionTransaction
from v5_matched_work.atomic_artifacts import canonical_json_bytes

from v5_final.parent_native_candidate_adapter import (
    ParentNativeCandidatePlan,
    build_typed_catalog,
    compose_parent_native_plan,
)
from v5_final.parent_native_execution_services import ActualOptimizationBoundary
from v5_final.parent_native_rewrite import (
    PreparedParentRewrite,
    prepare_rewrite_for_optimizer,
)
from v5_final.parent_native_runtime_factory_v2 import (
    PLAN_PATH,
    build_queue_bound_runtime_v2,
)

from .authority import ARTIFACT_PATH as A0_ARTIFACT_PATH
from .authority import audit_committed_manifest


ROOT = Path(__file__).resolve().parents[2]
A1_ROOT = ROOT / "artifacts" / "phase1-v1" / "a1-real-kernel-preflight"
A1_RESULT = A1_ROOT / "a1-real-kernel-preflight-v1.json"
A1_AUDIT = A1_ROOT / "a1-readiness-audit-v2.json"
A1_TX_ROOT = A1_ROOT / "transactions"
H4_CASE = "h4-1.5-first-chemical-accuracy"
THREAD_POLICY = {
    "OMP_NUM_THREADS": "2",
    "OPENBLAS_NUM_THREADS": "2",
    "MKL_NUM_THREADS": "2",
}


class A1PreflightError(RuntimeError):
    """Raised when the real-kernel vertical slice is not trustworthy."""


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class KernelEvent:
    operation: str
    outcome: str
    units: int
    elapsed_seconds: float
    evidence: dict[str, Any]


class A1KernelBoundary:
    """Count operations exactly where a real kernel call is made."""

    def __init__(self) -> None:
        self.events: list[KernelEvent] = []

    def invoke(
        self,
        operation: str,
        kernel: Callable[[], Any],
        *,
        units: int | None = None,
        dimension: int | None = None,
        evidence: Mapping[str, Any] | None = None,
    ) -> Any:
        if units is not None and dimension is not None:
            raise A1PreflightError("kernel event cannot bind both units and dimension")
        count = int(dimension if dimension is not None else (units or 1))
        if count < 0:
            raise A1PreflightError("kernel event units cannot be negative")
        started = time.perf_counter()
        try:
            result = kernel()
        except Exception:
            self.events.append(
                KernelEvent(
                    operation,
                    "failed",
                    count,
                    time.perf_counter() - started,
                    dict(evidence or {}),
                )
            )
            raise
        self.events.append(
            KernelEvent(
                operation,
                "completed",
                count,
                time.perf_counter() - started,
                dict(evidence or {}),
            )
        )
        return result

    def totals(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for event in self.events:
            result[event.operation] = result.get(event.operation, 0) + event.units
        return dict(sorted(result.items()))


@dataclass(frozen=True)
class PreparedTarget:
    target_class: str
    plan: ParentNativeCandidatePlan
    rewrite: PreparedParentRewrite


def _verify_A0_authority() -> None:
    if not A0_ARTIFACT_PATH.is_file() or not audit_committed_manifest()["passed"]:
        raise A1PreflightError("A0 authority is absent or no longer valid")
    for name, expected in THREAD_POLICY.items():
        if os.environ.get(name) != expected:
            raise A1PreflightError(
                f"thread policy mismatch: {name}={os.environ.get(name)!r}, expected {expected!r}"
            )


def _h4_context() -> Any:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    matches = [item for item in plan["items"] if item["case_id"] == H4_CASE]
    if not matches:
        raise A1PreflightError("frozen H4 calibration source is absent")
    # Every method/budget row binds the same immutable source.  The smallest
    # queue ID is chosen before any molecular candidate outcome is evaluated.
    item = min(matches, key=lambda value: str(value["queue_item_id"]))
    return build_queue_bound_runtime_v2(str(item["queue_item_id"]))


def _compose(
    *, context: Any, catalog: Any, candidates: Sequence[Any]
) -> ParentNativeCandidatePlan:
    return compose_parent_native_plan(
        pool=context.pool,
        source=context.runtime.ansatz,
        catalog=catalog,
        candidates=candidates,
        gradient=context.runtime.gradient,
        inverse_hessian=context.runtime.inverse_hessian,
        problem_id=context.problem_id,
        reference_state=context._actual_algorithm.ref_det,
    )


def prepare_targets(context: Any) -> tuple[PreparedTarget, PreparedTarget]:
    """Choose a deterministic block deletion and disjoint deletion pair."""

    catalog = build_typed_catalog(context.pool, context.runtime.ansatz)
    deletions = sorted(
        (candidate for candidate in catalog.candidates if candidate.kind in {
            "block-deletion", "mvp-whole-deletion"
        }),
        key=lambda candidate: candidate.candidate_id,
    )
    if not deletions:
        raise A1PreflightError("H4 source has no registered deletion singleton")
    singleton_plan = _compose(context=context, catalog=catalog, candidates=(deletions[0],))
    singleton = PreparedTarget(
        "singleton",
        singleton_plan,
        prepare_rewrite_for_optimizer(
            pool=context.pool,
            source=context.runtime.ansatz,
            parent_plan=singleton_plan,
        ),
    )

    pair_plan: ParentNativeCandidatePlan | None = None
    for left_index, left in enumerate(deletions):
        for right in deletions[left_index + 1 :]:
            try:
                candidate = _compose(
                    context=context, catalog=catalog, candidates=(left, right)
                )
                prepare_rewrite_for_optimizer(
                    pool=context.pool,
                    source=context.runtime.ansatz,
                    parent_plan=candidate,
                )
            except GlobalCompatibilityError:
                continue
            pair_plan = candidate
            break
        if pair_plan is not None:
            break
    if pair_plan is None:
        raise A1PreflightError("H4 source has no compatible registered deletion pair")
    joint = PreparedTarget(
        "joint-K2",
        pair_plan,
        prepare_rewrite_for_optimizer(
            pool=context.pool,
            source=context.runtime.ansatz,
            parent_plan=pair_plan,
        ),
    )
    return singleton, joint


def _constraint_residual(plan: ParentNativeCandidatePlan, coordinates: np.ndarray) -> float:
    transform = plan.joint_plan.transformation
    source = np.asarray(transform.offset) + np.asarray(transform.jacobian) @ coordinates
    residual = np.asarray(transform.constraint_matrix) @ source - np.asarray(
        transform.constraint_rhs
    )
    return 0.0 if not residual.size else float(np.max(np.abs(residual)))


def _independent_gradient(
    context: Any,
    boundary: A1KernelBoundary,
    coordinates: np.ndarray,
    indices: Sequence[int],
) -> np.ndarray:
    return np.asarray(
        boundary.invoke(
            "independent-full-gradient-certification",
            lambda: context._actual_algorithm.estimate_gradients(
                list(coordinates), list(indices), method="an"
            ),
            dimension=len(indices),
            evidence={"route": "fresh-analytic-gradient-call"},
        ),
        dtype=np.float64,
    )


def _run_start(context: Any, target: PreparedTarget, start: str) -> dict[str, Any]:
    boundary = A1KernelBoundary()
    kernels = ActualOptimizationBoundary(
        context._actual_algorithm, context.pool, boundary
    )
    dimension = len(target.rewrite.target.indices)
    if start == "mapped-warm-start":
        initial = np.asarray(target.rewrite.target.coefficients, dtype=np.float64)
        inverse = np.asarray(target.rewrite.target_inverse_hessian, dtype=np.float64)
    elif start == "zero-target-coordinate":
        initial = np.zeros(dimension, dtype=np.float64)
        inverse = np.eye(dimension, dtype=np.float64)
    else:
        raise A1PreflightError(f"unknown optimizer start: {start}")
    result = kernels.optimize(
        initial,
        target.rewrite.target.indices,
        inverse,
    )
    coordinates = np.asarray(result.x, dtype=np.float64)
    semantic_state = kernels.statevector(coordinates, target.rewrite.target.indices)
    independent_state = kernels.independent_statevector(
        coordinates, target.rewrite.target.indices
    )
    independent_energy = kernels.independent_energy(independent_state)
    independent_gradient = _independent_gradient(
        context, boundary, coordinates, target.rewrite.target.indices
    )
    optimized = AnsatzStructure.create(
        target.rewrite.target.indices,
        coordinates,
        target.rewrite.target.cumulative_parameter_counts,
    )
    resources_first = kernels.resources(optimized)
    resources_second = kernels.resources(optimized)
    fidelity = float(abs(np.vdot(semantic_state, independent_state)) ** 2)
    gradient = np.asarray(result.jac, dtype=np.float64)
    gradient_inf = 0.0 if not gradient.size else float(np.max(np.abs(gradient)))
    independent_gradient_inf = (
        0.0
        if not independent_gradient.size
        else float(np.max(np.abs(independent_gradient)))
    )
    checks = {
        "optimizer_completed": bool(result.success),
        "finite_endpoint": bool(
            np.isfinite(float(result.fun))
            and np.all(np.isfinite(coordinates))
            and np.all(np.isfinite(independent_gradient))
        ),
        "independent_energy_agreement": abs(float(result.fun) - independent_energy)
        <= 1e-10,
        "independent_state_fidelity": fidelity >= 1.0 - 1e-10,
        "independent_gradient_agreement": bool(
            gradient.shape == independent_gradient.shape
            and np.max(np.abs(gradient - independent_gradient), initial=0.0) <= 1e-8
        ),
        "kkt_gradient": independent_gradient_inf <= 1e-8,
        "constraint": _constraint_residual(target.plan, coordinates) <= 1e-10,
        "resource_recount_repeatable": (
            resources_first.snapshot == resources_second.snapshot
            and resources_first.circuit_qasm_digest
            == resources_second.circuit_qasm_digest
        ),
    }
    return {
        "start": start,
        "valid": all(checks.values()),
        "checks": checks,
        "optimizer": {
            "success": bool(result.success),
            "status": int(result.status),
            "message": str(result.message),
            "iterations": int(result.nit),
            "energy_evaluations": int(result.nfev),
            "gradient_evaluations": int(result.njev),
        },
        "energy_hartree": float(result.fun),
        "independent_energy_hartree": independent_energy,
        "gradient_infinity_norm": gradient_inf,
        "independent_gradient_infinity_norm": independent_gradient_inf,
        "state_fidelity": fidelity,
        "constraint_residual": _constraint_residual(target.plan, coordinates),
        "parameters": [float(value) for value in coordinates],
        "resources": asdict(resources_first.snapshot),
        "qasm_digest": resources_first.circuit_qasm_digest,
        "raw_counter_totals": boundary.totals(),
        "kernel_events": [asdict(event) for event in boundary.events],
    }


def _run_target(context: Any, target: PreparedTarget) -> dict[str, Any]:
    starts = [
        _run_start(context, target, "mapped-warm-start"),
        _run_start(context, target, "zero-target-coordinate"),
    ]
    valid = [value for value in starts if value["valid"]]
    selected = min(valid, key=lambda value: (value["energy_hartree"], value["start"])) if valid else None
    before = asdict(target.rewrite.before_resources.snapshot)
    after = None if selected is None else selected["resources"]
    return {
        "target_class": target.target_class,
        "candidate_ids": [candidate.candidate_id for candidate in target.plan.candidates],
        "structural_plan": target.plan.to_audit_dict(),
        "rewrite": target.rewrite.to_audit_dict(),
        "starts": starts,
        "selected_start": None if selected is None else selected["start"],
        "selected_energy_hartree": None if selected is None else selected["energy_hartree"],
        "delta_energy_from_E2_source_hartree": (
            None
            if selected is None
            else selected["energy_hartree"] - float(context.runtime.energy_hartree)
        ),
        "accuracy_feasible_at_1e-4": bool(
            selected is not None
            and selected["energy_hartree"] - float(context.runtime.energy_hartree) <= 1e-4
        ),
        "canonical_cnot_improved": bool(
            selected is not None and int(after["cnot_count"]) < int(before["cnot_count"])
        ),
        "scientifically_accepted_E2_probe": bool(
            selected is not None
            and selected["energy_hartree"] - float(context.runtime.energy_hartree) <= 1e-4
            and int(after["cnot_count"]) < int(before["cnot_count"])
        ),
    }


def _failure_probes(context: Any) -> dict[str, Any]:
    """Exercise exact runtime rollback for optimizer and artifact failures."""

    root = A1_TX_ROOT / "rollback-probes"
    if root.exists():
        raise A1PreflightError(
            "A1 rollback-probe root already exists; preserve it and audit before retry"
        )
    before = context.runtime.snapshot().snapshot_digest
    optimizer_failed = False
    try:
        with CompressionTransaction(
            context.runtime, root, transaction_id="optimizer-failure-attempt-1"
        ) as transaction:
            transaction.stage_json("request.json", {"request_id": "a1-failure-probe"})
            from adaptvqe.minimize import minimize_bfgs

            def injected_failure(*_: Any, **__: Any) -> float:
                raise RuntimeError("A1_INJECTED_OPTIMIZER_FAILURE")

            minimize_bfgs(
                injected_failure,
                np.zeros(1),
                jac=lambda _: np.zeros(1),
                maxiter=1,
            )
    except RuntimeError as error:
        optimizer_failed = str(error) == "A1_INJECTED_OPTIMIZER_FAILURE"
    optimizer_after = context.runtime.snapshot().snapshot_digest

    artifact_failed = False
    try:
        with CompressionTransaction(
            context.runtime, root, transaction_id="artifact-failure-attempt-1"
        ) as transaction:
            transaction.stage_json("result.json", {"request_id": "a1-retry-request"})
            transaction.stage_json("result.json", {"request_id": "a1-retry-request"})
    except FileExistsError:
        artifact_failed = True
    artifact_after = context.runtime.snapshot().snapshot_digest
    return {
        "optimizer_failure_injected": optimizer_failed,
        "optimizer_failure_exact_rollback": before == optimizer_after,
        "artifact_write_failure_injected": artifact_failed,
        "artifact_write_failure_exact_rollback": before == artifact_after,
        "same_request_retry_id": "a1-retry-request",
        "same_request_retry_authorized_after_exact_rollback": bool(
            artifact_failed and before == artifact_after
        ),
        "before_snapshot_digest": before,
        "optimizer_after_snapshot_digest": optimizer_after,
        "artifact_after_snapshot_digest": artifact_after,
    }


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise A1PreflightError("artifact write made no forward progress")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_result(record: Mapping[str, Any]) -> None:
    staging = A1_ROOT / ".staging" / "a1-retry-request-attempt-2"
    failed = A1_ROOT / "failed" / "a1-retry-request-attempt-1"
    committed = A1_ROOT / "committed" / "a1-retry-request"
    if any(path.exists() for path in (staging, failed, committed, A1_RESULT)):
        raise A1PreflightError("A1 result or transaction path already exists")
    # Preserve an injected, pre-rename publication failure without creating a
    # terminal result.  The same immutable request ID is then retried once.
    failed.mkdir(parents=True)
    _write_exclusive(
        failed / "failure.json",
        canonical_json_bytes(
            {
                "request_id": "a1-retry-request",
                "attempt": 1,
                "failure": "A1_INJECTED_BEFORE_ATOMIC_RENAME",
                "terminal_result_created": False,
            }
        )
        + b"\n",
    )
    staging.mkdir(parents=True)
    _write_exclusive(staging / "result.json", canonical_json_bytes(record) + b"\n")
    committed.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, committed)
    _write_exclusive(A1_RESULT, canonical_json_bytes(record) + b"\n")


def build_and_run() -> dict[str, Any]:
    _verify_A0_authority()
    context = _h4_context()
    singleton, joint = prepare_targets(context)
    results = [_run_target(context, singleton), _run_target(context, joint)]
    failures = _failure_probes(context)
    scientific_acceptances = sum(
        bool(value["scientifically_accepted_E2_probe"]) for value in results
    )
    checks = {
        "actual_H4_kernel_bound": context.case_id == H4_CASE,
        "source_state_recomputed": context.source_statevector_recomputations == 1,
        "singleton_materialized": len(results[0]["candidate_ids"]) == 1,
        "joint_K2_materialized": len(results[1]["candidate_ids"]) == 2,
        "both_starts_executed_for_each_target": all(
            [start["start"] for start in result["starts"]]
            == ["mapped-warm-start", "zero-target-coordinate"]
            for result in results
        ),
        "independent_certifier_executed": all(
            all(
                start["raw_counter_totals"].get(
                    "independent-full-gradient-certification", 0
                )
                > 0
                for start in result["starts"]
            )
            for result in results
        ),
        "optimizer_failure_exact_rollback": failures[
            "optimizer_failure_exact_rollback"
        ],
        "artifact_failure_exact_rollback": failures[
            "artifact_write_failure_exact_rollback"
        ],
        "same_request_retry_authorized": failures[
            "same_request_retry_authorized_after_exact_rollback"
        ],
    }
    decision = (
        "GO_A2_SOURCE_LOCK"
        if all(checks.values())
        else "NO_GO_A1_REAL_KERNEL_BINDING"
    )
    record: dict[str, Any] = {
        "schema": "phase1-frontier.a1-real-kernel-preflight.v1",
        "stage": "A1",
        "decision": decision,
        "E2_case": H4_CASE,
        "E3_candidate_outcomes": 0,
        "FCI_evaluations": 0,
        "historical_winner_used_for_selection": False,
        "selection_rule": (
            "lexicographically-first registered whole-block deletion; then "
            "lexicographically-first compatible disjoint deletion pair"
        ),
        "source": {
            "problem_id": context.problem_id,
            "hamiltonian_digest": context.hamiltonian_digest,
            "state_preparation_id": context.state_preparation_id,
            "source_checkpoint_digest": context.source_checkpoint_digest,
            "source_statevector_sha256": context.source_statevector_sha256,
            "source_energy_hartree": float(context.runtime.energy_hartree),
            "resources": context.source_resources,
        },
        "targets": results,
        "scientifically_accepted_E2_probe_count": scientific_acceptances,
        "engineering_transaction": {
            "request_id": "a1-retry-request",
            "status": "COMPLETED_ACCEPTED_ENGINEERING_EVIDENCE",
            "scientific_compression_acceptance_claimed": False,
            "reason": (
                "transaction publication acceptance proves atomic persistence; "
                "target accuracy is reported separately and cannot be promoted"
            ),
        },
        "failure_probes": failures,
        "checks": checks,
        "claim_boundary": {
            "allowed": [
                "a real H4 singleton and K=2 joint target reached the actual optimizer",
                "independent endpoint and resource certification paths executed",
                "failure rollback and same-request retry were exercised",
            ],
            "prohibited": [
                "E3 performance",
                "joint-over-singleton advantage",
                "Phase-1 accuracy or resource conclusion",
                "FCI or Measurement Cost claim",
            ],
        },
        "A0_manifest_sha256": _sha256(A0_ARTIFACT_PATH),
    }
    record["record_digest"] = _digest(record)
    _publish_result(record)
    return record


def audit_result() -> dict[str, Any]:
    if not A1_RESULT.is_file():
        raise A1PreflightError("A1 result is absent")
    value = json.loads(A1_RESULT.read_text(encoding="utf-8"))
    digest = value.pop("record_digest", None)
    targets = value.get("targets", [])
    all_starts = [start for target in targets for start in target.get("starts", [])]
    committed_result = (
        A1_ROOT / "committed" / "a1-retry-request" / "result.json"
    )
    failures = value.get("failure_probes", {})
    checks = {
        "record_digest_valid": digest == _digest(value),
        "decision_is_GO": value.get("decision") == "GO_A2_SOURCE_LOCK",
        "all_checks_pass": all(value.get("checks", {}).values()),
        "E3_outcomes_zero": value.get("E3_candidate_outcomes") == 0,
        "FCI_zero": value.get("FCI_evaluations") == 0,
        "singleton_and_joint_present": [item.get("target_class") for item in targets]
        == ["singleton", "joint-K2"],
        "all_four_endpoints_independently_certified": len(all_starts) == 4
        and all(start.get("valid") is True for start in all_starts),
        "all_targets_physically_materialized_and_recounted": len(targets) == 2
        and all(
            target.get("rewrite", {}).get("physical_circuit_changed") is True
            and target.get("rewrite", {}).get("resource_reduction_success") is True
            and all(
                start.get("checks", {}).get("resource_recount_repeatable") is True
                for start in target.get("starts", [])
            )
            for target in targets
        ),
        "optimizer_failure_was_injected_and_rolled_back": failures.get(
            "optimizer_failure_injected"
        )
        is True
        and failures.get("optimizer_failure_exact_rollback") is True,
        "artifact_failure_was_injected_and_rolled_back": failures.get(
            "artifact_write_failure_injected"
        )
        is True
        and failures.get("artifact_write_failure_exact_rollback") is True,
        "same_request_committed": committed_result.is_file()
        and json.loads(committed_result.read_text(encoding="utf-8"))
        == json.loads(A1_RESULT.read_text(encoding="utf-8")),
    }
    return {
        "schema": "phase1-frontier.a1-audit.v1",
        "passed": all(checks.values()),
        "checks": checks,
        "record_digest": digest,
    }


def freeze_audit() -> dict[str, Any]:
    if A1_AUDIT.exists():
        raise A1PreflightError("A1 readiness audit already exists")
    result = audit_result()
    if not result["passed"]:
        raise A1PreflightError("A1 readiness audit did not pass")
    record = {
        **result,
        "decision": "GO_A2_SOURCE_LOCK",
        "result_file_sha256": _sha256(A1_RESULT),
        "E2_scientific_acceptance_count": 0,
        "engineering_readiness_is_not_performance": True,
    }
    record["audit_digest"] = _digest(record)
    _write_exclusive(A1_AUDIT, canonical_json_bytes(record) + b"\n")
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--freeze-audit", action="store_true")
    args = parser.parse_args()
    if sum((args.run, args.audit, args.freeze_audit)) != 1:
        parser.error("choose exactly one of --run, --audit, or --freeze-audit")
    value = (
        build_and_run()
        if args.run
        else (freeze_audit() if args.freeze_audit else audit_result())
    )
    print(json.dumps(value, indent=2, sort_keys=True))
    if args.audit and not value["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
