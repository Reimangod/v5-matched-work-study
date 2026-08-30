"""Outcome-blind successor contract for unified CPU/A100 optimizer parity."""

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
from .p3_objective_contract import CONTRACT as HYBRID_CONTRACT


CONTRACT_V1 = (
    ARTIFACT_ROOT
    / "p3-unified-route-v1/unified-route-trajectory-contract-v1.json"
)
CONTRACT = (
    ARTIFACT_ROOT
    / "p3-unified-route-v2/unified-route-trajectory-contract-v2.json"
)
HYBRID_REPORT = (
    ARTIFACT_ROOT
    / "p3-objective-parity/production-objective-parity-report-v1.json"
)
TERMINAL_NO_GO = (
    ARTIFACT_ROOT / "p6-decision/a100-pilot-terminal-decision-v3.json"
)
SOURCE_PATHS = (
    ROOT / "src/aic_a100_pilot/unified_route.py",
    ROOT / "scripts/aic/a100_unified_trajectory.sbatch",
)


def _binding(path: Path, *, embedded_field: str) -> dict[str, str]:
    value = load_json(path)
    if not embedded_digest_valid(value, embedded_field):
        raise RuntimeError(f"invalid immutable evidence digest: {path}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(path),
        embedded_field: str(value[embedded_field]),
    }


def contract_body() -> dict[str, Any]:
    protocol = load_json(PROTOCOL)
    hybrid_contract = load_json(HYBRID_CONTRACT)
    hybrid_report = load_json(HYBRID_REPORT)
    terminal = load_json(TERMINAL_NO_GO)
    if not embedded_digest_valid(protocol, "protocol_digest"):
        raise RuntimeError("P0 protocol digest is invalid")
    if not embedded_digest_valid(hybrid_contract, "contract_digest"):
        raise RuntimeError("hybrid objective contract digest is invalid")
    if hybrid_report["status"] != "NO_GO_A100_NUMERICAL_NONPARITY":
        raise RuntimeError("hybrid report is not the immutable terminal No-Go")
    if terminal["status"] != "NO_GO_A100_NUMERICAL_NONPARITY":
        raise RuntimeError("terminal A100 decision is not the immutable No-Go")
    if terminal["terminal_failure"]["alias"] != "lih":
        raise RuntimeError("terminal A100 decision does not bind the LiH failure")
    missing = [path for path in SOURCE_PATHS if not path.is_file()]
    if missing:
        raise RuntimeError(f"unified-route implementation is incomplete: {missing}")
    tolerances = protocol["tolerances"]
    return {
        "schema": "aic-a100-pilot.unified-route-trajectory-contract.v2",
        "status": "GO_BOUNDED_UNIFIED_ROUTE_TRAJECTORY_PARITY",
        "frozen_before_new_unified_route_candidate_outcomes": True,
        "pre_outcome_correction": {
            "superseded_contract": _binding(
                CONTRACT_V1, embedded_field="contract_digest"
            ),
            "new_unified_route_candidate_outcomes_before_v2_freeze": 0,
            "reason": (
                "v1 bound source hashes but did not require each result to carry "
                "its exact Git, submodule, and software runtime identity"
            ),
            "v1_remains_immutable": True,
        },
        "immutable_predecessor_no_go": {
            "preserved_without_mutation": True,
            "hybrid_report": _binding(
                HYBRID_REPORT, embedded_field="report_digest"
            ),
            "terminal_decision": _binding(
                TERMINAL_NO_GO, embedded_field="decision_digest"
            ),
            "authorized_predecessor_claim": terminal["scientific_boundaries"][
                "authorized_claim"
            ],
        },
        "source_binding": {
            path.relative_to(ROOT).as_posix(): sha256_file(path)
            for path in SOURCE_PATHS
        },
        "candidate_binding": {
            "hybrid_contract_path": HYBRID_CONTRACT.relative_to(ROOT).as_posix(),
            "hybrid_contract_sha256": sha256_file(HYBRID_CONTRACT),
            "hybrid_contract_digest": hybrid_contract["contract_digest"],
            "candidate_selection_changed": False,
            "ansatz_or_rewrite_changed": False,
        },
        "route_contract": {
            "paired_devices": ["CPU", "GPU"],
            "state": "Qiskit Aer statevector, double precision, complex128 output",
            "energy": (
                "same-device statevector followed by serially specified complex128 "
                "CSR contribution construction and fixed pairwise reduction"
            ),
            "gradient": (
                "five-point central finite difference of the exact same energy "
                "function used by the optimizer"
            ),
            "CPU_analytic_gradient_used": False,
            "finite_difference_step_float64_hex": "3f1a36e2eb1c432d",
            "parameter_order": "target indices in frozen order, ascending position",
            "stencil_order": [-2, -1, 1, 2],
            "hamiltonian_order": (
                "CSR rows ascending; sorted column index within each row"
            ),
            "reduction_tree": (
                "adjacent complex128 pairwise sums; odd tail carried unchanged"
            ),
            "state_normalization": "same fixed pairwise complex128 norm reduction",
            "aer_fusion_enable": False,
            "aer_max_parallel_threads": 1,
            "aer_max_parallel_experiments": 1,
            "aer_max_parallel_shots": 1,
            "aer_seed_simulator": 0,
            "BLAS_and_OpenMP_threads": 1,
            "CPU_fallback_allowed": False,
            "runtime_source_hash_validation": "REQUIRED_BEFORE_CASE_PREPARATION",
            "result_runtime_identity": (
                "exact Git HEAD, expected HEAD, submodule HEADs, contract file SHA, "
                "source SHAs, Python, NumPy, SciPy, Qiskit, and Qiskit Aer"
            ),
        },
        "optimizer_contract": {
            "optimizer": "pinned adaptvqe.minimize:minimize_bfgs",
            "initial_coordinates": "unchanged selected rewrite target",
            "initial_inverse_hessian": "unchanged selected rewrite target",
            "gtol": 1e-8,
            "maxiter": 1000,
            "trajectory_observation": (
                "every completed BFGS iteration: coordinates, energy, gradient, "
                "inverse Hessian, and state prepared at the iteration coordinates"
            ),
        },
        "sequential_gate": {
            "case_order": ["h2", "h4", "lih", "h6", "beh2"],
            "mandatory_prefix_before_h6_beh2": ["h2", "h4", "lih"],
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
            "operation_kind_and_stencil_order": "EXACT_EQUALITY",
            "same_device_repeat_state_and_energy": "BITWISE_EQUALITY",
        },
        "timing_contract_if_and_only_if_all_parity_passes": {
            "complete_item_scope": (
                "rewrite preparation, optimization, acceptance checks, and full "
                "resource recount"
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
            "post_outcome_tolerance_change": "PROHIBITED",
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
