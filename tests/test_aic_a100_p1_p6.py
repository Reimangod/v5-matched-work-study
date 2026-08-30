from __future__ import annotations

from aic_a100_pilot.decision_gate import decision_body
from aic_a100_pilot.environment import operational_no_go_body


def test_p1_operational_no_go_is_fail_closed_and_sanitized():
    value = operational_no_go_body()
    assert value["status"] == "NO_GO_A100_OPERATIONAL_INSTABILITY"
    assert value["transport"]["username_persisted_in_repository_artifact"] is False
    assert value["allocation_diagnosis"]["a100_allocation_obtained"] is False
    assert [attempt["requested_gpus"] for attempt in value["allocation_attempts"]] == [1, 1]
    assert all(not attempt["compute_started"] for attempt in value["allocation_attempts"])
    assert value["cleanup"]["stale_job_detected"] is False
    assert all(number == 0 for number in value["route_counters"].values())


def test_p6_stops_all_outcome_phases():
    value = decision_body()
    assert value["status"] == "NO_GO_A100_OPERATIONAL_INSTABILITY"
    assert value["phase_status"]["P0_LOCAL_CPU_REFERENCE"] == "GO"
    assert value["phase_status"]["P1_AIC_PREFLIGHT"] == "NO_GO"
    for phase in ("P2_GPU_ENVIRONMENT_AND_SMOKE", "P3_SCIENTIFIC_PARITY", "P4_SAME_NODE_MICROBENCHMARK", "P5_LIMITED_SCIENTIFIC_PILOT"):
        assert value["phase_status"][phase] == "NOT_STARTED_NOT_AUTHORIZED"
    assert value["parity_table_status"] == "NOT_EXECUTED"
    assert value["speedup_table_status"] == "NOT_EXECUTED"
    assert all(number == 0 for number in value["route_counters"].values())
