"""Additive BeH2 successor for the dual-A100 v4 time-cap No-Go.

Only the scheduler envelope changes.  The molecular fixture, GPU objective,
optimizer, gradient, terminal CPU certificate, resource recount, and all
scientific claim boundaries are inherited unchanged from v4.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from v5_matched_work.atomic_artifacts import write_json_exclusive

from .common import A100PilotError, digest, embedded_digest_valid, load_json, sha256_file
from .dual_optimizer_execution import allocated_gpu_observation, intervals_overlap
from .gpu_terminal_certification import run_case


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = (
    ROOT
    / "artifacts/aic-a100-dual-optimizer-v1/preexecution/beh2-successor-contract-v1.json"
)
V4_CONTRACT = ROOT / "artifacts/aic-a100-dual-optimizer-v1/preexecution/contract-v4.json"
INCIDENT = (
    ROOT
    / "artifacts/aic-a100-dual-optimizer-v1/incidents/v4-job-2055-timeout-v1/incident-v1.json"
)
STATUS_GO = "GO_DUAL_A100_SCIENTIFIC_EXECUTION_SUCCESSOR_V1"
STATUS_NO_GO = "NO_GO_DUAL_A100_SCIENTIFIC_EXECUTION_SUCCESSOR_V1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_contract() -> dict[str, Any]:
    contract = load_json(CONTRACT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise A100PilotError("BeH2 successor contract digest is invalid")
    if contract.get("case") != "beh2":
        raise A100PilotError("BeH2 successor must contain exactly one fixed case")
    if contract.get("scheduler_change_only") is not True:
        raise A100PilotError("successor does not declare a scheduler-only change")
    if contract.get("source_sha256") != sha256_file(Path(__file__).resolve()):
        raise A100PilotError("BeH2 successor executor differs from frozen contract")
    dispatch = ROOT / "scripts/aic/a100_beh2_successor.sbatch"
    if contract.get("dispatch_source_sha256") != sha256_file(dispatch):
        raise A100PilotError("BeH2 successor dispatch differs from frozen contract")
    certificate = Path(__file__).with_name("gpu_terminal_certification.py")
    if contract.get("terminal_certification_source_sha256") != sha256_file(certificate):
        raise A100PilotError("terminal certificate source differs from successor contract")
    if contract.get("predecessor_incident_sha256") != sha256_file(INCIDENT):
        raise A100PilotError("predecessor incident differs from successor contract")
    return contract


def _require_scheduler(contract: dict[str, Any]) -> None:
    expected = contract["scheduler"]
    observed = {
        "partition": os.environ.get("A100_SCHEDULER_PARTITION"),
        "time_limit": os.environ.get("A100_SCHEDULER_TIME_LIMIT"),
        "gpu_per_task": int(os.environ.get("A100_SCHEDULER_GPU_PER_TASK", "-1")),
        "cpus_per_task": int(os.environ.get("SLURM_CPUS_PER_TASK", "-1")),
    }
    if observed != {
        "partition": expected["partition"],
        "time_limit": expected["time_limit"],
        "gpu_per_task": expected["gpu_per_task"],
        "cpus_per_task": expected["cpus_per_task"],
    }:
        raise A100PilotError(
            f"scheduler binding differs from frozen successor: {observed!r}"
        )
    if os.environ.get("SLURM_JOB_PARTITION") != expected["partition"]:
        raise A100PilotError("actual Slurm partition differs from frozen successor")
    if os.environ.get("SLURM_ARRAY_TASK_ID") is not None:
        raise A100PilotError("BeH2 successor must be a non-array single task")


def _exact_head() -> str:
    expected = os.environ.get("A100_EXPECTED_HEAD")
    if not expected:
        raise A100PilotError("A100_EXPECTED_HEAD is required")
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    observed = completed.stdout.strip()
    if observed != expected:
        raise A100PilotError("repository HEAD differs from A100_EXPECTED_HEAD")
    return observed


def execute(output_root: Path) -> dict[str, Any]:
    contract = _load_contract()
    _require_scheduler(contract)
    exact_head = _exact_head()
    shard = output_root / "beh2"
    start_path = shard / "start.json"
    result_path = shard / "scientific-result.json"
    terminal_path = shard / "terminal.json"
    if any(path.exists() for path in (start_path, result_path, terminal_path)):
        raise FileExistsError(f"immutable successor shard already exists: {shard}")

    gpu = allocated_gpu_observation()
    started_ns = time.time_ns()
    start = {
        "schema": "aic-a100-beh2-successor.task-start.v1",
        "alias": "beh2",
        "predecessor_array_job_id": "2055",
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "node": os.environ.get("SLURMD_NODENAME"),
        "started_utc": _utc_now(),
        "started_unix_ns": started_ns,
        "exact_repository_head": exact_head,
        "gpu": gpu,
        "scheduler": contract["scheduler"],
        "contract_digest": contract["contract_digest"],
        "scientific_boundary": contract["scientific_boundary"],
    }
    start["record_digest"] = digest(start)
    write_json_exclusive(start_path, start)

    try:
        scientific = run_case("beh2")
        scientific["successor_contract_digest"] = contract["contract_digest"]
        scientific["successor_note"] = (
            "Scheduler-only retry after job 2055 time-cap No-Go; VQE semantics unchanged."
        )
        scientific["record_digest"] = digest(
            {key: value for key, value in scientific.items() if key != "record_digest"}
        )
        write_json_exclusive(result_path, scientific)
        result_sha = sha256_file(result_path)
        status = "PASS" if scientific.get("status") == "PASS" else "FAIL"
        failure_type = None if status == "PASS" else "SCIENTIFIC_CERTIFICATION_FAILED"
    except Exception as error:
        result_sha = None
        status = "FAIL"
        failure_type = f"{type(error).__name__}: {error}"

    ended_ns = time.time_ns()
    terminal = {
        "schema": "aic-a100-beh2-successor.task-terminal.v1",
        "status": status,
        "failure_type": failure_type,
        "alias": "beh2",
        "predecessor_array_job_id": "2055",
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "node": os.environ.get("SLURMD_NODENAME"),
        "started_unix_ns": started_ns,
        "ended_unix_ns": ended_ns,
        "ended_utc": _utc_now(),
        "elapsed_seconds_informational_only": (ended_ns - started_ns) / 1e9,
        "speed_used_for_decision": False,
        "exact_repository_head": exact_head,
        "gpu": gpu,
        "scheduler": contract["scheduler"],
        "contract_digest": contract["contract_digest"],
        "start_sha256": sha256_file(start_path),
        "scientific_result_sha256": result_sha,
        "scientific_result_relative_path": (
            result_path.relative_to(output_root).as_posix() if result_sha else None
        ),
    }
    terminal["record_digest"] = digest(terminal)
    write_json_exclusive(terminal_path, terminal)
    if status != "PASS":
        raise A100PilotError(f"BeH2 successor failed closed: {failure_type}")
    return terminal


def _load_bound_pair(shard: Path, expected_contract: str) -> tuple[dict, dict]:
    terminal_path = shard / "terminal.json"
    scientific_path = shard / "scientific-result.json"
    if not terminal_path.is_file() or not scientific_path.is_file():
        raise A100PilotError(f"incomplete terminal/scientific pair: {shard}")
    terminal = load_json(terminal_path)
    scientific = load_json(scientific_path)
    if not embedded_digest_valid(terminal, "record_digest"):
        raise A100PilotError(f"invalid terminal digest: {shard}")
    if not embedded_digest_valid(scientific, "record_digest"):
        raise A100PilotError(f"invalid scientific digest: {shard}")
    if terminal.get("contract_digest") != expected_contract:
        raise A100PilotError(f"wrong contract binding: {shard}")
    if terminal.get("scientific_result_sha256") != sha256_file(scientific_path):
        raise A100PilotError(f"scientific file binding differs: {shard}")
    return terminal, scientific


def merge(predecessor_root: Path, successor_root: Path) -> dict[str, Any]:
    successor_contract = _load_contract()
    v4_contract = load_json(V4_CONTRACT)
    incident = load_json(INCIDENT)
    if not embedded_digest_valid(v4_contract, "contract_digest"):
        raise A100PilotError("v4 contract digest invalid")
    if incident.get("status") != "NO_GO_DUAL_A100_BEH2_TIME_CAP_V1":
        raise A100PilotError("wrong predecessor incident status")

    h2_terminal, h2_scientific = _load_bound_pair(
        predecessor_root / "shards/0000-h2", v4_contract["contract_digest"]
    )
    h6_terminal, h6_scientific = _load_bound_pair(
        predecessor_root / "shards/0001-h6", v4_contract["contract_digest"]
    )
    beh2_terminal, beh2_scientific = _load_bound_pair(
        successor_root / "beh2", successor_contract["contract_digest"]
    )
    terminals = [h2_terminal, h6_terminal, beh2_terminal]
    scientific = [h2_scientific, h6_scientific, beh2_scientific]
    checks = {
        "predecessor_is_formal_time_cap_no_go": True,
        "h2_h6_overlap_on_distinct_a100s": intervals_overlap(
            h2_terminal, h6_terminal
        )
        and h2_terminal["gpu"]["gpu_uuid_sha256"]
        != h6_terminal["gpu"]["gpu_uuid_sha256"],
        "all_three_terminal_certificates_passed": all(
            item.get("status") == "PASS" for item in terminals
        ),
        "all_three_scientific_certificates_passed": all(
            item.get("status") == "PASS" and all(item["checks"].values())
            for item in scientific
        ),
        "no_cpu_fallback": all(
            item["route_counters"]["gpu"]["N_cpu_fallback"] == 0
            for item in scientific
        ),
        "gpu_objective_invoked": all(
            item["checks"]["GPU_objective_was_invoked"] for item in scientific
        ),
        "no_full_cpu_optimization": all(
            item["checks"]["no_full_cpu_optimization"] for item in scientific
        ),
        "one_gpu_visible_per_task": all(
            item["gpu"]["CUDA_VISIBLE_DEVICES_count"] == 1
            and item["gpu"]["SLURM_JOB_GPUS_count"] == 1
            for item in terminals
        ),
        "successor_scheduler_exact": beh2_terminal["scheduler"]
        == successor_contract["scheduler"],
        "speed_excluded_from_decision": all(
            item["speed_used_for_decision"] is False for item in terminals
        ),
    }
    status = STATUS_GO if all(checks.values()) else STATUS_NO_GO
    report = {
        "schema": "aic-a100-beh2-successor.merged-decision.v1",
        "status": status,
        "checks": checks,
        "predecessor_contract_digest": v4_contract["contract_digest"],
        "successor_contract_digest": successor_contract["contract_digest"],
        "case_terminal_record_digests": {
            item["alias"]: item["record_digest"] for item in terminals
        },
        "case_scientific_record_digests": {
            item["alias"]: item["record_digest"] for item in scientific
        },
        "scientific_boundary": {
            "engineering_qualification_only": True,
            "FCI_evaluations": 0,
            "performance_claim": "NOT_AUTHORIZED",
            "CPU_speed_comparison": "NOT_REQUIRED_AND_NOT_USED",
            "CEO_MESC_phase_I": "NOT_STARTED",
        },
    }
    report["record_digest"] = digest(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--output-root", type=Path, required=True)
    merge_parser = commands.add_parser("merge")
    merge_parser.add_argument("--predecessor-root", type=Path, required=True)
    merge_parser.add_argument("--successor-root", type=Path, required=True)
    merge_parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "run":
        print(json.dumps(execute(arguments.output_root), sort_keys=True))
        return
    report = merge(arguments.predecessor_root, arguments.successor_root)
    write_json_exclusive(arguments.output, report)
    print(json.dumps(report, sort_keys=True))
    if report["status"] != STATUS_GO:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
