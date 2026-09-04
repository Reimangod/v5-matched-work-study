from __future__ import annotations

import json

from phase1_frontier.v2_s3_runner_readiness import OUTPUT, audit
from phase1_frontier.v2_s4_1_order_gate import audit as audit_order_successor


def test_s3_readiness_is_digest_bound_and_keeps_screen_closed() -> None:
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert value["decision"] == "GO_PHASE1_V2_S4_READINESS_GATE"
    assert all(value["checks"].values())
    assert value["H4_calibration"]["scientific_screen_member"] is False
    assert value["H4_calibration"]["FCI_evaluations"] == 0
    checks = audit()
    # S4.1 additively changed only the runner adapter to enforce the frozen
    # prefix.  The historical S3 evidence remains digest/queue valid, while
    # its live implementation hash must now differ and is re-authorized by
    # the current adapter-bound successor gate.
    assert checks["implementation_unchanged"] is False
    assert all(
        value for name, value in checks.items() if name != "implementation_unchanged"
    )
    assert all(audit_order_successor().values())


def test_s3_claim_boundary_does_not_promote_calibration_to_performance() -> None:
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    prohibited = " ".join(value["claim_boundary"]["prohibited"])
    assert "joint-over-singleton advantage" in prohibited
    assert "FCI" in prohibited
