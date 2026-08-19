"""Outcome-free S0 scope freeze for the RTX 2080 Ti platform study."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = (
    ROOT
    / "artifacts/v5-final/gpu-rtx2080ti/s0-scope-freeze-v1/scope-freeze-v1.json"
)

SOURCE_CPU_BRANCH = "agent/s11-v2-frozen-90-execution"
SOURCE_CPU_COMMIT = "94a54a5396b7595454880474b8a9adae99758080"
PARENT_COMMIT = "4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db"
CEO_COMMIT = "a3f89d03e6a03c89767d3cf8ee7657a57653dda0"
GPU_BRANCH = "gpu/rtx2080ti-matched-work-v1"

QUEUE_PATH = Path(
    "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v2/s11-v2-queue-v2.json"
)
CAP_PATH = Path(
    "artifacts/v5-final/parent-native/s11-v2-outcome-cap-freeze-v1/"
    "outcome-cap-freeze-v1.json"
)
P7_PATH = Path(
    "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v5/p7-go-v5.json"
)
PROTOCOL_PATH = Path("docs/GPU_RTX2080TI_STUDY_PROTOCOL.md")

EXPECTED_FILES = {
    str(QUEUE_PATH): "be88c730f7ba44efd8867c0bf571ecb01afe0349d68e5fdc11733e67c779b1b4",
    str(CAP_PATH): "3f0b7c5a8c09dcfb9e5553231894a923efc1e87bd92a6dde54afd5f028a68fb9",
    str(P7_PATH): "7ffd316208758bd4a5f63357b0e74b6b8f4df7fac0fe9a1e0b42240d70eb3a63",
}
EXPECTED_QUEUE_DIGEST = "c15a42b6e89fa72876d0293354b2eb52dc505d61386294ef7202280246c0271e"
EXPECTED_GATE_DIGEST = "701a327f20a4a195c1710af548211f541a2932b8d545492b9d219de9bd95b8b7"

CPU_OUTCOME_ROOT = Path(
    "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
)
GPU_ARTIFACT_ROOT = Path("artifacts/v5-final/gpu-rtx2080ti")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_without(record: dict[str, Any], field: str) -> str:
    value = dict(record)
    value.pop(field, None)
    return _sha256(canonical_json_bytes(value))


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _load(path: Path) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def build() -> dict[str, Any]:
    """Build S0 only from source/protocol inputs, never CPU outcome records."""

    observed_files = {
        path: _sha256((ROOT / path).read_bytes()) for path in EXPECTED_FILES
    }
    if observed_files != EXPECTED_FILES:
        raise RuntimeError("frozen CPU protocol input drift")

    queue = _load(QUEUE_PATH)
    p7 = _load(P7_PATH)
    if queue.get("queue_digest") != EXPECTED_QUEUE_DIGEST:
        raise RuntimeError("embedded queue digest drift")
    if len(queue.get("items", [])) != 90:
        raise RuntimeError("frozen queue must contain exactly 90 items")
    if p7.get("gate_digest") != EXPECTED_GATE_DIGEST:
        raise RuntimeError("embedded P7 gate digest drift")

    record: dict[str, Any] = {
        "schema": "v5-final.gpu-rtx2080ti.s0-scope-freeze.v1",
        "stage": "GPU-S0",
        "status": "COMPLETE",
        "study_id": "v5-matched-work-rtx2080ti-platform-v1",
        "source": {
            "cpu_branch": SOURCE_CPU_BRANCH,
            "cpu_commit": SOURCE_CPU_COMMIT,
            "parent_submodule_commit": PARENT_COMMIT,
            "ceo_submodule_commit": CEO_COMMIT,
            "cpu_terminal_prefix": {
                "terminal_items": 24,
                "status_counts": {
                    "COMPLETED": 14,
                    "ALGORITHM_REJECTED": 5,
                    "CAP_REJECTED": 4,
                    "FAILED_ENGINEERING_PRESERVED": 1,
                },
                "role": "historical provenance only",
                "allowed_as_gpu_execution_input": False,
            },
        },
        "frozen_protocol_inputs": {
            "files_sha256": observed_files,
            "queue_digest": EXPECTED_QUEUE_DIGEST,
            "queue_items": 90,
            "p7_gate_digest": EXPECTED_GATE_DIGEST,
            "p7_decision": p7.get("decision"),
        },
        "isolation": {
            "gpu_branch": GPU_BRANCH,
            "gpu_artifact_root": str(GPU_ARTIFACT_ROOT),
            "cpu_outcome_root": str(CPU_OUTCOME_ROOT),
            "cpu_outcome_root_access": "FORBIDDEN",
            "cpu_gpu_terminal_record_concatenation": "FORBIDDEN",
            "execution_start_index": 0,
            "execution_item_count": 90,
            "allowed_input_paths": sorted(
                [str(QUEUE_PATH), str(CAP_PATH), str(P7_PATH), str(PROTOCOL_PATH)]
            ),
        },
        "identity_policy": {
            "state_preparation_id_changed_by_backend": False,
            "backend_recorded_in": [
                "MeasurementContextID",
                "ExecutionPlatformID",
            ],
            "required_new_identifiers": [
                "ExecutionPlatformID",
                "GPUExecutionID",
                "GPUArtifactNamespace",
            ],
        },
        "scientific_invariants": {
            "candidate_set": "FROZEN_UNCHANGED",
            "ranking_and_tie_break": "FROZEN_UNCHANGED",
            "method_semantics": "FROZEN_UNCHANGED",
            "componentwise_work_caps": "FROZEN_UNCHANGED",
            "qiskit_resource_counting": "FROZEN_UNCHANGED",
            "gpu_tolerances": "MUST_BE_FROZEN_BEFORE_MOLECULAR_OUTCOMES",
        },
        "backend_safety": {
            "unexpected_cpu_fallback_limit": 0,
            "planned_hybrid_cpu_work_must_be_recorded": True,
            "production_dense_expm_policy": "PRESERVE_FROZEN_ZERO_REQUIREMENT",
            "fail_closed": True,
        },
        "authorization": {
            "s1_hardware_access_audit": "AUTHORIZED",
            "molecular_candidate_outcomes": "NOT_AUTHORIZED",
            "gpu_90_item_execution": "NOT_AUTHORIZED",
            "fci_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
            "s12_reporting": "NOT_AUTHORIZED",
        },
        "claim_boundary": (
            "S0 proves outcome isolation and immutable protocol binding only; "
            "it provides no numerical parity, speedup, energy, or VQE-performance evidence."
        ),
        "decision": "GO_RTX2080TI_S1_HARDWARE_AUDIT_ONLY",
    }
    record["scope_freeze_digest"] = _digest_without(record, "scope_freeze_digest")
    return record


def audit(*, require_clean: bool = False) -> dict[str, Any]:
    committed = json.loads(OUTPUT.read_text(encoding="utf-8"))
    rebuilt = build()
    allowed = set(committed["isolation"]["allowed_input_paths"])
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "scope_freeze_digest_valid": committed.get("scope_freeze_digest")
        == _digest_without(committed, "scope_freeze_digest"),
        "cpu_outcomes_not_allowed": str(CPU_OUTCOME_ROOT) not in allowed,
        "gpu_starts_from_item_zero": committed["isolation"]["execution_start_index"] == 0,
        "gpu_queue_has_90_items": committed["isolation"]["execution_item_count"] == 90,
        "unexpected_cpu_fallback_is_zero": committed["backend_safety"][
            "unexpected_cpu_fallback_limit"
        ]
        == 0,
        "outcomes_not_authorized": committed["authorization"][
            "molecular_candidate_outcomes"
        ]
        == "NOT_AUTHORIZED",
        "performance_not_authorized": committed["authorization"][
            "performance_claim"
        ]
        == "NOT_AUTHORIZED",
        "source_commit_is_ancestor": subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", SOURCE_CPU_COMMIT, "HEAD"],
            check=False,
        ).returncode
        == 0,
        "parent_submodule_exact": _git("-C", "provenance/dvg-obs-ceo", "rev-parse", "HEAD")
        == PARENT_COMMIT,
        "ceo_submodule_exact": _git(
            "-C", "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe", "rev-parse", "HEAD"
        )
        == CEO_COMMIT,
        "clean_if_required": (not require_clean) or _git("status", "--porcelain") == "",
    }
    failures = [name for name, passed in checks.items() if not passed]
    result: dict[str, Any] = {
        "schema": "v5-final.gpu-rtx2080ti.s0-scope-audit.v1",
        "stage": "GPU-S0",
        "passed": not failures,
        "checks": checks,
        "failed_checks": failures,
        "claim_boundary": committed["claim_boundary"],
    }
    result["audit_digest"] = _digest_without(result, "audit_digest")
    if failures:
        raise RuntimeError("GPU S0 audit failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    if args.action == "build":
        write_json_exclusive(OUTPUT, build())
        print(json.dumps({"path": str(OUTPUT), "status": "COMPLETE"}, sort_keys=True))
        return
    result = audit(require_clean=args.require_clean)
    print(json.dumps({"checks": len(result["checks"]), "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()
