from __future__ import annotations

import json

from v5_final.mb7_pre_calibration_audit import OUTPUT, audit


def test_mb7_fails_closed_before_any_candidate_energy() -> None:
    report = json.loads(OUTPUT.read_text())
    assert report["decision"] == "NO_GO_MB7_UNRESOLVED_PRODUCTION_BINDING_AND_CAPACITY"
    assert report["queue_state"]["calibration"] == {
        "expected": 36,
        "terminal": 0,
        "candidate_energy": 0,
    }
    assert report["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED"
    assert report["authorization"]["development_queue_execution"] == "NOT_AUTHORIZED"


def test_mb7_detects_missing_behavioral_kernel_binding_not_just_callable_names() -> None:
    report = json.loads(OUTPUT.read_text())
    assert report["checks"]["six_exact_executor_callables"] is True
    assert report["checks"]["six_method_entrypoints_behaviorally_bind_actual_kernel"] is False
    assert report["checks"]["production_recorder_delegates_instead_of_unconditionally_rejecting"] is False
    assert all(
        evidence["constructs_PinnedCEOProductionKernelBindings"] is False
        and evidence["calls_molecular_kernel_binding"] is False
        for evidence in report["method_binding_evidence"].values()
    )


def test_mb7_no_go_rebuilds_deterministically() -> None:
    assert all(audit().values())
