from __future__ import annotations

import json

from v5_final.infrastructure_no_go_release import OUTPUT, audit


def test_terminal_infrastructure_no_go_is_outcome_free_and_reproducible() -> None:
    release = json.loads(OUTPUT.read_text())
    assert release["decision"] == "NO_GO_V5_MATCHED_WORK_UNRESOLVED_INFRASTRUCTURE_V1"
    assert release["candidate_molecular_energy_evaluations"] == 0
    assert release["queue_completion"]["H2_H4_calibration"]["terminal"] == 0
    assert release["queue_completion"]["development"]["terminal"] == 0
    assert release["scientific_results"]["method_case_result_table"] == []
    assert release["scientific_results"]["figures"] == []
    assert all(audit().values())
