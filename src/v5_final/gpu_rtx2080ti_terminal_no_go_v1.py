"""Cross-stage terminal audit for the RTX 2080 Ti platform replication."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/v5-final/gpu-rtx2080ti/terminal-no-go-v1/terminal-no-go-v1.json"
STAGES = {
    "S0": ("s0-scope-freeze-v1/scope-freeze-v1.json", "GO_RTX2080TI_S1_HARDWARE_AUDIT_ONLY"),
    "S1": ("s1-hardware-audit-v1/hardware-audit-v1.json", "GO_RTX2080TI_S2_ENVIRONMENT_ONLY"),
    "S2": ("s2-environment-freeze-v1/environment-freeze-v1.json", "GO_RTX2080TI_S3_BACKEND_AUDIT_ONLY"),
    "S3": ("s3-backend-audit-v1/backend-audit-v1.json", "GO_RTX2080TI_S4_SAME_HOST_CPU_REFERENCE_ONLY"),
    "S4": ("s4-cpu-reference-v1/cpu-reference-v1.json", "GO_RTX2080TI_S5_BACKEND_IMPLEMENTATION_ONLY"),
    "S5": ("s5-backend-implementation-v1/backend-implementation-v1.json", "GO_RTX2080TI_S6_SYNTHETIC_PARITY_ONLY"),
    "S6": ("s6-synthetic-parity-v1/synthetic-parity-v1.json", "GO_RTX2080TI_S7_H2_H4_PARITY_ONLY"),
    "S7": ("s7-h2-h4-parity-v1/h2-h4-parity-v1.json", "GO_RTX2080TI_S8_END_TO_END_GATE_ONLY"),
    "S8": ("s8-end-to-end-gate-v1/end-to-end-gate-v1.json", "NO_GO_RTX2080TI_NO_END_TO_END_ADVANTAGE"),
}


def _digest_without(record: dict[str, Any], field: str) -> str:
    value = dict(record)
    value.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _stage_records() -> list[dict[str, Any]]:
    root = ROOT / "artifacts/v5-final/gpu-rtx2080ti"
    records = []
    for stage, (relative, expected_decision) in STAGES.items():
        path = root / relative
        raw = path.read_bytes()
        value = json.loads(raw)
        records.append(
            {
                "stage": stage,
                "path": str(path.relative_to(ROOT)),
                "file_sha256": hashlib.sha256(raw).hexdigest(),
                "decision": value.get("decision"),
                "expected_decision": expected_decision,
                "decision_matches": value.get("decision") == expected_decision,
            }
        )
    return records


def build() -> dict[str, Any]:
    stages = _stage_records()
    s8 = json.loads(
        (ROOT / "artifacts/v5-final/gpu-rtx2080ti/s8-end-to-end-gate-v1/end-to-end-gate-v1.json").read_text()
    )
    checks = {
        "all_s0_s8_artifacts_present_and_decisions_match": all(
            item["decision_matches"] for item in stages
        ),
        "terminal_reason_is_speed": s8["failed_checks"] == ["minimum_end_to_end_speed"],
        "candidate_energy_zero": s8["scientific_work"][
            "compression_candidate_energy_evaluations"
        ]
        == 0,
        "optimizer_zero": s8["scientific_work"]["optimizer_starts"] == 0,
        "fci_zero": s8["scientific_work"]["fci_evaluations"] == 0,
        "gpu_queue_zero_of_90": s8["scientific_work"]["gpu_90_item_terminal_count"] == 0,
        "s9_s12_blocked": all(
            s8["authorization"][key] == "NOT_AUTHORIZED"
            for key in (
                "s9_gpu_queue_refreeze",
                "s10_gpu_90_item_execution",
                "s11_closure",
                "s12_reporting",
            )
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError("terminal audit failed: " + ", ".join(failures))
    record: dict[str, Any] = {
        "schema": "v5-final.gpu-rtx2080ti.terminal-no-go.v1",
        "status": "TERMINAL_NO_GO",
        "decision": "NO_GO_RTX2080TI_NO_END_TO_END_ADVANTAGE",
        "stage_chain": stages,
        "checks": checks,
        "test_evidence": {
            "gpu_scoped": "31 passed",
            "core_suite_without_eight_live_GitHub_CLI_test_files": "438 passed, 3 expected xfailed",
            "full_suite": "450 passed, 3 expected xfailed, 9 infrastructure failures",
            "full_suite_failure_classification": {
                "missing_unauthenticated_remote_gh_cli": 8,
                "historical_thread_environment_invocation_mismatch": 1,
                "scientific_or_gpu_regression": 0,
            },
        },
        "stage_disposition": {
            "S0_S8": "COMPLETED",
            "S9": "NOT_AUTHORIZED_BY_S8",
            "S10": "NOT_AUTHORIZED_BY_S8",
            "S11": "NOT_AUTHORIZED_BY_S8",
            "S12": "NOT_AUTHORIZED_BY_S8",
        },
        "scientific_claim_boundary": (
            "The pinned CPU and RTX 2080 Ti hybrid source kernels agree numerically for H2/H4, "
            "but the preregistered steady-state source workload is slower on the RTX 2080 Ti. "
            "No compression candidate, optimizer, FCI reference, GPU 90-item queue, or V5 "
            "performance result was evaluated. This is a platform-port No-Go only."
        ),
    }
    record["terminal_audit_digest"] = _digest_without(record, "terminal_audit_digest")
    return record


def audit(path: Path = OUTPUT) -> dict[str, Any]:
    record = json.loads(path.read_text())
    checks = {
        "digest_valid": record.get("terminal_audit_digest")
        == _digest_without(record, "terminal_audit_digest"),
        "stage_chain_current": record["stage_chain"] == _stage_records(),
        "all_checks_true": all(record["checks"].values()),
        "terminal_no_go": record["decision"]
        == "NO_GO_RTX2080TI_NO_END_TO_END_ADVANTAGE",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError("terminal artifact verification failed: " + ", ".join(failures))
    return {"passed": True, "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.action == "build":
        value = build()
        write_json_exclusive(args.output, value)
        print(json.dumps({"decision": value["decision"], "path": str(args.output)}, sort_keys=True))
    else:
        print(json.dumps(audit(args.output), sort_keys=True))


if __name__ == "__main__":
    main()
