"""S5 implementation audit for the fail-closed CuPy hybrid kernel."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import expm_multiply

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .gpu_rtx2080ti_s4_cpu_reference_v1 import OUTPUT as S4_OUTPUT
from .gpu_sparse_action_v1 import (
    CuPyCEOStateKernelV1,
    CuPySparseExpmActionV1,
    HybridBackendLedger,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/v5-final/gpu-rtx2080ti/s5-backend-implementation-v1/backend-implementation-v1.json"
EXPECTED_S4_DIGEST = "82f9ef5ba4223d885f99b94e12e43335854fb92cd3ace97b4122f8c21151163a"
EXPECTED_BACKEND_SHA256 = "4b07541ad31d203ae5abe6c243cdf31e3f3ae75110ad6a8e234ee1483a581c94"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_without(record: dict[str, Any], field: str) -> str:
    value = dict(record)
    value.pop(field, None)
    return _sha256(canonical_json_bytes(value))


def synthetic_problem(dimension: int = 64):
    x = np.arange(dimension - 1, dtype=np.float64)
    first = sparse.diags(
        [0.05 + 0.01j * np.cos(x), -0.05 + 0.01j * np.cos(x)],
        [1, -1],
        shape=(dimension, dimension),
        dtype=np.complex128,
        format="csr",
    )
    first = (first - first.getH()).tocsr()
    second = sparse.diags(
        [0.03 * np.sin(x) + 0.02j, -0.03 * np.sin(x) + 0.02j],
        [1, -1],
        shape=(dimension, dimension),
        dtype=np.complex128,
        format="csr",
    )
    second = (second - second.getH()).tocsr()
    hamiltonian = sparse.diags(
        np.linspace(-1.0, 1.0, dimension), format="csr", dtype=np.complex128
    ) + 0.02 * sparse.diags(
        [np.ones(dimension - 1), np.ones(dimension - 1)],
        [1, -1],
        format="csr",
    )
    reference = np.zeros(dimension, dtype=np.complex128)
    reference[0] = 1.0
    return hamiltonian.tocsr(), {0: first, 1: second}, reference


def _cpu_energy(
    coefficients: np.ndarray,
    hamiltonian: sparse.csr_matrix,
    generators: dict[int, sparse.csr_matrix],
    reference: np.ndarray,
) -> float:
    state = reference
    for coefficient, index in zip(coefficients, (0, 1)):
        state = expm_multiply(float(coefficient) * generators[index], state)
    return float(np.vdot(state, hamiltonian @ state).real)


def build() -> dict[str, Any]:
    s4 = json.loads(S4_OUTPUT.read_text(encoding="utf-8"))
    hamiltonian, generators, reference = synthetic_problem()
    vector = np.cos(np.arange(64) * 0.2) + 1j * np.sin(np.arange(64) * 0.17)
    vector = np.asarray(vector / np.linalg.norm(vector), dtype=np.complex128)
    action_ledger = HybridBackendLedger()
    action = CuPySparseExpmActionV1(generators[0], action_ledger)
    action_errors = []
    action_plans = []
    for coefficient in (-0.7, -0.1, 0.0, 0.3, 0.9):
        expected = expm_multiply(coefficient * generators[0], vector)
        observed = action.apply(coefficient, vector)
        action_errors.append(float(np.linalg.norm(expected - observed)))
        plan = action.plan(coefficient)
        action_plans.append(
            {
                "coefficient_float64_hex": coefficient.hex(),
                "degree": plan.degree,
                "scaling": plan.scaling,
            }
        )

    kernel = CuPyCEOStateKernelV1(
        hamiltonian=hamiltonian,
        generators=generators,
        reference_state=reference,
    )
    coordinates = np.asarray([0.23, -0.31], dtype=np.float64)
    cpu_energy = _cpu_energy(coordinates, hamiltonian, generators, reference)
    gpu_energy = kernel.energy(coordinates, [0, 1])
    step = 1e-6
    finite_difference = np.asarray(
        [
            (
                _cpu_energy(
                    coordinates + np.eye(2)[position] * step,
                    hamiltonian,
                    generators,
                    reference,
                )
                - _cpu_energy(
                    coordinates - np.eye(2)[position] * step,
                    hamiltonian,
                    generators,
                    reference,
                )
            )
            / (2.0 * step)
            for position in range(2)
        ],
        dtype=np.float64,
    )
    gpu_gradient = kernel.gradient(coordinates, [0, 1])
    checks = {
        "s4_go_and_digest_bound": s4.get("decision")
        == "GO_RTX2080TI_S5_BACKEND_IMPLEMENTATION_ONLY"
        and s4.get("cpu_reference_digest") == EXPECTED_S4_DIGEST,
        "backend_source_exact": _sha256(
            (ROOT / "src/v5_final/gpu_sparse_action_v1.py").read_bytes()
        )
        == EXPECTED_BACKEND_SHA256,
        "action_smoke_max_error": max(action_errors) <= 1e-12,
        "energy_smoke_error": abs(cpu_energy - gpu_energy) <= 1e-12,
        "gradient_smoke_error": float(np.max(np.abs(finite_difference - gpu_gradient)))
        <= 1e-7,
        "unexpected_cpu_fallback_zero": action_ledger.unexpected_cpu_fallbacks == 0
        and kernel.ledger.unexpected_cpu_fallbacks == 0,
        "gpu_sparse_matvec_observed": action_ledger.totals()["gpu-sparse-matvec"] > 0
        and kernel.ledger.totals()["gpu-sparse-matvec"] > 0,
        "planned_cpu_selection_observed": action_ledger.totals()[
            "cpu-norm-and-taylor-parameter-selection"
        ]
        > 0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    decision = "GO_RTX2080TI_S6_SYNTHETIC_PARITY_ONLY" if not failures else "NO_GO_RTX2080TI_S5_BACKEND_IMPLEMENTATION"
    record: dict[str, Any] = {
        "schema": "v5-final.gpu-rtx2080ti.s5-backend-implementation.v1",
        "stage": "GPU-S5",
        "status": "COMPLETE",
        "s4_cpu_reference_digest": s4["cpu_reference_digest"],
        "backend": {
            "id": "cupy-scipy-parameterized-sparse-action-v1",
            "source_sha256": EXPECTED_BACKEND_SHA256,
            "cpu_control": "SciPy 1.10.1 Al-Mohy--Higham degree/scaling selection",
            "gpu_kernel": "CuPy 13.6 complex128 sparse matvec Taylor action",
            "unexpected_cpu_fallback_limit": 0,
            "matched_work_counter_schema_changed": False,
            "backend_telemetry_is_separate": True,
        },
        "smoke": {
            "action_errors": action_errors,
            "action_plans": action_plans,
            "cpu_energy": cpu_energy,
            "gpu_energy": gpu_energy,
            "finite_difference_gradient": finite_difference.tolist(),
            "gpu_analytic_gradient": gpu_gradient.tolist(),
            "action_backend_totals": action_ledger.totals(),
            "kernel_backend_totals": kernel.ledger.totals(),
            "unexpected_cpu_fallbacks": action_ledger.unexpected_cpu_fallbacks
            + kernel.ledger.unexpected_cpu_fallbacks,
        },
        "checks": checks,
        "failed_checks": failures,
        "authorization": {
            "s6_synthetic_parity": "AUTHORIZED" if not failures else "NOT_AUTHORIZED",
            "molecular_candidate_outcomes": "NOT_AUTHORIZED",
            "gpu_90_item_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "decision": decision,
        "claim_boundary": (
            "S5 is implementation and smoke evidence on a synthetic system. It does "
            "not establish molecular parity, matched-work validity, or speedup."
        ),
    }
    record["backend_implementation_digest"] = _digest_without(
        record, "backend_implementation_digest"
    )
    return record


def audit(path: Path = OUTPUT) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "digest_valid": record.get("backend_implementation_digest")
        == _digest_without(record, "backend_implementation_digest"),
        "decision_consistent": (
            record["decision"] == "GO_RTX2080TI_S6_SYNTHETIC_PARITY_ONLY"
        )
        == (not record["failed_checks"]),
        "outcomes_not_authorized": record["authorization"]["molecular_candidate_outcomes"]
        == "NOT_AUTHORIZED",
        "fallback_zero": record["smoke"]["unexpected_cpu_fallbacks"] == 0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError("GPU S5 artifact audit failed: " + ", ".join(failures))
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
