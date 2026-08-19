"""S2 reproducible CPU/GPU environment freeze and outcome-free CUDA smoke test."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .gpu_rtx2080ti_s1_hardware_audit_v1 import OUTPUT as S1_OUTPUT


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/v5-final/gpu-rtx2080ti/s2-environment-freeze-v1/environment-freeze-v1.json"
CPU_PYTHON = ROOT / "provenance/dvg-obs-ceo/.venv/bin/python"
GPU_PYTHON = ROOT / "provenance/dvg-obs-ceo/.venv-gpu/bin/python"

EXPECTED_FILE_SHA256 = {
    "uv.lock": "903584f4dc217af674dc07a4a3700e7d6b937fd7277cd08952bebd5dbe1c3814",
    "provenance/dvg-obs-ceo/uv.lock": "8a9021a72dd3bd6af8d8fc656d8f544adf620c1900c5ce081b26f484bbf6909d",
    "gpu-rtx2080ti-overlay.in": "eb9ab73a301d51e368cb391dc5a363fe91ec9a634f3be85c43ddcc80e27c8646",
    "gpu-rtx2080ti-overlay.lock": "707ad1ac498f04b7a08d57a616a02b5ee625c1563f609d4b203bd1b2275a003d",
}
EXPECTED_S1_DIGEST = "51aff462ae772a20cb689af5e3f9898e4da06f4133abf2c4c51c16cf8d9114a2"
EXPECTED_BASE_PACKAGES = {
    "numpy": "1.23.5",
    "scipy": "1.10.1",
    "qiskit": "0.43.3",
    "qiskit-aer": "0.12.2",
    "qiskit-terra": "0.24.2",
    "pyscf": "2.2.0",
    "openfermion": "1.5.1",
}
EXPECTED_GPU_OVERLAY = {
    "cupy-cuda12x": "13.6.0",
    "fastrlock": "0.8.3",
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_without(record: dict[str, Any], field: str) -> str:
    value = dict(record)
    value.pop(field, None)
    return _sha256(canonical_json_bytes(value))


def _normalize_distribution_name(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def _package_manifest(python: Path) -> dict[str, str]:
    script = (
        "import importlib.metadata,json;"
        "n=lambda x:x.lower().replace('_','-').replace('.','-');"
        "print(json.dumps(dict(sorted((n(d.metadata['Name']),d.version) "
        "for d in importlib.metadata.distributions()))))"
    )
    completed = subprocess.run(
        [str(python), "-c", script],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    return json.loads(completed.stdout)


def _current_manifest() -> dict[str, str]:
    return dict(
        sorted(
            (
                _normalize_distribution_name(distribution.metadata["Name"]),
                distribution.version,
            )
            for distribution in importlib.metadata.distributions()
        )
    )


def _gpu_probe() -> dict[str, Any]:
    import cupy as cp

    matrix = cp.asarray(
        [[1.0 + 2.0j, -3.0 + 0.5j], [2.5 - 1.0j, 4.0 + 3.0j]],
        dtype=cp.complex128,
    )
    vector = cp.asarray([0.25 - 0.5j, -1.5 + 2.0j], dtype=cp.complex128)
    value = cp.vdot(vector, matrix @ vector)
    cp.cuda.Stream.null.synchronize()
    observed = complex(cp.asnumpy(value))
    expected = complex(26.375, 21.4375)
    return {
        "cupy_version": cp.__version__,
        "cuda_runtime_version": int(cp.cuda.runtime.runtimeGetVersion()),
        "cuda_driver_version": int(cp.cuda.runtime.driverGetVersion()),
        "device_count": int(cp.cuda.runtime.getDeviceCount()),
        "device_name": cp.cuda.runtime.getDeviceProperties(0)["name"].decode("utf-8"),
        "dtype": str(matrix.dtype),
        "smoke_observed": [observed.real, observed.imag],
        "smoke_expected": [expected.real, expected.imag],
        "smoke_absolute_error": abs(observed - expected),
    }


def build(*, gpu_probe: Callable[[], dict[str, Any]] = _gpu_probe) -> dict[str, Any]:
    s1 = json.loads(S1_OUTPUT.read_text(encoding="utf-8"))
    file_sha256 = {
        path: _sha256((ROOT / path).read_bytes()) for path in EXPECTED_FILE_SHA256
    }
    cpu_packages = _package_manifest(CPU_PYTHON)
    gpu_packages = _current_manifest() if Path(sys.executable).resolve() == GPU_PYTHON.resolve() else _package_manifest(GPU_PYTHON)
    probe = gpu_probe()
    overlay_difference = {
        name: version
        for name, version in gpu_packages.items()
        if cpu_packages.get(name) != version
    }
    missing_from_gpu = sorted(name for name in cpu_packages if name not in gpu_packages)
    base_versions_match = all(
        cpu_packages.get(name) == version and gpu_packages.get(name) == version
        for name, version in EXPECTED_BASE_PACKAGES.items()
    )
    checks = {
        "s1_go_and_digest_bound": s1.get("decision") == "GO_RTX2080TI_S2_ENVIRONMENT_ONLY"
        and s1.get("hardware_audit_digest") == EXPECTED_S1_DIGEST,
        "lock_and_overlay_files_exact": file_sha256 == EXPECTED_FILE_SHA256,
        "cpu_python_exact": subprocess.check_output(
            [str(CPU_PYTHON), "-c", "import platform;print(platform.python_version())"],
            text=True,
        ).strip()
        == "3.10.19",
        "gpu_python_exact": subprocess.check_output(
            [str(GPU_PYTHON), "-c", "import platform;print(platform.python_version())"],
            text=True,
        ).strip()
        == "3.10.19",
        "base_package_versions_match": base_versions_match,
        "gpu_overlay_is_exact": overlay_difference == EXPECTED_GPU_OVERLAY,
        "gpu_environment_loses_no_cpu_package": not missing_from_gpu,
        "cupy_version_exact": probe["cupy_version"] == "13.6.0",
        "one_rtx_2080_ti_visible": probe["device_count"] == 1
        and "RTX 2080 Ti" in probe["device_name"],
        "cuda_driver_supports_runtime": probe["cuda_driver_version"]
        >= probe["cuda_runtime_version"],
        "complex128_smoke_passes": probe["dtype"] == "complex128"
        and probe["smoke_absolute_error"] <= 1e-12,
    }
    failures = [name for name, passed in checks.items() if not passed]
    decision = "GO_RTX2080TI_S3_BACKEND_AUDIT_ONLY" if not failures else "NO_GO_RTX2080TI_S2_ENVIRONMENT"
    record: dict[str, Any] = {
        "schema": "v5-final.gpu-rtx2080ti.s2-environment-freeze.v1",
        "stage": "GPU-S2",
        "status": "COMPLETE",
        "s1_hardware_audit_digest": s1["hardware_audit_digest"],
        "files_sha256": file_sha256,
        "environment": {
            "uv_version": "0.9.8",
            "python_version": "3.10.19",
            "cpu_environment": "provenance/dvg-obs-ceo/.venv",
            "gpu_environment": "provenance/dvg-obs-ceo/.venv-gpu",
            "base_packages": EXPECTED_BASE_PACKAGES,
            "gpu_overlay": overlay_difference,
            "cpu_package_manifest_digest": _sha256(canonical_json_bytes(cpu_packages)),
            "gpu_package_manifest_digest": _sha256(canonical_json_bytes(gpu_packages)),
            "cpu_package_count": len(cpu_packages),
            "gpu_package_count": len(gpu_packages),
            "missing_from_gpu": missing_from_gpu,
        },
        "cuda_probe": probe,
        "checks": checks,
        "failed_checks": failures,
        "authorization": {
            "s3_backend_bottleneck_audit": "AUTHORIZED" if not failures else "NOT_AUTHORIZED",
            "backend_implementation": "NOT_AUTHORIZED",
            "molecular_candidate_outcomes": "NOT_AUTHORIZED",
            "gpu_90_item_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "decision": decision,
        "claim_boundary": (
            "S2 establishes a lock-bound CUDA-capable environment and a synthetic "
            "complex128 smoke test only; it does not establish VQE parity or speedup."
        ),
    }
    record["environment_freeze_digest"] = _digest_without(record, "environment_freeze_digest")
    return record


def audit(path: Path = OUTPUT) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "digest_valid": record.get("environment_freeze_digest")
        == _digest_without(record, "environment_freeze_digest"),
        "decision_consistent": (
            record["decision"] == "GO_RTX2080TI_S3_BACKEND_AUDIT_ONLY"
        )
        == (not record["failed_checks"]),
        "outcomes_not_authorized": record["authorization"]["molecular_candidate_outcomes"]
        == "NOT_AUTHORIZED",
        "implementation_not_authorized": record["authorization"]["backend_implementation"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError("GPU S2 artifact audit failed: " + ", ".join(failures))
    return {"passed": True, "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.action == "build":
        artifact = build()
        write_json_exclusive(args.output, artifact)
        print(json.dumps({"decision": artifact["decision"], "path": str(args.output)}, sort_keys=True))
        return
    print(json.dumps(audit(args.output), sort_keys=True))


if __name__ == "__main__":
    main()
