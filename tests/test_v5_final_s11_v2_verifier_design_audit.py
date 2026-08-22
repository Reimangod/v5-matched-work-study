from __future__ import annotations

from v5_final import s11_v2_verifier_design_audit as subject


def test_design_freeze_reconstructs_when_committed():
    if not subject.OUTPUT_PATH.exists():
        return
    assert subject.audit() == {
        "byte_reconstructible": True,
        "design_digest_valid": True,
        "manifest_exact": True,
        "all_design_checks_pass": True,
        "candidate_outcomes_blocked": True,
    }


def test_design_policy_is_outcome_blind_and_top_k_is_fixed():
    record = subject.build_record()
    assert record["policy"]["top_k"] == 4
    assert record["policy"]["candidate_outcomes_used_to_choose_policy"] is False
    assert record["counter_schema"]["production_invariant"] == "N_dense_expm == 0"
    assert record["authorization"]["molecular_candidate_energy"] == "NOT_AUTHORIZED"
