"""Fail-closed paired CPU/A100 stable-control v2 execution route.

The scientific state, energy, gradient, control quantization, optimizer, and
acceptance semantics are inherited unchanged from stable-control v1.  V2 only
corrects the registered optimizer objective event name and makes start/failure
evidence durable in a new, non-overwriting namespace.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import pickle
import platform
from typing import Any, Mapping, MutableMapping, Sequence

import numpy as np

from v5_matched_work.atomic_artifacts import write_json_exclusive

from .aer_gpu_backend import phase_aligned_max_error
from .benchmark import _gpu_observation
from .common import (
    A100PilotError,
    ROOT,
    digest,
    embedded_digest_valid,
    git,
    load_json,
    publish,
    sha256_file,
)
from .objective_parity import (
    PilotBoundary,
    _attempt_with_kernels,
    _contract_case,
    _serialize_attempt,
)
from .stable_control_route import (
    ENERGY_CONTROL_QUANTUM,
    StableControlDeviceBoundary,
    _maximum_delta,
    quantize_control,
)
from .stable_control_v2_contract import CONTRACT, SOURCE_PATHS
from .unified_route import (
    _serialized_trajectory,
    _software_version,
    _trajectory_differences,
)


OPTIMIZER_EVENT_CROSSWALK = {
    "start": "optimizer-start",
    "iteration": "optimizer-iteration",
    "objective_energy": "optimizer-objective-energy",
    "full_gradient": "full-gradient-evaluation",
}


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
        raise A100PilotError("runtime stable-control v2 source hashes differ")
    thread_keys = (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    )
    process_threads = {key: os.environ.get(key) for key in thread_keys}
    if any(value != "1" for value in process_threads.values()):
        raise A100PilotError("stable-control v2 numerical thread count differs")
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
        raise A100PilotError("stable-control v2 bundle or manifest is absent")
    manifest = load_json(manifest_path)
    if not embedded_digest_valid(manifest, "manifest_digest"):
        raise A100PilotError("stable-control v2 source manifest digest is invalid")
    expected = {
        "schema": "aic-a100-pilot.stable-control-prepared-source.v2",
        "alias": alias,
        "contract_digest": contract["contract_digest"],
        "git_head": os.environ["A100_EXPECTED_HEAD"],
        "counter_scope": "SOURCE_PREPARATION_PROCESS_ONLY",
        "counter_scope_excludes_later_numerical_process": True,
        "candidate_outcomes": 0,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise A100PilotError("stable-control v2 prepared source identity differs")
    if manifest.get("bundle_sha256") != sha256_file(bundle_path):
        raise A100PilotError("stable-control v2 prepared bundle SHA-256 differs")
    with bundle_path.open("rb") as stream:
        prepared = pickle.load(stream)
    if not isinstance(prepared, tuple) or len(prepared) != 3:
        raise A100PilotError("stable-control v2 prepared payload is malformed")
    context, plan, rewrite = prepared
    if list(rewrite.verified_candidate_ids) != list(
        manifest["verified_candidate_ids"]
    ):
        raise A100PilotError("prepared rewrite identity differs from manifest")
    return context, plan, rewrite, manifest


class StableControlV2DeviceBoundary(StableControlDeviceBoundary):
    """Stable-control v1 numerics with registered optimizer accounting."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.optimizer_accounting_audit: list[dict[str, Any]] = []

    def energy(self, coordinates: Sequence[float], indices: Sequence[int]) -> float:
        raw, _ = self._energy_at(
            coordinates,
            indices,
            purpose=OPTIMIZER_EVENT_CROSSWALK["objective_energy"],
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

    def optimize(
        self,
        initial: Sequence[float],
        indices: Sequence[int],
        inverse_hessian: Any,
        *,
        f0: float | None = None,
        g0: Any | None = None,
    ) -> Any:
        result = super().optimize(
            initial, indices, inverse_hessian, f0=f0, g0=g0
        )
        operations = [event.operation for event in self.boundary.events]
        observed = Counter(operations)
        expected = {
            OPTIMIZER_EVENT_CROSSWALK["start"]: 1,
            OPTIMIZER_EVENT_CROSSWALK["iteration"]: int(result.nit),
            OPTIMIZER_EVENT_CROSSWALK["objective_energy"]: int(result.nfev),
            OPTIMIZER_EVENT_CROSSWALK["full_gradient"]: int(result.njev),
        }
        checks = {
            operation: observed[operation] == count
            for operation, count in expected.items()
        }
        audit = {
            "dimension": int(np.asarray(initial).size),
            "expected": expected,
            "observed": {key: observed[key] for key in expected},
            "checks": checks,
        }
        self.optimizer_accounting_audit.append(audit)
        if not all(checks.values()):
            raise A100PilotError(
                f"stable-control v2 optimizer accounting differs: {checks}"
            )
        return result


def _require_predecessors(
    alias: str, output_dir: Path, contract: Mapping[str, Any]
) -> list[dict[str, str]]:
    order = list(contract["sequential_gate"]["case_order"])
    if alias not in order:
        raise A100PilotError(f"case is outside stable-control v2 contract: {alias}")
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


def _kernel_snapshot(kernel: Any | None) -> dict[str, Any]:
    if kernel is None:
        return {"constructed": False}
    operations = Counter(
        event.operation for event in getattr(kernel.boundary, "events", [])
    )
    return {
        "constructed": True,
        "device": str(kernel.device),
        "route_counters": kernel.counters.as_dict(),
        "operation_counts": dict(sorted(operations.items())),
        "operation_trace_length": len(kernel.operation_trace),
        "control_record_count": len(kernel.control_trace),
        "quantization_audit_record_count": len(kernel.quantization_audit),
        "raw_gradient_series_count": len(kernel.raw_gradient_series),
        "trajectory_iteration_count": len(kernel.trajectory),
        "optimizer_accounting_audit": list(kernel.optimizer_accounting_audit),
        "metadata_count": len(kernel.metadata),
    }


def _publish_failure_incident(
    *,
    path: Path,
    alias: str,
    contract: Mapping[str, Any],
    start_record: Mapping[str, Any],
    stage: str,
    error: Exception,
    capture: Mapping[str, Any],
) -> dict[str, Any]:
    body = {
        "schema": "aic-a100-pilot.stable-control-v2-execution-incident.v1",
        "status": "FAILED_ENGINEERING_PRESERVED",
        "alias": alias,
        "contract_digest": contract["contract_digest"],
        "attempt_start_digest": start_record["start_digest"],
        "stage": stage,
        "exception": {
            "type": f"{type(error).__module__}.{type(error).__name__}",
            "message": str(error),
        },
        "partial_execution": {
            "cpu": _kernel_snapshot(capture.get("cpu_kernel")),
            "gpu": _kernel_snapshot(capture.get("gpu_kernel")),
        },
        "scientific_boundary": {
            "FCI_evaluations": 0,
            "existing_90_item_execution": "UNCHANGED",
            "partial_values_eligible_for_parity_or_performance_claim": False,
            "retry_in_same_v2_namespace": "NOT_AUTHORIZED",
        },
    }
    return publish(path, body, "incident_digest")


def _attempt_start_body(
    *, alias: str, contract: Mapping[str, Any], output: Path
) -> dict[str, Any]:
    return {
        "schema": "aic-a100-pilot.stable-control-v2-attempt-start.v1",
        "status": "STARTED_NO_TERMINAL_OUTCOME",
        "alias": alias,
        "contract_digest": contract["contract_digest"],
        "expected_git_head": os.environ.get("A100_EXPECTED_HEAD"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "node": os.environ.get("SLURMD_NODENAME"),
        "output_name": output.name,
        "candidate_outcomes_before_start_record": 0,
        "FCI_evaluations_before_start_record": 0,
        "existing_90_item_execution": "UNCHANGED",
    }


def _run_case_impl(
    alias: str,
    *,
    output_dir: Path,
    prepared_bundle: Path,
    prepared_manifest: Path,
    contract: Mapping[str, Any],
    start_record: Mapping[str, Any],
    capture: MutableMapping[str, Any],
) -> dict[str, Any]:
    capture["stage"] = "runtime-binding"
    runtime_binding = _runtime_binding(contract)
    capture["stage"] = "predecessor-validation"
    predecessors = _require_predecessors(alias, output_dir, contract)
    _, specification = _contract_case(alias)
    capture["stage"] = "prepared-source-validation"
    context, plan, rewrite, preparation_manifest = _load_prepared_bundle(
        alias=alias,
        contract=contract,
        bundle_path=prepared_bundle,
        manifest_path=prepared_manifest,
    )

    capture["stage"] = "kernel-construction"
    cpu_kernel = StableControlV2DeviceBoundary(
        context._actual_algorithm, context.pool, PilotBoundary(), device="CPU"
    )
    capture["cpu_kernel"] = cpu_kernel
    gpu_kernel = StableControlV2DeviceBoundary(
        context._actual_algorithm, context.pool, PilotBoundary(), device="GPU"
    )
    capture["gpu_kernel"] = gpu_kernel
    capture["stage"] = "cpu-determinism-probe"
    cpu_probe = cpu_kernel.determinism_probe(
        rewrite.target.coefficients, rewrite.target.indices
    )
    capture["stage"] = "gpu-determinism-probe"
    gpu_probe = gpu_kernel.determinism_probe(
        rewrite.target.coefficients, rewrite.target.indices
    )
    capture["stage"] = "cpu-candidate-attempt"
    cpu_raw = _attempt_with_kernels(
        context=context,
        kernels=cpu_kernel,
        target=rewrite.target,
        inverse_hessian=rewrite.target_inverse_hessian,
        parent_plan=plan,
    )
    capture["stage"] = "gpu-candidate-attempt"
    gpu_raw = _attempt_with_kernels(
        context=context,
        kernels=gpu_kernel,
        target=rewrite.target,
        inverse_hessian=rewrite.target_inverse_hessian,
        parent_plan=plan,
    )
    capture["stage"] = "paired-result-validation"
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
        "optimizer_accounting_complete": bool(
            cpu_kernel.optimizer_accounting_audit
        )
        and bool(gpu_kernel.optimizer_accounting_audit)
        and all(cpu_kernel.optimizer_accounting_audit[-1]["checks"].values())
        and all(gpu_kernel.optimizer_accounting_audit[-1]["checks"].values()),
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
        "schema": "aic-a100-pilot.stable-control-trajectory-case.v2",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "alias": alias,
        "case_id": specification["case_id"],
        "candidate_id": specification["candidate_id"],
        "contract_digest": contract["contract_digest"],
        "attempt_start_digest": start_record["start_digest"],
        "runtime_binding": runtime_binding,
        "source_preparation": {
            "manifest_digest": preparation_manifest["manifest_digest"],
            "bundle_sha256": preparation_manifest["bundle_sha256"],
            "counter_scope": preparation_manifest["counter_scope"],
            "counter_scope_excludes_later_numerical_process": True,
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
        "optimizer_accounting": {
            "event_crosswalk": OPTIMIZER_EVENT_CROSSWALK,
            "cpu": cpu_kernel.optimizer_accounting_audit,
            "gpu": gpu_kernel.optimizer_accounting_audit,
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
    capture["stage"] = "terminal-result-built"
    return result


def run_case(
    alias: str,
    *,
    output_dir: Path,
    prepared_bundle: Path,
    prepared_manifest: Path,
    incident_path: Path,
    start_record: Mapping[str, Any],
    execution_capture: MutableMapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract = load_json(CONTRACT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise A100PilotError("stable-control v2 contract digest is invalid")
    capture = execution_capture if execution_capture is not None else {}
    capture["stage"] = "preflight"
    try:
        return _run_case_impl(
            alias,
            output_dir=output_dir,
            prepared_bundle=prepared_bundle,
            prepared_manifest=prepared_manifest,
            contract=contract,
            start_record=start_record,
            capture=capture,
        )
    except Exception as error:
        _publish_failure_incident(
            path=incident_path,
            alias=alias,
            contract=contract,
            start_record=start_record,
            stage=str(capture["stage"]),
            error=error,
            capture=capture,
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case", choices=("h2", "h4", "lih", "h6", "beh2"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared-bundle", type=Path, required=True)
    parser.add_argument("--prepared-manifest", type=Path, required=True)
    parser.add_argument("--start-record", type=Path, required=True)
    parser.add_argument("--incident", type=Path, required=True)
    arguments = parser.parse_args()
    protected = (arguments.output, arguments.start_record, arguments.incident)
    existing = [path for path in protected if path.exists()]
    if existing:
        raise RuntimeError(f"refusing to overwrite stable-control v2 evidence: {existing}")
    contract = load_json(CONTRACT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise A100PilotError("stable-control v2 contract digest is invalid")
    start_record = publish(
        arguments.start_record,
        _attempt_start_body(
            alias=arguments.case, contract=contract, output=arguments.output
        ),
        "start_digest",
    )
    execution_capture: dict[str, Any] = {}
    result = run_case(
        arguments.case,
        output_dir=arguments.output.parent,
        prepared_bundle=arguments.prepared_bundle,
        prepared_manifest=arguments.prepared_manifest,
        incident_path=arguments.incident,
        start_record=start_record,
        execution_capture=execution_capture,
    )
    try:
        write_json_exclusive(arguments.output, result)
    except Exception as error:
        _publish_failure_incident(
            path=arguments.incident,
            alias=arguments.case,
            contract=contract,
            start_record=start_record,
            stage="terminal-result-publication",
            error=error,
            capture=execution_capture,
        )
        raise
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
