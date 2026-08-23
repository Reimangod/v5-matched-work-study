from pathlib import Path

import pytest

from v5_final.s12_offline_reporting_gate_v1 import (
    DECISION,
    EXPECTED_CASES,
    OUTPUT,
    S12OfflineReportingGateV1Error,
    _digest,
    _embedded_digest,
    _load,
    _validate_authorization,
    audit_frozen,
    build_artifact,
    inspect_completion,
)


def test_completion_snapshot_is_exact_90_and_outcome_safe() -> None:
    snapshot = inspect_completion()
    assert all(snapshot["checks"].values())
    assert snapshot["observed"]["terminal_count"] == 90
    assert snapshot["observed"]["FCI_evaluations"] == 0
    assert snapshot["observed"]["N_dense_expm"] == 0
    assert snapshot["observed"]["performance_claim"] == "NOT_AUTHORIZED"
    assert tuple(snapshot["frozen_reporting_scope"]["case_ids"]) == EXPECTED_CASES
    assert not snapshot["frozen_reporting_scope"][
        "candidate_outcomes_used_to_select_cases"
    ]


def test_gate_artifact_or_builder_is_valid() -> None:
    if OUTPUT.exists():
        artifact = _load(OUTPUT)
        assert artifact["decision"] == DECISION
        assert _embedded_digest(artifact, "gate_digest")
        assert all(audit_frozen()["checks"].values())
    else:
        artifact = build_artifact("a" * 40)
        assert artifact["decision"] == DECISION
        assert _embedded_digest(artifact, "gate_digest")
        assert _validate_authorization(artifact["authorization"])


def test_authorization_rejects_any_scope_expansion() -> None:
    authorization = build_artifact("a" * 40)["authorization"]
    assert _validate_authorization(authorization)
    authorization["performance_claim"] = "AUTHORIZED"
    assert not _validate_authorization(authorization)


def test_gate_digest_rejects_tamper() -> None:
    value = {"decision": DECISION}
    value["gate_digest"] = _digest(value)
    assert _embedded_digest(value, "gate_digest")
    value["decision"] = "TAMPERED"
    assert not _embedded_digest(value, "gate_digest")


def test_capture_rejects_unexpected_dirty_file(monkeypatch, tmp_path: Path) -> None:
    from v5_final import s12_offline_reporting_gate_v1 as subject

    monkeypatch.setattr(subject, "OUTPUT", tmp_path / "absent.json")
    monkeypatch.setattr(
        subject,
        "_git",
        lambda *args: {
            ("rev-parse", "HEAD"): "a" * 40,
            ("status", "--porcelain"): " M existing.py",
        }[args],
    )
    with pytest.raises(S12OfflineReportingGateV1Error, match="only the two new"):
        subject.capture()


def test_completion_fails_closed_if_FCI_was_already_run(monkeypatch) -> None:
    from v5_final import s12_offline_reporting_gate_v1 as subject

    real = subject._result_and_receipt_manifests

    def contaminated(adapter):
        result_manifest, receipt_manifest, results = real(adapter)
        results[0] = {**results[0], "FCI_evaluations": 1}
        return result_manifest, receipt_manifest, results

    monkeypatch.setattr(subject, "_result_and_receipt_manifests", contaminated)
    with pytest.raises(S12OfflineReportingGateV1Error, match="S11_FCI"):
        subject.inspect_completion()
