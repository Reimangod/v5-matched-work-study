"""Sanitized AIC preflight evidence and fail-closed P1 publication."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .common import ARTIFACT_ROOT, embedded_digest_valid, load_json, publish
from .p0_baseline import PROTOCOL, REFERENCE


P1 = ARTIFACT_ROOT / "p1-aic-preflight"
PREFLIGHT = P1 / "aic-preflight-operational-no-go-v1.json"
PREFLIGHT_RECOVERY = P1 / "aic-preflight-recovery-v2.json"


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


def preflight_recovery_body() -> dict[str, Any]:
    """Record an additive successor after diagnosing the original P1 No-Go.

    The original No-Go remains valid for its observation window.  This record
    does not rewrite it; it binds the old evidence and documents the later,
    reproducible allocation route on the active ``gpu-standard`` partition.
    """

    protocol = load_json(PROTOCOL)
    reference = load_json(REFERENCE)
    prior = load_json(PREFLIGHT)
    if not embedded_digest_valid(protocol, "protocol_digest"):
        raise RuntimeError("P0 protocol digest is invalid")
    if not embedded_digest_valid(reference, "reference_digest"):
        raise RuntimeError("P0 reference digest is invalid")
    if not embedded_digest_valid(prior, "preflight_digest"):
        raise RuntimeError("P1 v1 preflight digest is invalid")
    if prior["status"] != "NO_GO_A100_OPERATIONAL_INSTABILITY":
        raise RuntimeError("P1 v1 is not the expected operational No-Go")
    return {
        "schema": "aic-a100-pilot.p1-preflight-recovery.v2",
        "status": "GO_P2_PINNED_GPU_ENVIRONMENT",
        "phase": "P1_AIC_PREFLIGHT_ADDITIVE_RECOVERY",
        "observation_date_jst": "2026-08-30",
        "supersedes_without_mutation": {
            "path": PREFLIGHT.relative_to(ARTIFACT_ROOT.parent.parent).as_posix(),
            "preflight_digest": prior["preflight_digest"],
            "historical_no_go_remains_valid_for_original_window": True,
        },
        "evidence_binding": {
            "P0_protocol_digest": protocol["protocol_digest"],
            "P0_reference_digest": reference["reference_digest"],
        },
        "diagnosis": {
            "root_cause_class": "CROSS_PARTITION_SCHEDULING_WITHOUT_BACKFILL_ON_SHARED_DGX",
            "evidence": [
                "A CPU-only gpu-short probe remained pending while gpu-standard was active.",
                "A CPU-only gpu-standard probe started and completed immediately.",
                "A one-GPU gpu-standard probe then started and completed immediately.",
            ],
            "interpretation_boundary": (
                "This is an empirical diagnosis of the audited cluster state, not a "
                "general claim about Slurm or future AIC scheduling policy."
            ),
        },
        "scheduler_evidence": {
            "association_qos": "normal",
            "qos_max_gpu_per_user": 2,
            "requested_gpu_count": 1,
            "jobs": [
                {"id": 1954, "partition": "gpu-short", "gpu": 0, "state": "CANCELLED_BEFORE_START"},
                {"id": 1955, "partition": "gpu-standard", "gpu": 0, "state": "COMPLETED"},
                {"id": 1956, "partition": "gpu-standard", "gpu": 1, "state": "COMPLETED"},
                {"id": 1957, "partition": "gpu-standard", "gpu": 1, "state": "COMPLETED"},
            ],
            "active_user_jobs_after_probe": 0,
        },
        "allocated_device": {
            "node_class": "dgx-a100",
            "model": "NVIDIA A100-SXM4-80GB",
            "driver_version": "570.195.03",
            "nvidia_smi_cuda_version": "12.8",
            "slurm_alloc_tres_gpu": 1,
            "CUDA_VISIBLE_DEVICES_count": 1,
            "cuda_driver_device_count": 1,
            "nvidia_smi_management_visible_count": 3,
            "scope_explanation": (
                "nvidia-smi exposed node-management devices, whereas the CUDA driver "
                "inside the cgroup exposed exactly the single allocated device."
            ),
        },
        "transport": {
            "username_persisted_in_repository_artifact": False,
            "private_key_material_persisted": False,
            "credential_material_persisted": False,
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
        "successor_authorization": {
            "P2_GPU_ENVIRONMENT_AND_SMOKE": "AUTHORIZED",
            "P3_SCIENTIFIC_PARITY": "NOT_AUTHORIZED_PENDING_P2",
            "P4_SAME_NODE_BENCHMARK": "NOT_AUTHORIZED_PENDING_P3",
            "P5_LIMITED_SCIENTIFIC_PILOT": "NOT_AUTHORIZED_PENDING_P4",
        },
        "scientific_boundaries": {
            "candidate_molecular_energy_evaluations": 0,
            "optimizer_runs": 0,
            "FCI_evaluations": 0,
            "performance_claim_authorized": False,
        },
    }


def publish_preflight_recovery() -> dict[str, Any]:
    return publish(PREFLIGHT_RECOVERY, preflight_recovery_body(), "recovery_digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish-operational-no-go", action="store_true")
    parser.add_argument("--publish-recovery-v2", action="store_true")
    arguments = parser.parse_args()
    if arguments.publish_operational_no_go == arguments.publish_recovery_v2:
        raise RuntimeError("select exactly one publication action")
    value = (
        publish_operational_no_go()
        if arguments.publish_operational_no_go
        else publish_preflight_recovery()
    )
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
