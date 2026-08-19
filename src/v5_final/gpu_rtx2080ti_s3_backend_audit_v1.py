"""S3 outcome-free audit of GPU acceleration boundaries in the frozen kernel."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .gpu_rtx2080ti_s2_environment_freeze_v1 import OUTPUT as S2_OUTPUT


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/v5-final/gpu-rtx2080ti/s3-backend-audit-v1/backend-audit-v1.json"
EXPECTED_S2_DIGEST = "a9bb8bdcd67c8e9eda19f3b3e153935d50045a619f4c195fdca615e8801ad8dd"
EXPECTED_SOURCE_SHA256 = {
    "src/v5_final/parent_native_execution_services.py": "a8d7a865b2803f3a9026314820f8eb863672c3293a805b5a16123135b7edc5e0",
    "src/v5_final/verifier_v2.py": "5ff876091c4ed2145be18ad514429c3540be9e6ba79e22735a87b0b21e271659",
    "src/v5_final/s11_v2_execution_runner_v1.py": "7df8fa7fddf0004c405dace9899ac03a24be9429f4c7d695deb124ccf4826aca",
    "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe/adaptvqe/algorithms/adapt_vqe.py": "a30168bdf8f35181d6424dd40260b2a4421d6e6deeb781f726d3bdc1b89a2933",
    "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe/adaptvqe/pools.py": "76ee7bf37eaa0c0e6d2af0d8cb54831c860b35eb4a26189a2e53b421d26df2e7",
    "provenance/dvg-obs-ceo/src/dvg_obs_ceo/resources.py": "4220cc44fde4a264f793e1190ef61e5ef8c93497d3614d13cd96763f9db98efd",
    "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe/adaptvqe/minimize.py": "59f32bc22d2d7a9c1826a6280970bcfcc3beaebeb6cbd317d8cd1ba0e8ef462c",
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_without(record: dict[str, Any], field: str) -> str:
    value = dict(record)
    value.pop(field, None)
    return _sha256(canonical_json_bytes(value))


def _capability_probe() -> dict[str, Any]:
    import cupy as cp
    import cupyx.scipy.sparse.linalg as cupy_sparse_linalg
    from qiskit_aer import AerSimulator

    return {
        "cupy_device_count": int(cp.cuda.runtime.getDeviceCount()),
        "cupy_sparse_expm_multiply_available": hasattr(
            cupy_sparse_linalg, "expm_multiply"
        ),
        "qiskit_aer_devices": list(AerSimulator().available_devices()),
        "qiskit_aer_methods": list(AerSimulator().available_methods()),
    }


def _static_contract_checks() -> dict[str, bool]:
    execution = (ROOT / "src/v5_final/parent_native_execution_services.py").read_text()
    verifier = (ROOT / "src/v5_final/verifier_v2.py").read_text()
    adapt = (
        ROOT
        / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe/adaptvqe/algorithms/adapt_vqe.py"
    ).read_text()
    pools = (
        ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe/adaptvqe/pools.py"
    ).read_text()
    resources = (ROOT / "provenance/dvg-obs-ceo/src/dvg_obs_ceo/resources.py").read_text()
    return {
        "energy_calls_frozen_algorithm": "self.algorithm.evaluate_energy" in execution,
        "gradient_calls_frozen_algorithm": "self.algorithm.estimate_gradients" in execution,
        "bfgs_is_pinned_cpu_control": "from adaptvqe.minimize import minimize_bfgs" in execution,
        "independent_statevector_uses_qiskit": "from qiskit.quantum_info import Statevector" in execution,
        "resource_count_uses_paper_backend": "paper_era_backend()" in execution
        and "evaluate_full_circuit_resources" in resources,
        "verifier_uses_scipy_sparse_expm": "from scipy.sparse.linalg import expm_multiply" in verifier,
        "verifier_forbids_dense_expm": 'counts["N_dense_expm"] != 0' in verifier,
        "ceo_compute_state_uses_pool_expm_mult": "self.pool.expm_mult(coefficient, index, state)" in adapt,
        "pool_expm_mult_uses_scipy": "return expm_multiply(coefficient * self.get_imp_op(index), other)" in pools,
        "analytic_gradient_reuses_compute_state": "state = self.compute_state(coefficients, indices)" in adapt,
    }


def build(*, capability_probe: Callable[[], dict[str, Any]] = _capability_probe) -> dict[str, Any]:
    s2 = json.loads(S2_OUTPUT.read_text(encoding="utf-8"))
    source_sha256 = {
        path: _sha256((ROOT / path).read_bytes()) for path in EXPECTED_SOURCE_SHA256
    }
    static_checks = _static_contract_checks()
    capabilities = capability_probe()
    backend_map = [
        {
            "component": "candidate catalog, OBS ranking, semantic dedup",
            "frozen_owner": "CPU",
            "gpu_change_allowed_in_s5": False,
            "reason": "scientific selection semantics; not the dominant linear algebra kernel",
        },
        {
            "component": "Verifier V2 symbolic sparse checks and expm_multiply probes",
            "frozen_owner": "CPU_SCIpy_REFERENCE",
            "gpu_change_allowed_in_s5": "ONLY_AS_SEPARATE_PARITY_GATED_BACKEND",
            "reason": "CuPy 13.6 has no sparse expm_multiply; custom Krylov changes numerical implementation",
        },
        {
            "component": "CEO compute_state, energy, analytic gradient state evolution",
            "frozen_owner": "CPU_SCIpy_REFERENCE",
            "gpu_change_allowed_in_s5": "PRIMARY_CANDIDATE",
            "reason": "repeated sparse exponential action and Hamiltonian products dominate outcome kernels",
        },
        {
            "component": "pinned BFGS control, convergence, nfev/njev accounting",
            "frozen_owner": "CPU",
            "gpu_change_allowed_in_s5": False,
            "reason": "must preserve optimizer trajectory and durable componentwise counters",
        },
        {
            "component": "Qiskit independent statevector certification",
            "frozen_owner": "CPU_QISKIT_REFERENCE",
            "gpu_change_allowed_in_s5": False,
            "reason": "independent implementation is a certificate, not the production accelerator",
        },
        {
            "component": "paper-era Qiskit CNOT/depth/resource recount",
            "frozen_owner": "CPU_QISKIT",
            "gpu_change_allowed_in_s5": False,
            "reason": "changing compilation changes the registered physical-resource metric",
        },
        {
            "component": "append-only ledger, cap gate, rollback, digests",
            "frozen_owner": "CPU",
            "gpu_change_allowed_in_s5": False,
            "reason": "systems-safety control plane must remain independent of CUDA kernels",
        },
    ]
    candidate_backends = [
        {
            "backend": "current-qiskit-aer-gpu",
            "status": "UNAVAILABLE_UNDER_FROZEN_QISKIT_ENVIRONMENT",
            "evidence": capabilities["qiskit_aer_devices"],
        },
        {
            "backend": "direct-cupy-sparse-expm-multiply",
            "status": "UNAVAILABLE",
            "evidence": capabilities["cupy_sparse_expm_multiply_available"],
        },
        {
            "backend": "hybrid-cupy-custom-sparse-action",
            "status": "DESIGN_CANDIDATE_NOT_IMPLEMENTED",
            "required_gates": [
                "same-host CPU reference",
                "primitive numerical parity",
                "determinism",
                "zero unexpected CPU fallback",
                "componentwise work-counter parity",
            ],
        },
        {
            "backend": "newer-qiskit-aer-or-cuquantum-stack",
            "status": "NOT_SELECTED",
            "reason": "would alter the frozen Python/Qiskit dependency semantics before parity evidence",
        },
    ]
    checks = {
        "s2_go_and_digest_bound": s2.get("decision")
        == "GO_RTX2080TI_S3_BACKEND_AUDIT_ONLY"
        and s2.get("environment_freeze_digest") == EXPECTED_S2_DIGEST,
        "source_files_exact": source_sha256 == EXPECTED_SOURCE_SHA256,
        "static_contracts_all_found": all(static_checks.values()),
        "cuda_device_visible": capabilities["cupy_device_count"] == 1,
        "aer_gpu_not_silently_assumed": "GPU" not in capabilities["qiskit_aer_devices"],
        "cupy_sparse_expm_not_silently_assumed": capabilities[
            "cupy_sparse_expm_multiply_available"
        ]
        is False,
        "backend_map_complete": len(backend_map) == 7,
    }
    failures = [name for name, passed in checks.items() if not passed]
    decision = "GO_RTX2080TI_S4_SAME_HOST_CPU_REFERENCE_ONLY" if not failures else "NO_GO_RTX2080TI_S3_BACKEND_AUDIT"
    record: dict[str, Any] = {
        "schema": "v5-final.gpu-rtx2080ti.s3-backend-audit.v1",
        "stage": "GPU-S3",
        "status": "COMPLETE",
        "s2_environment_freeze_digest": s2["environment_freeze_digest"],
        "source_sha256": source_sha256,
        "static_contract_checks": static_checks,
        "runtime_capabilities": capabilities,
        "backend_map": backend_map,
        "candidate_backends": candidate_backends,
        "checks": checks,
        "failed_checks": failures,
        "authorization": {
            "s4_same_host_cpu_reference": "AUTHORIZED" if not failures else "NOT_AUTHORIZED",
            "gpu_backend_implementation": "NOT_AUTHORIZED",
            "molecular_candidate_outcomes": "NOT_AUTHORIZED",
            "gpu_90_item_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "decision": decision,
        "claim_boundary": (
            "S3 maps code ownership and feasible backend boundaries only. It provides "
            "no timing, numerical parity, molecular outcome, or speedup evidence."
        ),
    }
    record["backend_audit_digest"] = _digest_without(record, "backend_audit_digest")
    return record


def audit(path: Path = OUTPUT) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "digest_valid": record.get("backend_audit_digest")
        == _digest_without(record, "backend_audit_digest"),
        "decision_consistent": (
            record["decision"] == "GO_RTX2080TI_S4_SAME_HOST_CPU_REFERENCE_ONLY"
        )
        == (not record["failed_checks"]),
        "implementation_not_authorized": record["authorization"]["gpu_backend_implementation"]
        == "NOT_AUTHORIZED",
        "outcomes_not_authorized": record["authorization"]["molecular_candidate_outcomes"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError("GPU S3 artifact audit failed: " + ", ".join(failures))
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
