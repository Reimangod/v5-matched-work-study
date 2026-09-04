"""Fail-closed binding from the frozen Phase-1 v2 queue to the real kernel.

This module reconstructs identities and optimizer inputs only.  Importing it,
loading the queue, or binding a request never evaluates a molecular energy and
never starts an optimizer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from dvg_obs_ceo.composition import compose_registered_candidates
from dvg_obs_ceo.resources import AnsatzStructure
from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive
from v5_final.parent_native_execution_services import (
    ActualOptimizationBoundary,
    DurableWorkBoundary,
    _component_snapshot_digest,
)
from v5_final.parent_native_persistent_runner import (
    ParentNativePersistentRunner,
    make_attempt_id,
    publish_terminal_result_exclusive,
    replay_raw_ledger,
)
from v5_final.parent_native_work_accounting import (
    ComponentwiseCapRejected,
    ParentNativeWorkRequest,
    work_cap_digest,
)
from v5_final.semantic_contract_v2 import WorkDelta

from .a2_source_lock import _context, source_path
from .a3_grammar import (
    _representatives,
    case_path,
    structural_target_id,
)
from .a5_successor_v2 import (
    MAX_ENERGY_EVALUATIONS_PER_START,
    MAX_GRADIENT_VECTORS_PER_START,
    MAX_ITERATIONS_PER_START,
    QUEUE_PATH,
    STARTS,
    _decode,
    _digest,
    _float_hex,
    _initialization_id,
    _read_digest_valid,
    _v2_catalog,
)


class V2RunnerBindingError(RuntimeError):
    """Raised before kernel work when a frozen request cannot be reconstructed."""


S4_READINESS_PATH = (
    QUEUE_PATH.parents[1] / "s4-readiness" / "phase1-v2-s4-readiness-v1.json"
)


@dataclass(frozen=True)
class BoundV2Request:
    row: Mapping[str, Any]
    context: Any
    source_record: Mapping[str, Any]
    joint_plan: Any
    initial_coordinates: np.ndarray
    initial_inverse_hessian: np.ndarray
    target_structure: AnsatzStructure
    cap: WorkDelta
    work_request: ParentNativeWorkRequest


def _outcome_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


def load_frozen_queue(path: Path = QUEUE_PATH) -> dict[str, Any]:
    try:
        queue = _read_digest_valid(path, "queue_digest")
    except (FileNotFoundError, KeyError, ValueError) as error:
        raise V2RunnerBindingError("frozen v2 queue is absent or invalid") from error
    items = list(queue.get("items", ()))
    request_ids = [row.get("RequestID") for row in items]
    expected_order = sorted(
        items,
        key=lambda row: (
            row["case_id"],
            row["target_class"],
            row["CandidatePlanID"],
            row["start"],
        ),
    )
    if queue.get("status") != "FROZEN_NOT_STARTED":
        raise V2RunnerBindingError("queue is not in the frozen pre-outcome state")
    if len(items) != 1_266 or len(set(request_ids)) != len(items):
        raise V2RunnerBindingError("queue cardinality or RequestID uniqueness failed")
    if items != expected_order:
        raise V2RunnerBindingError("queue order differs from the frozen order")
    if any(row.get("status") != "NOT_STARTED" for row in items):
        raise V2RunnerBindingError("queue contains an outcome-bearing status")
    return queue


def _cap(dimension: int) -> WorkDelta:
    return WorkDelta(
        energy_evaluations=MAX_ENERGY_EVALUATIONS_PER_START,
        gradient_vector_evaluations=MAX_GRADIENT_VECTORS_PER_START,
        gradient_component_equivalents=(
            MAX_GRADIENT_VECTORS_PER_START * dimension
        ),
        optimizer_starts=1,
        optimizer_iterations=MAX_ITERATIONS_PER_START,
        resource_recounts=2,
        statevector_recomputations=2,
    )


@lru_cache(maxsize=4)
def _case_material(case_id: str, source_digest: str) -> tuple[Any, Any, Any, Any]:
    """Cache immutable reconstruction material, keyed by the verified source digest."""

    source_record = _read_digest_valid(source_path(case_id), "source_digest")
    if source_record["source_digest"] != source_digest:
        raise V2RunnerBindingError("source changed during request binding")
    context = _context(case_id)
    source, blocks, raw = _v2_catalog(case_id, source_record)
    representatives, _aliases = _representatives(raw)
    return context, source, blocks, representatives


def bind_request(request_id: str, *, queue_path: Path = QUEUE_PATH) -> BoundV2Request:
    """Rebuild one immutable queue row and bind it to kernel/accounting inputs."""

    queue = load_frozen_queue(queue_path)
    matches = [row for row in queue["items"] if row["RequestID"] == request_id]
    if len(matches) != 1:
        raise V2RunnerBindingError("unknown or duplicate frozen RequestID")
    row = matches[0]
    if row["start"] not in STARTS:
        raise V2RunnerBindingError("unregistered optimizer start")

    case_id = str(row["case_id"])
    source_record = _read_digest_valid(source_path(case_id), "source_digest")
    if row["B2SourceID"] != source_record["B2SourceID"]:
        raise V2RunnerBindingError("B2SourceID differs from the pinned source")
    context, source, blocks, representatives = _case_material(
        case_id, str(source_record["source_digest"])
    )
    candidate_by_id = {candidate.candidate_id: candidate for candidate in representatives}
    try:
        candidates = tuple(candidate_by_id[value] for value in row["candidate_ids"])
    except KeyError as error:
        raise V2RunnerBindingError("queue candidate is absent from the pinned catalog") from error
    joint_plan = compose_registered_candidates(source, blocks, candidates)
    grammar = _read_digest_valid(case_path(case_id), "case_digest")
    if row["target_class"] == "singleton":
        grammar_matches = [
            value
            for value in grammar["singletons"]
            if value["CandidatePlanID"] == row["CandidatePlanID"]
        ]
    elif row["target_class"] == "joint-K2":
        grammar_matches = [
            value
            for value in grammar["joints"]
            if value["CandidatePlanID"] == row["CandidatePlanID"]
        ]
    else:
        raise V2RunnerBindingError("unregistered target class")
    if len(grammar_matches) != 1:
        raise V2RunnerBindingError("CandidatePlanID is absent or duplicated in A3")
    grammar_row = grammar_matches[0]
    if row["target_class"] == "singleton":
        grammar_candidate_ids = grammar_row["candidate_ids"]
    else:
        grammar_candidate_ids = [
            grammar["singletons"][ordinal]["candidate_ids"][0]
            for ordinal in grammar_row["singleton_ordinals"]
        ]
    if sorted(grammar_candidate_ids) != sorted(row["candidate_ids"]):
        raise V2RunnerBindingError("CandidatePlanID and candidate membership differ")
    expected_target = structural_target_id(context.pool, joint_plan)
    if (
        row["StructuralTargetID"] != expected_target
        or grammar_row["StructuralTargetID"] != expected_target
    ):
        raise V2RunnerBindingError("StructuralTargetID reconstruction failed")

    coordinates = np.asarray(
        [_decode(value) for value in row["initial_coordinates_float64"]],
        dtype=np.float64,
    )
    if coordinates.ndim != 1 or len(coordinates) != len(joint_plan.target_indices):
        raise V2RunnerBindingError("optimizer coordinate dimension differs from target")
    expected_initialization = _initialization_id(
        str(row["CandidatePlanID"]),
        str(row["start"]),
        list(row["initial_coordinates_float64"]),
    )
    if row["OptimizationInitializationID"] != expected_initialization:
        raise V2RunnerBindingError("OptimizationInitializationID reconstruction failed")
    if row["initial_inverse_hessian_policy"] != "identity-target-dimension-v1":
        raise V2RunnerBindingError("initial inverse-Hessian policy is not frozen")

    transform = joint_plan.transformation
    mapped_source = np.asarray(transform.offset) + np.asarray(transform.jacobian) @ coordinates
    residual = np.asarray(transform.constraint_matrix) @ mapped_source - np.asarray(
        transform.constraint_rhs
    )
    if np.max(np.abs(residual), initial=0.0) > 1e-10:
        raise V2RunnerBindingError("frozen initialization violates the exact constraint")

    target_structure = AnsatzStructure.create(
        joint_plan.target_indices,
        coordinates,
        joint_plan.target_iteration_counts,
    )
    cap = _cap(len(coordinates))
    request = ParentNativeWorkRequest(
        queue_item_id=str(row["RequestID"]),
        method_id="same-structure-reoptimization",
        case_id=case_id,
        state_preparation_id=str(source_record["B2"]["StatePreparationID"]),
        problem_id=str(source_record["ProblemID"]),
        hamiltonian_digest=str(source_record["Hamiltonian_digest"]),
        source_checkpoint_digest=str(source_record["source_digest"]),
        frozen_queue_digest=str(queue["queue_digest"]),
        work_cap_digest=work_cap_digest(cap),
    )
    return BoundV2Request(
        row=row,
        context=context,
        source_record=source_record,
        joint_plan=joint_plan,
        initial_coordinates=coordinates,
        initial_inverse_hessian=np.eye(len(coordinates), dtype=np.float64),
        target_structure=target_structure,
        cap=cap,
        work_request=request,
    )


def _execute_bound_request(bound: BoundV2Request, execution_root: Path) -> dict[str, Any]:
    """Execute exactly one S4-authorized request through the durable boundary.

    The function exists for S3 validation but must not be called on the frozen
    molecular queue until the separate S4 readiness artifact authorizes S5.
    """

    request_id = str(bound.row["RequestID"])
    ledger_root = execution_root / "ledger"
    outcome_path = execution_root / "endpoint-outcome.json"
    terminal_path = execution_root / "terminal-result.json"
    if ledger_root.exists():
        state = replay_raw_ledger(
            ledger_root, request=bound.work_request, cap=bound.cap
        )
        if state.terminal is not None:
            if terminal_path.is_file():
                return json.loads(terminal_path.read_text(encoding="utf-8"))
            return publish_terminal_result_exclusive(
                terminal_path,
                ledger_root,
                request=bound.work_request,
                cap=bound.cap,
            )
        runner = ParentNativePersistentRunner.open(
            ledger_root, request=bound.work_request, cap=bound.cap
        )
        if outcome_path.is_file():
            outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
            observed = outcome.pop("outcome_digest", None)
            if observed != _outcome_digest(outcome):
                raise V2RunnerBindingError("interrupted endpoint outcome digest is invalid")
            runner.finish("ACCEPTED", outcome_digest=observed)
            return publish_terminal_result_exclusive(
                terminal_path,
                ledger_root,
                request=bound.work_request,
                cap=bound.cap,
            )
        raise V2RunnerBindingError(
            "active ledger has no certified outcome; exact rollback decision is required"
        )

    execution_root.mkdir(parents=True, exist_ok=False)
    attempt_id = make_attempt_id(
        bound.work_request, ordinal=1, nonce="phase1-v2-frozen-attempt-1"
    )
    runner = ParentNativePersistentRunner.create(
        ledger_root,
        request=bound.work_request,
        cap=bound.cap,
        attempt_id=attempt_id,
    )
    source_before = _component_snapshot_digest(bound.context.runtime)
    recorder = runner.resume_work_recorder()
    boundary = DurableWorkBoundary(runner, recorder)
    kernels = ActualOptimizationBoundary(
        bound.context._actual_algorithm, bound.context.pool, boundary
    )
    try:
        result = kernels.optimize(
            bound.initial_coordinates,
            bound.joint_plan.target_indices,
            bound.initial_inverse_hessian,
            maxiter=MAX_ITERATIONS_PER_START,
        )
        if not bool(result.success):
            runner.finish(
                "ALGORITHM_REJECTED",
                rejection_reason=f"PINNED_BFGS_STATUS_{int(result.status)}",
            )
            return publish_terminal_result_exclusive(
                terminal_path,
                ledger_root,
                request=bound.work_request,
                cap=bound.cap,
            )

        coordinates = np.asarray(result.x, dtype=np.float64)
        semantic_state = kernels.statevector(
            coordinates, bound.joint_plan.target_indices
        )
        independent_state = kernels.independent_statevector(
            coordinates, bound.joint_plan.target_indices
        )
        independent_energy = kernels.independent_energy(independent_state)
        independent_gradient = kernels.gradient(
            coordinates, bound.joint_plan.target_indices
        )
        structure = AnsatzStructure.create(
            bound.joint_plan.target_indices,
            coordinates,
            bound.joint_plan.target_iteration_counts,
        )
        resources_first = kernels.resources(structure)
        resources_second = kernels.resources(structure)
        transform = bound.joint_plan.transformation
        mapped_source = np.asarray(transform.offset) + np.asarray(
            transform.jacobian
        ) @ coordinates
        residual = np.asarray(transform.constraint_matrix) @ mapped_source - np.asarray(
            transform.constraint_rhs
        )
        constraint_residual = float(np.max(np.abs(residual), initial=0.0))
        gradient_inf = float(
            np.max(np.abs(independent_gradient), initial=0.0)
        )
        fidelity = float(abs(np.vdot(semantic_state, independent_state)) ** 2)
        checks = {
            "finite_endpoint": bool(
                np.isfinite(float(result.fun))
                and np.all(np.isfinite(coordinates))
                and np.all(np.isfinite(independent_gradient))
            ),
            "independent_energy_agreement": (
                abs(float(result.fun) - independent_energy) <= 1e-10
            ),
            "independent_state_fidelity": fidelity >= 1.0 - 1e-10,
            "independent_gradient_agreement": bool(
                np.asarray(result.jac).shape == independent_gradient.shape
                and np.max(
                    np.abs(np.asarray(result.jac) - independent_gradient), initial=0.0
                )
                <= 1e-8
            ),
            "stationary_endpoint": gradient_inf <= 1e-8,
            "exact_constraint": constraint_residual <= 1e-10,
            "resource_recount_repeatable": (
                resources_first.snapshot == resources_second.snapshot
                and resources_first.circuit_qasm_digest
                == resources_second.circuit_qasm_digest
            ),
        }
        if not all(checks.values()):
            runner.finish(
                "ALGORITHM_REJECTED",
                rejection_reason="INDEPENDENT_ENDPOINT_CERTIFICATION_FAILED",
            )
            return publish_terminal_result_exclusive(
                terminal_path,
                ledger_root,
                request=bound.work_request,
                cap=bound.cap,
            )
        outcome: dict[str, Any] = {
            "schema": "phase1-frontier.v2-certified-start-outcome.v1",
            "RequestID": request_id,
            "CandidatePlanID": bound.row["CandidatePlanID"],
            "StructuralTargetID": bound.row["StructuralTargetID"],
            "start": bound.row["start"],
            "energy_hartree": float(result.fun),
            "independent_energy_hartree": independent_energy,
            "delta_energy_from_B2_hartree": (
                float(result.fun) - float(bound.source_record["B2"]["energy_hartree"])
            ),
            "coordinates_float64": _float_hex(coordinates),
            "gradient_infinity_norm": gradient_inf,
            "state_fidelity": fidelity,
            "constraint_residual": constraint_residual,
            "resources": asdict(resources_first.snapshot),
            "qasm_digest": resources_first.circuit_qasm_digest,
            "optimizer": {
                "status": int(result.status),
                "iterations": int(result.nit),
                "energy_evaluations": int(result.nfev),
                "gradient_evaluations": int(result.njev),
            },
            "checks": checks,
            "scientific_compression_acceptance": "DEFERRED_UNTIL_PAIRED_TERMINAL_ANALYSIS",
            "FCI_evaluations": 0,
        }
        outcome["outcome_digest"] = _outcome_digest(outcome)
        write_json_exclusive(outcome_path, outcome)
        runner.finish("ACCEPTED", outcome_digest=outcome["outcome_digest"])
        return publish_terminal_result_exclusive(
            terminal_path,
            ledger_root,
            request=bound.work_request,
            cap=bound.cap,
        )
    except ComponentwiseCapRejected:
        runner.finish("CAP_REJECTED", rejection_reason="COMPONENTWISE_CAP_EXCEEDED")
        return publish_terminal_result_exclusive(
            terminal_path,
            ledger_root,
            request=bound.work_request,
            cap=bound.cap,
        )
    except Exception as error:
        if runner.state().terminal is not None:
            raise
        source_after = _component_snapshot_digest(bound.context.runtime)
        runner.rollback_active_attempt(
            component_digests_before=source_before,
            component_digests_after=source_after,
            reason=type(error).__name__,
        )
        runner.finish("KERNEL_FAILURE", rejection_reason=type(error).__name__)
        raise


def execute_bound_request(request_id: str, execution_root: Path) -> dict[str, Any]:
    """Run one molecular queue request only after the authoritative S4 Go."""

    try:
        readiness = _read_digest_valid(S4_READINESS_PATH, "readiness_digest")
    except (FileNotFoundError, KeyError, ValueError) as error:
        raise V2RunnerBindingError(
            "molecular outcome execution is blocked until a valid S4 readiness Go"
        ) from error
    if (
        readiness.get("decision") != "GO_PHASE1_V2_FROZEN_SCREEN_EXECUTION"
        or readiness.get("queue_sha256")
        != hashlib.sha256(QUEUE_PATH.read_bytes()).hexdigest()
    ):
        raise V2RunnerBindingError("S4 readiness does not authorize this exact queue")
    return _execute_bound_request(bind_request(request_id), execution_root)
