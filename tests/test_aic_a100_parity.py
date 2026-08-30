from __future__ import annotations

import numpy as np

from aic_a100_pilot.aer_gpu_backend import phase_aligned_max_error
from aic_a100_pilot.common import ROOT, digest, load_json
from aic_a100_pilot.p0_baseline import CALIBRATION_PLAN
from aic_a100_pilot.parity import _from_float_hex, project_plan_to_aic_runtime


ENVIRONMENT_PATH = (
    ROOT
    / "artifacts/v5-final/parent-native/mb6-v3/execution-environment-v3.json"
)


def test_phase_aligned_error_ignores_only_global_phase():
    reference = np.asarray([1.0, 1.0j], dtype=np.complex128) / np.sqrt(2)
    observed = reference * np.exp(0.75j)
    assert phase_aligned_max_error(reference, observed) < 1e-15


def test_float_hex_round_trip_matches_frozen_binary64():
    assert _from_float_hex("3ff0000000000000") == 1.0
    assert _from_float_hex("bfe0000000000000") == -0.5


def test_aic_projection_is_additive_and_content_addressed(monkeypatch):
    monkeypatch.setenv("MKL_NUM_THREADS", "2")
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "2")
    source_plan = load_json(CALIBRATION_PLAN)
    source_environment = load_json(ENVIRONMENT_PATH)
    projected, environment = project_plan_to_aic_runtime(
        source_plan, source_environment, required_threads=2
    )
    assert source_plan == load_json(CALIBRATION_PLAN)
    assert source_environment == load_json(ENVIRONMENT_PATH)
    assert environment["aic_pilot_projection"]["production_artifact_changed"] is False
    assert environment["environment_digest"] == digest(
        {key: value for key, value in environment.items() if key != "environment_digest"}
    )
    assert projected["plan_digest"] == digest(
        {key: value for key, value in projected.items() if key != "plan_digest"}
    )
    assert all(
        item["environment_digest"] == environment["environment_digest"]
        for item in projected["items"]
    )
