from v5_final.s12_post_outcome_aggregation_gate_v1 import (
    DECISION,
    _authorization,
    _embedded_digest,
    build_artifact,
    inspect_inputs,
)


def test_aggregation_inputs_are_exact_and_firewalls_remain_closed() -> None:
    inspected = inspect_inputs()
    assert all(inspected["checks"].values())
    assert inspected["observed"]["terminal_count"] == 90
    assert inspected["observed"]["offline_FCI_evaluations"] == 5
    assert inspected["observed"]["S11_FCI_evaluations"] == 0
    assert inspected["observed"]["production_N_dense_expm"] == 0


def test_gate_authorizes_only_read_only_frozen_population_aggregation() -> None:
    artifact = build_artifact("a" * 40)
    assert artifact["decision"] == DECISION
    assert _embedded_digest(artifact, "gate_digest")
    assert artifact["authorization"] == _authorization()
    assert artifact["authorization"]["exact_90_result_read_only_aggregation"] == (
        "AUTHORIZED"
    )
    assert artifact["authorization"]["S11_rerun"] == "NOT_AUTHORIZED"
    assert artifact["authorization"]["FCI_reexecution"] == "NOT_AUTHORIZED"
    assert artifact["authorization"]["case_or_status_exclusion_from_outcomes"] == (
        "NOT_AUTHORIZED"
    )
    assert artifact["authorization"]["general_superiority_claim"] == "NOT_AUTHORIZED"


def test_engineering_failure_and_rejections_are_not_imputed() -> None:
    artifact = build_artifact("b" * 40)
    handling = artifact["aggregation_contract"]["status_handling"]
    assert "never rerun or impute" in handling["FAILED_ENGINEERING_PRESERVED"]
    assert "no-accepted-candidate" in handling["ALGORITHM_REJECTED"]
    assert "incomplete-within-frozen-budget" in handling["CAP_REJECTED"]
    assert artifact["aggregation_contract"]["outcome_based_exclusion"] is False
