from aic_a100_pilot.common import embedded_digest_valid, load_json, sha256_file
from aic_a100_pilot.stable_control_v2_ci_incident import (
    CORRECTED_WORKFLOW,
    INCIDENT,
    RETRY_GATE,
    incident_body,
    retry_gate_body,
)


def test_first_v2_ci_failure_is_pre_outcome_and_environment_only():
    value = incident_body()
    assert value["status"] == "PRE_OUTCOME_CI_ENVIRONMENT_INCIDENT_MISSING_NUMPY"
    assert value["failure"]["scientific_code_executed"] is False
    assert value["outcome_boundary"]["candidate_energy_evaluations"] == 0
    assert value["outcome_boundary"]["optimizer_runs"] == 0
    assert value["outcome_boundary"]["FCI_evaluations"] == 0
    assert value["preservation"]["stable_control_v2_runtime_sources_modified"] is False
    published = load_json(INCIDENT)
    assert embedded_digest_valid(published, "incident_digest")


def test_corrected_ci_gate_uses_pinned_parent_lock_and_authorizes_no_aic_yet():
    value = retry_gate_body()
    assert value["status"] == "GO_CORRECTED_CI_RETRY_ONLY"
    assert value["corrected_workflow"]["sha256"] == sha256_file(
        CORRECTED_WORKFLOW
    )
    assert value["corrected_workflow"]["uv_frozen"] is True
    assert value["authorization"]["AIC_H2"] == (
        "NOT_AUTHORIZED_UNTIL_CORRECTED_CI_SUCCESS"
    )
    assert value["authorization"]["AIC_H4_LiH_H6_BeH2"] == "NOT_AUTHORIZED"


def test_published_retry_gate_is_content_addressed():
    value = load_json(RETRY_GATE)
    assert embedded_digest_valid(value, "gate_digest")
