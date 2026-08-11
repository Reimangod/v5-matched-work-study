from __future__ import annotations

import pytest


pytest.importorskip("numpy")

from v5_final import s9_h2_h4_calibration_runner as v1
from v5_final import s9_h2_h4_calibration_runner_v5 as v5


VENUE_ENV = {
    "CI": "true",
    "GITHUB_ACTIONS": "true",
    "RUNNER_OS": "Linux",
    "RUNNER_ARCH": "X64",
    "V5_S9_V5_EXECUTION_VENUE": v5.EXECUTION_VENUE,
    "MKL_NUM_THREADS": "2",
    "OMP_NUM_THREADS": "2",
    "OPENBLAS_NUM_THREADS": "2",
}


def test_v5_scope_is_fresh_and_restores_base_globals() -> None:
    original = v1.S9_DIR
    with v5._v5_scope():
        assert v1.S9_DIR == v5.S9_V5_DIR
        assert v1.COMPLETENESS_PATH == v5.COMPLETENESS_PATH
        assert v1.RUNNER_SOURCES == v5.RUNNER_SOURCES
    assert v1.S9_DIR == original


def test_v5_requires_exact_github_single_job_venue(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in VENUE_ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(v5.S9V5CalibrationError):
        v5._require_pre_output_environment()
    for name, value in VENUE_ENV.items():
        monkeypatch.setenv(name, value)
    assert all(v5._require_pre_output_environment().values())


def test_v5_current_namespace_is_halted_by_exact_index_zero_failure() -> None:
    assert v5._kernel_failure_receipts() == [
        "000-536bd9cab01a1fe9762310e82533b4d30ee88e8a26ea010489af621b740cf402.json"
    ]
    assert v5._failed_post_capacity_receipts() == []
    with pytest.raises(v5.S9V5CalibrationError, match="permanently halted"):
        v5._require_resumable_namespace()


def test_v5_sources_bind_state_machine_and_halt() -> None:
    relative = {str(path.relative_to(v5.ROOT)) for path in v5.RUNNER_SOURCES}
    assert ".github/workflows/v5-s9-v5-state-machine-gate.yml" in relative
    assert "src/v5_final/s9_v4_preauthorization_halt.py" in relative
    assert "src/v5_final/s9_h2_h4_calibration_runner_v5.py" in relative


def test_v5_evidence_schema_matches_base_contract() -> None:
    head = v5._git("rev-parse", "HEAD")
    evidence = {
        "schema": "v5-final.external-s9-readiness-exact-ci-evidence.v1",
        "head_sha": head,
        "conclusion": "success",
        "release_gate_job_conclusion": "success",
        "attested_commit": head,
        "report_schema": "v5-final.s9-h2-h4-ci-audit.v1",
        "readiness_audit_passed": True,
        "run_id": 1,
        "attestation_sha256": "0" * 64,
    }
    assert all(v1._validate_readiness_ci(evidence).values())
