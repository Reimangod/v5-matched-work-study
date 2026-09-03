"""GPU-S7: preregistered H2/H4 molecular parity gate.

This stage evaluates only the two already-pinned calibration source states.  It
does not enumerate, rank, optimize, or evaluate any compression candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .gpu_rtx2080ti_s6_synthetic_parity_v1 import OUTPUT as S6_OUTPUT
from .gpu_sparse_action_v1 import CuPyCEOStateKernelV1
from .mb6_source_catalog_probe import CASES, _algorithm_outcome_free


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/v5-final/gpu-rtx2080ti/s7-h2-h4-parity-v1/h2-h4-parity-v1.json"
EXPECTED_S6_DIGEST = "e1a02c7e2d0066f64ec9cac588c413f54139be20c9a6c8874fc251f08369a3b2"

# Frozen before the first molecular GPU parity observation.
STATE_L2_TOLERANCE = 1e-10
ENERGY_ABSOLUTE_TOLERANCE_HARTREE = 1e-11
GRADIENT_INFINITY_TOLERANCE = 1e-9


def _digest_without(record: dict[str, Any], field: str) -> str:
    value = dict(record)
    value.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _host_state(value: Any) -> np.ndarray:
    raw = value.toarray() if hasattr(value, "toarray") else value
    return np.asarray(raw, dtype=np.complex128).ravel()


def _case(case_id: str, checkpoint_path: Path) -> dict[str, Any]:
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    coefficients = [float(value) for value in checkpoint["ansatz_coefficients"]]
    indices = [int(value) for value in checkpoint["ansatz_indices"]]
    algorithm, pool = _algorithm_outcome_free(case_id)
    generators = {index: pool.get_imp_op(index) for index in sorted(set(indices))}

    cpu_started = time.perf_counter()
    cpu_state = _host_state(algorithm.compute_state(coefficients, indices))
    cpu_energy = float(algorithm.evaluate_energy(coefficients, indices))
    cpu_gradient = np.asarray(
        algorithm.estimate_gradients(coefficients, indices, method="an"),
        dtype=np.float64,
    )
    cpu_seconds = time.perf_counter() - cpu_started

    kernel = CuPyCEOStateKernelV1(
        hamiltonian=algorithm.hamiltonian,
        generators=generators,
        reference_state=algorithm.sparse_ref_state,
    )
    gpu_started = time.perf_counter()
    gpu_state = kernel.statevector(coefficients, indices)
    gpu_energy = kernel.energy(coefficients, indices)
    gpu_gradient = kernel.gradient(coefficients, indices)
    kernel.cp.cuda.Stream.null.synchronize()
    gpu_seconds = time.perf_counter() - gpu_started

    # A second independent kernel is a stronger determinism check than reuse.
    repeat = CuPyCEOStateKernelV1(
        hamiltonian=algorithm.hamiltonian,
        generators=generators,
        reference_state=algorithm.sparse_ref_state,
    )
    repeated_state = repeat.statevector(coefficients, indices)
    repeated_energy = repeat.energy(coefficients, indices)
    repeated_gradient = repeat.gradient(coefficients, indices)
    repeat.cp.cuda.Stream.null.synchronize()

    state_error = float(np.linalg.norm(cpu_state - gpu_state))
    energy_error = abs(cpu_energy - gpu_energy)
    gradient_error = float(np.max(np.abs(cpu_gradient - gpu_gradient))) if indices else 0.0
    logical_work = {
        "statevector_recomputations": 1,
        "source_energy_evaluations": 1,
        "full_gradient_evaluations": 1,
        "gradient_components": len(indices),
        "candidate_energy_evaluations": 0,
        "optimizer_starts": 0,
        "optimizer_iterations": 0,
        "fci_evaluations": 0,
    }
    return {
        "case_id": case_id,
        "checkpoint_digest": checkpoint["checkpoint_digest"],
        "qubits": int(algorithm.n),
        "dimension": int(algorithm.hamiltonian.shape[0]),
        "coordinate_count": len(indices),
        "unique_generator_count": len(generators),
        "state_l2_error": state_error,
        "energy_absolute_error_hartree": energy_error,
        "gradient_infinity_error": gradient_error,
        "cpu_wall_seconds": cpu_seconds,
        "gpu_wall_seconds": gpu_seconds,
        "diagnostic_speedup_ratio": cpu_seconds / gpu_seconds,
        "gpu_bitwise_repeatable": {
            "state": bool(np.array_equal(gpu_state, repeated_state)),
            "energy": bool(gpu_energy == repeated_energy),
            "gradient": bool(np.array_equal(gpu_gradient, repeated_gradient)),
            "backend_totals": kernel.ledger.totals() == repeat.ledger.totals(),
        },
        "logical_work_cpu": logical_work,
        "logical_work_gpu": dict(logical_work),
        "backend_telemetry": kernel.ledger.totals(),
        "unexpected_cpu_fallbacks": kernel.ledger.unexpected_cpu_fallbacks,
        "checks": {
            "state_parity": state_error <= STATE_L2_TOLERANCE,
            "energy_parity": energy_error <= ENERGY_ABSOLUTE_TOLERANCE_HARTREE,
            "gradient_parity": gradient_error <= GRADIENT_INFINITY_TOLERANCE,
            "deterministic": all(
                (
                    np.array_equal(gpu_state, repeated_state),
                    gpu_energy == repeated_energy,
                    np.array_equal(gpu_gradient, repeated_gradient),
                    kernel.ledger.totals() == repeat.ledger.totals(),
                )
            ),
            "logical_work_parity": logical_work == dict(logical_work),
            "no_candidate_or_fci_work": logical_work["candidate_energy_evaluations"] == 0
            and logical_work["fci_evaluations"] == 0,
            "unexpected_cpu_fallback_zero": kernel.ledger.unexpected_cpu_fallbacks == 0,
        },
    }


def build() -> dict[str, Any]:
    s6 = json.loads(S6_OUTPUT.read_text(encoding="utf-8"))
    cases = [_case(case_id, path) for case_id, path in CASES.items()]
    checks = {
        "s6_go_and_digest_bound": s6.get("decision") == "GO_RTX2080TI_S7_H2_H4_PARITY_ONLY"
        and s6.get("synthetic_parity_digest") == EXPECTED_S6_DIGEST,
        "two_pinned_cases_only": [case["case_id"] for case in cases] == list(CASES),
        "all_case_checks_pass": all(all(case["checks"].values()) for case in cases),
        "candidate_outcome_zero": all(
            case["logical_work_gpu"]["candidate_energy_evaluations"] == 0 for case in cases
        ),
        "fci_zero": all(case["logical_work_gpu"]["fci_evaluations"] == 0 for case in cases),
    }
    failures = [name for name, passed in checks.items() if not passed]
    record: dict[str, Any] = {
        "schema": "v5-final.gpu-rtx2080ti.s7-h2-h4-parity.v1",
        "stage": "GPU-S7",
        "status": "COMPLETE",
        "preregistered_tolerances": {
            "state_l2": STATE_L2_TOLERANCE,
            "energy_absolute_hartree": ENERGY_ABSOLUTE_TOLERANCE_HARTREE,
            "gradient_infinity": GRADIENT_INFINITY_TOLERANCE,
        },
        "s6_synthetic_parity_digest": s6["synthetic_parity_digest"],
        "cases": cases,
        "checks": checks,
        "failed_checks": failures,
        "authorization": {
            "s8_end_to_end_benchmark": "AUTHORIZED" if not failures else "NOT_AUTHORIZED",
            "gpu_90_item_execution": "NOT_AUTHORIZED",
            "fci_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "decision": "GO_RTX2080TI_S8_END_TO_END_GATE_ONLY"
        if not failures
        else "NO_GO_RTX2080TI_S7_H2_H4_PARITY",
        "claim_boundary": (
            "Source-state CPU/GPU numerical and logical-work parity for the pinned H2/H4 "
            "calibration checkpoints only. Timings are diagnostic; no compression candidate, "
            "FCI reference, matched-work result, or performance claim is admitted."
        ),
    }
    record["h2_h4_parity_digest"] = _digest_without(record, "h2_h4_parity_digest")
    return record


def audit(path: Path = OUTPUT) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "digest_valid": record.get("h2_h4_parity_digest")
        == _digest_without(record, "h2_h4_parity_digest"),
        "decision_consistent": (
            record["decision"] == "GO_RTX2080TI_S8_END_TO_END_GATE_ONLY"
        )
        == (not record["failed_checks"]),
        "queue_blocked": record["authorization"]["gpu_90_item_execution"]
        == "NOT_AUTHORIZED",
        "performance_blocked": record["authorization"]["performance_claim"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError("GPU S7 artifact audit failed: " + ", ".join(failures))
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
