"""Frozen successor contract for numerically stable CPU/A100 control parity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .common import (
    ARTIFACT_ROOT,
    ROOT,
    embedded_digest_valid,
    load_json,
    publish,
    sha256_file,
)
from .p0_baseline import PROTOCOL


CONTRACT = (
    ARTIFACT_ROOT
    / "p7-unified-stable-v1/stable-control-trajectory-contract-v1.json"
)
UNIFIED_V4_CONTRACT = (
    ARTIFACT_ROOT
    / "p3-unified-route-v4/unified-route-trajectory-contract-v4.json"
)
UNIFIED_V4_H4_RESULT = (
    ARTIFACT_ROOT / "p3-unified-route-v4/results/h4.json"
)
UNIFIED_V4_TERMINAL = (
    ARTIFACT_ROOT
    / "p6-unified-route-decision/unified-route-terminal-no-go-v1.json"
)
SOURCE_PATHS = (
    ROOT / "src/aic_a100_pilot/stable_control_route.py",
    ROOT / "src/aic_a100_pilot/stable_control_prepare.py",
    ROOT / "scripts/aic/a100_stable_control_trajectory.sbatch",
)


def _binding(path: Path, *, digest_field: str) -> dict[str, str]:
    value = load_json(path)
    if not embedded_digest_valid(value, digest_field):
        raise RuntimeError(f"invalid evidence digest: {path}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(path),
        digest_field: str(value[digest_field]),
    }


def contract_body() -> dict[str, Any]:
    protocol = load_json(PROTOCOL)
    predecessor_contract = load_json(UNIFIED_V4_CONTRACT)
    predecessor_result = load_json(UNIFIED_V4_H4_RESULT)
    predecessor_terminal = load_json(UNIFIED_V4_TERMINAL)
    if not embedded_digest_valid(protocol, "protocol_digest"):
        raise RuntimeError("P0 protocol digest is invalid")
    if not embedded_digest_valid(predecessor_contract, "contract_digest"):
        raise RuntimeError("unified-route v4 contract digest is invalid")
    if not embedded_digest_valid(predecessor_result, "record_digest"):
        raise RuntimeError("unified-route v4 H4 result digest is invalid")
    if not embedded_digest_valid(predecessor_terminal, "decision_digest"):
        raise RuntimeError("unified-route v4 decision digest is invalid")
    if predecessor_terminal["status"] != (
        "NO_GO_A100_UNIFIED_ROUTE_H4_TRAJECTORY_NONPARITY"
    ):
        raise RuntimeError("unified-route v4 terminal status differs")
    missing = [path for path in SOURCE_PATHS if not path.is_file()]
    if missing:
        raise RuntimeError(f"stable-control implementation is incomplete: {missing}")
    tolerances = protocol["tolerances"]
    return {
        "schema": "aic-a100-pilot.stable-control-trajectory-contract.v1",
        "status": "GO_BOUNDED_STABLE_CONTROL_TRAJECTORY_CALIBRATION",
        "frozen_before_new_stable_control_candidate_outcomes": True,
        "immutable_predecessor": {
            "preserved_without_mutation": True,
            "contract": _binding(
                UNIFIED_V4_CONTRACT, digest_field="contract_digest"
            ),
            "h4_result": _binding(
                UNIFIED_V4_H4_RESULT, digest_field="record_digest"
            ),
            "terminal_no_go": _binding(
                UNIFIED_V4_TERMINAL, digest_field="decision_digest"
            ),
            "status": predecessor_terminal["status"],
        },
        "causal_diagnosis": {
            "classification": "OPTIMIZER_CONTROL_NUMERICAL_SENSITIVITY",
            "H4_terminal_raw_energy_difference_hartree": predecessor_result[
                "terminal_differences"
            ]["energy_hartree"],
            "H4_first_iteration_inverse_hessian_max_abs": predecessor_result[
                "trajectory"
            ]["iterations"][0]["inverse_hessian_max_abs"],
            "H4_CPU_iterations": predecessor_result["trajectory"]["length_cpu"],
            "H4_GPU_iterations": predecessor_result["trajectory"]["length_gpu"],
            "interpretation": (
                "double-precision CPU/GPU state routes agree in terminal energy, "
                "but the h=1e-4 finite-difference derivative and BFGS update amplify "
                "roundoff into a line-search trajectory branch"
            ),
            "H4_is_declared_development_calibration_case": True,
            "H4_is_not_an_independent_confirmation_case": True,
        },
        "source_binding": {
            path.relative_to(ROOT).as_posix(): sha256_file(path)
            for path in SOURCE_PATHS
        },
        "candidate_binding": {
            "selection_changed": False,
            "ansatz_changed": False,
            "rewrite_changed": False,
            "molecular_source_changed": False,
            "only_optimizer_control_numerics_changed": True,
        },
        "route_contract": {
            "paired_devices": ["CPU", "GPU"],
            "state": "Qiskit Aer statevector, double precision, complex128 output",
            "raw_energy": (
                "same-device statevector followed by fixed-order complex128 CSR "
                "contributions and fixed pairwise reduction"
            ),
            "gradient": (
                "sixth-order seven-point central finite difference of the exact "
                "same raw energy function used on each device"
            ),
            "stencil_order": [-3, -2, -1, 1, 2, 3],
            "finite_difference_step": 0.01,
            "finite_difference_step_float64_hex": "3f847ae147ae147b",
            "optimizer_control_energy_quantum_hartree": 1e-12,
            "optimizer_control_gradient_quantum_hartree": 1e-10,
            "control_quantization": (
                "round-to-nearest-even integer grid in float64; integer control "
                "codes are recorded for every optimizer energy and gradient"
            ),
            "maximum_energy_control_perturbation_hartree": 5e-13,
            "maximum_gradient_control_perturbation_hartree": 5e-11,
            "final_acceptance_energy_is_raw_unquantized": True,
            "final_state_is_raw_unquantized_complex128": True,
            "raw_and_control_values_both_audited": True,
            "parameter_order": "target indices in frozen order, ascending position",
            "hamiltonian_order": "CSR rows ascending; sorted columns within row",
            "reduction_tree": (
                "adjacent complex128 pairwise sums; odd tail carried unchanged"
            ),
            "state_normalization": "fixed pairwise complex128 norm reduction",
            "aer_fusion_enable": False,
            "aer_max_parallel_threads": 1,
            "aer_max_parallel_experiments": 1,
            "aer_max_parallel_shots": 1,
            "aer_seed_simulator": 0,
            "source_reconstruction_thread_environment": {
                "h2": 2,
                "h4": 1,
                "lih": 1,
                "h6": 1,
                "beh2": 1,
            },
            "source_and_numerical_processes_are_separate": True,
            "numerical_process_thread_environment": 1,
            "CPU_fallback_allowed": False,
            "runtime_source_hash_validation": "REQUIRED_BEFORE_CASE_PREPARATION",
        },
        "numerical_change_rationale": {
            "bounded_single_successor_not_grid_search": True,
            "step_or_quantum_search_after_H4_outcomes": False,
            "seven_point_reason": (
                "the O(h^6) central stencil permits a larger h to suppress "
                "roundoff amplification while retaining small truncation error"
            ),
            "control_quantization_reason": (
                "prevent sub-physical double-precision route differences from "
                "changing BFGS line-search branches"
            ),
            "accuracy_guard": (
                "raw independent energy/state remain unquantized; energy control "
                "perturbation is 200 times smaller than the 1e-10 independent-"
                "energy agreement tolerance"
            ),
        },
        "optimizer_contract": {
            "optimizer": "pinned adaptvqe.minimize:minimize_bfgs",
            "initial_coordinates": "unchanged selected rewrite target",
            "initial_inverse_hessian": "unchanged selected rewrite target",
            "gtol": 1e-8,
            "maxiter": 1000,
            "trajectory_observation": (
                "every completed BFGS iteration: coordinates, control energy, "
                "control gradient, inverse Hessian, and raw state"
            ),
        },
        "sequential_gate": {
            "case_order": ["h2", "h4", "lih", "h6", "beh2"],
            "H2_role": "engineering sanity case",
            "H4_role": "declared development calibration case",
            "LiH_role": "first independent numerical confirmation checkpoint",
            "stop_on_first_failure": True,
            "H6_BeH2_before_LiH_pass": "NOT_AUTHORIZED",
            "complete_item_timing_before_all_parity_pass": "NOT_AUTHORIZED",
            "candidate_attempt_timing_during_parity": "NOT_RECORDED",
        },
        "parity_requirements": {
            "phase_aligned_state_error_max": tolerances[
                "phase_aligned_state_error_max"
            ],
            "absolute_energy_hartree_max": tolerances[
                "absolute_energy_hartree_max"
            ],
            "max_gradient_component_max": tolerances[
                "max_gradient_component_max"
            ],
            "coordinate_error_max": 1e-10,
            "inverse_hessian_element_error_max": 1e-8,
            "trajectory_length": "EXACT_EQUALITY",
            "optimizer_terminal_counts_and_status": "EXACT_EQUALITY",
            "terminal_decision": "EXACT_EQUALITY_CPU_GPU_AND_FROZEN_REFERENCE",
            "resource_vector": "EXACT_INTEGER_EQUALITY",
            "operation_kind_stencil_and_control_codes": "EXACT_EQUALITY",
            "same_device_repeat_state_and_energy": "BITWISE_EQUALITY",
            "raw_control_perturbation_bounds": "REQUIRED",
        },
        "timing_contract_if_and_only_if_all_parity_passes": {
            "complete_item_scope": (
                "source/rewrite preparation, optimization, acceptance checks, "
                "and full resource recount"
            ),
            "same_AIC_node": True,
            "warmups": 1,
            "measured_repetitions": 5,
            "report_median_and_all_samples": True,
            "speedup_threshold": 1.2,
        },
        "scientific_boundary": {
            "FCI_evaluations": 0,
            "existing_90_item_execution": "UNCHANGED",
            "Measurement_Cost_claim": "NOT_AUTHORIZED",
            "V5_performance_claim": "NOT_AUTHORIZED",
            "A100_adoption_for_matched_work": "NOT_AUTHORIZED_BY_THIS_CONTRACT",
            "post_outcome_threshold_change": "PROHIBITED",
        },
    }


def publish_contract() -> dict[str, Any]:
    return publish(CONTRACT, contract_body(), "contract_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish_contract(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
