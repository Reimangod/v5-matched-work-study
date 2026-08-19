from __future__ import annotations

import json
from pathlib import Path

from v5_final import gpu_rtx2080ti_s3_backend_audit_v1 as s3


def _capabilities() -> dict[str, object]:
    return {
        "cupy_device_count": 1,
        "cupy_sparse_expm_multiply_available": False,
        "qiskit_aer_devices": ["CPU"],
        "qiskit_aer_methods": ["automatic", "statevector"],
    }


def test_backend_audit_binds_exact_scientific_sources() -> None:
    observed = {
        path: s3._sha256((s3.ROOT / path).read_bytes())
        for path in s3.EXPECTED_SOURCE_SHA256
    }
    assert observed == s3.EXPECTED_SOURCE_SHA256


def test_static_contracts_locate_all_frozen_owners() -> None:
    assert all(s3._static_contract_checks().values())


def test_unavailable_gpu_apis_are_explicit() -> None:
    capabilities = _capabilities()
    assert capabilities["qiskit_aer_devices"] == ["CPU"]
    assert capabilities["cupy_sparse_expm_multiply_available"] is False


def test_invalid_s3_digest_fails_closed(tmp_path: Path) -> None:
    record = {
        "backend_audit_digest": "invalid",
        "decision": "NO_GO_RTX2080TI_S3_BACKEND_AUDIT",
        "failed_checks": ["example"],
        "authorization": {
            "gpu_backend_implementation": "NOT_AUTHORIZED",
            "molecular_candidate_outcomes": "NOT_AUTHORIZED",
        },
    }
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    try:
        s3.audit(path)
    except RuntimeError as error:
        assert "digest_valid" in str(error)
    else:
        raise AssertionError("digest drift must fail closed")
