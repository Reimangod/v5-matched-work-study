"""Queue-bound construction of actual parent molecular runtimes.

The factory validates every frozen identity before it constructs the molecular
algorithm.  It reconstructs the already-frozen source statevector, but it does
not initialize ADAPT, evaluate a candidate energy, rank a candidate, or run an
optimizer.  The returned algorithm facade blocks all outcome kernels until the
future S8 production-GO artifact is present and valid.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Mapping

import numpy as np

from dvg_obs_ceo.identity import canonical_json_bytes as parent_canonical_json_bytes
from dvg_obs_ceo.molecular_identity import problem_spec, state_preparation_spec
from dvg_obs_ceo.resources import (
    AnsatzStructure,
    evaluate_full_circuit_resources,
    paper_era_backend,
)
from dvg_obs_ceo.telemetry import WorkCounters
from dvg_obs_ceo.transaction import CompressionRuntime
from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .mb6_source_catalog_probe import CASES, _algorithm_outcome_free
from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT


QUEUE_PATH = ROOT / "artifacts/v5-final/mb6-v2/h2-h4-calibration-queue-v2.json"
CATALOG_PATH = ROOT / "artifacts/v5-final/mb6-v2/h2-h4-source-catalog-v2.json"
ENVIRONMENT_PATH = ROOT / "artifacts/v5-final/mb6-v2/execution-environment-v2.json"
S8_GO_PATH = ROOT / "artifacts/v5-final/production/s8-h2-h4-production-go-v1.json"
PARENT_ROOT = ROOT / "provenance/dvg-obs-ceo"
CEO_ROOT = PARENT_ROOT / "vendor/ceo-adapt-vqe"


class QueueBoundRuntimeError(RuntimeError):
    pass


class CandidateOutcomeNotAuthorized(QueueBoundRuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _parent_digest(value: Any) -> str:
    return hashlib.sha256(parent_canonical_json_bytes(value)).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_embedded_digest(
    value: Mapping[str, Any], field: str, *, parent_encoding: bool = False
) -> None:
    body = dict(value)
    observed = body.pop(field, None)
    expected = _parent_digest(body) if parent_encoding else _artifact_digest(body)
    if observed != expected:
        raise QueueBoundRuntimeError(f"{field} mismatch")


def _git_output(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _verify_pinned_kernels(environment: Mapping[str, Any]) -> dict[str, str]:
    observed = {
        "parent": _git_output(PARENT_ROOT, "rev-parse", "HEAD"),
        "CEO": _git_output(CEO_ROOT, "rev-parse", "HEAD"),
    }
    expected = {
        "parent": str(environment["parent_commit"]),
        "CEO": str(environment["CEO_commit"]),
    }
    if expected != {"parent": PARENT_COMMIT, "CEO": CEO_COMMIT}:
        raise QueueBoundRuntimeError("environment does not name the pinned kernels")
    if observed != expected:
        raise QueueBoundRuntimeError("checked-out molecular kernel commit drifted")
    if _git_output(PARENT_ROOT, "status", "--porcelain", "--untracked-files=no"):
        raise QueueBoundRuntimeError("parent molecular kernel has tracked modifications")
    if _git_output(CEO_ROOT, "status", "--porcelain", "--untracked-files=no"):
        raise QueueBoundRuntimeError("CEO molecular kernel has tracked modifications")
    return observed


def _verify_environment(environment: Mapping[str, Any]) -> dict[str, Any]:
    _verify_embedded_digest(environment, "environment_digest")
    runtime = {
        "byte_order": sys.byteorder,
        "machine": platform.machine().lower(),
        "python_implementation": platform.python_implementation().lower(),
        "python_version": platform.python_version(),
        "system": platform.system().lower(),
    }
    if runtime != environment["runtime"]:
        raise QueueBoundRuntimeError("runtime platform differs from frozen environment")
    required_threads = dict(environment["required_threads"])
    observed_threads = {name: os.environ.get(name) for name in required_threads}
    if observed_threads != required_threads:
        raise QueueBoundRuntimeError("thread environment differs from frozen environment")
    locks = environment["dependency_locks"]
    observed_locks = {
        "parent_uv_lock_sha256": _sha(PARENT_ROOT / "uv.lock"),
        "root_uv_lock_sha256": _sha(ROOT / "uv.lock"),
    }
    if observed_locks != locks:
        raise QueueBoundRuntimeError("dependency lock digest drifted")
    commits = _verify_pinned_kernels(environment)
    return {
        "runtime": runtime,
        "threads": observed_threads,
        "dependency_locks": observed_locks,
        "commits": commits,
    }


def _verify_queue(queue: Mapping[str, Any]) -> None:
    _verify_embedded_digest(queue, "queue_digest")
    items = list(queue.get("items", ()))
    if (
        queue.get("status") != "FROZEN_NOT_AUTHORIZED_FOR_EXECUTION"
        or queue.get("frozen_item_count") != 36
        or len(items) != 36
        or queue.get("candidate_energy_evaluations") != 0
    ):
        raise QueueBoundRuntimeError("queue is not the frozen, unexecuted 36-item queue")
    rebuilt_ids = []
    for item in items:
        body = {key: value for key, value in item.items() if key != "queue_item_id"}
        expected = "mb6-calibration-item-v2:" + _artifact_digest(body)
        if item.get("queue_item_id") != expected:
            raise QueueBoundRuntimeError("queue item identity mismatch")
        if item.get("terminal_status") != "NOT_STARTED":
            raise QueueBoundRuntimeError("queue item is not outcome-free")
        rebuilt_ids.append(expected)
    if len(set(rebuilt_ids)) != 36:
        raise QueueBoundRuntimeError("queue item identities are not unique")


def _verify_catalog(catalog: Mapping[str, Any]) -> None:
    _verify_embedded_digest(catalog, "probe_digest")
    cases = list(catalog.get("cases", ()))
    if (
        len(cases) != 2
        or {case.get("case_id") for case in cases} != set(CASES)
        or catalog.get("candidate_energy_evaluations") != 0
    ):
        raise QueueBoundRuntimeError("source catalog is not the two-case outcome-free catalog")


def build_s3_corrected_environment() -> dict[str, Any]:
    """Return the additive, outcome-free correction needed for exact H4 identity.

    MB6-v2 recorded single-thread execution, but its frozen H4 Hamiltonian was
    produced reproducibly with two BLAS/OpenMP threads.  The old artifact stays
    immutable; S7 will bind its successor queue to this corrected environment.
    """

    environment = _json(ENVIRONMENT_PATH)
    _verify_embedded_digest(environment, "environment_digest")
    result = {
        key: deepcopy(value)
        for key, value in environment.items()
        if key not in {"schema", "environment_digest", "successor_provenance"}
    }
    result["schema"] = "v5-final.s3-execution-environment-correction.v1"
    result["required_threads"] = {
        "MKL_NUM_THREADS": "2",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
    }
    result["correction_provenance"] = {
        "superseded_environment_path": str(ENVIRONMENT_PATH.relative_to(ROOT)),
        "superseded_environment_sha256": _sha(ENVIRONMENT_PATH),
        "allowed_change": "required thread counts only",
        "scientific_protocol_changed": False,
        "reason": (
            "exact reproduction of both frozen Hamiltonian digests; "
            "single-thread H4 differs at the byte-level"
        ),
    }
    result["environment_digest"] = _artifact_digest(result)
    return result


def project_queue_to_environment(
    queue: Mapping[str, Any], environment: Mapping[str, Any]
) -> dict[str, Any]:
    """Project MB6-v2 IDs to an environment for an unfrozen S3 dry run.

    This never writes or authorizes a queue.  S7 independently creates the
    versioned, byte-reproducible MB6-v3 successor after all executor work.
    """

    _verify_queue(queue)
    _verify_embedded_digest(environment, "environment_digest")
    result = deepcopy(dict(queue))
    result["environment_digest"] = environment["environment_digest"]
    for item in result["items"]:
        item["environment_digest"] = environment["environment_digest"]
        body = {key: value for key, value in item.items() if key != "queue_item_id"}
        item["queue_item_id"] = "mb6-calibration-item-v2:" + _artifact_digest(body)
    result.pop("queue_digest", None)
    result["queue_digest"] = _artifact_digest(result)
    return result


@dataclass(frozen=True)
class QueueSourceBinding:
    queue_item: dict[str, Any]
    catalog_case: dict[str, Any]
    checkpoint: dict[str, Any]
    checkpoint_path: Path
    queue_digest: str
    catalog_digest: str
    environment_digest: str
    environment_observation: dict[str, Any]


def preflight_queue_binding(
    queue_item_id: str,
    *,
    queue_record: Mapping[str, Any] | None = None,
    catalog_record: Mapping[str, Any] | None = None,
    environment_record: Mapping[str, Any] | None = None,
) -> QueueSourceBinding:
    """Validate queue, source, and environment before any molecular build."""

    queue = deepcopy(dict(queue_record)) if queue_record is not None else _json(QUEUE_PATH)
    catalog = (
        deepcopy(dict(catalog_record))
        if catalog_record is not None
        else _json(CATALOG_PATH)
    )
    environment = (
        deepcopy(dict(environment_record))
        if environment_record is not None
        else _json(ENVIRONMENT_PATH)
    )
    _verify_queue(queue)
    _verify_catalog(catalog)
    environment_observation = _verify_environment(environment)
    if queue["catalog_digest"] != catalog["probe_digest"]:
        raise QueueBoundRuntimeError("queue is not bound to the source catalog")
    if queue["environment_digest"] != environment["environment_digest"]:
        raise QueueBoundRuntimeError("queue is not bound to the execution environment")
    matches = [item for item in queue["items"] if item["queue_item_id"] == queue_item_id]
    if len(matches) != 1:
        raise QueueBoundRuntimeError("queue item is absent or duplicated")
    item = matches[0]
    case_matches = [case for case in catalog["cases"] if case["case_id"] == item["case_id"]]
    if len(case_matches) != 1:
        raise QueueBoundRuntimeError("catalog case is absent or duplicated")
    case = case_matches[0]
    identity_fields = (
        "StatePreparationID",
        "ProblemID",
        "Hamiltonian_digest",
        "source_checkpoint_digest",
        "source_checkpoint_sha256",
    )
    if any(item.get(field) != case.get(field) for field in identity_fields):
        raise QueueBoundRuntimeError("queue item and source catalog identity mismatch")
    if item.get("environment_digest") != environment["environment_digest"]:
        raise QueueBoundRuntimeError("queue item environment identity mismatch")

    checkpoint_path = (ROOT / str(case["source_checkpoint_path"])).resolve()
    allowed_path = CASES[str(item["case_id"])].resolve()
    if checkpoint_path != allowed_path or checkpoint_path.parent != allowed_path.parent:
        raise QueueBoundRuntimeError("source checkpoint path is not the pinned calibration path")
    if _sha(checkpoint_path) != item["source_checkpoint_sha256"]:
        raise QueueBoundRuntimeError("source checkpoint file digest mismatch")
    checkpoint = _json(checkpoint_path)
    _verify_embedded_digest(checkpoint, "checkpoint_digest", parent_encoding=True)
    if (
        checkpoint["case_id"] != item["case_id"]
        or checkpoint["checkpoint_digest"] != item["source_checkpoint_digest"]
    ):
        raise QueueBoundRuntimeError("source checkpoint semantic identity mismatch")
    return QueueSourceBinding(
        item,
        case,
        checkpoint,
        checkpoint_path,
        str(queue["queue_digest"]),
        str(catalog["probe_digest"]),
        str(environment["environment_digest"]),
        environment_observation,
    )


class OutcomeBlockedAlgorithm:
    """Read-only facade that blocks every molecular outcome entrypoint."""

    _BLOCKED = frozenset(
        {
            "initialize",
            "run",
            "run_iteration",
            "get_state",
            "compute_state",
            "evaluate_energy",
            "evaluate_observable",
            "estimate_gradients",
            "estimate_gradient",
            "estimate_hessian",
            "optimize",
        }
    )

    def __init__(self, algorithm: Any) -> None:
        self.__algorithm = algorithm

    def __getattr__(self, name: str) -> Any:
        if name in self._BLOCKED:
            def blocked(*_: Any, **__: Any) -> Any:
                raise CandidateOutcomeNotAuthorized(
                    f"molecular outcome kernel is blocked before S8 GO: {name}"
                )

            return blocked
        return getattr(self.__algorithm, name)


@dataclass(frozen=True)
class QueueBoundMolecularRuntime:
    queue_item_id: str
    case_id: str
    method_id: str
    queue_digest: str
    catalog_digest: str
    environment_digest: str
    source_checkpoint_digest: str
    source_statevector_sha256: str
    problem_id: str
    hamiltonian_digest: str
    state_preparation_id: str
    source_resources: dict[str, int]
    source_statevector_recomputations: int
    algorithm: OutcomeBlockedAlgorithm
    pool: Any
    runtime: CompressionRuntime
    _actual_algorithm: Any

    def release_for_h2_h4_execution(self) -> Any:
        """Release the actual algorithm only through the future S8 GO artifact."""

        if not S8_GO_PATH.exists():
            raise CandidateOutcomeNotAuthorized("S8 production-GO artifact does not exist")
        gate = _json(S8_GO_PATH)
        _verify_embedded_digest(gate, "gate_digest")
        if (
            gate.get("schema") != "v5-final.s8-production-go-gate.v1"
            or gate.get("decision") != "GO_H2_H4_CALIBRATION_ONLY"
            or gate.get("candidate_energy_evaluations_before_GO") != 0
            or gate.get("queue_digest") != self.queue_digest
            or not all(gate.get("checks", {}).values())
            or gate.get("authorization", {}).get("H2_H4_execution")
            != "AUTHORIZED_ONLY"
        ):
            raise CandidateOutcomeNotAuthorized("S8 production-GO artifact is invalid")
        return self._actual_algorithm


def _resource_vector(result: Any) -> dict[str, int]:
    snapshot = result.snapshot
    return {
        "cnot_count": int(snapshot.cnot_count),
        "cnot_depth": int(snapshot.cnot_depth),
        "total_depth": int(snapshot.total_depth),
        "parameter_count": int(snapshot.parameter_count),
        "logical_block_count": int(snapshot.logical_block_count),
    }


def build_queue_bound_runtime(
    queue_item_id: str,
    *,
    queue_record: Mapping[str, Any] | None = None,
    catalog_record: Mapping[str, Any] | None = None,
    environment_record: Mapping[str, Any] | None = None,
) -> QueueBoundMolecularRuntime:
    binding = preflight_queue_binding(
        queue_item_id,
        queue_record=queue_record,
        catalog_record=catalog_record,
        environment_record=environment_record,
    )
    item = binding.queue_item
    catalog_case = binding.catalog_case
    checkpoint = binding.checkpoint
    algorithm, pool = _algorithm_outcome_free(str(item["case_id"]))
    if algorithm.molecule.fci_energy is not None or algorithm.molecule.ccsd_energy is not None:
        raise QueueBoundRuntimeError("FCI/CCSD outcome entered source construction")

    problem = problem_spec(algorithm=algorithm, case_id=str(item["case_id"]))
    problem_checks = {
        "ProblemID": problem.problem_id == item["ProblemID"],
        "Hamiltonian_digest": (
            problem.hamiltonian_digest == item["Hamiltonian_digest"]
        ),
        "problem_payload": problem.payload() == catalog_case["problem_payload"],
    }
    if not all(problem_checks.values()):
        failed = ", ".join(
            name for name, passed in problem_checks.items() if not passed
        )
        raise QueueBoundRuntimeError(
            "actual molecular problem differs from frozen identity: " + failed
        )

    structure = AnsatzStructure.create(
        checkpoint["ansatz_indices"],
        checkpoint["ansatz_coefficients"],
        checkpoint["iteration_counts"],
    )
    resources = evaluate_full_circuit_resources(pool, structure, paper_era_backend())
    resource_vector = _resource_vector(resources)
    if resource_vector != catalog_case["source_resources"]:
        raise QueueBoundRuntimeError("actual source resources differ from frozen catalog")

    source_state = np.asarray(
        algorithm.compute_state(
            list(structure.coefficients), list(structure.indices)
        ).toarray(),
        dtype=np.complex128,
    ).ravel()
    source_state /= np.linalg.norm(source_state)
    state_sha = hashlib.sha256(
        np.asarray(source_state, dtype=">c16").tobytes()
    ).hexdigest()
    if state_sha != checkpoint["statevector_sha256"]:
        raise QueueBoundRuntimeError("actual source statevector differs from checkpoint")

    runtime = CompressionRuntime.create(
        ansatz=structure,
        energy_hartree=float(checkpoint["energy_hartree"]),
        gradient=checkpoint["gradient"],
        inverse_hessian=checkpoint["recycled_inverse_hessian"],
        statevector=source_state,
        work=WorkCounters(),
        adapt_iteration=len(structure.cumulative_parameter_counts),
        metadata={
            "resource_structure_digest": resources.snapshot.structure_digest,
            "budget_reference_energy_hartree": float(checkpoint["energy_hartree"]),
            "queue_item_id": queue_item_id,
            "source_checkpoint_digest": checkpoint["checkpoint_digest"],
            "ProblemID": problem.problem_id,
            "source_statevector_recomputations": 1,
        },
    )
    state = state_preparation_spec(runtime, algorithm=algorithm, pool=pool)
    if (
        state.state_preparation_id != item["StatePreparationID"]
        or state.payload() != catalog_case["state_preparation_payload"]
    ):
        raise QueueBoundRuntimeError("actual source preparation differs from frozen identity")
    return QueueBoundMolecularRuntime(
        queue_item_id=queue_item_id,
        case_id=str(item["case_id"]),
        method_id=str(item["method_id"]),
        queue_digest=binding.queue_digest,
        catalog_digest=binding.catalog_digest,
        environment_digest=binding.environment_digest,
        source_checkpoint_digest=str(checkpoint["checkpoint_digest"]),
        source_statevector_sha256=state_sha,
        problem_id=problem.problem_id,
        hamiltonian_digest=problem.hamiltonian_digest,
        state_preparation_id=state.state_preparation_id,
        source_resources=resource_vector,
        source_statevector_recomputations=1,
        algorithm=OutcomeBlockedAlgorithm(algorithm),
        pool=pool,
        runtime=runtime,
        _actual_algorithm=algorithm,
    )
