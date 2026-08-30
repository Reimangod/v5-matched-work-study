"""Content-addressed P2 A100/Aer smoke evidence."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .common import ARTIFACT_ROOT, digest, embedded_digest_valid, load_json, publish
from .environment import PREFLIGHT_RECOVERY


P2 = ARTIFACT_ROOT / "p2-gpu-smoke"
SMOKE = P2 / "aer-gpu-smoke-v1.json"

PINNED_GPU_PACKAGES = [
    "cudensitymat-cu11==0.2.0",
    "cuquantum-cu11==25.6.0",
    "custatevec-cu11==1.9.0",
    "cutensor-cu11==2.2.0",
    "cutensornet-cu11==2.8.0",
    "numpy==1.23.5",
    "nvidia-cublas-cu11==11.11.3.6",
    "nvidia-cuda-runtime-cu11==11.8.89",
    "nvidia-cusolver-cu11==11.4.1.48",
    "nvidia-cusparse-cu11==11.7.5.86",
    "qiskit-aer-gpu-cu11==0.12.2",
    "qiskit-terra==0.24.2",
    "scipy==1.10.1",
]


def smoke_body() -> dict[str, Any]:
    recovery = load_json(PREFLIGHT_RECOVERY)
    if not embedded_digest_valid(recovery, "recovery_digest"):
        raise RuntimeError("P1 recovery digest is invalid")
    if recovery["status"] != "GO_P2_PINNED_GPU_ENVIRONMENT":
        raise RuntimeError("P1 recovery does not authorize P2")
    return {
        "schema": "aic-a100-pilot.p2-gpu-smoke.v1",
        "status": "GO_P3_SCIENTIFIC_PARITY",
        "phase": "P2_GPU_ENVIRONMENT_AND_SMOKE",
        "P1_recovery_digest": recovery["recovery_digest"],
        "environment": {
            "python": "3.10.19",
            "qiskit_terra": "0.24.2",
            "qiskit_aer_gpu_cu11": "0.12.2",
            "numpy": "1.23.5",
            "scipy": "1.10.1",
            "package_subset": PINNED_GPU_PACKAGES,
            "package_subset_digest": digest(PINNED_GPU_PACKAGES),
            "cuda_runtime_family": "CUDA 11.8 wheels on driver 570.195.03",
            "rejected_resolution": (
                "qiskit-aer-gpu==0.12.2 resolved CUDA 12.9 dependencies, newer "
                "than the driver-reported CUDA 12.8 capability."
            ),
            "library_discovery_policy": (
                "LD_LIBRARY_PATH is generated at job runtime from sorted pip NVIDIA "
                "site-packages */lib directories; no credential or username is stored."
            ),
        },
        "slurm": {
            "job_id": 1958,
            "partition": "gpu-standard",
            "requested_gpu_count": 1,
            "terminal_state": "COMPLETED",
            "active_user_jobs_after_completion": 0,
        },
        "device": {
            "model": "NVIDIA A100-SXM4-80GB",
            "CUDA_VISIBLE_DEVICES_count": 1,
            "cuda_driver_device_count": 1,
            "aer_available_devices": ["CPU", "GPU"],
        },
        "smoke": {
            "backend_configuration": {
                "method": "statevector",
                "device": "GPU",
                "precision": "double",
            },
            "four_qubit_GHZ_experiment_metadata_device": "GPU",
            "four_qubit_GHZ_experiment_metadata_method": "statevector",
            "four_qubit_state_max_abs_error": 1.1102230246251565e-16,
            "twenty_four_qubit_load_probe_seconds": 0.3718,
            "process_observed_by_nvidia_smi": True,
            "maximum_observed_process_memory_mib": 674,
        },
        "route_counters": {
            "N_gpu_statevector": 2,
            "N_gpu_energy": 0,
            "N_gpu_gradient_component": 0,
            "N_cpu_statevector": 0,
            "N_cpu_energy": 0,
            "N_cpu_gradient_component": 0,
            "N_cpu_fallback": 0,
        },
        "scientific_boundaries": {
            "molecular_case_executed": False,
            "candidate_molecular_energy_evaluations": 0,
            "optimizer_runs": 0,
            "FCI_evaluations": 0,
            "numerical_parity_claim_authorized": False,
            "speedup_claim_authorized": False,
            "performance_claim_authorized": False,
        },
        "successor_authorization": {
            "P3_SCIENTIFIC_PARITY": "AUTHORIZED_IN_FROZEN_CASE_ORDER",
            "P4_SAME_NODE_BENCHMARK": "NOT_AUTHORIZED_PENDING_P3",
            "P5_LIMITED_SCIENTIFIC_PILOT": "NOT_AUTHORIZED_PENDING_P4",
        },
    }


def publish_smoke() -> dict[str, Any]:
    return publish(SMOKE, smoke_body(), "smoke_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish:
        raise RuntimeError("select --publish")
    print(json.dumps(publish_smoke(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
