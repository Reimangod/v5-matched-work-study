from v5_final.s11_v2_execution_readiness_v1 import (
    DECISION,
    OUTPUT,
    audit_frozen,
)
from v5_final.s11_v2_execution_readiness_v2 import READINESS_V1


def test_historical_no_go_is_audited_at_its_commit_not_rebuilt_from_head() -> None:
    report = audit_frozen()
    assert report["decision"] == DECISION
    assert all(report["checks"].values())
    assert READINESS_V1 == OUTPUT


def test_execution_readiness_lifecycle_is_no_go_before_or_audited_after_freeze() -> None:
    if OUTPUT.exists():
        report = audit_frozen()
        assert report["decision"] == DECISION
        assert all(report["checks"].values())
    else:
        assert OUTPUT.name == "execution-readiness-no-go-v1.json"
        assert DECISION.startswith("NO_GO_S11_V2_")
