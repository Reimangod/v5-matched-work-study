"""P4 same-node CPU/A100 source-route benchmark.

The registered route is state preparation followed by the expectation value of
the pinned sparse Hamiltonian.  Molecular setup, candidate generation, circuit
construction and compilation are deliberately outside the timed region.  No
candidate energy, optimizer, FCI value or terminal compression decision is
evaluated by this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time
from typing import Any, Callable, Sequence

import numpy as np

from .aer_gpu_backend import (
    RouteCounters,
    build_gpu_backend,
    hybrid_gpu_state_cpu_sparse_energy,
    phase_aligned_max_error,
)
from .common import A100PilotError, digest, embedded_digest_valid, load_json
from .p0_baseline import CASE_SPECS, PROTOCOL
from .parity import _reference_case, build_context


CURRENT_ORDER = ("h2", "h4", "lih", "h6", "beh2")
SYNTHETIC_QUBITS = (16, 18, 20)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _gpu_observation() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,uuid,driver_version,memory.total",
        "--format=csv,noheader,nounits",
    ]
    completed = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    rows = [row.strip() for row in completed.stdout.splitlines() if row.strip()]
    if len(rows) != 1:
        raise A100PilotError(f"expected exactly one visible GPU, observed {len(rows)}")
    fields = [field.strip() for field in rows[0].split(",")]
    if len(fields) != 4 or "A100" not in fields[0].upper():
        raise A100PilotError(f"allocated GPU is not one A100: {fields!r}")
    return {
        "model": fields[0],
        "uuid": fields[1],
        "driver_version": fields[2],
        "memory_total_mib": int(fields[3]),
    }


def _cpu_route(
    reference: Sequence[complex],
    circuit: Any,
    hamiltonian: Any,
    counters: RouteCounters,
) -> tuple[float, np.ndarray]:
    from qiskit.quantum_info import Statevector

    state = np.asarray(Statevector(reference).evolve(circuit).data, dtype=np.complex128)
    state /= np.linalg.norm(state)
    energy = float(np.real(np.vdot(state, hamiltonian @ state)))
    if not np.isfinite(energy):
        raise A100PilotError("CPU expectation returned a nonfinite energy")
    counters.N_cpu_statevector += 1
    counters.N_cpu_energy += 1
    return energy, state


def _time_call(function: Callable[[], tuple[Any, ...]]) -> tuple[float, tuple[Any, ...]]:
    started = time.perf_counter()
    value = function()
    elapsed = time.perf_counter() - started
    if elapsed <= 0.0 or not np.isfinite(elapsed):
        raise A100PilotError(f"invalid wall time: {elapsed!r}")
    return float(elapsed), value


def _measure_routes(
    *,
    reference: np.ndarray,
    circuit: Any,
    hamiltonian: Any,
    backend: Any,
    warmups: int,
    repetitions: int,
    tolerances: dict[str, Any],
) -> dict[str, Any]:
    warmup = RouteCounters()
    measured = RouteCounters()

    for _ in range(warmups):
        _cpu_route(reference, circuit, hamiltonian, warmup)
        hybrid_gpu_state_cpu_sparse_energy(
            reference, circuit, hamiltonian, backend=backend, counters=warmup
        )

    cpu_seconds: list[float] = []
    gpu_seconds: list[float] = []
    state_errors: list[float] = []
    energy_errors: list[float] = []
    metadata: list[dict[str, Any]] = []
    for repetition in range(repetitions):
        cpu_call = lambda: _cpu_route(reference, circuit, hamiltonian, measured)
        gpu_call = lambda: hybrid_gpu_state_cpu_sparse_energy(
            reference, circuit, hamiltonian, backend=backend, counters=measured
        )
        if repetition % 2 == 0:
            cpu_elapsed, (cpu_energy, cpu_state) = _time_call(cpu_call)
            gpu_elapsed, (gpu_energy, gpu_state, gpu_metadata) = _time_call(gpu_call)
        else:
            gpu_elapsed, (gpu_energy, gpu_state, gpu_metadata) = _time_call(gpu_call)
            cpu_elapsed, (cpu_energy, cpu_state) = _time_call(cpu_call)
        cpu_seconds.append(cpu_elapsed)
        gpu_seconds.append(gpu_elapsed)
        state_errors.append(phase_aligned_max_error(cpu_state, gpu_state))
        energy_errors.append(abs(float(cpu_energy) - float(gpu_energy)))
        metadata.append(
            {
                "device": str(gpu_metadata.get("device", "")),
                "method": str(gpu_metadata.get("method", "")),
            }
        )

    cpu_median = float(statistics.median(cpu_seconds))
    gpu_median = float(statistics.median(gpu_seconds))
    speedup = cpu_median / gpu_median
    max_state_error = max(state_errors, default=0.0)
    max_energy_error = max(energy_errors, default=0.0)
    checks = {
        "state": max_state_error
        <= float(tolerances["phase_aligned_state_error_max"]),
        "energy": max_energy_error
        <= float(tolerances["absolute_energy_hartree_max"]),
        "explicit_gpu_metadata": all(
            value["device"].upper() == "GPU"
            and "statevector" in value["method"].lower()
            for value in metadata
        ),
        "no_cpu_fallback": measured.N_cpu_fallback == 0
        and warmup.N_cpu_fallback == 0,
    }
    return {
        "timing_scope": {
            "included": [
                "statevector propagation",
                "statevector normalization",
                "sparse Hamiltonian expectation on host",
                "GPU result synchronization and state transfer for GPU route",
            ],
            "excluded": [
                "molecular integral construction",
                "source context reconstruction",
                "candidate catalog construction",
                "circuit construction",
                "optimizer",
                "FCI",
            ],
        },
        "warmup_repetitions": warmups,
        "measured_repetitions": repetitions,
        "alternating_order": "CPU_FIRST_ON_EVEN_REPETITIONS_GPU_FIRST_ON_ODD",
        "cpu_seconds": cpu_seconds,
        "gpu_seconds": gpu_seconds,
        "cpu_median_seconds": cpu_median,
        "gpu_median_seconds": gpu_median,
        "speedup_cpu_over_gpu": speedup,
        "errors": {
            "phase_aligned_state_max_abs": max_state_error,
            "absolute_energy_hartree": max_energy_error,
        },
        "checks": checks,
        "warmup_route_counters": warmup.as_dict(),
        "measured_route_counters": measured.as_dict(),
        "gpu_metadata": metadata,
    }


def _base_record(*, protocol: dict[str, Any], benchmark_kind: str) -> dict[str, Any]:
    return {
        "schema": "aic-a100-pilot.p4-same-node-route-benchmark.v1",
        "benchmark_kind": benchmark_kind,
        "P0_protocol_digest": protocol["protocol_digest"],
        "same_aic_node_cpu_gpu": True,
        "hardware": {
            "gpu": _gpu_observation(),
            "node": os.environ.get("SLURMD_NODENAME") or platform.node(),
            "slurm_job_id": int(os.environ["SLURM_JOB_ID"]),
            "python_version": platform.python_version(),
            "machine": platform.machine(),
        },
        "candidate_molecular_energy_evaluations": 0,
        "optimizer_runs": 0,
        "FCI_evaluations": 0,
        "performance_claim_authorized": False,
    }


def run_current_case(alias: str) -> dict[str, Any]:
    if alias not in CURRENT_ORDER:
        raise A100PilotError(f"unknown current-system case: {alias}")
    protocol = load_json(PROTOCOL)
    if not embedded_digest_valid(protocol, "protocol_digest"):
        raise A100PilotError("P0 protocol digest is invalid")
    expected = _reference_case(alias)
    context = build_context(alias)
    indices = [int(value) for value in context.runtime.ansatz.indices]
    coefficients = [float(value) for value in context.runtime.ansatz.coefficients]
    circuit = context.pool.get_circuit(indices, coefficients)
    qasm_sha256 = _sha256_text(circuit.qasm())
    if qasm_sha256 != expected["source_qasm_sha256"]:
        raise A100PilotError("source circuit digest differs")
    reference = np.asarray(
        context._actual_algorithm.ref_state.toarray(), dtype=np.complex128
    ).ravel()
    benchmark = protocol["benchmark_policy"]
    result = _base_record(protocol=protocol, benchmark_kind="CURRENT_FROZEN_SOURCE")
    result.update(
        {
            "alias": alias,
            "case_id": expected["case_id"],
            "qubit_count": int(expected["qubit_count"]),
            "source_qasm_sha256": qasm_sha256,
            "StatePreparationID": expected["StatePreparationID"],
            "ProblemID": expected["ProblemID"],
            "Hamiltonian_digest": expected["Hamiltonian_digest"],
            "threads": int(CASE_SPECS[alias]["threads"]),
            "measurement": _measure_routes(
                reference=reference,
                circuit=circuit,
                hamiltonian=context._actual_algorithm.hamiltonian,
                backend=build_gpu_backend(),
                warmups=max(1, int(benchmark["warmup_repetitions_min"])),
                repetitions=int(benchmark["measured_repetitions"]),
                tolerances=protocol["tolerances"],
            ),
        }
    )
    result["record_digest"] = digest(result)
    return result


def _synthetic_fixture(qubits: int) -> tuple[np.ndarray, Any, Any, str]:
    from qiskit import QuantumCircuit
    from scipy import sparse

    if qubits not in SYNTHETIC_QUBITS:
        raise A100PilotError(f"unregistered synthetic qubit count: {qubits}")
    circuit = QuantumCircuit(qubits)
    for layer in range(4):
        for qubit in range(qubits):
            angle = (layer + 1) * (qubit + 1) / 97.0
            circuit.ry(angle, qubit)
        offset = layer % 2
        for qubit in range(offset, qubits - 1, 2):
            circuit.cx(qubit, qubit + 1)
        circuit.cx(qubits - 1, 0)
    dimension = 1 << qubits
    reference = np.zeros(dimension, dtype=np.complex128)
    reference[0] = 1.0
    diagonal = np.linspace(-1.0, 1.0, dimension, dtype=np.float64)
    hamiltonian = sparse.diags(diagonal, offsets=0, format="csc")
    definition = {
        "schema": "aic-a100-pilot.synthetic-scaling-fixture.v1",
        "qubits": qubits,
        "layers": 4,
        "single_qubit_gate": "ry((layer+1)*(qubit+1)/97)",
        "two_qubit_topology": "alternating-neighbor-pairs-plus-last-to-zero",
        "reference": "computational-zero",
        "Hamiltonian": "diagonal-linspace-minus-one-to-one",
        "qasm_sha256": _sha256_text(circuit.qasm()),
    }
    return reference, circuit, hamiltonian, digest(definition)


def run_synthetic_case(qubits: int) -> dict[str, Any]:
    protocol = load_json(PROTOCOL)
    if not embedded_digest_valid(protocol, "protocol_digest"):
        raise A100PilotError("P0 protocol digest is invalid")
    if list(protocol["benchmark_policy"]["synthetic_scaling_qubits"]) != list(
        SYNTHETIC_QUBITS
    ):
        raise A100PilotError("synthetic scaling qubits differ from P0")
    reference, circuit, hamiltonian, fixture_digest = _synthetic_fixture(qubits)
    benchmark = protocol["benchmark_policy"]
    result = _base_record(protocol=protocol, benchmark_kind="SYNTHETIC_DIAGNOSTIC")
    result.update(
        {
            "alias": f"synthetic-{qubits}q",
            "qubit_count": qubits,
            "fixture_digest": fixture_digest,
            "source_qasm_sha256": _sha256_text(circuit.qasm()),
            "scientific_scope": "DIAGNOSTIC_ONLY_CANNOT_OVERRIDE_CURRENT_SYSTEM_GATE",
            "measurement": _measure_routes(
                reference=reference,
                circuit=circuit,
                hamiltonian=hamiltonian,
                backend=build_gpu_backend(),
                warmups=max(1, int(benchmark["warmup_repetitions_min"])),
                repetitions=int(benchmark["measured_repetitions"]),
                tolerances=protocol["tolerances"],
            ),
        }
    )
    result["record_digest"] = digest(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--case", choices=CURRENT_ORDER)
    group.add_argument("--synthetic-qubits", type=int, choices=SYNTHETIC_QUBITS)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    output = arguments.output
    if output is None:
        raw = os.environ.get("A100_BENCHMARK_OUTPUT")
        if not raw:
            raise RuntimeError("set --output or A100_BENCHMARK_OUTPUT")
        output = Path(raw)
    result = (
        run_current_case(str(arguments.case))
        if arguments.case is not None
        else run_synthetic_case(int(arguments.synthetic_qubits))
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if not all(result["measurement"]["checks"].values()):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
