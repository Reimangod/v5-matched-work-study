"""Paired CPU/A100 BFGS trajectory parity on one numerical route.

The historical hybrid route remains immutable.  This additive successor uses
the same device-state/deterministic-energy function for both optimizer energy
and every finite-difference gradient component.  CPU and GPU differ only in
the Aer statevector device.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
from importlib import import_module
from importlib import metadata as importlib_metadata
import json
import os
from pathlib import Path
import pickle
import platform
import struct
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import numpy as np

from .benchmark import _gpu_observation
from .common import (
    A100PilotError,
    ROOT,
    digest,
    embedded_digest_valid,
    git,
    load_json,
    sha256_file,
)
from .objective_parity import (
    PilotBoundary,
    _attempt_with_kernels,
    _contract_case,
    _serialize_attempt,
)
from .aer_gpu_backend import phase_aligned_max_error
from .unified_route_contract import CONTRACT, SOURCE_PATHS


STENCIL = (-2, -1, 1, 2)
FINITE_DIFFERENCE_STEP = np.float64(1e-4)


def _software_version(
    module_name: str, distribution_candidates: Sequence[str]
) -> dict[str, str]:
    for distribution in distribution_candidates:
        try:
            version = importlib_metadata.version(distribution)
        except importlib_metadata.PackageNotFoundError:
            continue
        if not version:
            raise A100PilotError(f"empty software version: {distribution}")
        return {
            "module": module_name,
            "version": str(version),
            "source": f"distribution:{distribution}",
        }
    module = import_module(module_name)
    version = getattr(module, "__version__", None)
    if not isinstance(version, str) or not version:
        raise A100PilotError(
            f"software version unavailable for importable module: {module_name}"
        )
    return {
        "module": module_name,
        "version": version,
        "source": f"module:{module_name}.__version__",
    }


def _runtime_binding(contract: Mapping[str, Any], alias: str) -> dict[str, Any]:
    expected_head = os.environ.get("A100_EXPECTED_HEAD")
    if not expected_head or len(expected_head) != 40:
        raise A100PilotError("A100_EXPECTED_HEAD must contain one full Git SHA")
    actual_head = git("rev-parse", "HEAD")
    if actual_head != expected_head:
        raise A100PilotError(
            f"runtime Git HEAD differs: {actual_head} != {expected_head}"
        )
    observed_sources = {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in SOURCE_PATHS
    }
    if observed_sources != contract["source_binding"]:
        raise A100PilotError("runtime unified-route source hashes differ from contract")
    thread_keys = (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    )
    process_threads = {key: os.environ.get(key) for key in thread_keys}
    if any(value != "1" for value in process_threads.values()):
        raise A100PilotError(
            "numerical route process thread environment differs from one"
        )
    if os.environ.get("A100_NUMERICAL_THREADS") != "1":
        raise A100PilotError("A100_NUMERICAL_THREADS must be exactly one")
    versions = {
        "numpy": _software_version("numpy", ("numpy",)),
        "scipy": _software_version("scipy", ("scipy",)),
        "qiskit": _software_version("qiskit", ("qiskit", "qiskit-terra")),
        "qiskit_aer": _software_version(
            "qiskit_aer", ("qiskit-aer", "qiskit_aer")
        ),
    }
    return {
        "git_head": actual_head,
        "expected_git_head": expected_head,
        "parent_submodule_head": git(
            "rev-parse", "HEAD", root=ROOT / "provenance/dvg-obs-ceo"
        ),
        "CEO_submodule_head": git(
            "rev-parse",
            "HEAD",
            root=ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe",
        ),
        "contract_path": CONTRACT.relative_to(ROOT).as_posix(),
        "contract_file_sha256": sha256_file(CONTRACT),
        "contract_digest": contract["contract_digest"],
        "source_sha256": observed_sources,
        "python_version": platform.python_version(),
        "distributions": versions,
        "numerical_process_thread_environment": process_threads,
        "registered_numerical_thread_limit": 1,
    }


def _load_prepared_bundle(
    *,
    alias: str,
    contract: Mapping[str, Any],
    bundle_path: Path,
    manifest_path: Path,
) -> tuple[Any, Any, Any, dict[str, Any]]:
    if not bundle_path.is_file() or not manifest_path.is_file():
        raise A100PilotError("prepared source bundle or manifest is absent")
    manifest = load_json(manifest_path)
    if not embedded_digest_valid(manifest, "manifest_digest"):
        raise A100PilotError("prepared source manifest digest is invalid")
    expected = {
        "alias": alias,
        "contract_digest": contract["contract_digest"],
        "git_head": os.environ["A100_EXPECTED_HEAD"],
        "candidate_outcomes": 0,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise A100PilotError("prepared source manifest identity differs")
    if manifest.get("bundle_sha256") != sha256_file(bundle_path):
        raise A100PilotError("prepared source bundle SHA-256 differs")
    with bundle_path.open("rb") as stream:
        prepared = pickle.load(stream)
    if not isinstance(prepared, tuple) or len(prepared) != 3:
        raise A100PilotError("prepared source bundle payload is malformed")
    context, plan, rewrite = prepared
    if list(rewrite.verified_candidate_ids) != list(
        manifest["verified_candidate_ids"]
    ):
        raise A100PilotError("prepared rewrite identity differs from manifest")
    return context, plan, rewrite, manifest


def _float_hex(value: float) -> str:
    return struct.pack(">d", float(value)).hex()


def _array_hex(value: Sequence[float]) -> list[str]:
    return [_float_hex(item) for item in np.asarray(value, dtype=np.float64)]


def fixed_pairwise_complex_sum(values: Sequence[complex]) -> np.complex128:
    work = np.asarray(values, dtype=np.complex128).reshape(-1).copy()
    if not work.size:
        return np.complex128(0.0)
    while work.size > 1:
        paired = work.size // 2
        reduced = work[: 2 * paired : 2] + work[1 : 2 * paired : 2]
        if work.size % 2:
            work = np.concatenate((reduced, work[-1:]))
        else:
            work = reduced
    return np.complex128(work[0])


def deterministic_normalize(state: Sequence[complex]) -> np.ndarray:
    value = np.asarray(state, dtype=np.complex128).reshape(-1).copy()
    norm_squared = fixed_pairwise_complex_sum(np.conjugate(value) * value)
    if abs(float(np.imag(norm_squared))) > 1e-14:
        raise A100PilotError("complex128 norm reduction returned an imaginary part")
    norm = np.sqrt(np.float64(np.real(norm_squared)))
    if not np.isfinite(norm) or norm == 0.0:
        raise A100PilotError("state has a zero or nonfinite deterministic norm")
    value /= norm
    return np.asarray(value, dtype=np.complex128)


class DeterministicHamiltonian:
    def __init__(self, hamiltonian: Any) -> None:
        matrix = hamiltonian.tocsr(copy=True).astype(np.complex128)
        matrix.sum_duplicates()
        matrix.sort_indices()
        if matrix.shape[0] != matrix.shape[1]:
            raise A100PilotError("Hamiltonian is not square")
        self.shape = tuple(int(value) for value in matrix.shape)
        self.indptr = np.asarray(matrix.indptr, dtype=np.int64)
        self.indices = np.asarray(matrix.indices, dtype=np.int64)
        self.data = np.asarray(matrix.data, dtype=np.complex128)
        self.rows = np.repeat(
            np.arange(self.shape[0], dtype=np.int64), np.diff(self.indptr)
        )
        body = (
            np.asarray(self.shape, dtype=">i8").tobytes()
            + np.asarray(self.indptr, dtype=">i8").tobytes()
            + np.asarray(self.indices, dtype=">i8").tobytes()
            + np.asarray(self.data, dtype=">c16").tobytes()
        )
        self.operation_order_digest = hashlib.sha256(body).hexdigest()

    def energy(self, state: Sequence[complex]) -> float:
        value = np.asarray(state, dtype=np.complex128).reshape(-1)
        if value.shape != (self.shape[0],):
            raise A100PilotError("state and deterministic Hamiltonian shapes differ")
        contributions = (
            np.conjugate(value[self.rows])
            * self.data
            * value[self.indices]
        )
        expectation = fixed_pairwise_complex_sum(contributions)
        if abs(float(np.imag(expectation))) > 1e-10:
            raise A100PilotError("deterministic expectation is not real")
        energy = float(np.real(expectation))
        if not np.isfinite(energy):
            raise A100PilotError("deterministic expectation is nonfinite")
        return energy


@dataclass
class UnifiedCounters:
    device: str
    N_device_statevector: int = 0
    N_deterministic_energy: int = 0
    N_gradient_component: int = 0
    N_cpu_fallback: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _backend(device: str) -> Any:
    from qiskit_aer import AerSimulator

    normalized = device.upper()
    if normalized not in {"CPU", "GPU"}:
        raise A100PilotError(f"unsupported Aer device: {device}")
    backend = AerSimulator(
        method="statevector",
        device=normalized,
        precision="double",
        fusion_enable=False,
        max_parallel_threads=1,
        max_parallel_experiments=1,
        max_parallel_shots=1,
        seed_simulator=0,
    )
    if normalized == "GPU":
        available = {str(value).upper() for value in backend.available_devices()}
        if "GPU" not in available:
            raise A100PilotError(f"Aer GPU unavailable: {sorted(available)}")
    return backend


class UnifiedDeviceBoundary:
    def __init__(
        self,
        algorithm: Any,
        pool: Any,
        boundary: PilotBoundary,
        *,
        device: str,
    ) -> None:
        from v5_final.parent_native_zero_dimensional_v2 import (
            ActualOptimizationBoundaryV2,
        )

        # Use composition rather than mutating the production boundary class.
        self._resource_boundary = ActualOptimizationBoundaryV2(
            algorithm, pool, boundary
        )
        self.algorithm = algorithm
        self.pool = pool
        self.boundary = boundary
        self.device = device.upper()
        self.backend = _backend(self.device)
        self.reference = deterministic_normalize(
            np.asarray(algorithm.ref_state.toarray(), dtype=np.complex128).ravel()
        )
        self.hamiltonian = DeterministicHamiltonian(algorithm.hamiltonian)
        self.counters = UnifiedCounters(device=self.device)
        self.metadata: list[dict[str, str]] = []
        self.operation_trace: list[dict[str, Any]] = []
        self.trajectory: list[dict[str, Any]] = []
        self._latest_states: dict[bytes, np.ndarray] = {}

    @staticmethod
    def _key(coordinates: Sequence[float]) -> bytes:
        return np.asarray(coordinates, dtype=">f8").reshape(-1).tobytes()

    def _circuit(self, coordinates: Sequence[float], indices: Sequence[int]) -> Any:
        from qiskit import QuantumCircuit
        from qiskit_aer.library import SetStatevector

        ansatz = self.pool.get_circuit(list(indices), list(coordinates))
        circuit = QuantumCircuit(ansatz.num_qubits)
        circuit.append(SetStatevector(self.reference), circuit.qubits)
        circuit.compose(ansatz, inplace=True)
        circuit.save_statevector()
        return circuit

    def _state_at(
        self,
        coordinates: Sequence[float],
        indices: Sequence[int],
        *,
        purpose: str,
        parameter_position: int | None = None,
        stencil_multiple: int | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        circuit = self._circuit(coordinates, indices)

        def call() -> tuple[np.ndarray, dict[str, Any]]:
            result = self.backend.run(circuit).result()
            experiments = getattr(result, "results", None)
            if not experiments or len(experiments) != 1:
                raise A100PilotError("Aer route must return one experiment")
            metadata = getattr(experiments[0], "metadata", None)
            if not isinstance(metadata, dict):
                raise A100PilotError("Aer route lacks experiment metadata")
            observed_device = str(metadata.get("device", "")).upper()
            method = str(metadata.get("method", "")).lower()
            if observed_device != self.device or "statevector" not in method:
                self.counters.N_cpu_fallback += int(self.device == "GPU")
                raise A100PilotError(
                    "Aer route device/method differs: "
                    f"{observed_device!r}, {method!r}"
                )
            raw = np.asarray(result.get_statevector(circuit), dtype=np.complex128)
            return deterministic_normalize(raw), metadata

        state, metadata = self.boundary.invoke(
            purpose,
            call,
            evidence={
                "device": self.device,
                "coordinates_float64": _array_hex(coordinates),
                "parameter_position": parameter_position,
                "stencil_multiple": stencil_multiple,
            },
        )
        self.counters.N_device_statevector += 1
        self.metadata.append(
            {
                "device": str(metadata.get("device", "")),
                "method": str(metadata.get("method", "")),
            }
        )
        self._latest_states[self._key(coordinates)] = state.copy()
        return state, metadata

    def _energy_at(
        self,
        coordinates: Sequence[float],
        indices: Sequence[int],
        *,
        purpose: str,
        parameter_position: int | None = None,
        stencil_multiple: int | None = None,
    ) -> tuple[float, np.ndarray]:
        state, _ = self._state_at(
            coordinates,
            indices,
            purpose=purpose,
            parameter_position=parameter_position,
            stencil_multiple=stencil_multiple,
        )
        energy = self.hamiltonian.energy(state)
        self.counters.N_deterministic_energy += 1
        self.operation_trace.append(
            {
                "purpose": purpose,
                "parameter_position": parameter_position,
                "stencil_multiple": stencil_multiple,
            }
        )
        return energy, state

    def energy(self, coordinates: Sequence[float], indices: Sequence[int]) -> float:
        value, _ = self._energy_at(
            coordinates, indices, purpose="optimizer-objective-energy"
        )
        return value

    def gradient(
        self, coordinates: Sequence[float], indices: Sequence[int]
    ) -> np.ndarray:
        origin = np.asarray(coordinates, dtype=np.float64).reshape(-1)

        def call() -> np.ndarray:
            derivatives: list[float] = []
            for position in range(origin.size):
                energies: dict[int, float] = {}
                for multiple in STENCIL:
                    point = origin.copy()
                    point[position] = np.float64(
                        point[position]
                        + np.float64(multiple) * FINITE_DIFFERENCE_STEP
                    )
                    energies[multiple], _ = self._energy_at(
                        point,
                        indices,
                        purpose="gradient-stencil-energy",
                        parameter_position=position,
                        stencil_multiple=multiple,
                    )
                # Preserve the registered arithmetic order explicitly.  This
                # avoids allowing an implementation or refactor to reassociate
                # the four-point numerator.
                numerator = np.float64(energies[-2])
                numerator = np.float64(
                    numerator - np.float64(8.0) * np.float64(energies[-1])
                )
                numerator = np.float64(
                    numerator + np.float64(8.0) * np.float64(energies[1])
                )
                numerator = np.float64(
                    numerator - np.float64(energies[2])
                )
                denominator = np.float64(
                    np.float64(12.0) * FINITE_DIFFERENCE_STEP
                )
                derivative = np.float64(numerator / denominator)
                derivatives.append(float(derivative))
                self.counters.N_gradient_component += 1
            return np.asarray(derivatives, dtype=np.float64)

        return np.asarray(
            self.boundary.invoke(
                "full-gradient-evaluation",
                call,
                dimension=origin.size,
                evidence={"route": "same-energy-five-point-fixed-order"},
            ),
            dtype=np.float64,
        )

    def optimize(
        self,
        initial: Sequence[float],
        indices: Sequence[int],
        inverse_hessian: Any,
        *,
        f0: float | None = None,
        g0: Any | None = None,
    ) -> Any:
        from adaptvqe.minimize import minimize_bfgs

        if f0 is not None or g0 is not None:
            raise A100PilotError("unified route prohibits seeded optimizer outcomes")
        initial_array = np.asarray(initial, dtype=np.float64).reshape(-1)
        index_values = list(indices)
        inverse = np.asarray(inverse_hessian, dtype=np.float64)
        if len(index_values) != initial_array.size:
            raise A100PilotError("unified optimizer dimension differs")
        if inverse.shape != (initial_array.size, initial_array.size):
            raise A100PilotError("unified inverse-Hessian dimension differs")
        self.boundary.invoke("optimizer-start", lambda: None)
        if not initial_array.size:
            value = self.energy(initial_array, index_values)
            return SimpleNamespace(
                x=initial_array,
                fun=value,
                jac=np.empty((0,), dtype=np.float64),
                hess_inv=inverse,
                success=True,
                status=0,
                message="zero-dimensional unified-route evaluation",
                nit=0,
                nfev=1,
                njev=0,
            )

        def objective(values: Any, bound_indices: Sequence[int]) -> float:
            return self.energy(
                np.asarray(values, dtype=np.float64), bound_indices
            )

        def jacobian(values: Any, bound_indices: Sequence[int]) -> np.ndarray:
            return self.gradient(
                np.asarray(values, dtype=np.float64), bound_indices
            )

        def callback(result: Any) -> None:
            coordinates = np.asarray(result.x, dtype=np.float64)
            state = self._latest_states.get(self._key(coordinates))
            if state is None:
                state, _ = self._state_at(
                    coordinates,
                    index_values,
                    purpose="trajectory-state-recomputation",
                )
            entry = {
                "iteration": len(self.trajectory),
                "coordinates": coordinates.copy(),
                "energy_hartree": float(result.fun),
                "gradient": np.asarray(result.gradient, dtype=np.float64).copy(),
                "inverse_hessian": np.asarray(
                    result.inv_hessian, dtype=np.float64
                ).copy(),
                "statevector": state.copy(),
            }
            self.trajectory.append(entry)
            self.boundary.invoke(
                "optimizer-iteration",
                lambda: None,
                evidence={
                    "iteration": entry["iteration"],
                    "energy_float64": _float_hex(entry["energy_hartree"]),
                    "coordinates_float64": _array_hex(coordinates),
                    "gradient_float64": _array_hex(entry["gradient"]),
                },
            )

        result = minimize_bfgs(
            objective,
            initial_array,
            args=(index_values,),
            jac=jacobian,
            callback=callback,
            gtol=1e-8,
            maxiter=1000,
            disp=False,
            initial_inv_hessian=inverse,
        )
        operations = [event.operation for event in self.boundary.events]
        checks = {
            "optimizer-start": operations.count("optimizer-start") == 1,
            "optimizer-iteration": operations.count("optimizer-iteration")
            == int(result.nit),
            "optimizer-objective-energy": operations.count(
                "optimizer-objective-energy"
            )
            == int(result.nfev),
            "full-gradient-evaluation": operations.count(
                "full-gradient-evaluation"
            )
            == int(result.njev),
        }
        if not all(checks.values()):
            raise A100PilotError(f"unified optimizer accounting differs: {checks}")
        return result

    def statevector(
        self, coordinates: Sequence[float], indices: Sequence[int]
    ) -> np.ndarray:
        state, _ = self._state_at(
            coordinates, indices, purpose="semantic-state-recomputation"
        )
        return state

    def independent_statevector(
        self, coordinates: Sequence[float], indices: Sequence[int]
    ) -> np.ndarray:
        state, _ = self._state_at(
            coordinates, indices, purpose="independent-state-recomputation"
        )
        return state

    def independent_energy(self, statevector: np.ndarray) -> float:
        def call() -> float:
            return self.hamiltonian.energy(statevector)

        value = float(
            self.boundary.invoke("acceptance-energy", call, evidence={})
        )
        self.counters.N_deterministic_energy += 1
        return value

    def resources(self, structure: Any) -> Any:
        return self._resource_boundary.resources(structure)

    def determinism_probe(
        self, coordinates: Sequence[float], indices: Sequence[int]
    ) -> dict[str, Any]:
        first_energy, first_state = self._energy_at(
            coordinates, indices, purpose="determinism-probe-energy"
        )
        second_energy, second_state = self._energy_at(
            coordinates, indices, purpose="determinism-probe-energy"
        )
        return {
            "state_bitwise_equal": np.array_equal(first_state, second_state),
            "energy_bitwise_equal": _float_hex(first_energy)
            == _float_hex(second_energy),
            "state_sha256": hashlib.sha256(
                np.asarray(first_state, dtype=">c16").tobytes()
            ).hexdigest(),
            "energy_float64": _float_hex(first_energy),
        }


def _serialized_trajectory(kernel: UnifiedDeviceBoundary) -> list[dict[str, Any]]:
    return [
        {
            "iteration": int(value["iteration"]),
            "coordinates_float64": _array_hex(value["coordinates"]),
            "energy_float64": _float_hex(value["energy_hartree"]),
            "gradient_float64": _array_hex(value["gradient"]),
            "inverse_hessian_float64": [
                _array_hex(row) for row in value["inverse_hessian"]
            ],
            "statevector_sha256": hashlib.sha256(
                np.asarray(value["statevector"], dtype=">c16").tobytes()
            ).hexdigest(),
        }
        for value in kernel.trajectory
    ]


def _trajectory_differences(
    cpu: UnifiedDeviceBoundary, gpu: UnifiedDeviceBoundary
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for left, right in zip(cpu.trajectory, gpu.trajectory):
        rows.append(
            {
                "iteration": int(left["iteration"]),
                "coordinate_max_abs": float(
                    np.max(np.abs(left["coordinates"] - right["coordinates"]))
                ),
                "energy_hartree_abs": abs(
                    float(left["energy_hartree"])
                    - float(right["energy_hartree"])
                ),
                "gradient_max_abs": float(
                    np.max(np.abs(left["gradient"] - right["gradient"]))
                ),
                "inverse_hessian_max_abs": float(
                    np.max(
                        np.abs(
                            left["inverse_hessian"] - right["inverse_hessian"]
                        )
                    )
                ),
                "phase_aligned_state_max_abs": phase_aligned_max_error(
                    left["statevector"], right["statevector"]
                ),
            }
        )
    return {
        "length_cpu": len(cpu.trajectory),
        "length_gpu": len(gpu.trajectory),
        "iterations": rows,
    }


def _require_predecessors(alias: str, output_dir: Path) -> list[dict[str, str]]:
    contract = load_json(CONTRACT)
    order = list(contract["sequential_gate"]["case_order"])
    if alias not in order:
        raise A100PilotError(f"case is outside unified route contract: {alias}")
    evidence: list[dict[str, str]] = []
    for predecessor in order[: order.index(alias)]:
        path = output_dir / f"{predecessor}.json"
        if not path.is_file():
            raise A100PilotError(f"missing predecessor parity result: {predecessor}")
        value = load_json(path)
        if not embedded_digest_valid(value, "record_digest"):
            raise A100PilotError(f"invalid predecessor digest: {predecessor}")
        if value["status"] != "PASS":
            raise A100PilotError(f"predecessor did not pass: {predecessor}")
        if value["contract_digest"] != contract["contract_digest"]:
            raise A100PilotError(f"predecessor contract differs: {predecessor}")
        evidence.append(
            {
                "alias": predecessor,
                "record_digest": value["record_digest"],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return evidence


def run_case(
    alias: str,
    *,
    output_dir: Path,
    prepared_bundle: Path,
    prepared_manifest: Path,
) -> dict[str, Any]:
    contract = load_json(CONTRACT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise A100PilotError("unified route contract digest is invalid")
    runtime_binding = _runtime_binding(contract, alias)
    predecessors = _require_predecessors(alias, output_dir)
    _, specification = _contract_case(alias)
    context, plan, rewrite, preparation_manifest = _load_prepared_bundle(
        alias=alias,
        contract=contract,
        bundle_path=prepared_bundle,
        manifest_path=prepared_manifest,
    )

    cpu_boundary = PilotBoundary()
    cpu_kernel = UnifiedDeviceBoundary(
        context._actual_algorithm,
        context.pool,
        cpu_boundary,
        device="CPU",
    )
    gpu_boundary = PilotBoundary()
    gpu_kernel = UnifiedDeviceBoundary(
        context._actual_algorithm,
        context.pool,
        gpu_boundary,
        device="GPU",
    )
    cpu_probe = cpu_kernel.determinism_probe(
        rewrite.target.coefficients, rewrite.target.indices
    )
    gpu_probe = gpu_kernel.determinism_probe(
        rewrite.target.coefficients, rewrite.target.indices
    )

    cpu_raw = _attempt_with_kernels(
        context=context,
        kernels=cpu_kernel,
        target=rewrite.target,
        inverse_hessian=rewrite.target_inverse_hessian,
        parent_plan=plan,
    )
    gpu_raw = _attempt_with_kernels(
        context=context,
        kernels=gpu_kernel,
        target=rewrite.target,
        inverse_hessian=rewrite.target_inverse_hessian,
        parent_plan=plan,
    )

    cpu = _serialize_attempt(cpu_raw)
    gpu = _serialize_attempt(gpu_raw)
    trajectory = _trajectory_differences(cpu_kernel, gpu_kernel)
    requirements = contract["parity_requirements"]
    trajectory_checks = [
        value["coordinate_max_abs"] <= requirements["coordinate_error_max"]
        and value["energy_hartree_abs"]
        <= requirements["absolute_energy_hartree_max"]
        and value["gradient_max_abs"]
        <= requirements["max_gradient_component_max"]
        and value["inverse_hessian_max_abs"]
        <= requirements["inverse_hessian_element_error_max"]
        and value["phase_aligned_state_max_abs"]
        <= requirements["phase_aligned_state_error_max"]
        for value in trajectory["iterations"]
    ]
    terminal_gradient_error = max(
        (
            abs(left - right)
            for left, right in zip(cpu["gradient"], gpu["gradient"])
        ),
        default=0.0,
    )
    terminal_state_error = phase_aligned_max_error(
        cpu_raw["independent_statevector"], gpu_raw["independent_statevector"]
    )
    expected_resources = dict(specification["frozen_CPU_resource_vector"])
    operation_order_equal = cpu_kernel.operation_trace == gpu_kernel.operation_trace
    checks = {
        "predecessor_prefix_passed": len(predecessors)
        == contract["sequential_gate"]["case_order"].index(alias),
        "candidate_ids_exact": list(rewrite.verified_candidate_ids)
        == list(specification["composition_candidate_ids"]),
        "same_device_repeat_determinism": all(
            (
                cpu_probe["state_bitwise_equal"],
                cpu_probe["energy_bitwise_equal"],
                gpu_probe["state_bitwise_equal"],
                gpu_probe["energy_bitwise_equal"],
            )
        ),
        "operation_kind_and_stencil_order": operation_order_equal,
        "trajectory_length": trajectory["length_cpu"]
        == trajectory["length_gpu"],
        "trajectory_iteration_parity": all(trajectory_checks),
        "optimizer_terminal_counts_and_status": all(
            cpu["optimizer_terminal"][field]
            == gpu["optimizer_terminal"][field]
            for field in (
                "success",
                "status",
                "iterations",
                "energy_evaluations_reported",
                "gradient_evaluations_reported",
            )
        ),
        "terminal_energy": abs(
            cpu["energy_hartree"] - gpu["energy_hartree"]
        )
        <= requirements["absolute_energy_hartree_max"],
        "terminal_gradient": terminal_gradient_error
        <= requirements["max_gradient_component_max"],
        "terminal_state": terminal_state_error
        <= requirements["phase_aligned_state_error_max"],
        "terminal_decision": cpu["terminal_decision"]
        == gpu["terminal_decision"]
        == specification["frozen_CPU_terminal_decision"],
        "resources_exact": cpu["resources"]
        == gpu["resources"]
        == expected_resources,
        "explicit_device_metadata": bool(cpu_kernel.metadata)
        and bool(gpu_kernel.metadata)
        and all(value["device"].upper() == "CPU" for value in cpu_kernel.metadata)
        and all(value["device"].upper() == "GPU" for value in gpu_kernel.metadata),
        "no_CPU_fallback": gpu_kernel.counters.N_cpu_fallback == 0,
    }
    result = {
        "schema": "aic-a100-pilot.unified-route-trajectory-case.v4",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "alias": alias,
        "case_id": specification["case_id"],
        "candidate_id": specification["candidate_id"],
        "contract_digest": contract["contract_digest"],
        "runtime_binding": runtime_binding,
        "source_preparation": {
            "manifest_digest": preparation_manifest["manifest_digest"],
            "bundle_sha256": preparation_manifest["bundle_sha256"],
            "candidate_outcomes": 0,
            "separate_process": True,
        },
        "predecessors": predecessors,
        "checks": checks,
        "cpu": cpu,
        "gpu": gpu,
        "determinism_probe": {"cpu": cpu_probe, "gpu": gpu_probe},
        "trajectory": trajectory,
        "trajectory_records": {
            "cpu": _serialized_trajectory(cpu_kernel),
            "gpu": _serialized_trajectory(gpu_kernel),
        },
        "terminal_differences": {
            "energy_hartree": abs(
                cpu["energy_hartree"] - gpu["energy_hartree"]
            ),
            "gradient_max_abs": terminal_gradient_error,
            "phase_aligned_state_max_abs": terminal_state_error,
        },
        "operation_order": {
            "hamiltonian_digest": cpu_kernel.hamiltonian.operation_order_digest,
            "cpu_trace_digest": digest(cpu_kernel.operation_trace),
            "gpu_trace_digest": digest(gpu_kernel.operation_trace),
            "exact_equal": operation_order_equal,
        },
        "route_counters": {
            "cpu": cpu_kernel.counters.as_dict(),
            "gpu": gpu_kernel.counters.as_dict(),
        },
        "hardware": {
            "gpu": _gpu_observation(),
            "slurm_job_id": int(os.environ["SLURM_JOB_ID"]),
            "node": os.environ.get("SLURMD_NODENAME"),
        },
        "scientific_boundary": {
            "new_paired_CPU_candidate_outcomes": 1,
            "new_GPU_candidate_outcomes": 1,
            "FCI_evaluations": 0,
            "candidate_attempt_timing_recorded": False,
            "complete_item_speed_claim": "NOT_AUTHORIZED_BY_CASE_PARITY",
            "existing_90_item_execution": "UNCHANGED",
            "V5_performance_claim": "NOT_AUTHORIZED",
        },
    }
    result["record_digest"] = digest(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case", choices=("h2", "h4", "lih", "h6", "beh2"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared-bundle", type=Path, required=True)
    parser.add_argument("--prepared-manifest", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise RuntimeError(f"refusing to overwrite parity evidence: {arguments.output}")
    result = run_case(
        arguments.case,
        output_dir=arguments.output.parent,
        prepared_bundle=arguments.prepared_bundle,
        prepared_manifest=arguments.prepared_manifest,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
