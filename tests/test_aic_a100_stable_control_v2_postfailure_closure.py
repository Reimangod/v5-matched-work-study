from __future__ import annotations

from aic_a100_pilot.common import embedded_digest_valid, load_json, sha256_file
from aic_a100_pilot.stable_control_v2_postfailure_closure import (
    BEH2_RESULT,
    EXPECTED_BEH2_RESULT_SHA256,
    TERMINAL_DECISION,
    terminal_decision_body,
    validate_beh2_result,
)


def test_raw_beh2_diagnostic_is_exact_and_fail_closed():
    result = validate_beh2_result()
    assert sha256_file(BEH2_RESULT) == EXPECTED_BEH2_RESULT_SHA256
    assert result["status"] == "DIAGNOSTIC_FAIL"
    assert {
        key for key, passed in result["checks"].items() if not passed
    } == {"terminal_decision"}
    assert result["checks"]["optimizer_terminal_counts_and_status"]
    assert result["checks"]["trajectory_iteration_parity"]
    assert result["checks"]["terminal_control_energy"]
    assert result["checks"]["terminal_gradient"]
    assert result["checks"]["terminal_state"]
    assert result["route_counters"]["gpu"]["N_cpu_fallback"] == 0
    assert result["scientific_boundary"]["FCI_evaluations"] == 0


def test_beh2_failure_is_historical_semantics_not_cpu_gpu_nonparity():
    result = validate_beh2_result()
    assert result["cpu"]["terminal_decision"] == "REJECTED"
    assert result["gpu"]["terminal_decision"] == "REJECTED"
    assert result["cpu"]["optimizer_terminal"] == result["gpu"][
        "optimizer_terminal"
    ]
    assert result["terminal_differences"]["control_energy_hartree"] == 0.0
    assert result["terminal_differences"]["control_gradient_max_abs"] == 0.0
    assert result["terminal_differences"][
        "phase_aligned_state_max_abs"
    ] <= 1e-10


def test_terminal_decision_preserves_claim_boundary():
    value = terminal_decision_body()
    assert value["status"] == (
        "NO_GO_A100_STABLE_CONTROL_V2_HISTORICAL_OPTIMIZER_SEMANTICS"
    )
    observed = value["observed_BeH2_diagnostic"]
    assert observed["CPU_terminal_decision"] == "REJECTED"
    assert observed["GPU_terminal_decision"] == "REJECTED"
    assert observed["frozen_historical_CPU_terminal_decision"] == "ACCEPTED"
    assert observed["CPU_GPU_optimizer_terminal_exact"]
    assert value["preservation"]["BeH2_attempts"] == 1
    assert not value["preservation"]["threshold_or_numerics_changed"]
    assert value["preservation"]["existing_90_item_execution"] == "UNCHANGED"
    assert value["preservation"]["FCI_evaluations"] == 0
    assert value["preservation"]["performance_claim"] == "NOT_AUTHORIZED"


def test_published_terminal_decision_is_content_addressed():
    if not TERMINAL_DECISION.is_file():
        return
    value = load_json(TERMINAL_DECISION)
    assert embedded_digest_valid(value, "decision_digest")
    assert value == terminal_decision_body() | {
        "decision_digest": value["decision_digest"]
    }
