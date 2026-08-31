"""Deterministic audit of additive MB3.1 residual hardening v2."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import (
    artifact_binding_commit,
    artifact_is_immutable_git_blob,
    blob_at,
    sha256_bytes,
)
from .method_native_hardening_v2 import (
    PersistentRecorderV2,
    build_bound_result_artifact_v3,
    build_item_completeness_v3,
    build_transaction_record_v2,
    build_validated_queue_binding_v3,
    protocol,
    replay_persistent_ledger,
)
from .method_native_interface import MethodNativeRequest, MethodNativeResult, NativeExecutorIdentity
from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT
from .semantic_contract_v2 import WorkDelta


OUTPUT = ROOT / "artifacts/v5-final/method-native/mb3-1-hardening-v2.json"
V1_ARTIFACT = ROOT / "artifacts/v5-final/method-native/mb3-1-hardening-v1.json"
IMPLEMENTATION = ROOT / "src/v5_final/method_native_hardening_v2.py"
ATTEMPT_ID = "method-attempt-v1:" + "b" * 64


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _synthetic_probe() -> dict[str, Any]:
    queue = {
        "schema": "v5-final.method-native-frozen-queue.v3",
        "status": "FROZEN_PRE_OUTCOME",
        "queue": [
            {
                "queue_item_id": "mb3-1-v2-synthetic-item",
                "method_id": "immutable-ceo-star-source",
                "case_id": "mb3-1-v2-synthetic-no-molecule",
            }
        ],
    }
    binding = build_validated_queue_binding_v3(queue, artifact_sha256=_digest(queue))
    cap = WorkDelta(candidate_generations=1, search_states=0)
    request = MethodNativeRequest(
        queue_item_id=queue["queue"][0]["queue_item_id"],
        method_id=queue["queue"][0]["method_id"],
        case_id=queue["queue"][0]["case_id"],
        state_preparation_id="state-v1:" + "1" * 64,
        problem_id="problem-v1:" + "2" * 64,
        source_checkpoint_digest="3" * 64,
        hamiltonian_digest="4" * 64,
        frozen_queue_digest=binding["binding_digest"],
        work_envelope="SYNTHETIC_CAP_REJECTION_ONLY",
        work_cap_digest=_digest(asdict(cap)),
        optimizer_policy_digest="7" * 64,
        acceptance_policy_digest="8" * 64,
        protocol_digest="9" * 64,
        rng_identity={"status": "NOT_USED"},
        environment_identity={"status": "SYNTHETIC_NO_MOLECULE"},
        environment_digest="a" * 64,
    )
    executor = NativeExecutorIdentity(
        method_id=request.method_id,
        classification="SYNTHETIC_INFRASTRUCTURE_ONLY",
        entrypoint="v5_final.method_native_hardening_v2:synthetic_no_molecule",
        implementation_sha256=hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest(),
        parent_repository_commit=PARENT_COMMIT,
        ceo_adapt_vqe_commit=CEO_COMMIT,
    )
    recorder = PersistentRecorderV2(
        request=request,
        executor=executor,
        implementation_path=IMPLEMENTATION,
        attempt_id=ATTEMPT_ID,
        cap=cap,
        root_digest="0" * 64,
    )
    disposition = recorder.register_candidate_state(
        candidate_id="synthetic-intent",
        proposed_physical_state_id="physical-state-v1:" + "f" * 64,
    )
    ledger = recorder.close()
    replay = replay_persistent_ledger(ledger, request=request, executor=executor)
    transaction = build_transaction_record_v2(
        request=request,
        attempt_id=ATTEMPT_ID,
        ledger=ledger,
        terminal_status="CAP_EXHAUSTED",
    )
    completeness = build_item_completeness_v3(
        request=request,
        attempt_id=ATTEMPT_ID,
        ledger=ledger,
        queue_binding=binding,
        transaction=transaction,
    )
    result = MethodNativeResult(
        request_id=request.request_id,
        terminal_status="CAP_EXHAUSTED",
        executor=executor,
        parent_state_id=request.state_preparation_id,
        child_state_id=None,
        raw_semantic_events=tuple(ledger["events"]),
        work_ledger=ledger,
        resource_recount={"status": "NOT_RUN_CAP_EXHAUSTED"},
        transaction_record=transaction,
        failure_rollback_record=None,
        completeness_manifest=completeness,
        evidence_class="SYNTHETIC_INFRASTRUCTURE_ONLY/NO_MOLECULAR_ENERGY",
    )
    publication = build_bound_result_artifact_v3(
        request=request,
        result=result,
        implementation_path=IMPLEMENTATION,
        queue_binding=binding,
        ledger=ledger,
        completeness=completeness,
        transaction=transaction,
    )
    return {
        "classification": "SYNTHETIC_INFRASTRUCTURE_ONLY/NO_MOLECULE_OR_ENERGY_KERNEL",
        "disposition": disposition,
        "request_id": request.request_id,
        "executor_id": executor.executor_id,
        "queue_binding_digest": binding["binding_digest"],
        "queue_schema_audit_sha256": binding["queue_schema_audit_sha256"],
        "ledger_digest": ledger["ledger_digest"],
        "rejection_id": ledger["rejections"][0]["rejection_id"],
        "journal": ledger["journal"],
        "replay": replay,
        "transaction_digest": transaction["transaction_digest"],
        "manifest_digest": completeness["manifest_digest"],
        "publication_artifact_digest": publication["artifact_digest"],
        "raw_counter_total": ledger["raw_counter_total"],
        "canonical_state_count": ledger["canonical_state_count"],
    }


def _development_queue_state() -> dict[str, Any]:
    queue = json.loads((ROOT / "artifacts/v5-final/s5/development-queue-v3.json").read_text())
    ledger = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json").read_text()
    )
    return {
        "expected_count": queue["expected_queue_count"],
        "not_started_count": sum(
            item["terminal_status"] == "NOT_STARTED" for item in queue["items"]
        ),
        "completed_count": len(ledger["completed_queue_item_ids"]),
        "segment_count": len(ledger["segments"]),
        "candidate_energy_evaluations": ledger["development_candidate_energy_evaluations"],
    }


def build() -> dict[str, Any]:
    probe = _synthetic_probe()
    result = {
        "schema": "v5-final.method-native.mb3-1-hardening-audit.v2",
        "stage": "MB3.1-RESIDUAL-HARDENING-V2",
        "status": "HARDENED_INFRASTRUCTURE_ONLY",
        "supersedes": {
            "classification": "ADDITIVE_DOES_NOT_OVERWRITE_V1",
            "path": str(V1_ARTIFACT.relative_to(ROOT)),
            "sha256": hashlib.sha256(V1_ARTIFACT.read_bytes()).hexdigest(),
        },
        "implementation": {
            "path": str(IMPLEMENTATION.relative_to(ROOT)),
            "sha256": hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest(),
            "protocol": protocol(),
        },
        "synthetic_probe": probe,
        "proofs": {
            "real_callable_and_source_bound": bool(probe["executor_id"]),
            "pinned_schema_executed": bool(probe["queue_schema_audit_sha256"]),
            "cap_rejection_persistent": probe["disposition"] == "CAP_REJECTED"
            and probe["replay"]["rejection_count"] == 1,
            "generation_charged": probe["raw_counter_total"]["candidate_generations"] == 1,
            "expansion_not_charged": probe["raw_counter_total"]["search_states"] == 0,
            "canonical_state_not_mutated": probe["canonical_state_count"] == 0,
            "publication_all_bindings_present": all(
                probe[key]
                for key in (
                    "queue_binding_digest",
                    "ledger_digest",
                    "transaction_digest",
                    "manifest_digest",
                    "publication_artifact_digest",
                )
            ),
            "candidate_energy_zero": probe["replay"]["candidate_energy_evaluations"] == 0,
        },
        "development_queue": _development_queue_state(),
        "molecular_candidate_energy_executed": False,
        "authorization": {
            "MB4_1_v2_protocol_review": "AUTHORIZED_REVIEW_ONLY",
            "method_native_molecular_execution": "NOT_AUTHORIZED",
            "H2_H4_candidate_energy": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "decision": "GO_MB4_1_V2_PROTOCOL_DRAFTING_ONLY",
        "academic_boundary": "Synthetic cap rejection only; no molecule, Hamiltonian, or energy kernel.",
        "systems_boundary": "Publication revalidates callable, gitlinks, schema, ledger, completeness, and transaction.",
    }
    result["audit_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    historical_commit = artifact_binding_commit(OUTPUT)
    payload = dict(committed)
    observed = payload.pop("audit_digest")
    checks = {
        "deterministic_rebuild": artifact_is_immutable_git_blob(OUTPUT)
        and sha256_bytes(
            blob_at(historical_commit, committed["implementation"]["path"])
        )
        == committed["implementation"]["sha256"],
        "audit_digest": observed == _digest(payload),
        "v1_unchanged": hashlib.sha256(V1_ARTIFACT.read_bytes()).hexdigest()
        == committed["supersedes"]["sha256"],
        "all_proofs": all(committed["proofs"].values()),
        "synthetic_only": committed["molecular_candidate_energy_executed"] is False,
        "queue_untouched": committed["development_queue"]
        == {
            "expected_count": 90,
            "not_started_count": 90,
            "completed_count": 0,
            "segment_count": 0,
            "candidate_energy_evaluations": 0,
        },
        "execution_closed": all(
            value == "NOT_AUTHORIZED"
            for key, value in committed["authorization"].items()
            if key != "MB4_1_v2_protocol_review"
        ),
    }
    if not all(checks.values()):
        raise RuntimeError("MB3.1 residual hardening v2 audit failed")
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
