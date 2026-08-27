from __future__ import annotations

from copy import deepcopy
import hashlib

import pytest
from v5_matched_work.atomic_artifacts import canonical_json_bytes

from v5_final.s11_interruption_recovery_item028_v1 import (
    DECLARATION_PATH,
    S11InterruptionRecoveryError,
    audit_declaration,
    build_authorization,
    build_static_report,
)


def test_item028_declaration_replays_exact_outcome_free_prefix() -> None:
    assert DECLARATION_PATH.is_file()
    assert all(audit_declaration().values())


def test_item028_static_report_keeps_execution_and_claims_blocked() -> None:
    report = build_static_report()
    assert report["status"] == "PASS_OUTCOME_FREE_INTERRUPTION_RECOVERY_DESIGN"
    assert report["decision"] == "READY_AWAITING_OWNER_RECOVERY_AUTHORIZATION"
    assert set(report["authorization"].values()) == {"NOT_AUTHORIZED"}


def test_item028_declaration_rejects_semantic_event_tampering() -> None:
    declaration = __import__("json").loads(DECLARATION_PATH.read_text())
    altered = deepcopy(declaration)
    altered["interrupted_ledger_prefix"][2]["record"]["payload"]["operation"] = (
        "candidate-energy-evaluation"
    )
    with pytest.raises(S11InterruptionRecoveryError):
        audit_declaration(altered)


def test_item028_owner_authorization_is_exact_ci_bound_and_narrow() -> None:
    report = build_static_report()
    report_sha256 = hashlib.sha256(canonical_json_bytes(report)).hexdigest()
    authorization = build_authorization(
        report,
        report_sha256=report_sha256,
        run_id=123,
        job_id=456,
        run_url="https://github.com/Reimangod/v5-matched-work-study/actions/runs/123",
    )
    assert authorization["decision"] == "GO_EXACT_ITEM_028_SYSTEM_RETRY_ONLY"
    assert authorization["authorization"]["execute_same_frozen_item_once"] is True
    assert authorization["authorization"]["queue_reordering"] is False
    assert authorization["authorization"]["performance_claim"] == "NOT_AUTHORIZED"

    altered = deepcopy(report)
    altered["status"] = "PASS_BUT_DIFFERENT"
    with pytest.raises(S11InterruptionRecoveryError):
        build_authorization(
            altered,
            report_sha256=hashlib.sha256(canonical_json_bytes(altered)).hexdigest(),
            run_id=123,
            job_id=456,
            run_url="https://github.com/Reimangod/v5-matched-work-study/actions/runs/123",
        )
