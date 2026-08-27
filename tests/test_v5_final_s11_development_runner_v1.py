from __future__ import annotations

import json

import pytest


pytest.importorskip("numpy")

from v5_final import s9_h2_h4_calibration_runner as core
from v5_final.s11_development_runner_v1 import (
    AUTHORIZATION_PATH,
    CI_EVIDENCE_CHECK_KEYS,
    EXECUTION_DIR,
    PLAN_PATH,
    READINESS_PATH,
    READINESS_AUDIT_CHECK_KEYS,
    RUNNER_SOURCES,
    S11DevelopmentRunnerError,
    STATIC_AUDIT_CHECK_KEYS,
    _core_scope,
    _digest,
    _environment_contract,
    _plan,
    _progress_snapshot,
    _validate_readiness_ci_evidence,
    _write_dispatch,
    audit_authorization,
    audit_readiness,
    build_static_audit,
)


def test_s11_runner_binds_exact_frozen_90_item_plan() -> None:
    plan = _plan()
    assert plan["schema"] == "v5-final.s11-development-plan.v4"
    assert plan["frozen_item_count"] == 90
    assert len(plan["items"]) == 90
    assert len({item["queue_item_id"] for item in plan["items"]}) == 90
    assert plan["candidate_energy_evaluations"] == 0
    assert all(item["terminal_status"] == "NOT_STARTED" for item in plan["items"])


def test_s11_runner_environment_is_original_single_thread_darwin() -> None:
    runtime, threads = _environment_contract()
    assert runtime == {
        "byte_order": "little",
        "machine": "arm64",
        "python_implementation": "cpython",
        "python_version": "3.10.19",
        "system": "darwin",
    }
    assert threads == {
        "MKL_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }


def test_s11_progress_never_claims_performance_or_premature_FCI() -> None:
    plan = _plan()
    work = {component: 0 for component in core.WORK_COMPONENTS}
    receipt = {
        "queue_item_id": plan["items"][0]["queue_item_id"],
        "receipt_digest": "a" * 64,
        "terminal_status": "ACCEPTED",
        "work_total": work,
        "candidate_energy_evaluations": 7,
        "capacity_after_terminal": {"passed": True},
    }
    progress = _progress_snapshot(plan, [receipt])
    assert progress["completed_terminal_count"] == 1
    assert progress["candidate_energy_evaluations"] == 7
    assert progress["FCI_reporting_performed"] is False
    assert progress["authorization"]["FCI_reporting"] == (
        "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL"
    )
    assert progress["authorization"]["performance_claim"] == "NOT_AUTHORIZED"


def test_s11_core_scope_is_narrow_and_restored() -> None:
    names = (
        "S9_DIR",
        "PLAN_PATH",
        "READINESS_PATH",
        "AUTHORIZATION_PATH",
        "execute_frozen_item",
        "_progress_snapshot",
        "_write_dispatch",
    )
    original = {name: getattr(core, name) for name in names}
    with _core_scope():
        assert core.S9_DIR == EXECUTION_DIR
        assert core.PLAN_PATH == PLAN_PATH
        assert core.READINESS_PATH == READINESS_PATH
        assert core.AUTHORIZATION_PATH == AUTHORIZATION_PATH
        assert core._progress_snapshot is _progress_snapshot
        assert core._write_dispatch is _write_dispatch
    assert {name: getattr(core, name) for name in names} == original


def test_capacity_failure_precedes_dispatch_output(tmp_path, monkeypatch) -> None:
    from v5_final import s11_development_runner_v1 as runner

    plan = _plan()
    monkeypatch.setattr(runner, "DISPATCH_DIR", tmp_path / "dispatch")
    monkeypatch.setattr(
        core,
        "_current_capacity",
        lambda: {
            "filesystem_available_bytes": 1,
            "required_study_bytes": 1,
            "mandatory_reserve_bytes": 1,
            "execution_threshold_bytes": 2,
            "passed": False,
        },
    )
    with pytest.raises(S11DevelopmentRunnerError, match="before S11 item dispatch"):
        _write_dispatch(plan, plan["items"][0], 0)
    assert not (tmp_path / "dispatch").exists()


def test_readiness_ci_evidence_validator_is_exact() -> None:
    commit = "b" * 40
    report = {
        "schema": "v5-final.s11-static-ci-audit.v1",
        "validated_exact_commit": commit,
        "status": "PASS_S11_STATIC_INTEGRITY",
        "decision": "READY_AWAITING_S11_OWNER_AUTHORIZATION",
        "run_namespace": "s11-development-execution-v1",
        "execution_venue": "repository-owner-local-darwin-arm64-single-process",
        "namespace_halted": False,
        "readiness_audit": {
            key: True for key in READINESS_AUDIT_CHECK_KEYS
        },
        "checks": {key: True for key in STATIC_AUDIT_CHECK_KEYS},
        "progress": {
            "expected_item_count": 90,
            "completed_terminal_count": 0,
            "candidate_energy_evaluations": 0,
            "FCI_reporting_performed": False,
        },
        "candidate_molecular_energy_evaluations": 0,
        "authorization": {
            "performance_claim": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
        },
    }
    report["audit_digest"] = _digest(report)
    evidence = {
        "schema": "v5-final.external-s11-static-readiness-ci-evidence.v1",
        "attested_commit": commit,
        "conclusion": "success",
        "run_id": 1,
        "job_id": 2,
        "run_url": (
            "https://github.com/Reimangod/v5-matched-work-study/actions/runs/1"
        ),
        "capture_phase": (
            "OUTCOME_FREE_STATIC_READINESS_BEFORE_OWNER_AUTHORIZATION"
        ),
        "report_schema": "v5-final.s11-static-ci-audit.v1",
        "report_sha256": _digest(report),
        "static_report": report,
        "candidate_molecular_energy_evaluations": 0,
        "checks": {key: True for key in CI_EVIDENCE_CHECK_KEYS},
    }
    assert all(
        _validate_readiness_ci_evidence(
            evidence, readiness_commit=commit
        ).values()
    )
    evidence["candidate_molecular_energy_evaluations"] = 1
    assert not all(
        _validate_readiness_ci_evidence(
            evidence, readiness_commit=commit
        ).values()
    )


def test_s11_static_audit_preserves_claim_boundary() -> None:
    report = build_static_audit()
    assert all(report["checks"].values())
    assert report["progress"]["expected_item_count"] == 90
    assert report["progress"]["FCI_reporting_performed"] is False
    assert report["authorization"]["performance_claim"] == "NOT_AUTHORIZED"
    assert report["candidate_molecular_energy_evaluations"] == report["progress"][
        "candidate_energy_evaluations"
    ]


def test_committed_readiness_and_authorization_are_auditable_if_present() -> None:
    assert all(path.is_file() for path in RUNNER_SOURCES)
    if READINESS_PATH.exists():
        assert all(audit_readiness().values())
        readiness = json.loads(READINESS_PATH.read_text())
        assert readiness["candidate_molecular_energy_evaluations"] == 0
    if AUTHORIZATION_PATH.exists():
        assert all(audit_authorization(require_current_preflight=False).values())
        authorization = json.loads(AUTHORIZATION_PATH.read_text())
        assert authorization[
            "candidate_molecular_energy_evaluations_before_authorization"
        ] == 0
