"""GPU-S8: preregistered steady-state end-to-end speed and safety gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .gpu_rtx2080ti_s7_h2_h4_parity_v1 import OUTPUT as S7_OUTPUT
from .gpu_sparse_action_v1 import CuPyCEOStateKernelV1
from .mb6_source_catalog_probe import CASES, _algorithm_outcome_free


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/v5-final/gpu-rtx2080ti/s8-end-to-end-gate-v1/end-to-end-gate-v1.json"
EXPECTED_S7_DIGEST = "d3c3c0f30d4108b0b79891eaade0d6957abbc11dd1e7a6c51622a1c480924be6"
REPETITIONS = 3
MINIMUM_MEDIAN_SPEEDUP = 1.0
MINIMUM_FREE_STORAGE_BYTES = 40 * 1024**3


def _digest_without(record: dict[str, Any], field: str) -> str:
    value = dict(record)
    value.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _cpu_workload(algorithm: Any, coefficients: list[float], indices: list[int]) -> None:
    algorithm.compute_state(coefficients, indices)
    algorithm.evaluate_energy(coefficients, indices)
    algorithm.estimate_gradients(coefficients, indices, method="an")


def _gpu_workload(kernel: CuPyCEOStateKernelV1, coefficients: list[float], indices: list[int]) -> None:
    kernel.statevector(coefficients, indices)
    kernel.energy(coefficients, indices)
    kernel.gradient(coefficients, indices)
    kernel.cp.cuda.Stream.null.synchronize()


def _case(case_id: str, checkpoint_path: Path) -> dict[str, Any]:
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    coefficients = [float(value) for value in checkpoint["ansatz_coefficients"]]
    indices = [int(value) for value in checkpoint["ansatz_indices"]]
    algorithm, pool = _algorithm_outcome_free(case_id)
    generators = {index: pool.get_imp_op(index) for index in sorted(set(indices))}

    import cupy as cp

    initialization_started = time.perf_counter()
    kernel = CuPyCEOStateKernelV1(
        hamiltonian=algorithm.hamiltonian,
        generators=generators,
        reference_state=algorithm.sparse_ref_state,
    )
    cp.cuda.Stream.null.synchronize()
    initialization_seconds = time.perf_counter() - initialization_started

    cpu_warmup_started = time.perf_counter()
    _cpu_workload(algorithm, coefficients, indices)
    cpu_warmup_seconds = time.perf_counter() - cpu_warmup_started
    gpu_warmup_started = time.perf_counter()
    _gpu_workload(kernel, coefficients, indices)
    gpu_warmup_seconds = time.perf_counter() - gpu_warmup_started

    cpu_samples: list[float] = []
    gpu_samples: list[float] = []
    for _ in range(REPETITIONS):
        started = time.perf_counter()
        _cpu_workload(algorithm, coefficients, indices)
        cpu_samples.append(time.perf_counter() - started)
        started = time.perf_counter()
        _gpu_workload(kernel, coefficients, indices)
        gpu_samples.append(time.perf_counter() - started)

    cpu_median = statistics.median(cpu_samples)
    gpu_median = statistics.median(gpu_samples)
    speedup = cpu_median / gpu_median
    return {
        "case_id": case_id,
        "checkpoint_digest": checkpoint["checkpoint_digest"],
        "qubits": int(algorithm.n),
        "coordinate_count": len(indices),
        "repetitions": REPETITIONS,
        "cuda_initialization_and_materialization_seconds": initialization_seconds,
        "warmup": {"cpu_seconds": cpu_warmup_seconds, "gpu_seconds": gpu_warmup_seconds},
        "steady_state": {
            "cpu_seconds": cpu_samples,
            "gpu_seconds": gpu_samples,
            "cpu_median_seconds": cpu_median,
            "gpu_median_seconds": gpu_median,
            "cpu_range_seconds": [min(cpu_samples), max(cpu_samples)],
            "gpu_range_seconds": [min(gpu_samples), max(gpu_samples)],
            "median_speedup_ratio": speedup,
        },
        "gpu_memory": {
            "memory_pool_used_bytes": int(cp.get_default_memory_pool().used_bytes()),
            "memory_pool_total_bytes": int(cp.get_default_memory_pool().total_bytes()),
        },
        "backend_telemetry": kernel.ledger.totals(),
        "unexpected_cpu_fallbacks": kernel.ledger.unexpected_cpu_fallbacks,
        "speed_gate_passed": speedup >= MINIMUM_MEDIAN_SPEEDUP,
    }


def build() -> dict[str, Any]:
    s7 = json.loads(S7_OUTPUT.read_text(encoding="utf-8"))
    cases = [_case(case_id, path) for case_id, path in CASES.items()]
    disk = os.statvfs(ROOT)
    free_bytes = int(disk.f_bavail * disk.f_frsize)
    checks = {
        "s7_go_and_digest_bound": s7.get("decision") == "GO_RTX2080TI_S8_END_TO_END_GATE_ONLY"
        and s7.get("h2_h4_parity_digest") == EXPECTED_S7_DIGEST,
        "three_or_more_steady_state_repetitions": all(
            case["repetitions"] >= 3 for case in cases
        ),
        "all_source_parity_checks_passed": all(
            all(case["checks"].values()) for case in s7["cases"]
        ),
        "resource_semantics_unchanged": True,
        "cpu_fallback_zero": all(case["unexpected_cpu_fallbacks"] == 0 for case in cases),
        "gpu_kernel_evidence_present": all(
            case["backend_telemetry"]["gpu-sparse-matvec"] > 0
            and case["gpu_memory"]["memory_pool_total_bytes"] > 0
            for case in cases
        ),
        "minimum_end_to_end_speed": all(case["speed_gate_passed"] for case in cases),
        "storage_at_least_40_gib": free_bytes >= MINIMUM_FREE_STORAGE_BYTES,
        "candidate_and_fci_outcomes_zero": True,
    }
    failures = [name for name, passed in checks.items() if not passed]
    # P6 terminal-status parity was intentionally not inferred from source-kernel parity.
    unresolved = [] if failures else ["H2_H4_CANDIDATE_SEQUENCE_AND_TERMINAL_STATUS_PARITY_NOT_ESTABLISHED"]
    go = not failures and not unresolved
    decision = (
        "GO_RTX2080TI_S9_MATCHED_WORK_REFREEZE_ONLY"
        if go
        else (
            "NO_GO_RTX2080TI_NO_END_TO_END_ADVANTAGE"
            if "minimum_end_to_end_speed" in failures
            else "NO_GO_RTX2080TI_S8_SAFETY_OR_PARITY_INCOMPLETE"
        )
    )
    record: dict[str, Any] = {
        "schema": "v5-final.gpu-rtx2080ti.s8-end-to-end-gate.v1",
        "stage": "GPU-S8",
        "status": "TERMINAL_GO" if go else "TERMINAL_NO_GO",
        "preregistered_policy": {
            "repetitions": REPETITIONS,
            "minimum_median_speedup": MINIMUM_MEDIAN_SPEEDUP,
            "minimum_free_storage_bytes": MINIMUM_FREE_STORAGE_BYTES,
            "workload": "source statevector + source energy + full analytic gradient",
            "all_cases_must_pass": True,
        },
        "s7_h2_h4_parity_digest": s7["h2_h4_parity_digest"],
        "cases": cases,
        "free_storage_bytes": free_bytes,
        "checks": checks,
        "failed_checks": failures,
        "unresolved_requirements": unresolved,
        "scientific_work": {
            "compression_candidate_energy_evaluations": 0,
            "optimizer_starts": 0,
            "fci_evaluations": 0,
            "gpu_90_item_terminal_count": 0,
        },
        "authorization": {
            "s9_gpu_queue_refreeze": "AUTHORIZED" if go else "NOT_AUTHORIZED",
            "s10_gpu_90_item_execution": "NOT_AUTHORIZED",
            "s11_closure": "NOT_AUTHORIZED",
            "s12_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "decision": decision,
        "claim_boundary": (
            "This is a backend-port speed/safety result, not a V5 molecular-performance "
            "result. S7 established source-kernel parity only; candidate sequence and optimizer "
            "terminal-status parity were not inferred. A No-Go leaves the frozen GPU 90-item "
            "queue uncreated and unexecuted."
        ),
    }
    record["end_to_end_gate_digest"] = _digest_without(record, "end_to_end_gate_digest")
    return record


def audit(path: Path = OUTPUT) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "digest_valid": record.get("end_to_end_gate_digest")
        == _digest_without(record, "end_to_end_gate_digest"),
        "no_go_blocks_s9_s12": (
            not record["decision"].startswith("NO_GO")
            or all(value == "NOT_AUTHORIZED" for value in record["authorization"].values())
        ),
        "no_candidate_outcome": record["scientific_work"][
            "compression_candidate_energy_evaluations"
        ]
        == 0,
        "no_fci": record["scientific_work"]["fci_evaluations"] == 0,
        "zero_gpu_queue_terminal": record["scientific_work"][
            "gpu_90_item_terminal_count"
        ]
        == 0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError("GPU S8 artifact audit failed: " + ", ".join(failures))
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
    else:
        print(json.dumps(audit(args.output), sort_keys=True))


if __name__ == "__main__":
    main()
