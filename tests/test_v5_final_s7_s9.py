from __future__ import annotations

import json

from v5_final.s0_successor import ROOT
from v5_final.s7_s9_contract import audit


def test_predictor_pareto_and_certification_contracts_remain_outcome_blind() -> None:
    value = json.loads(
        (
            ROOT
            / "artifacts/v5-final/s7-s9/predictor-pareto-certification-contract-v1.json"
        ).read_text()
    )
    assert value["predictor_probe"]["actual_energy_leakage_rejected"] is True
    assert value["predictor_probe"]["uncertainty_unestablished_is_null"] is True
    assert value["pareto_probe"]["primary_axes_not_scalarized"] is True
    assert value["certification_probe"]["complete_evidence_accepted"]["accepted"] is True
    assert value["certification_probe"]["missing_ledger_closure_rejected"][
        "accepted"
    ] is False
    assert value["authorization"]["performance_experiment"] == "NOT_AUTHORIZED"
    assert all(audit().values())
