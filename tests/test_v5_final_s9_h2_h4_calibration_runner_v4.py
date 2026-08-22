from __future__ import annotations

import pytest


pytest.importorskip("numpy")

from v5_final import s9_h2_h4_calibration_runner as v1
from v5_final import s9_h2_h4_calibration_runner_v4 as v4


VENUE_ENV = {
    "CI": "true",
    "GITHUB_ACTIONS": "true",
    "RUNNER_OS": "Linux",
    "RUNNER_ARCH": "X64",
    "V5_S9_V4_EXECUTION_VENUE": v4.EXECUTION_VENUE,
    "MKL_NUM_THREADS": "2",
    "OMP_NUM_THREADS": "2",
    "OPENBLAS_NUM_THREADS": "2",
}


def test_v4_scope_is_fresh_and_restores_base_globals() -> None:
    original = v1.S9_DIR
    with v4._v4_scope():
        assert v1.S9_DIR == v4.S9_V4_DIR
        assert v1.COMPLETENESS_PATH == v4.COMPLETENESS_PATH
        assert v1.RUNNER_SOURCES == v4.RUNNER_SOURCES
    assert v1.S9_DIR == original


def test_v4_requires_exact_github_single_job_venue(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in VENUE_ENV:
        monkeypatch.delenv(name, raising=False)
    assert not all(v4.audit_execution_venue().values())
    with pytest.raises(v4.S9V4CalibrationError):
        v4._require_pre_output_environment()

    for name, value in VENUE_ENV.items():
        monkeypatch.setenv(name, value)
    assert all(v4._require_pre_output_environment().values())


def test_v4_namespace_is_not_halted_at_the_current_prefix() -> None:
    assert v4._kernel_failure_receipts() == []
    assert v4._failed_post_capacity_receipts() == []
    v4._require_resumable_namespace()


def test_v4_sources_bind_all_execution_workflows() -> None:
    relative = {str(path.relative_to(v4.ROOT)) for path in v4.RUNNER_SOURCES}
    assert ".github/workflows/v5-s9-v4-github-runner-gate.yml" in relative
    assert ".github/workflows/v5-s9-v4-artifact-builder.yml" in relative
    assert ".github/workflows/v5-s9-v4-execute.yml" in relative
    assert "src/v5_final/s9_v3_capacity_halt.py" in relative
