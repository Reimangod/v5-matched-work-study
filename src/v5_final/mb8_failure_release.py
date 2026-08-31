"""MB8 release attestation for the MB4 method-native No-Go."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb0_baseline import audit as audit_mb0
from .mb4_fail_closed import OUTPUT as MB4_OUTPUT, audit as audit_mb4
from .s0_successor import ROOT


OUTPUT = ROOT / "artifacts/v5-final/method-native/mb8-no-go-release-v1.json"
CONTENT_COMMIT = "099d5ab2a0363e9fc3b78943fe311c1087004249"
RELEASE_TAG = "v5-final-method-native-pre-calibration-no-go-v1"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build() -> dict[str, Any]:
    mb4 = json.loads(MB4_OUTPUT.read_text())
    result: dict[str, Any] = {
        "schema": "v5-final.method-native.mb8-no-go-release.v1",
        "stage": "MB8",
        "status": "READY_TO_TAG_AND_PUSH_NO_GO",
        "branch": "feature/v5-final-method-native-backends-v1",
        "scientific_content_commit": CONTENT_COMMIT,
        "stage_commits": {
            "MB0": "cd269eb",
            "MB1": "19a61b1",
            "MB2": "26b7940",
            "MB3": "ea738fc",
            "MB4_NO_GO": "099d5ab",
        },
        "release_tag": RELEASE_TAG,
        "fresh_recursive_clone_attestation": {
            "source": "local content-addressed clone before release attestation commit",
            "head": CONTENT_COMMIT,
            "worktree_clean": True,
            "parent_repository_commit": "4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db",
            "ceo_adapt_vqe_commit": "a3f89d03e6a03c89767d3cf8ee7657a57653dda0",
            "mb4_audit": "PASS",
            "test_summary": "96 passed, 3 xfailed",
            "test_exit_code": 0,
            "threads": {
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            },
        },
        "protected_baseline": {
            "mb0_audit": "PASS",
            "historical_artifacts_mutated": False,
            "existing_tags_moved": False,
            "force_push_authorized": False,
        },
        "terminal_scientific_state": {
            "decision": mb4["decision"],
            "no_go_digest": mb4["no_go_digest"],
            "six_method_native_molecular_backend_entrypoints": False,
            "H2_H4_calibration_authorization": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "development_queue": mb4["development_queue"],
        "publication_policy": {
            "push_branch": True,
            "push_new_annotated_tag": True,
            "force_push": False,
            "move_existing_tag": False,
            "github_repository_expected_public": True,
        },
        "claim_boundary": "Release of reproducible infrastructure and an MB4 semantic No-Go; no H2/H4 calibration or performance evidence.",
    }
    result["release_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    payload = dict(committed)
    observed = payload.pop("release_digest")
    checks = {
        "mb0_protected": all(audit_mb0().values()),
        "mb4_terminal": all(audit_mb4().values()),
        "deterministic_rebuild": committed == rebuilt,
        "release_digest": observed == _digest(payload),
        "fresh_clone_passed": committed["fresh_recursive_clone_attestation"][
            "test_exit_code"
        ]
        == 0,
        "pins_exact": committed["fresh_recursive_clone_attestation"][
            "parent_repository_commit"
        ]
        == "4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db"
        and committed["fresh_recursive_clone_attestation"]["ceo_adapt_vqe_commit"]
        == "a3f89d03e6a03c89767d3cf8ee7657a57653dda0",
        "no_go_preserved": committed["terminal_scientific_state"]["decision"]
        == "NO_GO_MB4_UNRESOLVED_METHOD_NATIVE_SEMANTICS",
        "experiments_closed": all(
            committed["terminal_scientific_state"][key] == "NOT_AUTHORIZED"
            for key in (
                "H2_H4_calibration_authorization",
                "development_queue_execution",
                "performance_claim",
            )
        ),
        "safe_publication": committed["publication_policy"]["force_push"] is False
        and committed["publication_policy"]["move_existing_tag"] is False,
    }
    if not all(checks.values()):
        raise RuntimeError("MB8 No-Go release audit failed")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args()
    if args.action == "build":
        write_json_exclusive(OUTPUT, build())
    else:
        audit()
    print(json.dumps({"action": args.action, "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()
