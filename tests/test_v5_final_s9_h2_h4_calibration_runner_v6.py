from __future__ import annotations

import pytest


pytest.importorskip("numpy")

from v5_final import s9_h2_h4_calibration_runner as v1
from v5_final import s9_h2_h4_calibration_runner_v6 as v6


def test_v6_scope_is_fresh_and_restores_base_globals() -> None:
    original = v1.S9_DIR
    with v6._v6_scope():
        assert v1.S9_DIR == v6.S9_V6_DIR
        assert v1.COMPLETENESS_PATH == v6.COMPLETENESS_PATH
        assert v1.execute_frozen_item is v6.execute_frozen_item_v2
    assert v1.S9_DIR == original


def test_v6_frozen_environment_contract_is_exact() -> None:
    runtime, threads = v6._environment_contract()
    assert runtime == {
        "byte_order": "little",
        "machine": "arm64",
        "python_implementation": "cpython",
        "python_version": "3.10.19",
        "system": "darwin",
    }
    assert threads == {
        "MKL_NUM_THREADS": "2",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
    }


def test_v6_rejects_wrong_runtime_before_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(v6.platform, "system", lambda: "Linux")
    with pytest.raises(v6.S9V6CalibrationError, match="before output publication"):
        v6._require_local_preflight()


def test_v6_static_audit_is_exact_and_downstream_closed() -> None:
    report = v6.build_static_audit()
    assert all(report["checks"].values())
    assert report["run_namespace"] == v6.RUN_NAMESPACE
    assert report["progress"]["expected_item_count"] == 36
    assert report["authorization"]["development_queue_execution"] == (
        "NOT_AUTHORIZED"
    )
    assert report["authorization"]["performance_claim"] == "NOT_AUTHORIZED"
    if report["progress"]["complete"]:
        assert report["progress"]["completed_terminal_count"] == 36
        assert report["progress"]["terminal_status_counts"]["KERNEL_FAILURE"] == 0


def test_v6_frozen_artifacts_are_valid_if_present() -> None:
    if v6.READINESS_PATH.exists():
        assert all(v6.audit_readiness().values())
    if v6.AUTHORIZATION_PATH.exists():
        assert all(v6.audit_authorization(require_current_preflight=False).values())


def test_v6_sources_bind_static_ci_and_v5_halt() -> None:
    relative = {str(path.relative_to(v6.ROOT)) for path in v6.RUNNER_SOURCES}
    assert ".github/workflows/v5-s9-v6-local-darwin-gate.yml" in relative
    assert "src/v5_final/s9_v5_platform_halt.py" in relative
    assert "src/v5_final/s9_h2_h4_calibration_runner_v6.py" in relative
