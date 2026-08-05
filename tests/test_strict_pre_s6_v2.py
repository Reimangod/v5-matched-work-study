from v5_matched_work.strict_pre_s6_v2 import build, not_authorized


def test_strict_gate_supersedes_fixture_only_s5_authorization() -> None:
    incident = build()
    assert incident["candidate_energy_evaluations"] == 0
    assert incident["decision"] == "NO_GO_PRODUCTION_MOLECULAR_ADAPTERS_INCOMPLETE"
    assert "six_concrete_molecular_backend_entrypoints" in incident["failed_checks"]
    assert not_authorized(6, incident)["status"] == "NOT_AUTHORIZED"
