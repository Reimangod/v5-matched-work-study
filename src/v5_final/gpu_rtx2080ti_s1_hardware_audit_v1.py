"""S1 RTX 2080 Ti hardware/access audit with no molecular imports or outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Callable

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .gpu_rtx2080ti_s0_scope_freeze_v1 import OUTPUT as S0_OUTPUT


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/v5-final/gpu-rtx2080ti/s1-hardware-audit-v1/hardware-audit-v1.json"
GIB = 1024**3


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_without(record: dict[str, Any], field: str) -> str:
    value = dict(record)
    value.pop(field, None)
    return _sha256(canonical_json_bytes(value))


def _run(arguments: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            arguments,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as error:
        return {
            "arguments": arguments,
            "returncode": 127,
            "stdout": "",
            "stderr": str(error),
        }
    return {
        "arguments": arguments,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _parse_gpu_rows(stdout: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 7:
            continue
        index, uuid, name, memory_mib, driver, compute_cap, mode = fields
        try:
            rows.append(
                {
                    "index": int(index),
                    "uuid": uuid,
                    "name": name,
                    "memory_total_mib": int(memory_mib),
                    "driver_version": driver,
                    "compute_capability": compute_cap,
                    "compute_mode": mode,
                }
            )
        except ValueError:
            continue
    return rows


def _memory_total_bytes() -> int:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * page_size)
    except (AttributeError, OSError, TypeError, ValueError):
        return 0


def capture(*, runner: Callable[[list[str]], dict[str, Any]] = _run) -> dict[str, Any]:
    s0 = json.loads(S0_OUTPUT.read_text(encoding="utf-8"))
    gpu_query = runner(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,memory.total,driver_version,compute_cap,compute_mode",
            "--format=csv,noheader,nounits",
        ]
    )
    compute_apps = runner(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    nvcc = runner(["nvcc", "--version"])
    disk = shutil.disk_usage(ROOT)
    gpu_rows = _parse_gpu_rows(gpu_query["stdout"] if gpu_query["returncode"] == 0 else "")
    active_compute_rows = [
        line for line in compute_apps["stdout"].splitlines() if line.strip()
    ] if compute_apps["returncode"] == 0 else []

    checks = {
        "s0_authorizes_s1_only": s0.get("decision")
        == "GO_RTX2080TI_S1_HARDWARE_AUDIT_ONLY",
        "linux_host": platform.system() == "Linux",
        "nvidia_smi_query_succeeded": gpu_query["returncode"] == 0,
        "exactly_one_visible_gpu": len(gpu_rows) == 1,
        "gpu_is_rtx_2080_ti": len(gpu_rows) == 1
        and "RTX 2080 Ti" in gpu_rows[0]["name"],
        "gpu_memory_at_least_10_gib": len(gpu_rows) == 1
        and gpu_rows[0]["memory_total_mib"] >= 10 * 1024,
        "compute_capability_is_7_5": len(gpu_rows) == 1
        and gpu_rows[0]["compute_capability"] == "7.5",
        "no_preexisting_compute_process": compute_apps["returncode"] == 0
        and not active_compute_rows,
        "logical_cpu_at_least_2": (os.cpu_count() or 0) >= 2,
        "memory_at_least_7_gib": _memory_total_bytes() >= 7 * GIB,
        "disk_free_at_least_40_gib": disk.free >= 40 * GIB,
    }
    failures = [name for name, passed in checks.items() if not passed]
    decision = "GO_RTX2080TI_S2_ENVIRONMENT_ONLY" if not failures else "NO_GO_RTX2080TI_S1_HARDWARE_AUDIT"
    record: dict[str, Any] = {
        "schema": "v5-final.gpu-rtx2080ti.s1-hardware-audit.v1",
        "stage": "GPU-S1",
        "status": "COMPLETE",
        "s0_scope_freeze_digest": s0["scope_freeze_digest"],
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version,
            "logical_cpu_count": os.cpu_count(),
            "memory_total_bytes": _memory_total_bytes(),
            "disk_total_bytes": disk.total,
            "disk_free_bytes": disk.free,
        },
        "gpu": {
            "rows": gpu_rows,
            "active_compute_rows": active_compute_rows,
            "nvidia_smi_query": gpu_query,
            "compute_apps_query": compute_apps,
            "nvcc_diagnostic": nvcc,
        },
        "service_contract": {
            "source": "https://docs.keioaic.dev/jupyterhub_user_manual",
            "documented_resources": {
                "logical_cpu": 2,
                "memory_gib": 8,
                "storage_gib": 100,
                "gpu": "RTX 2080 Ti x 1 (shared physical GPU)",
            },
            "important_runtime_constraint": (
                "the instance may stop when no foreground work is detected; production "
                "execution requires a documented foreground/resume strategy"
            ),
        },
        "checks": checks,
        "failed_checks": failures,
        "authorization": {
            "s2_environment_construction": "AUTHORIZED" if not failures else "NOT_AUTHORIZED",
            "molecular_candidate_outcomes": "NOT_AUTHORIZED",
            "gpu_90_item_execution": "NOT_AUTHORIZED",
            "fci_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "decision": decision,
        "claim_boundary": (
            "S1 is hardware/access evidence only. It does not establish CUDA backend "
            "availability, numerical parity, speedup, or molecular VQE performance."
        ),
    }
    record["hardware_audit_digest"] = _digest_without(record, "hardware_audit_digest")
    return record


def audit(path: Path = OUTPUT) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "digest_valid": record.get("hardware_audit_digest")
        == _digest_without(record, "hardware_audit_digest"),
        "outcomes_not_authorized": record["authorization"]["molecular_candidate_outcomes"]
        == "NOT_AUTHORIZED",
        "performance_not_authorized": record["authorization"]["performance_claim"]
        == "NOT_AUTHORIZED",
        "decision_consistent": (
            record["decision"] == "GO_RTX2080TI_S2_ENVIRONMENT_ONLY"
        )
        == (not record["failed_checks"]),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError("GPU S1 artifact audit failed: " + ", ".join(failures))
    return {"passed": True, "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("capture", "verify"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.action == "capture":
        artifact = capture()
        write_json_exclusive(args.output, artifact)
        print(json.dumps({"decision": artifact["decision"], "path": str(args.output)}, sort_keys=True))
        return
    result = audit(args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
