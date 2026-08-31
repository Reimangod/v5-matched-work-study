"""Fail-closed Qiskit Aer GPU adapter for the isolated A100 pilot.

This module deliberately does not silently select a CPU backend.  Every run
must return Aer metadata declaring ``device=GPU``; otherwise the run fails and
increments the fallback counter.  Energy evaluation is explicitly hybrid:
state preparation is performed by Aer GPU and the pinned sparse Hamiltonian
expectation is evaluated on CPU after state transfer.  That boundary is named
and counted so it cannot be mistaken for an all-GPU implementation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

import numpy as np

from .common import A100PilotError


@dataclass
class RouteCounters:
    N_gpu_statevector: int = 0
    N_gpu_energy: int = 0
    N_gpu_gradient_component: int = 0
    N_cpu_statevector: int = 0
    N_cpu_energy: int = 0
    N_cpu_gradient_component: int = 0
    N_cpu_fallback: int = 0

    def record_gpu_statevector(self) -> None:
        self.N_gpu_statevector += 1

    def record_hybrid_energy(self) -> None:
        self.N_gpu_energy += 1
        self.N_cpu_energy += 1

    def record_gpu_gradient_component(self) -> None:
        self.N_gpu_gradient_component += 1

    def record_fallback(self) -> None:
        self.N_cpu_fallback += 1

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def _experiment_metadata(result: Any) -> dict[str, Any]:
    results = getattr(result, "results", None)
    if not results or len(results) != 1:
        raise A100PilotError("Aer result must contain exactly one experiment")
    metadata = getattr(results[0], "metadata", None)
    if not isinstance(metadata, dict):
        raise A100PilotError("Aer result lacks experiment metadata")
    return metadata


def require_gpu_metadata(result: Any, counters: RouteCounters) -> dict[str, Any]:
    metadata = _experiment_metadata(result)
    device = str(metadata.get("device", "")).upper()
    method = str(metadata.get("method", "")).lower()
    if device != "GPU" or "statevector" not in method:
        counters.record_fallback()
        raise A100PilotError(
            f"CPU fallback or wrong method detected: device={device!r}, method={method!r}"
        )
    return metadata


def build_gpu_backend() -> Any:
    from qiskit_aer import AerSimulator

    backend = AerSimulator(method="statevector", device="GPU", precision="double")
    devices = {str(value).upper() for value in backend.available_devices()}
    if "GPU" not in devices:
        raise A100PilotError(f"Aer GPU unavailable; reported devices={sorted(devices)}")
    return backend


def _state_preparation_circuit(reference: Sequence[complex], ansatz_circuit: Any) -> Any:
    from qiskit import QuantumCircuit
    from qiskit_aer.library import SetStatevector

    vector = np.asarray(reference, dtype=np.complex128).reshape(-1)
    expected = 1 << int(ansatz_circuit.num_qubits)
    if vector.size != expected:
        raise A100PilotError(
            f"reference dimension {vector.size} differs from circuit dimension {expected}"
        )
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or abs(norm - 1.0) > 1e-12:
        raise A100PilotError(f"reference state is not normalized: norm={norm}")
    circuit = QuantumCircuit(ansatz_circuit.num_qubits)
    circuit.append(SetStatevector(vector), circuit.qubits)
    circuit.compose(ansatz_circuit, inplace=True)
    circuit.save_statevector()
    return circuit


def gpu_statevector(
    reference: Sequence[complex],
    ansatz_circuit: Any,
    *,
    backend: Any,
    counters: RouteCounters,
) -> tuple[np.ndarray, dict[str, Any]]:
    circuit = _state_preparation_circuit(reference, ansatz_circuit)
    result = backend.run(circuit).result()
    metadata = require_gpu_metadata(result, counters)
    state = np.asarray(result.get_statevector(circuit), dtype=np.complex128)
    norm = float(np.linalg.norm(state))
    if not np.isfinite(norm) or norm == 0.0:
        raise A100PilotError("Aer returned a zero or nonfinite state")
    state /= norm
    counters.record_gpu_statevector()
    return state, metadata


def hybrid_gpu_state_cpu_sparse_energy(
    reference: Sequence[complex],
    ansatz_circuit: Any,
    hamiltonian: Any,
    *,
    backend: Any,
    counters: RouteCounters,
) -> tuple[float, np.ndarray, dict[str, Any]]:
    state, metadata = gpu_statevector(
        reference, ansatz_circuit, backend=backend, counters=counters
    )
    energy = float(np.real(np.vdot(state, hamiltonian @ state)))
    if not np.isfinite(energy):
        raise A100PilotError("hybrid expectation returned a nonfinite energy")
    counters.record_hybrid_energy()
    return energy, state, metadata


def phase_aligned_max_error(reference: Sequence[complex], observed: Sequence[complex]) -> float:
    expected = np.asarray(reference, dtype=np.complex128).reshape(-1)
    actual = np.asarray(observed, dtype=np.complex128).reshape(-1)
    if expected.shape != actual.shape:
        raise A100PilotError("statevector shapes differ")
    overlap = np.vdot(expected, actual)
    if abs(overlap) > 0.0:
        actual = actual * np.exp(-1j * np.angle(overlap))
    return float(np.max(np.abs(expected - actual)))
