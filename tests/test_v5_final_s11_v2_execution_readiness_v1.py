from v5_final.s11_v2_execution_readiness_v1 import (
    DECISION,
    OUTPUT,
    _function_calls,
    audit_frozen,
    inspect_readiness,
)
from v5_final.s11_v2_execution_readiness_v1 import (
    EXECUTION_SERVICES,
    EXECUTORS,
    REWRITE,
)


def test_frozen_dynamic_path_conflict_is_detected_without_outcomes() -> None:
    report = inspect_readiness()
    assert all(report["checks"].values())
    assert report["observed_outcomes"] == {
        "candidate_energy_evaluations": 0,
        "optimizer_iterations": 0,
        "FCI_evaluations": 0,
    }
    assert "_rank_parent_candidates" in _function_calls(
        EXECUTION_SERVICES, "_dynamic_v5_preparation"
    )
    assert "prepare_rewrite_for_optimizer" in _function_calls(
        EXECUTORS, "_rank_parent_candidates"
    )
    assert "toarray" in _function_calls(REWRITE, "_generator_matrix")


def test_execution_readiness_lifecycle_is_no_go_before_or_audited_after_freeze() -> None:
    if OUTPUT.exists():
        report = audit_frozen()
        assert report["decision"] == DECISION
        assert all(report["checks"].values())
    else:
        assert OUTPUT.name == "execution-readiness-no-go-v1.json"
        assert DECISION.startswith("NO_GO_S11_V2_")
