from __future__ import annotations

import os

import pytest


pytest.importorskip("numpy")

from v5_matched_work.atomic_artifacts import canonical_json_bytes
from v5_final import s9_h2_h4_calibration_runner as v1
from v5_final import s9_h2_h4_calibration_runner_v3 as v3


def test_v3_current_progress_is_integral_and_downstream_blocked() -> None:
    report = v3.build_ci_audit()

    assert all(report["checks"].values())
    assert all(report["v2_halt_audit"].values())
    assert all(report["v3_checks"].values())
    assert report["run_namespace"] == "s9-h2-h4-calibration-v3"
    assert report["progress"]["expected_item_count"] == 36
    assert report["candidate_molecular_energy_evaluations"] == report["progress"][
        "candidate_energy_evaluations"
    ]
    assert report["authorization"]["development_queue_execution"] == "NOT_AUTHORIZED"
    assert report["authorization"]["performance_claim"] == "NOT_AUTHORIZED"


def test_v3_external_environment_is_exact_in_parent_gate() -> None:
    assert all(v3.audit_external_environment().values())
    assert {name: os.environ[name] for name in v3._required_thread_environment()} == {
        "MKL_NUM_THREADS": "2",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
    }


def test_v3_rejects_bad_environment_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed = False

    def forbidden_run(*, max_items: int | None = None) -> dict[str, object]:
        nonlocal executed
        executed = True
        return {"max_items": max_items}

    monkeypatch.setattr(v3, "_halt", lambda: {})
    monkeypatch.setattr(v3, "audit_authorization", lambda: {})
    monkeypatch.setattr(
        v3,
        "_required_thread_environment",
        lambda: {
            "MKL_NUM_THREADS": "2",
            "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "2",
        },
    )
    monkeypatch.setattr(v1, "run_calibration", forbidden_run)
    monkeypatch.delenv("OMP_NUM_THREADS")

    with pytest.raises(v3.S9V3CalibrationError, match="before output publication"):
        v3.run_calibration(max_items=1)

    assert executed is False


def test_v3_kernel_failure_receipt_permanently_blocks_namespace(tmp_path) -> None:
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    (receipt_dir / "000-failure.json").write_bytes(
        canonical_json_bytes({"terminal_status": "KERNEL_FAILURE"})
    )
    (receipt_dir / "001-accepted.json").write_bytes(
        canonical_json_bytes({"terminal_status": "ACCEPTED"})
    )

    assert v3._kernel_failure_receipts(receipt_dir) == ["000-failure.json"]


def test_v3_prior_kernel_failure_blocks_next_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed = False

    def forbidden_run(*, max_items: int | None = None) -> dict[str, object]:
        nonlocal executed
        executed = True
        return {"max_items": max_items}

    monkeypatch.setattr(v3, "_halt", lambda: {})
    monkeypatch.setattr(v3, "audit_authorization", lambda: {})
    monkeypatch.setattr(v3, "_require_external_environment", lambda: {})
    monkeypatch.setattr(v3, "_kernel_failure_receipts", lambda: ["000-failure.json"])
    monkeypatch.setattr(v1, "run_calibration", forbidden_run)

    with pytest.raises(v3.S9V3CalibrationError, match="permanently halted"):
        v3.run_calibration(max_items=1)

    assert executed is False


def test_v3_scope_restores_v1_globals_after_exception() -> None:
    before = {name: getattr(v1, name) for name in v3._OVERRIDES}

    with pytest.raises(RuntimeError, match="sentinel"):
        with v3._v3_scope():
            assert v1.S9_DIR == v3.S9_V3_DIR
            assert v1.execute_frozen_item is v3.execute_frozen_item_v2
            raise RuntimeError("sentinel")

    assert {name: getattr(v1, name) for name in v3._OVERRIDES} == before
