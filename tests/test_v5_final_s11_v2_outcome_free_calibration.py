from __future__ import annotations

import inspect

from v5_final import s11_v2_outcome_free_calibration as calibration
from v5_final import s11_v2_calibration_development_worker as development_worker
from v5_final.verifier_v2 import CandidateV2, VerifierV2, VerifierV2Policy
from v5_final.verifier_v2_structural_calibration import prepare_structural_only


def test_structural_calibration_stops_before_resource_and_numeric_work(tmp_path):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("heavy work crossed structural-only boundary")

    candidate = CandidateV2(
        "candidate-a",
        "semantic-a",
        "state-a",
        ("generator-a",),
        (),
        ((),),
        0.0,
        4,
        2,
        forbidden,
        deletion_shortcut=True,
    )
    alias = CandidateV2(
        "candidate-a-alias",
        "semantic-a",
        "state-a-alias",
        ("generator-a",),
        (),
        ((),),
        0.0,
        4,
        2,
        forbidden,
        deletion_shortcut=True,
    )
    verifier = VerifierV2(
        policy=VerifierV2Policy(),
        generator_loader=forbidden,
        checkpoint_dir=tmp_path,
        source_binding={"case_id": "structural-test"},
    )
    core = prepare_structural_only(verifier, (candidate, alias))
    counters = core["deterministic_work_counters"]
    assert core["status"] == "STRUCTURAL_PREPARATION_COMPLETE_OUTCOME_FREE"
    assert counters["candidate_generations"] == 2
    assert counters["unique_semantic_candidates"] == 1
    assert counters["resource_recounts"] == 0
    assert counters["N_sparse_expm_multiply"] == 0
    assert counters["N_dense_expm"] == 0
    assert core["ranking_performed"] is False
    assert core["numeric_verification_performed"] is False


def test_calibration_code_forbids_h6_legacy_dense_catalog_execution():
    source = inspect.getsource(calibration) + inspect.getsource(development_worker)
    assert '"legacy_dense_verifier_candidate_count": 0' in source
    assert "two SHA256-smallest physical representatives" in source
    assert "candidate_energy" not in source or "NOT_AUTHORIZED" in source


def test_committed_calibration_audits_when_present():
    if calibration.SUMMARY_PATH.exists():
        assert all(calibration.audit().values())
