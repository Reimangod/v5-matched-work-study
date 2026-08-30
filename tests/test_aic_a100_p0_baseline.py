from __future__ import annotations

from pathlib import Path

from aic_a100_pilot.common import digest, tree_inventory_digest
from aic_a100_pilot.p0_baseline import CASE_SPECS, protocol_body


def test_protocol_is_outcome_free_and_fixes_five_cases():
    value = protocol_body()
    assert value["status"] == "FROZEN_BEFORE_REGISTERED_P0_REFERENCE_AND_GPU_OUTCOMES"
    assert value["prefreeze_diagnostics"]["registered_pilot_outcome"] is False
    assert value["prefreeze_diagnostics"]["used_to_set_tolerances_or_case_order"] is False
    assert value["case_order"] == ["h2", "h4", "lih", "h6", "beh2"]
    assert set(value["case_specs"]) == set(CASE_SPECS)
    assert value["scientific_boundaries"]["full_90_item_rerun_authorized"] is False
    assert value["scientific_boundaries"]["measurement_cost_claim_authorized"] is False
    assert value["backend_policy"]["cpu_fallback_is_success"] is False
    assert value["benchmark_policy"]["measured_repetitions"] == 5


def test_tree_inventory_digest_is_content_addressed(tmp_path: Path):
    protected = tmp_path / "protected"
    protected.mkdir()
    first = protected / "a.txt"
    first.write_text("alpha", encoding="utf-8")
    observed = tree_inventory_digest((protected,), root=tmp_path)
    assert observed["file_count"] == 1
    assert observed["total_size_bytes"] == 5
    assert observed["inventory_digest"] == digest(
        [{"path": "protected/a.txt", "sha256": "8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8", "size_bytes": 5}]
    )
