from __future__ import annotations

import json

from v5_matched_work.s0_common import ROOT


def test_s2_identity_layers_are_separate_when_artifact_exists() -> None:
    path = ROOT / "artifacts/s2/stationary-source-protocol-v1.json"
    if not path.exists():
        return
    value = json.loads(path.read_text())
    for case in value["quantum_probe"]["cases"]:
        identity = case["identities"]
        assert identity["StatePreparationID"] != identity["ProblemID"]
        assert "measurement_plan_version" not in identity["state_preparation_payload"]
        assert identity["measurement_context_payload"]["state_preparation_id"] == identity["StatePreparationID"]
