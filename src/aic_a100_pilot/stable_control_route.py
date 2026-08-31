"""Numerically stable paired CPU/A100 route for optimizer-control parity.

The raw state and energy paths are unchanged from unified-route v4.  Only the
optimizer control surface changes: a seven-point O(h^6) derivative at h=1e-2
and preregistered, audited control grids prevent sub-physical floating-point
differences from selecting different BFGS line-search branches.  Acceptance
energy and state remain raw and unquantized.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata as importlib_metadata
import json
import os
from pathlib import Path
import pickle
import platform
from typing import Any, Mapping, Sequence

import numpy as np

from .aer_gpu_backend import phase_aligned_max_error
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
from .stable_control_contract import CONTRACT, SOURCE_PATHS
from .unified_route import (
    UnifiedDeviceBoundary,
    _array_hex,
    _float_hex,
    _serialized_trajectory,
    _software_version,
    _trajectory_differences,
)


STENCIL = (-3, -2, -1, 1, 2, 3)
STENCIL_WEIGHTS = (-1, 9, -45, 45, -9, 1)
FINITE_DIFFERENCE_STEP = np.float64(1e-2)
ENERGY_CONTROL_QUANTUM = np.float64(1e-12)
GRADIENT_CONTROL_QUANTUM = np.float64(1e-10)


def quantize_control(value: float, quantum: np.float64) -> tuple[float, int, float]:
    raw = np.float64(value)
    spacing = np.float64(quantum)
    if not np.isfinite(raw) or not np.isfinite(spacing) or spacing <= 0.0:
        raise A100PilotError("control quantization received a nonfinite value")
    code = int(np.rint(np.float64(raw / spacing)))
    control = np.float64(np.float64(code) * spacing)
    delta = float(abs(np.float64(control - raw)))
    allowance = float(spacing / np.float64(2.0)) + 8.0 * float(
        np.spacing(abs(raw) if raw != 0.0 else np.float64(1.0))
    )
    if delta > allowance:
        raise A100PilotError("control quantization exceeded the frozen half-grid")
    return float(control), code, delta


def seven_point_derivative(
    energies: Mapping[int, float], step: np.float64 = FINITE_DIFFERENCE_STEP
) -> float:
    if tuple(energies) != STENCIL:
        raise A100PilotError("seven-point energies are outside frozen order")
    numerator = np.float64(0.0)
    for multiple, weight in zip(STENCIL, STENCIL_WEIGHTS):
        term = np.float64(np.float64(weight) * np.float64(energies[multiple]))
        numerator = np.float64(numerator + term)
    denominator = np.float64(np.float64(60.0) * np.float64(step))
    return float(np.float64(numerator / denominator))


def _runtime_binding(contract: Mapping[str, Any]) -> dict[str, Any]:
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
        raise A100PilotError("runtime stable-control source hashes differ")
    thread_keys = (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    )
    process_threads = {key: os.environ.get(key) for key in thread_keys}
    if any(value != "1" for value in process_threads.values()):
        raise A100PilotError("stable-control numerical thread count differs")
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
        raise A100PilotError("stable-control bundle or manifest is absent")
    manifest = load_json(manifest_path)
    if not embedded_digest_valid(manifest, "manifest_digest"):
        raise A100PilotError("stable-control source manifest digest is invalid")
    expected = {
        "alias": alias,
        "contract_digest": contract["contract_digest"],
        "git_head": os.environ["A100_EXPECTED_HEAD"],
        "candidate_outcomes": 0,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise A100PilotError("stable-control prepared source identity differs")
    if manifest.get("bundle_sha256") != sha256_file(bundle_path):
        raise A100PilotError("stable-control prepared bundle SHA-256 differs")
    with bundle_path.open("rb") as stream:
        prepared = pickle.load(stream)
    if not isinstance(prepared, tuple) or len(prepared) != 3:
        raise A100PilotError("stable-control prepared payload is malformed")
    context, plan, rewrite = prepared
    if list(rewrite.verified_candidate_ids) != list(
        manifest["verified_candidate_ids"]
    ):
        raise A100PilotError("prepared rewrite identity differs from manifest")
    return context, plan, rewrite, manifest


class StableControlDeviceBoundary(UnifiedDeviceBoundary):
    """Unchanged raw quantum route with a canonical optimizer control plane."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.control_trace: list[dict[str, Any]] = []
        self.quantization_audit: list[dict[str, Any]] = []
        self.raw_gradient_series: list[list[float]] = []

    def _record_control(
        self,
        *,
        kind: str,
        raw: float,
        control: float,
        code: int,
        delta: float,
        parameter_position: int | None = None,
    ) -> None:
        self.control_trace.append(
            {
                "kind": kind,
                "parameter_position": parameter_position,
                "integer_code": code,
            }
        )
        self.quantization_audit.append(
            {
                "kind": kind,
                "parameter_position": parameter_position,
                "raw_float64": _float_hex(raw),
                "control_float64": _float_hex(control),
                "integer_code": code,
                "absolute_delta": delta,
            }
        )

    def energy(self, coordinates: Sequence[float], indices: Sequence[int]) -> float:
        raw, _ = self._energy_at(
            coordinates, indices, purpose="optimizer-objective-raw-energy"
        )
        control, code, delta = quantize_control(raw, ENERGY_CONTROL_QUANTUM)
        self._record_control(
            kind="optimizer-control-energy",
            raw=raw,
            control=control,
            code=code,
            delta=delta,
        )
        return control

    def gradient(
        self, coordinates: Sequence[float], indices: Sequence[int]
    ) -> np.ndarray:
        origin = np.asarray(coordinates, dtype=np.float64).reshape(-1)

        def call() -> np.ndarray:
            raw_derivatives: list[float] = []
            controls: list[float] = []
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
                        purpose="gradient-stencil-raw-energy",
                        parameter_position=position,
                        stencil_multiple=multiple,
                    )
                raw = seven_point_derivative(energies)
                control, code, delta = quantize_control(
                    raw, GRADIENT_CONTROL_QUANTUM
                )
                raw_derivatives.append(raw)
                controls.append(control)
                self._record_control(
                    kind="optimizer-control-gradient",
                    raw=raw,
                    control=control,
                    code=code,
                    delta=delta,
                    parameter_position=position,
                )
                self.counters.N_gradient_component += 1
            self.raw_gradient_series.append(raw_derivatives)
            return np.asarray(controls, dtype=np.float64)

        return np.asarray(
            self.boundary.invoke(
                "full-gradient-evaluation",
                call,
                dimension=origin.size,
                evidence={
                    "route": "same-raw-energy-seven-point-stable-control",
                    "step_float64": _float_hex(FINITE_DIFFERENCE_STEP),
                },
            ),
            dtype=np.float64,
        )


