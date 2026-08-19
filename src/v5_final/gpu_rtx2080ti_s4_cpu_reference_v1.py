"""S4 same-host CPU reference for the frozen sparse exponential-action primitive."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import statistics
import time
from typing import Any

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import expm_multiply, norm as sparse_norm

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .gpu_rtx2080ti_s3_backend_audit_v1 import OUTPUT as S3_OUTPUT


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/v5-final/gpu-rtx2080ti/s4-cpu-reference-v1/cpu-reference-v1.json"
EXPECTED_S3_DIGEST = "e2c77bb6edf610332dd81f10c678f4a1ccb3ca32684f7b5333f8d0a8a95d059e"
THREAD_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "CUDA_VISIBLE_DEVICES": "",
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_without(record: dict[str, Any], field: str) -> str:
    value = dict(record)
    value.pop(field, None)
    return _sha256(canonical_json_bytes(value))


def _antihermitian_matrix(dimension: int) -> sparse.csr_matrix:
    if dimension < 16 or dimension & (dimension - 1):
        raise ValueError("dimension must be a power of two at least 16")
    indices = np.arange(dimension, dtype=np.float64)
    diagonal = 0.03j * np.sin(indices * 0.17)
    upper_one = 0.05 + 0.02j * np.cos(indices[:-1] * 0.11)
    upper_three = 0.025 * np.sin(indices[:-3] * 0.07) + 0.015j
    upper_seven = 0.01 * np.cos(indices[:-7] * 0.13) - 0.008j
    upper = sparse.diags(
        [upper_one, upper_three, upper_seven],
        offsets=[1, 3, 7],
        shape=(dimension, dimension),
        dtype=np.complex128,
        format="csr",
    )
    matrix = upper - upper.getH() + sparse.diags(
        diagonal, offsets=0, format="csr"
    )
    return matrix.astype(np.complex128)


def _probe_vector(dimension: int) -> np.ndarray:
    index = np.arange(dimension, dtype=np.float64)
    vector = np.cos(index * 0.19) + 1j * np.sin(index * 0.23)
    return np.asarray(vector / np.linalg.norm(vector), dtype=np.complex128)


def _single_benchmark(dimension: int, repetitions: int) -> dict[str, Any]:
    matrix = _antihermitian_matrix(dimension)
    vector = _probe_vector(dimension)
    coefficient = 0.37
    expm_multiply(coefficient * matrix, vector)
    timings: list[float] = []
    output = vector
    for _ in range(repetitions):
        started = time.perf_counter()
        output = np.asarray(
            expm_multiply(coefficient * matrix, vector), dtype=np.complex128
        )
        timings.append(time.perf_counter() - started)
    median = statistics.median(timings)
    return {
        "dimension": dimension,
        "qubits": int(math.log2(dimension)),
        "matrix_nnz": int(matrix.nnz),
        "repetitions": repetitions,
        "wall_seconds": timings,
        "median_wall_seconds": median,
        "coefficient_of_variation": (
            statistics.pstdev(timings) / statistics.fmean(timings)
            if len(timings) > 1 and statistics.fmean(timings) > 0
            else 0.0
        ),
        "output_norm": float(np.linalg.norm(output)),
        "output_sha256": _sha256(
            np.asarray(output, dtype=">c16").tobytes()
        ),
        "antihermitian_residual": float(sparse_norm(matrix + matrix.getH())),
    }


def _chain_benchmark(dimension: int = 4096, length: int = 12) -> dict[str, Any]:
    matrix = _antihermitian_matrix(dimension)
    initial = _probe_vector(dimension)
    coefficients = np.linspace(-0.31, 0.29, length, dtype=np.float64)

    def run() -> np.ndarray:
        state = initial
        for coefficient in coefficients:
            state = expm_multiply(float(coefficient) * matrix, state)
        return np.asarray(state, dtype=np.complex128)

    run()
    timings: list[float] = []
    state = initial
    for _ in range(3):
        started = time.perf_counter()
        state = run()
        timings.append(time.perf_counter() - started)
    return {
        "dimension": dimension,
        "qubits": int(math.log2(dimension)),
        "chain_length": length,
        "wall_seconds": timings,
        "median_wall_seconds": statistics.median(timings),
        "coefficient_of_variation": statistics.pstdev(timings)
        / statistics.fmean(timings),
        "output_norm": float(np.linalg.norm(state)),
        "output_sha256": _sha256(np.asarray(state, dtype=">c16").tobytes()),
    }


def build() -> dict[str, Any]:
    s3 = json.loads(S3_OUTPUT.read_text(encoding="utf-8"))
    observed_env = {name: os.environ.get(name) for name in THREAD_ENV}
    started_cpu = time.process_time()
    started_wall = time.perf_counter()
    primitives = [
        _single_benchmark(256, 5),
        _single_benchmark(1024, 5),
        _single_benchmark(4096, 5),
    ]
    chain = _chain_benchmark()
    elapsed_cpu = time.process_time() - started_cpu
    elapsed_wall = time.perf_counter() - started_wall
    checks = {
        "s3_go_and_digest_bound": s3.get("decision")
        == "GO_RTX2080TI_S4_SAME_HOST_CPU_REFERENCE_ONLY"
        and s3.get("backend_audit_digest") == EXPECTED_S3_DIGEST,
        "deterministic_thread_environment": observed_env == THREAD_ENV,
        "dimensions_cover_8_10_12_qubits": [item["dimension"] for item in primitives]
        == [256, 1024, 4096],
        "antihermitian_construction_exact": all(
            item["antihermitian_residual"] <= 1e-14 for item in primitives
        ),
        "norm_preserved": all(abs(item["output_norm"] - 1.0) <= 1e-12 for item in primitives)
        and abs(chain["output_norm"] - 1.0) <= 1e-11,
        "timings_positive_and_finite": all(
            item["median_wall_seconds"] > 0
            and math.isfinite(item["median_wall_seconds"])
            for item in (*primitives, chain)
        ),
        "large_primitive_variation_bounded": primitives[-1][
            "coefficient_of_variation"
        ]
        <= 0.50,
        "chain_variation_bounded": chain["coefficient_of_variation"] <= 0.50,
    }
    failures = [name for name, passed in checks.items() if not passed]
    decision = "GO_RTX2080TI_S5_BACKEND_IMPLEMENTATION_ONLY" if not failures else "NO_GO_RTX2080TI_S4_CPU_REFERENCE"
    record: dict[str, Any] = {
        "schema": "v5-final.gpu-rtx2080ti.s4-cpu-reference.v1",
        "stage": "GPU-S4",
        "status": "COMPLETE",
        "s3_backend_audit_digest": s3["backend_audit_digest"],
        "benchmark_contract": {
            "scientific_outcome": False,
            "molecular_hamiltonian": False,
            "matrix_family": "deterministic synthetic sparse anti-Hermitian band matrix",
            "primitive": "scipy.sparse.linalg.expm_multiply",
            "dtype": "complex128",
            "timing_clock": "time.perf_counter",
            "warmup": 1,
            "thread_environment": observed_env,
        },
        "primitive_results": primitives,
        "chain_result": chain,
        "process": {
            "total_cpu_seconds": elapsed_cpu,
            "total_wall_seconds": elapsed_wall,
            "peak_rss_raw": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
        "checks": checks,
        "failed_checks": failures,
        "authorization": {
            "s5_backend_implementation": "AUTHORIZED" if not failures else "NOT_AUTHORIZED",
            "molecular_candidate_outcomes": "NOT_AUTHORIZED",
            "gpu_90_item_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "decision": decision,
        "claim_boundary": (
            "S4 is an operational CPU reference on synthetic matrices. It is not a "
            "molecular result and does not establish GPU speedup or VQE parity."
        ),
    }
    record["cpu_reference_digest"] = _digest_without(record, "cpu_reference_digest")
    return record


def audit(path: Path = OUTPUT) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "digest_valid": record.get("cpu_reference_digest")
        == _digest_without(record, "cpu_reference_digest"),
        "decision_consistent": (
            record["decision"] == "GO_RTX2080TI_S5_BACKEND_IMPLEMENTATION_ONLY"
        )
        == (not record["failed_checks"]),
        "outcomes_not_authorized": record["authorization"]["molecular_candidate_outcomes"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError("GPU S4 artifact audit failed: " + ", ".join(failures))
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
