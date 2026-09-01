"""Fail-closed dual-A100 execution for the existing GPU-backed VQE objective.

The scientific kernel is intentionally not reimplemented here.  Each Slurm
array task calls :mod:`aic_a100_pilot.objective_parity`, which keeps the pinned
BFGS, gradient, Hamiltonian, circuit, acceptance, and resource semantics.  This
module adds only dispatch identity, exclusive artifact publication, and a
deterministic merger.  Wall time is recorded as operational metadata and is
never a GO/No-Go criterion.
"""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Mapping, Sequence

from v5_matched_work.atomic_artifacts import write_json_exclusive

from .common import A100PilotError, digest, embedded_digest_valid, load_json, sha256_file
from .gpu_terminal_certification import run_case


CASES = ("h2", "h6", "beh2")
STATUS_GO = "GO_DUAL_A100_SCIENTIFIC_EXECUTION_V4"
STATUS_NO_GO = "NO_GO_DUAL_A100_EXECUTION_V4"
CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "artifacts/aic-a100-dual-optimizer-v1/preexecution/contract-v4.json"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _single_token(name: str) -> str:
    values = [value.strip() for value in os.environ.get(name, "").split(",") if value.strip()]
    if len(values) != 1:
        raise A100PilotError(f"{name} must identify exactly one GPU, observed={values!r}")
    return values[0]


def _select_allocated_gpu(
    rows: Sequence[Mapping[str, str]], allocated: str
) -> tuple[Mapping[str, str], str]:
    """Resolve Slurm physical identity under either host or cgroup indexing.

    Some Slurm configurations expose only the allocated device to
    ``nvidia-smi`` and renumber it to zero while ``SLURM_JOB_GPUS`` retains the
    host-physical index.  A single management-visible row is therefore already
    an unambiguous binding.  If multiple rows are visible, exact index/UUID
    matching remains mandatory.
    """

    if len(rows) == 1:
        return rows[0], "SINGLE_CGROUP_VISIBLE_GPU"
    matches = [
        row for row in rows if row["index"] == allocated or row["uuid"] == allocated
    ]
    if len(matches) != 1:
        raise A100PilotError(
            "SLURM_JOB_GPUS did not resolve to exactly one management GPU: "
            f"allocated={allocated!r}, rows={len(rows)}, matches={len(matches)}"
        )
    return matches[0], "EXACT_HOST_INDEX_OR_UUID"


def allocated_gpu_observation() -> dict[str, Any]:
    """Return a privacy-preserving identity for the one Slurm-allocated GPU."""

    visible = _single_token("CUDA_VISIBLE_DEVICES")
    allocated = _single_token("SLURM_JOB_GPUS")
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    rows: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 5:
            raise A100PilotError("nvidia-smi GPU inventory is malformed")
        rows.append(
            {
                "index": fields[0],
                "uuid": fields[1],
                "model": fields[2],
                "driver_version": fields[3],
                "memory_total_mib": fields[4],
            }
        )
    driver = ctypes.CDLL("libcuda.so.1")
    if int(driver.cuInit(0)) != 0:
        raise A100PilotError("CUDA driver initialization failed")
    count = ctypes.c_int()
    if int(driver.cuDeviceGetCount(ctypes.byref(count))) != 0 or count.value != 1:
        raise A100PilotError(
            f"CUDA execution boundary must expose exactly one GPU: {count.value}"
        )
    device = ctypes.c_int()
    if int(driver.cuDeviceGet(ctypes.byref(device), 0)) != 0:
        raise A100PilotError("CUDA logical device zero is unavailable")
    name_buffer = ctypes.create_string_buffer(256)
    if int(driver.cuDeviceGetName(name_buffer, len(name_buffer), device)) != 0:
        raise A100PilotError("CUDA device name query failed")
    model = name_buffer.value.decode("utf-8", errors="strict")
    if "A100" not in model.upper():
        raise A100PilotError(f"CUDA execution device is not an A100: {model!r}")
    uuid_buffer = (ctypes.c_ubyte * 16)()
    uuid_function = getattr(driver, "cuDeviceGetUuid_v2", None) or getattr(
        driver, "cuDeviceGetUuid", None
    )
    if uuid_function is None or int(uuid_function(ctypes.byref(uuid_buffer), device)) != 0:
        raise A100PilotError("CUDA device UUID query failed")
    management_models = sorted({row["model"] for row in rows})
    management_drivers = sorted({row["driver_version"] for row in rows})
    if any("A100" not in value.upper() for value in management_models):
        raise A100PilotError("nvidia-smi management inventory contains a non-A100")
    return {
        "model": model,
        "management_driver_versions": management_drivers,
        "gpu_uuid_sha256": hashlib.sha256(bytes(uuid_buffer)).hexdigest(),
        "CUDA_VISIBLE_DEVICES_count": 1,
        "SLURM_JOB_GPUS_count": 1,
        "cuda_driver_visible_device_count": count.value,
        "identity_resolution_mode": "CUDA_DRIVER_LOGICAL_DEVICE_UUID",
        "nvidia_smi_visible_gpu_count": len(rows),
        "CUDA_VISIBLE_DEVICES_token_sha256": hashlib.sha256(visible.encode("utf-8")).hexdigest(),
    }


