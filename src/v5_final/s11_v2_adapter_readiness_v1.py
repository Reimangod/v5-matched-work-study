"""Freeze the outcome-free queue-v2 native-adapter readiness binding."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import (
    artifact_is_immutable_git_blob,
    manifest_matches_artifact_commit,
)
from .s0_successor import ROOT
from .s11_v2_queue_native_adapter import (
    EXPECTED_QUEUE_DIGEST,
    METHOD_IDS,
    QUEUE_V2,
    audit_adapter_contract,
)


OUTPUT_DIR = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-adapter-readiness-v1"
)
OUTPUT = OUTPUT_DIR / "adapter-readiness-v1.json"
SOURCES = (
    ROOT / "src/v5_final/s11_v2_queue_native_adapter.py",
    ROOT / "src/v5_final/parent_native_verifier_v2.py",
    ROOT / "src/v5_final/verifier_v2.py",
    ROOT / "src/v5_final/parent_native_execution_services.py",
    ROOT / "src/v5_final/parent_native_persistent_runner.py",
    ROOT / "src/v5_final/parent_native_work_accounting.py",
    ROOT / "tests/test_v5_final_s11_v2_queue_native_adapter.py",
    ROOT / "tests/test_v5_final_bfgs_runtime_parity_v1.py",
)
PINNED_BFGS = (
    ROOT
    / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe/adaptvqe/minimize.py"
)


class AdapterReadinessError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build() -> dict[str, Any]:
    adapter = audit_adapter_contract()
    source_sha256 = {
        str(path.relative_to(ROOT)): _sha(path) for path in SOURCES
    }
    source_sha256[str(PINNED_BFGS.relative_to(ROOT))] = _sha(PINNED_BFGS)
    binding = {
        "schema": "v5-final.s11-v2-native-adapter-source-binding.v1",
        "queue_v2": {
            "path": str(QUEUE_V2.relative_to(ROOT)),
            "sha256": _sha(QUEUE_V2),
            "queue_digest": EXPECTED_QUEUE_DIGEST,
            "modified": False,
        },
        "source_sha256": source_sha256,
        "method_ids": list(METHOD_IDS),
        "shared_interface": (
            "v5_final.s11_v2_queue_native_adapter:QueueV2NativeAdapter"
        ),
        "verifier": "VerifierV2",
        "legacy_dense_verifier_allowed": False,
        "persistent_control": {
            "checkpoint": "ParentNativePersistentRunner.open",
            "rollback": "ParentNativePersistentRunner.rollback_active_attempt",
            "retry": "ParentNativePersistentRunner.start_retry",
        },
        "BFGS_runtime_parity_required": True,
    }
    binding["adapter_digest"] = _digest(binding)
    checks = {
        "adapter_contract_passed": all(adapter["checks"].values()),
        "queue_digest_exact": adapter["queue_digest"] == EXPECTED_QUEUE_DIGEST,
        "all_six_methods_bound": adapter["method_count"] == 6,
        "queue_v2_unchanged": binding["queue_v2"]["modified"] is False,
        "source_manifest_nonempty": len(source_sha256) == len(SOURCES) + 1,
        "production_dense_verifier_forbidden": binding[
            "legacy_dense_verifier_allowed"
        ]
        is False,
        "candidate_energy_zero": adapter["candidate_energy_evaluations"] == 0,
        "optimizer_zero": adapter["optimizer_iterations"] == 0,
        "FCI_zero": adapter["FCI_evaluations"] == 0,
    }
    result = {
        "schema": "v5-final.s11-v2-native-adapter-readiness.v1",
        "stage": "P7_V5_ADAPTER_READINESS_PREREQUISITE",
        "status": "PASS_OUTCOME_FREE_ADAPTER_READY_EXECUTION_STILL_BLOCKED",
        "semantic_diff_classification": (
            "TRANSPORT_ONLY_QUEUE_V2_SCIENTIFIC_SEMANTICS_UNCHANGED"
        ),
        "binding": binding,
        "checks": checks,
        "test_contract": {
            "all_six_methods_outcome_free": True,
            "cap_rejection_before_state_mutation": True,
            "checkpoint_rollback_retry": True,
            "BFGS_nfev_njev_nit_parity": True,
            "BFGS_f0_g0_combinations": 4,
            "BFGS_initial_and_normal_convergence": True,
            "BFGS_line_search_failure": True,
            "BFGS_failed_call_and_retry_preservation": True,
            "molecular_candidate_energy_used": False,
        },
        "candidate_energy_evaluations": 0,
        "optimizer_iterations": 0,
        "FCI_evaluations": 0,
        "authorization": {
            "S11_v2_90_item_execution": "NOT_AUTHORIZED_PENDING_P7_V5",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "optimizer": "NOT_AUTHORIZED",
            "FCI": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "This artifact proves transport, verifier, accounting, and optimizer "
            "runtime readiness only; it contains no molecular candidate outcome."
        ),
    }
    if not all(checks.values()):
        raise AdapterReadinessError(
            [name for name, passed in checks.items() if not passed]
        )
    result["readiness_digest"] = _digest(result)
    return result


def audit() -> dict[str, Any]:
    if not OUTPUT.is_file():
        raise AdapterReadinessError("adapter readiness artifact is absent")
    raw = OUTPUT.read_bytes()
    artifact = json.loads(raw)
    body = dict(artifact)
    readiness_digest = body.pop("readiness_digest", None)
    binding = dict(artifact["binding"])
    adapter_digest = binding.pop("adapter_digest", None)
    source_manifest = [
        {"path": path, "sha256": expected}
        for path, expected in artifact["binding"]["source_sha256"].items()
        if not path.startswith("provenance/")
    ]
    pinned_sources = {
        path: expected
        for path, expected in artifact["binding"]["source_sha256"].items()
        if path.startswith("provenance/")
    }
    checks = {
        "canonical_immutable_artifact": raw == canonical_json_bytes(artifact)
        and artifact_is_immutable_git_blob(OUTPUT),
        "readiness_digest_valid": readiness_digest == _digest(body),
        "adapter_digest_valid": adapter_digest == _digest(binding),
        "historical_source_manifest_valid": manifest_matches_artifact_commit(
            OUTPUT, source_manifest
        )
        and all(_sha(ROOT / path) == expected for path, expected in pinned_sources.items()),
        "queue_v2_still_exact": artifact["binding"]["queue_v2"]["sha256"]
        == _sha(QUEUE_V2)
        and artifact["binding"]["queue_v2"]["queue_digest"]
        == EXPECTED_QUEUE_DIGEST,
        "outcomes_zero": artifact["candidate_energy_evaluations"]
        == artifact["optimizer_iterations"]
        == artifact["FCI_evaluations"]
        == 0,
    }
    if not all(checks.values()):
        raise AdapterReadinessError(
            [name for name, passed in checks.items() if not passed]
        )
    return {
        "status": "PASS_ADAPTER_READINESS_ARTIFACT",
        "checks": artifact["checks"] | checks,
        "adapter_digest": artifact["binding"]["adapter_digest"],
        "readiness_digest": artifact["readiness_digest"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        write_json_exclusive(OUTPUT, build())
    print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
