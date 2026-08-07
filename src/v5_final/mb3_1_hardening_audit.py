"""Deterministic synthetic audit for the additive MB3.1 hardening layer."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .method_native_hardening import ExecutorBoundRecorder, protocol
from .method_native_interface import MethodNativeRequest, NativeExecutorIdentity
from .s0_successor import ROOT
from .semantic_contract_v2 import WorkDelta


OUTPUT = ROOT / "artifacts/v5-final/method-native/mb3-1-hardening-v1.json"
IMPLEMENTATION = ROOT / "src/v5_final/method_native_hardening.py"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _probe() -> dict[str, Any]:
    cap = WorkDelta(candidate_generations=1, search_states=0)
    request = MethodNativeRequest(
        queue_item_id="mb3-1-synthetic-item",
        method_id="immutable-ceo-star-source",
        case_id="mb3-1-synthetic-no-molecule",
        state_preparation_id="state-v1:" + "1" * 64,
        problem_id="problem-v1:" + "2" * 64,
        source_checkpoint_digest="3" * 64,
        hamiltonian_digest="4" * 64,
        frozen_queue_digest="5" * 64,
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
        entrypoint="v5_final.method_native_hardening:synthetic_no_molecule",
        implementation_sha256=hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest(),
        parent_repository_commit="4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db",
        ceo_adapt_vqe_commit="a3f89d03e6a03c89767d3cf8ee7657a57653dda0",
    )
    recorder = ExecutorBoundRecorder(
        request=request,
        executor=executor,
        implementation_path=IMPLEMENTATION,
        cap=cap,
        root_digest="0" * 64,
    )
    disposition = recorder.register_candidate_state(
        candidate_id="synthetic-intent",
        proposed_physical_state_id="physical-state-v1:" + "f" * 64,
    )
    ledger = recorder.close()
    event = ledger["events"][0]
    return {
        "classification": "SYNTHETIC_INFRASTRUCTURE_ONLY/NO_MOLECULE_OR_ENERGY_KERNEL",
        "disposition": disposition,
        "event_operations": [value["operation"] for value in ledger["events"]],
        "raw_counter_total": ledger["raw_counter_total"],
        "canonical_state_count": ledger["canonical_state_count"],
        "executor_id": executor.executor_id,
        "event_executor_id": event["evidence"]["native_executor_id"],
        "event_executor_identity": event["evidence"]["native_executor"],
        "event_producer": event["producer"],
    }


def _development_queue_state() -> dict[str, Any]:
    queue = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-queue-v3.json").read_text()
    )
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
    probe = _probe()
    result = {
        "schema": "v5-final.method-native.mb3-1-hardening-audit.v1",
        "stage": "MB3.1",
        "status": "HARDENED_INFRASTRUCTURE_ONLY",
        "implementation": {
            "path": str(IMPLEMENTATION.relative_to(ROOT)),
            "sha256": hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest(),
            "protocol": protocol(),
        },
        "synthetic_probe": probe,
        "proofs": {
            "executor_identity_bound_to_event": probe["executor_id"]
            == probe["event_executor_id"],
            "producer_bound_to_executor_entrypoint": probe["event_producer"]
            == probe["event_executor_identity"]["entrypoint"],
            "generation_work_preserved": probe["raw_counter_total"]["candidate_generations"]
            == 1,
            "cap_rejected_expansion_not_charged": probe["disposition"] == "CAP_REJECTED"
            and probe["raw_counter_total"]["search_states"] == 0,
            "cap_rejected_expansion_not_mutated": probe["canonical_state_count"] == 0,
            "no_energy_event": "candidate-energy-evaluation" not in probe["event_operations"],
        },
        "development_queue": _development_queue_state(),
        "molecular_candidate_energy_executed": False,
        "authorization": {
            "method_native_molecular_execution": "NOT_AUTHORIZED",
            "H2_H4_candidate_energy": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "test_scope": [
            "exact SHA-256 and executor binding",
            "cap boundary and semantic-state mutation",
            "attempt/retry terminal lifecycle",
            "queue schema-audit binding",
            "exclusive request/result publication",
            "digest-valid semantic tampering",
        ],
        "academic_boundary": "The probe loads no molecule or Hamiltonian and evaluates no energy.",
        "systems_boundary": "All production authorizations remain closed after additive hardening.",
        "decision": "GO_MB4_1_PROTOCOL_REVIEW_ONLY",
    }
    result["audit_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    payload = dict(committed)
    observed = payload.pop("audit_digest")
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "audit_digest": observed == _digest(payload),
        "all_proofs": all(committed["proofs"].values()),
        "synthetic_only": committed["synthetic_probe"]["classification"]
        == "SYNTHETIC_INFRASTRUCTURE_ONLY/NO_MOLECULE_OR_ENERGY_KERNEL",
        "queue_untouched": committed["development_queue"]
        == {
            "expected_count": 90,
            "not_started_count": 90,
            "completed_count": 0,
            "segment_count": 0,
            "candidate_energy_evaluations": 0,
        },
        "everything_closed": all(
            value == "NOT_AUTHORIZED" for value in committed["authorization"].values()
        ),
    }
    if not all(checks.values()):
        raise RuntimeError("MB3.1 hardening audit failed")
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
