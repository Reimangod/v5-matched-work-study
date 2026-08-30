"""Sanitized AIC preflight evidence and fail-closed P1 publication."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .common import ARTIFACT_ROOT, embedded_digest_valid, load_json, publish
from .p0_baseline import PROTOCOL, REFERENCE


P1 = ARTIFACT_ROOT / "p1-aic-preflight"
PREFLIGHT = P1 / "aic-preflight-operational-no-go-v1.json"


def operational_no_go_body() -> dict[str, Any]:
    protocol = load_json(PROTOCOL)
    reference = load_json(REFERENCE)
    if not embedded_digest_valid(protocol, "protocol_digest"):
        raise RuntimeError("P0 protocol digest is invalid")
    if not embedded_digest_valid(reference, "reference_digest"):
        raise RuntimeError("P0 reference digest is invalid")
    return {
        "schema": "aic-a100-pilot.p1-preflight.v1",
        "status": "NO_GO_A100_OPERATIONAL_INSTABILITY",
        "phase": "P1_AIC_PREFLIGHT",
        "P0_protocol_digest": protocol["protocol_digest"],
        "P0_reference_digest": reference["reference_digest"],
        "official_manual": {
            "url": "https://docs.keioaic.dev/slurm_user_manual",
            "checked_date_jst": "2026-08-30",
            "manual_gpu_limit_per_user": 2,
            "pilot_gpu_count_per_job": 1,
            "manual_example_gres_gpu_4_rejected_as_non_authoritative": True,
            "actual_scontrol_and_sinfo_used_as_authority": True,
        },
        "transport": {
            "bastion_key_authentication": "PASS",
            "login_node_key_authentication": "PASS",
            "login_host": "nadeko",
            "username_persisted_in_repository_artifact": False,
            "private_key_material_read_or_persisted": False,
            "preexisting_ssh_config": False,
            "transport_remediation": (
                "Used the documented ProxyJump topology with the existing private-key "
                "path; no username or key material was written to repository artifacts."
            ),
        },
        "actual_cluster_state": {
            "login_python": "3.12.3",
            "python_3_10_on_login_path": False,
            "environment_module_command_available": False,
            "compute_node": "dgx-a100",
            "node_state": "MIXED",
            "node_gpu_inventory": "gpu:a100:6",
            "node_gpu_count": 6,
            "node_gpu_allocated_at_audit": 1,
            "node_gpu_apparently_unallocated_at_audit": 5,
            "share_available_bytes": 176442810368,
            "partitions": {
                "gpu-interactive": {
                    "state": "UP",
                    "max_time": "02:00:00",
                    "max_cpus_per_node": 16,
                    "gpu_inventory": "gpu:a100:6",
                },
                "gpu-short": {
                    "state": "UP",
                    "max_time": "01:00:00",
                    "max_cpus_per_node": 8,
                    "gpu_inventory": "gpu:a100:6",
                },
                "gpu-standard": {
                    "state": "UP",
                    "max_time": "1-00:00:00",
                    "max_cpus_per_node": 32,
                    "gpu_inventory": "gpu:a100:6",
                },
                "gpu-strong": {
                    "state": "UP",
                    "max_time": "1-12:00:00",
                    "max_cpus_per_node": 64,
                    "gpu_inventory": "gpu:a100:6",
                },
            },
        },
        "allocation_attempts": [
            {
                "slurm_job_id": 1951,
                "partition": "gpu-interactive",
                "requested_gpus": 1,
                "requested_cpus": 8,
                "requested_memory_mb": 32000,
                "requested_time": "00:10:00",
                "terminal_state": "CANCELLED_BEFORE_ALLOCATION",
                "observed_pending_reason": "Resources",
                "compute_started": False,
                "candidate_outcomes": 0,
            },
            {
                "slurm_job_id": 1952,
                "partition": "gpu-short",
                "requested_gpus": 1,
                "requested_cpus": 1,
                "requested_memory_mb": 2000,
                "requested_time": "00:05:00",
                "terminal_state": "CANCELLED_BEFORE_ALLOCATION",
                "observed_pending_reason": "Resources",
                "compute_started": False,
                "candidate_outcomes": 0,
            },
        ],
        "invalid_qos_probe": {
            "requested_partition": "gpu-interactive",
            "requested_qos": "gpu-interactive-qos",
            "result": "REJECTED_INVALID_QOS_SPECIFICATION",
            "slurm_job_created": False,
        },
        "allocation_diagnosis": {
            "a100_allocation_obtained": False,
            "nvidia_smi_from_allocated_job_obtained": False,
            "cuda_runtime_observed": False,
            "nvidia_driver_observed": False,
            "visible_gpu_count_observed_from_job": False,
            "both_valid_one_gpu_jobs_predicted_after_the_only_running_job_end": True,
            "reason": (
                "The scheduler reported Resources for both gpu-interactive and gpu-short "
                "despite five of six configured A100 GRES appearing unallocated. No "
                "compute job started, so real device access cannot be certified."
            ),
        },
        "cleanup": {
            "job_1951_cancelled": True,
            "job_1952_cancelled": True,
            "SIGKILL_used": False,
            "user_jobs_after_cleanup": 0,
            "stale_job_detected": False,
        },
        "route_counters": {
            "N_gpu_statevector": 0,
            "N_gpu_energy": 0,
            "N_gpu_gradient_component": 0,
            "N_cpu_statevector": 0,
            "N_cpu_energy": 0,
            "N_cpu_gradient_component": 0,
            "N_cpu_fallback": 0,
        },
        "scientific_state": {
            "GPU_package_installed": False,
            "GPU_smoke_executed": False,
            "candidate_molecular_energy_evaluations": 0,
            "FCI_evaluations": 0,
            "parity_claim_authorized": False,
            "speedup_claim_authorized": False,
            "measurement_cost_claim_authorized": False,
        },
        "successor_authorization": {
            "P2_GPU_ENVIRONMENT_AND_SMOKE": "NOT_AUTHORIZED",
            "P3_SCIENTIFIC_PARITY": "NOT_AUTHORIZED",
            "P4_SAME_NODE_BENCHMARK": "NOT_AUTHORIZED",
            "P5_LIMITED_SCIENTIFIC_PILOT": "NOT_AUTHORIZED",
        },
    }


def publish_operational_no_go() -> dict[str, Any]:
    return publish(PREFLIGHT, operational_no_go_body(), "preflight_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish-operational-no-go", action="store_true")
    arguments = parser.parse_args()
    if not arguments.publish_operational_no_go:
        raise RuntimeError("select --publish-operational-no-go")
    print(json.dumps(publish_operational_no_go(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
