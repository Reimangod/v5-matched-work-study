"""Pinned upstream H2 exact-statevector worker for the S4 production smoke.

The worker writes JSON Lines only. Raw operations are flushed before the next
operation, allowing the host executor to append semantic events on the live
execution path rather than reconstructing them from a final report.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import struct
import sys
import time
from typing import Any, Callable

import numpy as np


WORK_FIELDS = (
    "energy_evaluations",
    "gradient_vector_evaluations",
    "gradient_component_equivalents",
    "hvp_evaluations",
    "optimizer_starts",
    "optimizer_iterations",
    "resource_recounts",
    "candidate_generations",
    "search_states",
    "rewrite_verifications",
    "statevector_recomputations",
)


def _line(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True)


class RawEmitter:
    def __init__(self) -> None:
        self.total = {field: 0 for field in WORK_FIELDS}

    def emit(
        self,
        event_type: str,
        *,
        scientific_value: dict[str, str] | None = None,
        **delta: int,
    ) -> None:
        for field, value in delta.items():
            if field not in self.total or isinstance(value, bool) or value < 0:
                raise RuntimeError("invalid raw counter delta")
            self.total[field] += value
        _line(
            {
                "kind": "raw-operation",
                "event_type": event_type,
                "work_delta": {field: delta.get(field, 0) for field in WORK_FIELDS},
                "raw_counter_after": dict(self.total),
                "scientific_value": scientific_value,
            }
        )


def _float_bytes(value: float) -> str:
    if not math.isfinite(float(value)):
        raise RuntimeError("nonfinite float cannot enter exact circuit identity")
    return struct.pack(">d", float(value)).hex()


def _state_digest(state: Any) -> str:
    vector = np.asarray(state.toarray(), dtype=np.complex128).ravel()
    vector /= np.linalg.norm(vector)
    return hashlib.sha256(np.asarray(vector, dtype=">c16").tobytes()).hexdigest()


def _sparse_digest(matrix: Any) -> str:
    value = matrix.tocsr()
    payload = (
        np.asarray(value.shape, dtype=">i8").tobytes()
        + np.asarray(value.indptr, dtype=">i8").tobytes()
        + np.asarray(value.indices, dtype=">i8").tobytes()
        + np.asarray(value.data, dtype=">c16").tobytes()
    )
    return hashlib.sha256(payload).hexdigest()


def _reference_bits(state: Any, qubits: int) -> list[int]:
    array = np.asarray(state.toarray()).ravel()
    nonzero = np.flatnonzero(np.abs(array) > 1e-12)
    if nonzero.size != 1:
        raise RuntimeError("upstream reference is not a computational basis state")
    index = int(nonzero[0])
    return [(index >> qubit) & 1 for qubit in range(qubits)]


def _native_gates(pool: Any, indices: list[int], coefficients: list[float]) -> list[dict[str, Any]]:
    circuit = pool.get_circuit(indices, coefficients)
    result = []
    for instruction in circuit.data:
        operation = instruction.operation
        result.append(
            {
                "gate": operation.name,
                "qubits": [circuit.find_bit(qubit).index for qubit in instruction.qubits],
                "parameter_bytes": [_float_bytes(float(value)) for value in operation.params],
            }
        )
    if not result:
        raise RuntimeError("actual upstream circuit unexpectedly contains no gates")
    return result


def _load_kernel() -> tuple[Any, Any, Any, Any, Any, Any]:
    from dvg_obs_ceo.baseline import verify_upstream
    from dvg_obs_ceo.block_ir import recover_dvg_blocks
    from dvg_obs_ceo.identity import ProblemSpec
    from dvg_obs_ceo.resources import (
        AnsatzStructure,
        evaluate_full_circuit_resources,
        paper_era_backend,
        resources_to_dict,
    )
    from dvg_obs_ceo.s8_probe import _algorithm

    provenance = verify_upstream()
    with contextlib.redirect_stdout(sys.stderr):
        algorithm, pool = _algorithm("h2-1.5-iteration-1")
        algorithm.initialize()
    return (
        algorithm,
        pool,
        provenance,
        recover_dvg_blocks,
        ProblemSpec,
        (AnsatzStructure, evaluate_full_circuit_resources, paper_era_backend, resources_to_dict),
    )


def _structure_payload(
    algorithm: Any,
    pool: Any,
    indices: list[int],
    coefficients: list[float],
    counts: list[int],
    recover_blocks: Callable[..., Any],
    resource_api: tuple[Any, Any, Any, Any],
    emitter: RawEmitter,
) -> dict[str, Any]:
    AnsatzStructure, evaluate_resources, paper_backend, resources_to_dict = resource_api
    structure = AnsatzStructure.create(indices, coefficients, counts)
    resources = resources_to_dict(evaluate_resources(pool, structure, paper_backend()))
    emitter.emit("RESOURCE_RECOUNTED", resource_recounts=1)
    blocks = recover_blocks(pool, indices, coefficients, counts)
    generators = []
    for block in blocks:
        for position, support in zip(block.ansatz_positions, [block.support_qubits] * len(block.ansatz_positions)):
            sign = -1 if block.orientation == "diff" else 1
            generators.append(
                {
                    "support": list(support),
                    "operator_family": block.family + ":" + block.generator_digests[
                        block.ansatz_positions.index(position)
                    ],
                    "sign": sign,
                    "coefficient_bytes": _float_bytes(coefficients[position]),
                }
            )
    return {
        "ansatz_indices": indices,
        "coefficient_bytes": [_float_bytes(value) for value in coefficients],
        "cumulative_parameter_counts": counts,
        "block_order": [block.block_id for block in blocks],
        "generator_semantics": generators,
        "target_structure": {
            "block_ids": [block.block_id for block in blocks],
            "families": [block.family for block in blocks],
            "upstream_pool_indices": indices,
        },
        "native_circuit_semantics": _native_gates(pool, indices, coefficients),
        "resources": resources["snapshot"],
        "circuit_digest": resources["circuit_qasm_digest"],
    }


def inspect(request: dict[str, Any]) -> dict[str, Any]:
    emitter = RawEmitter()
    algorithm, pool, provenance, recover_blocks, ProblemSpec, resource_api = _load_kernel()
    source = request["source"]
    indices = [int(value) for value in source["ansatz_indices"]]
    coefficients = [float(value) for value in source["ansatz_coefficients"]]
    counts = [int(value) for value in source["cumulative_parameter_counts"]]
    delta = float(request["candidate_coefficient_delta"])
    candidate_coefficients = list(coefficients)
    candidate_coefficients[0] += delta
    source_payload = _structure_payload(
        algorithm, pool, indices, coefficients, counts, recover_blocks, resource_api, emitter
    )
    source_energy = float(algorithm.evaluate_energy(coefficients, indices))
    emitter.emit(
        "ENERGY_EVALUATED",
        energy_evaluations=1,
        scientific_value={"quantity": "source_energy", "value": repr(source_energy)},
    )
    source_gradient = np.asarray(
        algorithm.estimate_gradients(coefficients, indices, method="an"), dtype=np.float64
    )
    source_gradient_infinity = float(np.max(np.abs(source_gradient))) if source_gradient.size else 0.0
    emitter.emit(
        "GRADIENT_EVALUATED",
        gradient_vector_evaluations=1,
        gradient_component_equivalents=int(source_gradient.size),
        scientific_value={
            "quantity": "source_gradient_infinity",
            "value": repr(source_gradient_infinity),
        },
    )
    source_state = algorithm.compute_state(coefficients, indices)
    emitter.emit("STATEVECTOR_RECOMPUTED", statevector_recomputations=1)
    candidate_payload = _structure_payload(
        algorithm,
        pool,
        indices,
        candidate_coefficients,
        counts,
        recover_blocks,
        resource_api,
        emitter,
    )
    hamiltonian_digest = _sparse_digest(algorithm.hamiltonian)
    problem = ProblemSpec(
        hamiltonian_digest=hamiltonian_digest,
        molecule="H2",
        geometry_angstrom=(("H", (0.0, 0.0, 0.0)), ("H", (0.0, 0.0, 1.5))),
        basis_set="sto-3g",
        active_space=(0, 1),
        frozen_orbitals=(),
        fermion_to_qubit_mapping_convention="jordan-wigner-paper-era",
    )
    return {
        "kind": "result",
        "action": "inspect",
        "upstream": provenance,
        "problem_id": problem.problem_id,
        "hamiltonian_digest": hamiltonian_digest,
        "reference_state": _reference_bits(algorithm.ref_state, pool.n),
        "mapping": "jordan-wigner-paper-era",
        "qubit_order": list(range(pool.n)),
        "source": source_payload,
        "source_energy_hartree": repr(source_energy),
        "source_gradient_infinity": repr(source_gradient_infinity),
        "source_statevector_digest": _state_digest(source_state),
        "candidate": candidate_payload,
        "raw_counter": emitter.total,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "threads": {
                name: os.environ.get(name)
                for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
            },
        },
    }


def execute(request: dict[str, Any]) -> dict[str, Any]:
    from scipy.optimize import minimize

    emitter = RawEmitter()
    algorithm, pool, provenance, recover_blocks, _, resource_api = _load_kernel()
    indices = [int(value) for value in request["ansatz_indices"]]
    initial = np.asarray(
        [struct.unpack(">d", bytes.fromhex(value))[0] for value in request["coefficient_bytes"]],
        dtype=np.float64,
    )
    counts = [int(value) for value in request["cumulative_parameter_counts"]]

    def energy(x: np.ndarray) -> float:
        value = float(algorithm.evaluate_energy(list(x), indices))
        if not math.isfinite(value):
            raise RuntimeError("upstream energy is nonfinite")
        emitter.emit(
            "ENERGY_EVALUATED",
            energy_evaluations=1,
            scientific_value={"quantity": "candidate_energy", "value": repr(value)},
        )
        return value

    def gradient(x: np.ndarray) -> np.ndarray:
        value = np.asarray(algorithm.estimate_gradients(list(x), indices, method="an"), dtype=np.float64)
        if not np.all(np.isfinite(value)):
            raise RuntimeError("upstream gradient is nonfinite")
        emitter.emit(
            "GRADIENT_EVALUATED",
            gradient_vector_evaluations=1,
            gradient_component_equivalents=int(value.size),
            scientific_value={
                "quantity": "gradient_infinity",
                "value": repr(float(np.max(np.abs(value))) if value.size else 0.0),
            },
        )
        return value

    emitter.emit("OPTIMIZER_STARTED", optimizer_starts=1)
    result = minimize(
        energy,
        initial,
        jac=gradient,
        method="L-BFGS-B",
        options={"maxiter": int(request["maximum_optimizer_iterations"]), "gtol": 1e-10, "ftol": 1e-15, "maxls": 5},
    )
    emitter.emit("OPTIMIZER_ITERATED", optimizer_iterations=int(result.nit))
    final = np.asarray(result.x, dtype=np.float64)
    certified_energy = energy(final)
    certified_gradient = gradient(final)
    state = algorithm.compute_state(list(final), indices)
    emitter.emit("STATEVECTOR_RECOMPUTED", statevector_recomputations=1)
    structure = _structure_payload(
        algorithm,
        pool,
        indices,
        list(final),
        counts,
        recover_blocks,
        resource_api,
        emitter,
    )
    if request.get("failure_injection") == "nan":
        certified_energy = float("nan")
    return {
        "kind": "result",
        "action": "execute",
        "upstream": provenance,
        "optimizer": {
            "success": bool(result.success),
            "status": int(result.status),
            "message": str(result.message),
            "iterations": int(result.nit),
        },
        "energy_hartree": repr(certified_energy),
        "gradient_infinity": repr(
            float(np.max(np.abs(certified_gradient))) if certified_gradient.size else 0.0
        ),
        "statevector_digest": _state_digest(state),
        "final": structure,
        "raw_counter": emitter.total,
    }


def main() -> None:
    request = json.loads(sys.stdin.read())
    injection = request.get("failure_injection")
    if injection == "crash":
        os._exit(23)
    if injection == "timeout":
        time.sleep(120)
    if injection == "malformed_json":
        print("{malformed", flush=True)
        return
    action = request.get("action")
    result = inspect(request) if action == "inspect" else execute(request)
    _line(result)


if __name__ == "__main__":
    main()
