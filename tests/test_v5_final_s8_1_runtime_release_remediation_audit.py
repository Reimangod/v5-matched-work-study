from v5_final.s8_1_runtime_release_remediation_audit import audit


def test_successor_factory_and_service_are_actual_but_outcome_blocked():
    # S8.1 is an immutable MB6-v3 historical proof.  Rebuilding it after the
    # additive MB6-v4 plan exists would select the active v4 plan and mix two
    # protocol generations.  Current v4 behavior is exercised by the dedicated
    # MB6-v4 and S8-v2 tests; this test verifies the preserved S8.1 evidence.
    assert all(audit().values())
