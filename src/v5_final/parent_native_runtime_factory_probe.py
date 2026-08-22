"""Outcome-free integration and negative probes for the S3 runtime factory."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
from typing import Any, Iterator

from adaptvqe.algorithms.adapt_vqe import LinAlgAdapt

from .parent_native_runtime_factory import (
    CATALOG_PATH,
    QUEUE_PATH,
    CandidateOutcomeNotAuthorized,
    QueueBoundRuntimeError,
    _artifact_digest,
    build_s3_corrected_environment,
    build_queue_bound_runtime,
    preflight_queue_binding,
    project_queue_to_environment,
)


@contextmanager
def _candidate_kernel_guard() -> Iterator[dict[str, int]]:
    forbidden = (
        "initialize",
        "run",
        "run_iteration",
        "evaluate_energy",
        "estimate_gradients",
        "estimate_hessian",
        "optimize",
    )
    originals = {name: getattr(LinAlgAdapt, name) for name in forbidden}
    calls = {name: 0 for name in forbidden}
    original_compute_state = LinAlgAdapt.compute_state
    calls["compute_state"] = 0

    def blocked(name: str):
        def stop(*_: Any, **__: Any) -> Any:
            calls[name] += 1
            raise RuntimeError(f"S3 candidate outcome guard blocked: {name}")

        return stop

    def counted_compute_state(*args: Any, **kwargs: Any) -> Any:
        calls["compute_state"] += 1
        return original_compute_state(*args, **kwargs)

    try:
        for name in forbidden:
            setattr(LinAlgAdapt, name, blocked(name))
        LinAlgAdapt.compute_state = counted_compute_state
        yield calls
    finally:
        for name, value in originals.items():
            setattr(LinAlgAdapt, name, value)
        LinAlgAdapt.compute_state = original_compute_state


def _refresh_queue_digest(queue: dict[str, Any]) -> None:
    queue.pop("queue_digest", None)
    queue["queue_digest"] = _artifact_digest(queue)


def _refresh_item_identity(item: dict[str, Any]) -> None:
    item.pop("queue_item_id", None)
    item["queue_item_id"] = "mb6-calibration-item-v2:" + _artifact_digest(item)


def _negative_preflight_checks(
    queue: dict[str, Any], environment: dict[str, Any]
) -> dict[str, bool]:
    catalog = json.loads(CATALOG_PATH.read_text())
    selected = next(
        item
        for item in queue["items"]
        if item["case_id"] == "h2-1.5-iteration-1"
        and item["method_id"] == "immutable-ceo-star-source"
    )

    identity_tamper = deepcopy(queue)
    target = next(
        item
        for item in identity_tamper["items"]
        if item["queue_item_id"] == selected["queue_item_id"]
    )
    target["StatePreparationID"] = "state-v1:" + "0" * 64
    _refresh_item_identity(target)
    _refresh_queue_digest(identity_tamper)
    identity_rejected = False
    try:
        preflight_queue_binding(
            target["queue_item_id"],
            queue_record=identity_tamper,
            catalog_record=catalog,
            environment_record=environment,
        )
    except QueueBoundRuntimeError:
        identity_rejected = True

    checkpoint_tamper = deepcopy(catalog)
    case = next(
        value
        for value in checkpoint_tamper["cases"]
        if value["case_id"] == "h2-1.5-iteration-1"
    )
    case["source_checkpoint_sha256"] = "0" * 64
    checkpoint_tamper.pop("probe_digest", None)
    checkpoint_tamper["probe_digest"] = _artifact_digest(checkpoint_tamper)
    checkpoint_queue = deepcopy(queue)
    checkpoint_queue["catalog_digest"] = checkpoint_tamper["probe_digest"]
    changed_id = None
    for item in checkpoint_queue["items"]:
        if item["case_id"] == "h2-1.5-iteration-1":
            was_selected = item["queue_item_id"] == selected["queue_item_id"]
            item["source_checkpoint_sha256"] = "0" * 64
            _refresh_item_identity(item)
            if was_selected:
                changed_id = item["queue_item_id"]
    _refresh_queue_digest(checkpoint_queue)
    checkpoint_rejected = False
    try:
        preflight_queue_binding(
            str(changed_id),
            queue_record=checkpoint_queue,
            catalog_record=checkpoint_tamper,
            environment_record=environment,
        )
    except QueueBoundRuntimeError:
        checkpoint_rejected = True
    return {
        "queue_identity_mismatch_rejected_pre_algorithm": identity_rejected,
        "checkpoint_file_mismatch_rejected_pre_algorithm": checkpoint_rejected,
    }


def build() -> dict[str, Any]:
    original_queue = json.loads(QUEUE_PATH.read_text())
    environment = build_s3_corrected_environment()
    queue = project_queue_to_environment(original_queue, environment)
    selected = [
        next(
            item
            for item in queue["items"]
            if item["case_id"] == case_id
            and item["method_id"] == "immutable-ceo-star-source"
        )
        for case_id in (
            "h2-1.5-iteration-1",
            "h4-1.5-first-chemical-accuracy",
        )
    ]
    with _candidate_kernel_guard() as calls:
        contexts = [
            build_queue_bound_runtime(
                item["queue_item_id"],
                queue_record=queue,
                environment_record=environment,
            )
            for item in selected
        ]
    guard_checks = []
    for context in contexts:
        blocked = False
        try:
            context.algorithm.evaluate_energy([], [])
        except CandidateOutcomeNotAuthorized:
            blocked = True
        guard_checks.append(blocked)
    cases = [
        {
            "case_id": context.case_id,
            "queue_item_id": context.queue_item_id,
            "method_id": context.method_id,
            "actual_algorithm_type": type(context._actual_algorithm).__name__,
            "actual_pool_type": type(context.pool).__name__,
            "actual_runtime_type": type(context.runtime).__name__,
            "ProblemID": context.problem_id,
            "Hamiltonian_digest": context.hamiltonian_digest,
            "StatePreparationID": context.state_preparation_id,
            "source_checkpoint_digest": context.source_checkpoint_digest,
            "source_statevector_sha256": context.source_statevector_sha256,
            "source_resources": context.source_resources,
            "ansatz_dimension": len(context.runtime.ansatz.indices),
            "gradient_dimension": len(context.runtime.gradient),
            "inverse_hessian_dimension": len(context.runtime.inverse_hessian),
            "source_statevector_recomputations": (
                context.source_statevector_recomputations
            ),
            "FCI_used": context._actual_algorithm.molecule.fci_energy is not None,
            "CCSD_used": context._actual_algorithm.molecule.ccsd_energy is not None,
            "pre_GO_algorithm_guard_verified": guard,
        }
        for context, guard in zip(contexts, guard_checks, strict=True)
    ]
    candidate_calls = {
        name: count for name, count in calls.items() if name != "compute_state"
    }
    return {
        "schema": "v5-final.s3-queue-bound-runtime-factory-probe.v1",
        "cases": cases,
        "negative_preflight": _negative_preflight_checks(queue, environment),
        "corrected_environment_digest": environment["environment_digest"],
        "projected_unfrozen_queue_digest": queue["queue_digest"],
        "projected_queue_written_or_authorized": False,
        "candidate_kernel_calls": candidate_calls,
        "source_statevector_recomputations": calls["compute_state"],
        "candidate_energy_evaluations": calls["evaluate_energy"],
        "optimizer_calls": calls["optimize"],
        "academic_boundary": (
            "Only pinned source checkpoints and source statevectors were reconstructed; "
            "no candidate energy, optimizer, FCI, or CCSD outcome was evaluated."
        ),
    }


def main() -> None:
    print(json.dumps(build(), sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
