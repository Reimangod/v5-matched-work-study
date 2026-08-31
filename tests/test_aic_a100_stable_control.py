from __future__ import annotations

import struct

import numpy as np

from aic_a100_pilot.common import (
    embedded_digest_valid,
    load_json,
    sha256_file,
)
from aic_a100_pilot.stable_control_contract import (
    CONTRACT,
    SOURCE_PATHS,
    UNIFIED_V4_CONTRACT,
    UNIFIED_V4_H4_RESULT,
    UNIFIED_V4_TERMINAL,
    contract_body,
)
from aic_a100_pilot.stable_control_route import (
    ENERGY_CONTROL_QUANTUM,
    FINITE_DIFFERENCE_STEP,
    GRADIENT_CONTROL_QUANTUM,
    STENCIL,
    quantize_control,
    seven_point_derivative,
)


EXPECTED_V4_CONTRACT_SHA256 = (
    "0192e2e0362f74b9c6054fd361525c0ef9f52ec5b027c16ad73ed9a73c9414b4"
)
EXPECTED_V4_H4_SHA256 = (
    "0e81de6db420df5f6f139b87478f326a4f0559804a6b4680ae44363bcd747a49"
)
EXPECTED_V4_TERMINAL_SHA256 = (
    "93c40ac7d43977bb86ea2ecd4a6a82d232c78b70155c0f985d3a7541fa5d5a3f"
)


def _float_hex(value: float) -> str:
    return struct.pack(">d", float(value)).hex()


def test_stable_contract_is_additive_and_preserves_v4_no_go():
    value = contract_body()
    assert value["status"] == "GO_BOUNDED_STABLE_CONTROL_TRAJECTORY_CALIBRATION"
    assert value["frozen_before_new_stable_control_candidate_outcomes"] is True
    assert sha256_file(UNIFIED_V4_CONTRACT) == EXPECTED_V4_CONTRACT_SHA256
    assert sha256_file(UNIFIED_V4_H4_RESULT) == EXPECTED_V4_H4_SHA256
    assert sha256_file(UNIFIED_V4_TERMINAL) == EXPECTED_V4_TERMINAL_SHA256
    assert value["immutable_predecessor"]["preserved_without_mutation"] is True
    assert value["causal_diagnosis"][
        "H4_is_declared_development_calibration_case"
    ] is True
    assert value["causal_diagnosis"][
        "H4_is_not_an_independent_confirmation_case"
    ] is True
    assert value["candidate_binding"]["only_optimizer_control_numerics_changed"]
    assert value["route_contract"]["stencil_order"] == list(STENCIL)
    assert value["route_contract"]["finite_difference_step_float64_hex"] == (
        _float_hex(FINITE_DIFFERENCE_STEP)
    )
    assert value["route_contract"]["final_acceptance_energy_is_raw_unquantized"]
    assert value["route_contract"]["final_state_is_raw_unquantized_complex128"]
    assert value["numerical_change_rationale"][
        "bounded_single_successor_not_grid_search"
    ]
    assert value["numerical_change_rationale"][
        "step_or_quantum_search_after_H4_outcomes"
    ] is False
    assert value["sequential_gate"]["case_order"] == [
        "h2",
        "h4",
        "lih",
        "h6",
        "beh2",
    ]
    assert value["sequential_gate"]["H6_BeH2_before_LiH_pass"] == (
        "NOT_AUTHORIZED"
    )
    assert value["scientific_boundary"]["FCI_evaluations"] == 0
    assert value["scientific_boundary"]["existing_90_item_execution"] == (
        "UNCHANGED"
    )


def test_seven_point_derivative_is_exact_for_low_degree_polynomials():
    x = np.float64(0.37)
    for degree in range(1, 7):
        energies = {
            multiple: float((x + multiple * FINITE_DIFFERENCE_STEP) ** degree)
            for multiple in STENCIL
        }
        observed = seven_point_derivative(energies)
        expected = float(degree * x ** (degree - 1))
        assert abs(observed - expected) < 2e-11


def test_control_quantization_is_bounded_and_returns_integer_codes():
    energy_raw = -1.9947889343241307
    energy, energy_code, energy_delta = quantize_control(
        energy_raw, ENERGY_CONTROL_QUANTUM
    )
    assert energy == float(np.float64(energy_code) * ENERGY_CONTROL_QUANTUM)
    assert energy_delta <= 5e-13 + 8 * np.spacing(abs(energy_raw))

    gradient_raw = 1.3071025743253508e-9
    gradient, gradient_code, gradient_delta = quantize_control(
        gradient_raw, GRADIENT_CONTROL_QUANTUM
    )
    assert gradient == float(
        np.float64(gradient_code) * GRADIENT_CONTROL_QUANTUM
    )
    assert gradient_delta <= 5e-11 + 8 * np.spacing(abs(gradient_raw))


def test_published_stable_contract_is_content_addressed_and_source_bound():
    if not CONTRACT.is_file():
        return
    value = load_json(CONTRACT)
    assert embedded_digest_valid(value, "contract_digest")
    assert value["source_binding"] == {
        path.relative_to(CONTRACT.parents[3]).as_posix(): sha256_file(path)
        for path in SOURCE_PATHS
    }


def test_stable_batch_preserves_two_process_and_one_thread_numerical_route():
    batch = next(
        path
        for path in SOURCE_PATHS
        if path.name == "a100_stable_control_trajectory.sbatch"
    ).read_text(encoding="utf-8")
    assert "stable_control_prepare" in batch
    assert "stable_control_route" in batch
    assert "A100_NUMERICAL_THREADS=1" in batch
    for variable in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        assert f'{variable}="${{source_threads}}"' in batch
        assert f"{variable}=1" in batch
