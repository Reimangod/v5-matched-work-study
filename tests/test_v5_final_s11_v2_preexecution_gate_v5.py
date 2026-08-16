from v5_final.s11_v2_preexecution_gate_v5 import (
    GO_DECISION,
    OUTPUT,
    _pytest_summary,
    audit_frozen,
)


def test_full_suite_summary_combines_both_thread_partitions() -> None:
    summary = _pytest_summary(
        "280 passed, 3 xfailed, 95 warnings in 1.0s\n"
        "41 passed, 109 warnings in 2.0s\n"
    )
    assert summary == {"partitions": 2, "passed": 321, "xfailed": 3}


def test_p7_v5_lifecycle_is_fail_closed_before_or_audited_after_freeze() -> None:
    if OUTPUT.exists():
        report = audit_frozen()
        assert report["decision"] == GO_DECISION
        assert all(report["checks"].values())
    else:
        assert OUTPUT.name == "p7-go-v5.json"
        assert GO_DECISION == "GO_S11_V2_FROZEN_90_ITEM_EXECUTION"
