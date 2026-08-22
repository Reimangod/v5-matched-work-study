from v5_final.s8_go_v1_suspension import audit, build


def test_s8_v1_is_suspended_before_any_outcome():
    artifact = build()
    assert all(artifact["checks"].values())
    assert artifact["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED"
    assert artifact["candidate_molecular_energy_evaluations"] == 0
    assert all(audit().values())
