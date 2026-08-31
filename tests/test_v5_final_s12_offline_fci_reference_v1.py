from copy import deepcopy
from pathlib import Path

import pytest

from v5_final.s12_offline_fci_reference_v1 import (
    EXPECTED_CASES,
    RESULT_STATUS,
    S12OfflineFCIReferenceV1Error,
    _case_bindings,
    _digest,
    _embedded_digest,
    build_readiness,
)


def test_case_bindings_are_exact_and_outcome_free() -> None:
    bindings = _case_bindings()
    assert tuple(binding["case_id"] for binding in bindings) == EXPECTED_CASES
    assert all("FCI_energy_hartree" not in binding for binding in bindings)
    assert all("energy_hartree" not in binding for binding in bindings)
    assert all(len(binding["ProblemID"]) > 64 for binding in bindings)
    assert all(len(binding["Hamiltonian_digest"]) == 64 for binding in bindings)


def test_readiness_freezes_solver_code_cases_and_firewalls() -> None:
    readiness = build_readiness("a" * 40)
    assert readiness["decision"].startswith("GO_S12_EXACT_FIVE_CASE")
    assert _embedded_digest(readiness, "readiness_digest")
    assert tuple(readiness["execution_contract"]["case_ids"]) == EXPECTED_CASES
    assert readiness["execution_contract"]["FCI_evaluations"] == 5
    assert readiness["execution_contract"]["candidate_energy"] == "NOT_AUTHORIZED"
    assert readiness["execution_contract"]["S11_rerun"] == "NOT_AUTHORIZED"
    assert readiness["supersession"]["scientific_semantics_changed"] is False
    assert readiness["supersession"]["FCI_evaluations_before_successor"] == 0
    assert set(readiness["bindings"]["source_sha256"]) == {
        "src/v5_final/s12_offline_fci_reference_v1.py",
        "tests/test_v5_final_s12_offline_fci_reference_v1.py",
    }


def test_git_output_preserves_clean_submodule_marker() -> None:
    from v5_final.s12_offline_fci_reference_v1 import _git

    lines = _git("submodule", "status", "--recursive").splitlines()
    assert lines
    assert all(line.startswith(" ") for line in lines)


def test_readiness_digest_rejects_tamper() -> None:
    value = {"decision": "GO"}
    value["readiness_digest"] = _digest(value)
    assert _embedded_digest(value, "readiness_digest")
    value["decision"] = "TAMPERED"
    assert not _embedded_digest(value, "readiness_digest")


def test_execute_uses_exact_case_order_and_one_atomic_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from v5_final import s12_offline_fci_reference_v1 as subject

    readiness = build_readiness("a" * 40)
    readiness_path = tmp_path / "readiness.json"
    readiness_path.write_text(__import__("json").dumps(readiness), encoding="utf-8")
    result_path = tmp_path / "result.json"
    calls: list[str] = []
    monkeypatch.setattr(subject, "READINESS", readiness_path)
    monkeypatch.setattr(subject, "RESULT", result_path)
    monkeypatch.setattr(subject, "audit_readiness", lambda **kwargs: {})
    monkeypatch.setattr(subject, "_sha", lambda path: "b" * 64)
    monkeypatch.setattr(
        subject,
        "_solve_case",
        lambda binding: calls.append(binding["case_id"]) or {
            "case_id": binding["case_id"],
            "ProblemID": binding["ProblemID"],
            "Hamiltonian_digest": binding["Hamiltonian_digest"],
            "FCI_energy_hartree": -1.0,
            "FCI_evaluations": 1,
            "n_electrons": 2,
            "n_spatial_orbitals": 2,
        },
    )
    monkeypatch.setattr(subject.os, "environ", {
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"
    })
    result = subject.execute()
    assert tuple(calls) == EXPECTED_CASES
    assert result["status"] == RESULT_STATUS
    assert result["counters"]["FCI_evaluations"] == 5
    assert result_path.is_file()
    with pytest.raises(FileExistsError):
        subject.execute()


def test_execute_rejects_thread_contract_before_solver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from v5_final import s12_offline_fci_reference_v1 as subject

    readiness = build_readiness("a" * 40)
    readiness_path = tmp_path / "readiness.json"
    readiness_path.write_text(__import__("json").dumps(readiness), encoding="utf-8")
    monkeypatch.setattr(subject, "READINESS", readiness_path)
    monkeypatch.setattr(subject, "RESULT", tmp_path / "result.json")
    monkeypatch.setattr(subject, "audit_readiness", lambda **kwargs: {})
    monkeypatch.setattr(subject.os, "environ", {})
    monkeypatch.setattr(subject, "_solve_case", lambda binding: pytest.fail("solver called"))
    with pytest.raises(S12OfflineFCIReferenceV1Error, match="thread environment"):
        subject.execute()


def test_result_audit_rejects_identity_tamper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from v5_final import s12_offline_fci_reference_v1 as subject

    readiness = build_readiness("a" * 40)
    cases = []
    for binding in readiness["bindings"]["case_bindings"]:
        cases.append({
            "case_id": binding["case_id"], "ProblemID": binding["ProblemID"],
            "Hamiltonian_digest": binding["Hamiltonian_digest"],
            "FCI_energy_hartree": -1.0, "FCI_evaluations": 1,
            "n_electrons": 2, "n_spatial_orbitals": 2,
        })
    result = {
        "schema": "v5-final.s12-offline-fci-reference-result.v1",
        "status": RESULT_STATUS,
        "bindings": {
            "readiness_digest": readiness["readiness_digest"],
            "readiness_sha256": "b" * 64,
            "S12_gate_digest": readiness["bindings"]["S12_gate_digest"],
            "source_catalog_sha256": readiness["bindings"]["source_catalog_sha256"],
        },
        "solver_contract": readiness["solver_contract"], "cases": cases,
        "counters": {"FCI_evaluations": 5, "candidate_energy_evaluations": 0,
                     "optimizer_starts": 0, "S11_items_rerun": 0,
                     "production_N_dense_expm": 0},
        "control_inputs": "exact frozen case identities only; no S11 outcomes",
        "authorization_after_publication": {},
    }
    result["result_digest"] = _digest(result)
    readiness_path, result_path = tmp_path / "rdy.json", tmp_path / "result.json"
    readiness_path.write_text(__import__("json").dumps(readiness), encoding="utf-8")
    result_path.write_text(__import__("json").dumps(result), encoding="utf-8")
    monkeypatch.setattr(subject, "READINESS", readiness_path)
    monkeypatch.setattr(subject, "RESULT", result_path)
    monkeypatch.setattr(subject, "audit_readiness", lambda **kwargs: {"checks": {"ok": True}})
    monkeypatch.setattr(subject, "_sha", lambda path: "b" * 64)
    assert all(subject.audit_result()["checks"].values())
    tampered = deepcopy(result)
    tampered["cases"][0]["ProblemID"] = "problem-v1:" + "0" * 64
    tampered["result_digest"] = _digest({k: v for k, v in tampered.items() if k != "result_digest"})
    result_path.write_text(__import__("json").dumps(tampered), encoding="utf-8")
    with pytest.raises(S12OfflineFCIReferenceV1Error, match="problem_identities_exact"):
        subject.audit_result()
