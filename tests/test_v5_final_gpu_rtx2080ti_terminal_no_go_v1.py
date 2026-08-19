from v5_final.gpu_rtx2080ti_terminal_no_go_v1 import STAGES, build


def test_terminal_no_go_closes_without_candidate_outcomes() -> None:
    record = build()
    assert list(STAGES) == [f"S{index}" for index in range(9)]
    assert record["decision"] == "NO_GO_RTX2080TI_NO_END_TO_END_ADVANTAGE"
    assert record["checks"]["candidate_energy_zero"]
    assert record["checks"]["fci_zero"]
    assert record["stage_disposition"]["S12"] == "NOT_AUTHORIZED_BY_S8"
