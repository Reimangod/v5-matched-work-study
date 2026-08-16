from __future__ import annotations

from v5_final.parent_native_persistent_runner_probe import run_probe
from v5_final.s6_parent_native_persistent_runner_audit import audit, build, verify


def test_s6_persistent_runner_fault_matrix_is_complete_and_outcome_free():
    probe = run_probe()
    assert probe["accepted_terminal_count"] == 1
    assert probe["orphan_attempt_rejected"] is True
    assert probe["duplicate_terminal_rejected"] is True
    assert probe["digest_mismatch_rejected"] is True
    assert probe["molecular_candidate_energy_evaluations"] == 0


def test_s6_retry_preserves_failed_work_and_requires_rollback():
    probe = run_probe()
    assert probe["retry_attempt_count"] == 2
    assert probe["retry_rollback_count"] == 1
    assert probe["retry_preserved_failed_and_successful_work"] is True
    assert probe["invalid_rollback_rejected_before_append"] is True


def test_s6_audit_is_scoped_and_immutable():
    built = build()
    assert all(verify(built).values())
    assert built["decision"] == "GO_S7_OUTCOME_BLIND_MB6_V3_REFREEZE_ONLY"
    assert all(audit().values())
