from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from v5_final.s0_successor import ROOT


def test_actual_parent_candidate_is_typed_composed_and_identity_separated() -> None:
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
            "v5_final.parent_native_candidate_probe",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["block_type"] == "DVGBlock"
    assert result["candidate_type"] == "CompressionCandidate"
    assert result["candidate_is_mapping"] is False
    assert result["candidate_count"] > 0
    assert result["candidate_id"].startswith("candidate-v1:")
    assert result["equivalence_class_id"].startswith("transform-v1:")
    assert result["target_indices"]
    assert result["target_iteration_counts"][-1] == len(result["target_indices"])
    assert result["constraint_semantic_id"].startswith("constraint-semantic-v1:")
    assert result["constraint_numerical_id"].startswith("constraint-numerical-v1:")
    assert result["candidate_intent_id"].startswith("candidate-intent-v1:")
    assert result["proposed_physical_state_id"].startswith("physical-state-v2:")
    assert result["proposed_state_preparation_id"].startswith("state-v1:")
    assert len(
        {
            result["candidate_intent_id"],
            result["proposed_physical_state_id"],
            result["proposed_state_preparation_id"],
        }
    ) == 3
    assert result["warm_start_dimension"] == len(result["target_indices"])
    assert result["inverse_hessian_dimension"] == len(result["target_indices"])
    assert result["candidate_energy_evaluations"] == 0
