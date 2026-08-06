from __future__ import annotations

import json

from v5_final.s0_successor import ROOT
from v5_final.s6_method_parity import audit


def test_six_method_controllers_share_interface_and_fail_closed() -> None:
    value = json.loads(
        (ROOT / "artifacts/v5-final/s6/method-controller-parity-v1.json").read_text()
    )
    assert value["six_concrete_controllers"] is True
    assert all(value["common_interface_symmetry"].values())
    assert all(value["causal_ablation_parity"].values())
    assert all(value["execution_entrypoints_fail_closed"].values())
    assert value["authorization"]["candidate_molecular_execution"] == "NOT_AUTHORIZED"
    assert all(audit().values())
