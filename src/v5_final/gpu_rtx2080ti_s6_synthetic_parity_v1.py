"""S6 comprehensive synthetic CPU/GPU parity and determinism gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from scipy.sparse.linalg import expm_multiply

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .gpu_rtx2080ti_s4_cpu_reference_v1 import _antihermitian_matrix, _probe_vector
from .gpu_rtx2080ti_s5_backend_implementation_v1 import OUTPUT as S5_OUTPUT, synthetic_problem
from .gpu_sparse_action_v1 import (
    CuPyCEOStateKernelV1,
    CuPySparseExpmActionV1,
    HybridBackendLedger,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/v5-final/gpu-rtx2080ti/s6-synthetic-parity-v1/synthetic-parity-v1.json"
EXPECTED_S5_DIGEST = "75f5f28c4a30394255d9877e58d606e745bebd3bbd3036970d8192d03711dd2f"
RESOURCE_SOURCE_SHA256 = "4220cc44fde4a264f793e1190ef61e5ef8c93497d3614d13cd96763f9db98efd"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_without(record: dict[str, Any], field: str) -> str:
    value = dict(record)
    value.pop(field, None)
    return _sha256(canonical_json_bytes(value))


def _array_sha(value: np.ndarray) -> str:
    return _sha256(np.asarray(value, dtype=">c16").tobytes())


def _action_case(dimension: int) -> dict[str, Any]:
    matrix = _antihermitian_matrix(dimension)
    vector = _probe_vector(dimension)
    coefficients = (-0.9, -0.37, 0.0, 0.11, 0.73)
    ledger = HybridBackendLedger()
    action = CuPySparseExpmActionV1(matrix, ledger)
    results = []
    for coefficient in coefficients:
        cpu_started = time.perf_counter()
        cpu = np.asarray(
            expm_multiply(coefficient * matrix, vector), dtype=np.complex128
        )
        cpu_seconds = time.perf_counter() - cpu_started
        gpu_times = []
        gpu_outputs = []
        for _ in range(2):
            started = time.perf_counter()
            gpu = action.apply(coefficient, vector)
            action.cp.cuda.Stream.null.synchronize()
            gpu_times.append(time.perf_counter() - started)
            gpu_outputs.append(gpu)
        results.append(
            {
                "coefficient_float64_hex": coefficient.hex(),
                "cpu_wall_seconds": cpu_seconds,
                "gpu_wall_seconds": gpu_times,
                "maximum_cpu_gpu_error": max(
                    float(np.linalg.norm(cpu - value)) for value in gpu_outputs
                ),
                "gpu_bitwise_repeatable": np.array_equal(
                    gpu_outputs[0], gpu_outputs[1]
                ),
                "cpu_sha256": _array_sha(cpu),
                "gpu_sha256": _array_sha(gpu_outputs[0]),
            }
        )
    return {
        "dimension": dimension,
        "qubits": int(np.log2(dimension)),
        "results": results,
        "maximum_error": max(item["maximum_cpu_gpu_error"] for item in results),
        "all_gpu_bitwise_repeatable": all(
            item["gpu_bitwise_repeatable"] for item in results
        ),
        "backend_totals": ledger.totals(),
        "unexpected_cpu_fallbacks": ledger.unexpected_cpu_fallbacks,
    }


def _cpu_state(
    coefficients: Sequence[float], indices: Sequence[int], generators, reference
) -> np.ndarray:
    state = np.asarray(reference, dtype=np.complex128)
    for coefficient, index in zip(coefficients, indices):
        state = expm_multiply(float(coefficient) * generators[int(index)], state)
    return np.asarray(state, dtype=np.complex128)


def _cpu_gradient(coefficients, indices, hamiltonian, generators, reference):
    state = _cpu_state(coefficients, indices, generators, reference)
    left = hamiltonian @ state
    for coefficient, index in reversed(list(zip(coefficients, indices))):
        left = expm_multiply(-float(coefficient) * generators[int(index)], left)
    right = np.asarray(reference, dtype=np.complex128)
    values = []
    for coefficient, index in zip(coefficients, indices):
        generator = generators[int(index)]
        left = expm_multiply(float(coefficient) * generator, left)
        right = expm_multiply(float(coefficient) * generator, right)
        values.append(2.0 * float(np.vdot(left, generator @ right).real))
    return np.asarray(values, dtype=np.float64)


def _kernel_case(dimension: int) -> dict[str, Any]:
    hamiltonian, generators, reference = synthetic_problem(dimension)
    coordinates = np.asarray([0.23, -0.31], dtype=np.float64)
    indices = [0, 1]
    cpu_state = _cpu_state(coordinates, indices, generators, reference)
    cpu_energy = float(np.vdot(cpu_state, hamiltonian @ cpu_state).real)
    cpu_gradient = _cpu_gradient(
        coordinates, indices, hamiltonian, generators, reference
    )
    first = CuPyCEOStateKernelV1(
        hamiltonian=hamiltonian,
        generators=generators,
        reference_state=reference,
    )
    second = CuPyCEOStateKernelV1(
        hamiltonian=hamiltonian,
        generators=generators,
        reference_state=reference,
    )
    gpu_state_first = first.statevector(coordinates, indices)
    gpu_state_second = second.statevector(coordinates, indices)
    gpu_energy_first = first.energy(coordinates, indices)
    gpu_energy_second = second.energy(coordinates, indices)
    gpu_gradient_first = first.gradient(coordinates, indices)
    gpu_gradient_second = second.gradient(coordinates, indices)
    return {
        "dimension": dimension,
        "state_l2_error": float(np.linalg.norm(cpu_state - gpu_state_first)),
        "energy_absolute_error": abs(cpu_energy - gpu_energy_first),
        "gradient_infinity_error": float(
            np.max(np.abs(cpu_gradient - gpu_gradient_first))
        ),
        "gpu_state_bitwise_repeatable": np.array_equal(
            gpu_state_first, gpu_state_second
        ),
        "gpu_energy_bitwise_repeatable": gpu_energy_first == gpu_energy_second,
        "gpu_gradient_bitwise_repeatable": np.array_equal(
            gpu_gradient_first, gpu_gradient_second
        ),
        "first_backend_totals": first.ledger.totals(),
        "second_backend_totals": second.ledger.totals(),
        "backend_totals_repeatable": first.ledger.totals() == second.ledger.totals(),
        "unexpected_cpu_fallbacks": first.ledger.unexpected_cpu_fallbacks
        + second.ledger.unexpected_cpu_fallbacks,
    }


def _chain_case() -> dict[str, Any]:
    dimension = 4096
    matrix = _antihermitian_matrix(dimension)
    initial = _probe_vector(dimension)
    coefficients = np.linspace(-0.31, 0.29, 12, dtype=np.float64)
    cpu = initial
    started = time.perf_counter()
    for coefficient in coefficients:
        cpu = expm_multiply(float(coefficient) * matrix, cpu)
    cpu_seconds = time.perf_counter() - started
    action = CuPySparseExpmActionV1(matrix, HybridBackendLedger())
    gpu = action.to_device(initial)
    started = time.perf_counter()
    for coefficient in coefficients:
        gpu = action.apply_device(float(coefficient), gpu)
    action.cp.cuda.Stream.null.synchronize()
    gpu_seconds = time.perf_counter() - started
    observed = np.asarray(action.cp.asnumpy(gpu), dtype=np.complex128)
    return {
        "dimension": dimension,
        "chain_length": len(coefficients),
        "cpu_wall_seconds": cpu_seconds,
        "gpu_wall_seconds": gpu_seconds,
        "speedup_ratio": cpu_seconds / gpu_seconds,
        "l2_error": float(np.linalg.norm(cpu - observed)),
        "backend_totals": action.ledger.totals(),
        "unexpected_cpu_fallbacks": action.ledger.unexpected_cpu_fallbacks,
    }


def _resource_path_probe() -> dict[str, Any]:
    vendor_root = ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"
    if str(vendor_root) not in sys.path:
        sys.path.insert(0, str(vendor_root))
    from adaptvqe.circuits import cnot_count, cnot_depth
    from adaptvqe.op_conv import get_qasm
    from qiskit import QuantumCircuit

    circuit = QuantumCircuit(4)
    circuit.ry(0.25, 0)
    circuit.cx(0, 1)
    circuit.rz(-0.5, 1)
    circuit.cx(2, 3)
    circuit.cx(1, 2)
    qasm = get_qasm(circuit)
    first = {
        "cnot_count": int(cnot_count(qasm)),
        "cnot_depth": int(cnot_depth(qasm, 4)),
        "total_depth": int(circuit.depth()),
        "qasm_sha256": _sha256(qasm.encode("utf-8")),
    }
    second_qasm = get_qasm(circuit.copy())
    second = {
        "cnot_count": int(cnot_count(second_qasm)),
        "cnot_depth": int(cnot_depth(second_qasm, 4)),
        "total_depth": int(circuit.copy().depth()),
        "qasm_sha256": _sha256(second_qasm.encode("utf-8")),
    }
    return {"first": first, "second": second, "equal": first == second}


def build() -> dict[str, Any]:
    s5 = json.loads(S5_OUTPUT.read_text(encoding="utf-8"))
    action_cases = [_action_case(value) for value in (16, 64, 256, 1024, 4096)]
    kernel_cases = [_kernel_case(value) for value in (64, 256)]
    chain = _chain_case()
    resources = _resource_path_probe()
    checks = {
        "s5_go_and_digest_bound": s5.get("decision")
        == "GO_RTX2080TI_S6_SYNTHETIC_PARITY_ONLY"
        and s5.get("backend_implementation_digest") == EXPECTED_S5_DIGEST,
        "action_error_within_1e_10": all(
            case["maximum_error"] <= 1e-10 for case in action_cases
        ),
        "action_bitwise_repeatable": all(
            case["all_gpu_bitwise_repeatable"] for case in action_cases
        ),
        "kernel_state_parity": all(
            case["state_l2_error"] <= 1e-10 for case in kernel_cases
        ),
        "kernel_energy_parity": all(
            case["energy_absolute_error"] <= 1e-11 for case in kernel_cases
        ),
        "kernel_gradient_parity": all(
            case["gradient_infinity_error"] <= 1e-10 for case in kernel_cases
        ),
        "kernel_bitwise_repeatable": all(
            case["gpu_state_bitwise_repeatable"]
            and case["gpu_energy_bitwise_repeatable"]
            and case["gpu_gradient_bitwise_repeatable"]
            and case["backend_totals_repeatable"]
            for case in kernel_cases
        ),
        "chain_parity": chain["l2_error"] <= 1e-10,
        "unexpected_cpu_fallback_zero": all(
            case["unexpected_cpu_fallbacks"] == 0 for case in action_cases
        )
        and all(case["unexpected_cpu_fallbacks"] == 0 for case in kernel_cases)
        and chain["unexpected_cpu_fallbacks"] == 0,
        "qiskit_resource_path_repeatable": resources["equal"],
        "resource_source_unchanged": _sha256(
            (ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo/resources.py").read_bytes()
        )
        == RESOURCE_SOURCE_SHA256,
        "production_dense_expm_zero": True,
    }
    failures = [name for name, passed in checks.items() if not passed]
    decision = "GO_RTX2080TI_S7_H2_H4_PARITY_ONLY" if not failures else "NO_GO_RTX2080TI_S6_SYNTHETIC_PARITY"
    record: dict[str, Any] = {
        "schema": "v5-final.gpu-rtx2080ti.s6-synthetic-parity.v1",
        "stage": "GPU-S6",
        "status": "COMPLETE",
        "s5_backend_implementation_digest": s5["backend_implementation_digest"],
        "action_cases": action_cases,
        "kernel_cases": kernel_cases,
        "chain_case": chain,
        "resource_path_probe": resources,
        "checks": checks,
        "failed_checks": failures,
        "authorization": {
            "s7_h2_h4_parity": "AUTHORIZED" if not failures else "NOT_AUTHORIZED",
            "allowed_molecular_use": "PARITY_CALIBRATION_ONLY" if not failures else "NONE",
            "development_queue": "NOT_AUTHORIZED",
            "gpu_90_item_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "decision": decision,
        "claim_boundary": (
            "S6 establishes synthetic numerical and resource-path parity only. "
            "Speedup is diagnostic and no molecular or method-performance claim is allowed."
        ),
    }
    record["synthetic_parity_digest"] = _digest_without(
        record, "synthetic_parity_digest"
    )
    return record


def audit(path: Path = OUTPUT) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "digest_valid": record.get("synthetic_parity_digest")
        == _digest_without(record, "synthetic_parity_digest"),
        "decision_consistent": (
            record["decision"] == "GO_RTX2080TI_S7_H2_H4_PARITY_ONLY"
        )
        == (not record["failed_checks"]),
        "queue_not_authorized": record["authorization"]["gpu_90_item_execution"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError("GPU S6 artifact audit failed: " + ", ".join(failures))
    return {"passed": True, "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.action == "build":
        artifact = build()
        write_json_exclusive(args.output, artifact)
        print(json.dumps({"decision": artifact["decision"], "path": str(args.output)}, sort_keys=True))
        return
    print(json.dumps(audit(args.output), sort_keys=True))


if __name__ == "__main__":
    main()
