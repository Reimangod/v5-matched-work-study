from __future__ import annotations

import json
import os
import subprocess

from v5_final.s0_successor import ROOT


def _probe() -> dict[str, object]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(ROOT / "src"),
            str(ROOT / "provenance/dvg-obs-ceo/src"),
            str(ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"),
        )
    )
    completed = subprocess.run(
        [
            str(ROOT / "provenance/dvg-obs-ceo/.venv/bin/python"),
            "-m",
            "v5_final.parent_native_rewrite_probe",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout)


def test_actual_rewrite_matrices_and_parent_resources_precede_optimizer() -> None:
    result = _probe()
    rewrite = result["rewrite"]
    assert result["rewrite_applied_before_optimizer_arguments"] is True
    assert result["optimizer_called"] is False
    assert result["candidate_energy_evaluations"] == 0
    assert rewrite["actual_matrix_counts"]["source"] > 0
    assert rewrite["actual_matrix_counts"]["target"] > 0
    assert rewrite["target_native_circuits_verified"] > 0
    assert rewrite["parent_physical_structural_snapshot_equal"] is True
    assert rewrite["physical_circuit_changed"] is True
    assert rewrite["circuit_metric_reduced"] is True
    assert rewrite["parameter_only_reduction_claimed"] is False
    assert rewrite["resource_reduction_success"] is True
    h2 = result["known_h2_parent_parity"]
    assert h2["exact_match"] is True
    assert h2["first"] == h2["second"]
    assert h2["first"]["cnot_count"] == 9
    assert h2["first"]["cnot_depth"] == 7