def _require_predecessors(
    alias: str, output_dir: Path, contract: Mapping[str, Any]
) -> list[dict[str, str]]:
    order = list(contract["sequential_gate"]["case_order"])
    if alias not in order:
        raise A100PilotError(f"case is outside stable-control contract: {alias}")
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


def _maximum_delta(records: Sequence[Mapping[str, Any]], kind: str) -> float:
    values = [
        float(record["absolute_delta"])
        for record in records
        if record["kind"] == kind
    ]
    return max(values, default=0.0)


def run_case(
    alias: str,
    *,
    output_dir: Path,
    prepared_bundle: Path,
    prepared_manifest: Path,
) -> dict[str, Any]:
    contract = load_json(CONTRACT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise A100PilotError("stable-control contract digest is invalid")
    runtime_binding = _runtime_binding(contract)
    predecessors = _require_predecessors(alias, output_dir, contract)
    _, specification = _contract_case(alias)
    context, plan, rewrite, preparation_manifest = _load_prepared_bundle(
        alias=alias,
        contract=contract,
        bundle_path=prepared_bundle,
        manifest_path=prepared_manifest,
    )

    cpu_kernel = StableControlDeviceBoundary(
        context._actual_algorithm, context.pool, PilotBoundary(), device="CPU"
    )
    gpu_kernel = StableControlDeviceBoundary(
        context._actual_algorithm, context.pool, PilotBoundary(), device="GPU"
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
        (abs(left - right) for left, right in zip(cpu["gradient"], gpu["gradient"])),
        default=0.0,
    )
    terminal_state_error = phase_aligned_max_error(
        cpu_raw["independent_statevector"], gpu_raw["independent_statevector"]
    )
    terminal_raw_energy_error = abs(
        cpu["independent_energy_hartree"] - gpu["independent_energy_hartree"]
    )
    expected_resources = dict(specification["frozen_CPU_resource_vector"])
    operation_order_equal = cpu_kernel.operation_trace == gpu_kernel.operation_trace
    control_code_equal = cpu_kernel.control_trace == gpu_kernel.control_trace
    energy_delta_max = max(
        _maximum_delta(cpu_kernel.quantization_audit, "optimizer-control-energy"),
        _maximum_delta(gpu_kernel.quantization_audit, "optimizer-control-energy"),
    )
    gradient_delta_max = max(
        _maximum_delta(cpu_kernel.quantization_audit, "optimizer-control-gradient"),
        _maximum_delta(gpu_kernel.quantization_audit, "optimizer-control-gradient"),
    )
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
        "optimizer_control_codes": control_code_equal,
        "raw_control_perturbation_bounds": energy_delta_max
        <= contract["route_contract"][
            "maximum_energy_control_perturbation_hartree"
        ]
        and gradient_delta_max
        <= contract["route_contract"][
            "maximum_gradient_control_perturbation_hartree"
        ],
        "trajectory_length": trajectory["length_cpu"]
        == trajectory["length_gpu"],
        "trajectory_iteration_parity": all(trajectory_checks),
        "optimizer_terminal_counts_and_status": all(
            cpu["optimizer_terminal"][field] == gpu["optimizer_terminal"][field]
            for field in (
                "success",
                "status",
                "iterations",
                "energy_evaluations_reported",
                "gradient_evaluations_reported",
            )
        ),
        "terminal_control_energy": abs(
            cpu["energy_hartree"] - gpu["energy_hartree"]
        )
        <= requirements["absolute_energy_hartree_max"],
        "terminal_raw_energy": terminal_raw_energy_error
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
        "schema": "aic-a100-pilot.stable-control-trajectory-case.v1",
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
            "control_energy_hartree": abs(
                cpu["energy_hartree"] - gpu["energy_hartree"]
            ),
            "raw_independent_energy_hartree": terminal_raw_energy_error,
            "control_gradient_max_abs": terminal_gradient_error,
            "phase_aligned_state_max_abs": terminal_state_error,
        },
        "control_audit": {
            "CPU_records": cpu_kernel.quantization_audit,
            "GPU_records": gpu_kernel.quantization_audit,
            "CPU_control_trace_digest": digest(cpu_kernel.control_trace),
            "GPU_control_trace_digest": digest(gpu_kernel.control_trace),
            "control_codes_exact_equal": control_code_equal,
            "maximum_energy_control_delta_hartree": energy_delta_max,
            "maximum_gradient_control_delta_hartree": gradient_delta_max,
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
