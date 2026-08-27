from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import subprocess

from v5_final.s3_parent_native_runtime_factory_audit import audit


ROOT = Path(__file__).resolve().parents[1]


def test_actual_h2_h4_queue_bound_factory_is_outcome_free():
    if platform.machine().lower() != "arm64":
        # The frozen molecular runtime is macOS arm64.  Foreign CI must verify
        # the immutable audit and must not pretend to reproduce that runtime.
        assert all(audit().values())
        return
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(ROOT / "src"),
            str(ROOT / "provenance/dvg-obs-ceo/src"),
            str(ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"),
        )
    )
    for name in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        environment[name] = "2"
    completed = subprocess.run(
        [
            str(ROOT / "provenance/dvg-obs-ceo/.venv/bin/python"),
            "-m",
            "v5_final.parent_native_runtime_factory_probe",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    probe = json.loads(completed.stdout)
    assert len(probe["cases"]) == 2
    assert all(case["actual_runtime_type"] == "CompressionRuntime" for case in probe["cases"])
    assert all(case["pre_GO_algorithm_guard_verified"] for case in probe["cases"])
    assert all(probe["negative_preflight"].values())
    assert probe["candidate_energy_evaluations"] == 0
    assert probe["optimizer_calls"] == 0
    assert probe["projected_queue_written_or_authorized"] is False
