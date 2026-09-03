from __future__ import annotations

from v5_final.gpu_rtx2080ti_s0_scope_freeze_v1 import (
    CPU_OUTCOME_ROOT,
    EXPECTED_FILES,
    EXPECTED_GATE_DIGEST,
    EXPECTED_QUEUE_DIGEST,
    audit,
    build,
)


def test_scope_freeze_binds_exact_frozen_cpu_protocol() -> None:
    artifact = build()
    inputs = artifact["frozen_protocol_inputs"]
    assert inputs["files_sha256"] == EXPECTED_FILES
    assert inputs["queue_digest"] == EXPECTED_QUEUE_DIGEST
    assert inputs["p7_gate_digest"] == EXPECTED_GATE_DIGEST
    assert inputs["queue_items"] == 90


def test_cpu_terminal_prefix_is_provenance_not_gpu_input() -> None:
    artifact = build()
    prefix = artifact["source"]["cpu_terminal_prefix"]
    assert prefix["terminal_items"] == 24
    assert prefix["allowed_as_gpu_execution_input"] is False
    assert str(CPU_OUTCOME_ROOT) not in artifact["isolation"]["allowed_input_paths"]
    assert artifact["isolation"]["cpu_outcome_root_access"] == "FORBIDDEN"


def test_gpu_study_is_a_fresh_90_item_execution() -> None:
    isolation = build()["isolation"]
    assert isolation["execution_start_index"] == 0
    assert isolation["execution_item_count"] == 90
    assert isolation["cpu_gpu_terminal_record_concatenation"] == "FORBIDDEN"


def test_s0_authorizes_hardware_audit_only() -> None:
    artifact = build()
    assert artifact["decision"] == "GO_RTX2080TI_S1_HARDWARE_AUDIT_ONLY"
    assert artifact["authorization"]["s1_hardware_access_audit"] == "AUTHORIZED"
    for key in (
        "molecular_candidate_outcomes",
        "gpu_90_item_execution",
        "fci_reporting",
        "performance_claim",
        "s12_reporting",
    ):
        assert artifact["authorization"][key] == "NOT_AUTHORIZED"


def test_backend_identity_and_fallback_policy_are_explicit() -> None:
    artifact = build()
    assert artifact["identity_policy"]["state_preparation_id_changed_by_backend"] is False
    assert artifact["backend_safety"]["unexpected_cpu_fallback_limit"] == 0
    assert artifact["backend_safety"]["planned_hybrid_cpu_work_must_be_recorded"] is True


def test_scope_audit_passes_without_release_cleanliness_check() -> None:
    result = audit(require_clean=False)
    assert result["passed"] is True
    assert all(result["checks"].values())