def _load_contract() -> dict[str, Any]:
    contract = load_json(CONTRACT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise A100PilotError("dual-A100 contract digest is invalid")
    if tuple(contract.get("cases", ())) != CASES:
        raise A100PilotError("dual-A100 contract case order differs")
    if contract.get("speed_is_a_go_no_go_criterion") is not False:
        raise A100PilotError("speed must be excluded from the dual-A100 decision")
    source = Path(__file__).resolve()
    if contract.get("source_sha256") != sha256_file(source):
        raise A100PilotError("dual-A100 executor source differs from frozen contract")
    certificate_source = source.with_name("gpu_terminal_certification.py")
    if contract.get("terminal_certification_source_sha256") != sha256_file(
        certificate_source
    ):
        raise A100PilotError("terminal CPU certificate source differs from contract")
    return contract


def _task_identity(alias: str) -> tuple[int, int, str]:
    try:
        task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
        task_count = int(os.environ["SLURM_ARRAY_TASK_COUNT"])
    except (KeyError, ValueError) as error:
        raise A100PilotError("valid Slurm array identity is required") from error
    if task_count != len(CASES) or not 0 <= task_id < len(CASES):
        raise A100PilotError("Slurm array cardinality differs from frozen contract")
    expected = CASES[task_id]
    if alias != expected:
        raise A100PilotError(f"task/case mapping differs: task={task_id}, alias={alias!r}")
    job_id = os.environ.get("SLURM_ARRAY_JOB_ID") or os.environ.get("SLURM_JOB_ID")
    if not job_id:
        raise A100PilotError("Slurm job identity is absent")
    return task_id, task_count, str(job_id)


def execute_task(alias: str, output_root: Path) -> dict[str, Any]:
    contract = _load_contract()
    task_id, task_count, array_job_id = _task_identity(alias)
    shard = output_root / "shards" / f"{task_id:04d}-{alias}"
    start_path = shard / "start.json"
    result_path = shard / "scientific-result.json"
    terminal_path = shard / "terminal.json"
    if any(path.exists() for path in (start_path, result_path, terminal_path)):
        raise FileExistsError(f"immutable shard already exists: {shard}")

    gpu = allocated_gpu_observation()
    started_ns = time.time_ns()
    start = {
        "schema": "aic-a100-dual-optimizer.task-start.v4",
        "alias": alias,
        "task_id": task_id,
        "task_count": task_count,
        "array_job_id": array_job_id,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "node": os.environ.get("SLURMD_NODENAME"),
        "started_utc": _utc_now(),
        "started_unix_ns": started_ns,
        "gpu": gpu,
        "contract_digest": contract["contract_digest"],
        "scientific_boundary": {
            "engineering_fixture_only": True,
            "FCI_evaluations_authorized": False,
            "performance_claim_authorized": False,
            "speed_claim_authorized": False,
        },
    }
    start["record_digest"] = digest(start)
    write_json_exclusive(start_path, start)

    try:
        scientific = run_case(alias)
        scientific["dual_dispatch_note"] = (
            "GPU-backed optimization with terminal-only CPU certification; no VQE semantics changed."
        )
        scientific["record_digest"] = digest(
            {key: value for key, value in scientific.items() if key != "record_digest"}
        )
        write_json_exclusive(result_path, scientific)
        result_sha = sha256_file(result_path)
        status = "PASS" if scientific.get("status") == "PASS" else "FAIL"
        failure_type = None if status == "PASS" else "SCIENTIFIC_CERTIFICATION_FAILED"
    except Exception as error:
        scientific = None
        result_sha = None
        status = "FAIL"
        failure_type = f"{type(error).__name__}: {error}"

    ended_ns = time.time_ns()
    terminal = {
        "schema": "aic-a100-dual-optimizer.task-terminal.v4",
        "status": status,
        "failure_type": failure_type,
        "alias": alias,
        "task_id": task_id,
        "task_count": task_count,
        "array_job_id": array_job_id,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "node": os.environ.get("SLURMD_NODENAME"),
        "started_unix_ns": started_ns,
        "ended_unix_ns": ended_ns,
        "ended_utc": _utc_now(),
        "elapsed_seconds_informational_only": (ended_ns - started_ns) / 1e9,
        "speed_used_for_decision": False,
        "gpu": gpu,
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
        raise A100PilotError(f"dual-A100 task failed closed: {failure_type}")
    return terminal


def intervals_overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return max(int(left["started_unix_ns"]), int(right["started_unix_ns"])) < min(
        int(left["ended_unix_ns"]), int(right["ended_unix_ns"])
    )


def merge_shards(output_root: Path) -> dict[str, Any]:
    contract = _load_contract()
    terminals: list[dict[str, Any]] = []
    scientific_results: list[dict[str, Any]] = []
    for task_id, alias in enumerate(CASES):
        shard = output_root / "shards" / f"{task_id:04d}-{alias}"
        terminal_path = shard / "terminal.json"
        result_path = shard / "scientific-result.json"
        if not terminal_path.is_file() or not result_path.is_file():
            raise A100PilotError(f"incomplete shard: {shard}")
        terminal = load_json(terminal_path)
        scientific = load_json(result_path)
        if not embedded_digest_valid(terminal, "record_digest"):
            raise A100PilotError(f"terminal digest invalid: {alias}")
        if not embedded_digest_valid(scientific, "record_digest"):
            raise A100PilotError(f"scientific digest invalid: {alias}")
        if terminal.get("scientific_result_sha256") != sha256_file(result_path):
            raise A100PilotError(f"scientific file binding invalid: {alias}")
        terminals.append(terminal)
        scientific_results.append(scientific)

    overlap_pairs = [
        {
            "aliases": [left["alias"], right["alias"]],
            "distinct_gpu_uuid_digests": left["gpu"]["gpu_uuid_sha256"]
            != right["gpu"]["gpu_uuid_sha256"],
        }
        for index, left in enumerate(terminals)
        for right in terminals[index + 1 :]
        if intervals_overlap(left, right)
    ]
    checks = {
        "exact_case_order": [value["alias"] for value in terminals] == list(CASES),
        "all_tasks_passed": all(value["status"] == "PASS" for value in terminals),
        "all_scientific_certifications_passed": all(
            value["status"] == "PASS" for value in scientific_results
        ),
        "no_cpu_fallback": all(
            int(value["route_counters"]["gpu"]["N_cpu_fallback"]) == 0
            for value in scientific_results
        ),
        "gpu_objective_invoked": all(
            bool(value["checks"]["GPU_objective_was_invoked"])
            for value in scientific_results
        ),
        "cpu_certified_terminal_decisions": all(
            bool(value["checks"]["cpu_gpu_terminal_decision"])
            and bool(value["checks"]["resources_exact"])
            for value in scientific_results
        ),
        "at_least_two_tasks_overlapped_on_distinct_gpus": any(
            value["distinct_gpu_uuid_digests"] for value in overlap_pairs
        ),
        "unique_task_ids": len({value["task_id"] for value in terminals}) == len(CASES),
        "one_gpu_visible_per_task": all(
            value["gpu"]["CUDA_VISIBLE_DEVICES_count"] == 1
            and value["gpu"]["SLURM_JOB_GPUS_count"] == 1
            for value in terminals
        ),
        "speed_excluded_from_decision": all(
            value["speed_used_for_decision"] is False for value in terminals
        ),
    }
    status = STATUS_GO if all(checks.values()) else STATUS_NO_GO
    report = {
        "schema": "aic-a100-dual-optimizer.merged-decision.v4",
        "status": status,
        "checks": checks,
        "overlap_pairs": overlap_pairs,
        "case_terminal_record_digests": {
            value["alias"]: value["record_digest"] for value in terminals
        },
        "case_scientific_record_digests": {
            value["alias"]: value["record_digest"] for value in scientific_results
        },
        "contract_digest": contract["contract_digest"],
        "scientific_boundary": {
            "engineering_fixture_only": True,
            "FCI_evaluations": 0,
            "performance_claim": "NOT_AUTHORIZED",
            "CPU_speed_comparison": "NOT_REQUIRED_AND_NOT_USED",
            "CEO_MESC_phase_I": "NOT_STARTED",
        },
    }
    report["record_digest"] = digest(report)
    return report


def _write_merge(output_root: Path, output: Path) -> None:
    report = merge_shards(output_root)
    write_json_exclusive(output, report)
    print(json.dumps(report, sort_keys=True))
    if report["status"] != STATUS_GO:
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--case", choices=CASES, required=True)
    run_parser.add_argument("--output-root", type=Path, required=True)
    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--output-root", type=Path, required=True)
    merge_parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "run":
        result = execute_task(arguments.case, arguments.output_root)
        print(json.dumps(result, sort_keys=True))
    else:
        _write_merge(arguments.output_root, arguments.output)


if __name__ == "__main__":
    main()
