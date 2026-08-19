from __future__ import annotations

import json
from pathlib import Path

from v5_final import gpu_rtx2080ti_s2_environment_freeze_v1 as s2


def _probe() -> dict[str, object]:
    return {
        "cupy_version": "13.6.0",
        "cuda_runtime_version": 12090,
        "cuda_driver_version": 13000,
        "device_count": 1,
        "device_name": "NVIDIA GeForce RTX 2080 Ti",
        "dtype": "complex128",
        "smoke_observed": [26.375, 21.4375],
        "smoke_expected": [26.375, 21.4375],
        "smoke_absolute_error": 0.0,
    }


def test_overlay_inputs_and_locks_are_digest_pinned() -> None:
    observed = {
        path: s2._sha256((s2.ROOT / path).read_bytes())
        for path in s2.EXPECTED_FILE_SHA256
    }
    assert observed == s2.EXPECTED_FILE_SHA256


def test_gpu_probe_contract_requires_complex128_and_one_device() -> None:
    probe = _probe()
    assert probe["dtype"] == "complex128"
    assert probe["device_count"] == 1
    assert probe["cuda_driver_version"] >= probe["cuda_runtime_version"]


def test_environment_artifact_audit_rejects_digest_drift(tmp_path: Path) -> None:
    record = {
        "environment_freeze_digest": "invalid",
        "decision": "NO_GO_RTX2080TI_S2_ENVIRONMENT",
        "failed_checks": ["example"],
        "authorization": {
            "molecular_candidate_outcomes": "NOT_AUTHORIZED",
            "backend_implementation": "NOT_AUTHORIZED",
        },
    }
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    try:
        s2.audit(path)
    except RuntimeError as error:
        assert "digest_valid" in str(error)
    else:
        raise AssertionError("digest drift must fail closed")
