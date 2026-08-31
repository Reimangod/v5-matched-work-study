from v5_final.s12_final_archive_audit_v1 import (
    DECISION,
    build_artifact,
)


def test_final_archive_binds_exact_population_and_closes_reexecution() -> None:
    value = build_artifact("fc1cb8599c01fbcd412632c83084b3e404b716ff")
    assert value["decision"] == DECISION
    assert value["observed"]["terminal_status_counts"] == {
        "ALGORITHM_REJECTED": 23,
        "CAP_REJECTED": 8,
        "COMPLETED": 58,
        "FAILED_ENGINEERING_PRESERVED": 1,
    }
    assert value["observed"]["FCI_counters"] == {
        "FCI_evaluations": 5,
        "candidate_energy_evaluations": 0,
        "optimizer_starts": 0,
        "S11_items_rerun": 0,
        "production_N_dense_expm": 0,
    }
    assert value["authorization"]["FCI_reexecution"] == "NOT_AUTHORIZED"
    assert value["bindings"]["queue_v2_digest"]
