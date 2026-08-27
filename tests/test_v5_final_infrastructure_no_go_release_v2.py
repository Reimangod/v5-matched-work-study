from __future__ import annotations

import json

from v5_final.infrastructure_no_go_release_v2 import OUTPUT, audit, verify


def test_terminal_v2_release_is_pre_outcome_infrastructure_no_go() -> None:
    release = json.loads(OUTPUT.read_text())
    assert release["decision"] == "NO_GO_V5_MATCHED_WORK_INFRASTRUCTURE_V2"
    assert release["candidate_molecular_energy_evaluations"] == 0
    assert release["queue_completion"]["H2_H4_calibration_v2"]["terminal"] == 0
    assert release["queue_completion"]["development"]["terminal"] == 0
    assert release["scientific_results"]["method_case_result_table"] == []
    assert release["scientific_results"]["figures"] == []
    assert release["scientific_results"]["negative_performance_result"] is None
    assert all(verify(release).values())
    assert all(audit().values())
