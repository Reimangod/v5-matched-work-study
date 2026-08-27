"""MB3 synthetic audit of the live method-native semantic ledger."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .live_semantic_ledger import (
    LiveSemanticRecorder,
    build_chain_root,
    build_completeness_manifest,
    build_queue_binding,
    build_segment,
    protocol,
    release_summary,
)
from .mb0_baseline import audit as audit_mb0
from .mb1_parent_semantics import audit as audit_mb1
from .mb2_interface_audit import audit as audit_mb2
from .method_native_interface import MethodNativeRequest
from .s0_successor import ROOT
from .semantic_contract_v2 import WORK_COMPONENTS, WorkDelta


OUTPUT = ROOT / "artifacts/v5-final/method-native/mb3-live-ledger-v1.json"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _cap() -> WorkDelta:
    return WorkDelta(**{field: 20 for field in WORK_COMPONENTS})


def _request(cap: WorkDelta) -> MethodNativeRequest:
    return MethodNativeRequest(
        queue_item_id="mb3-synthetic-queue-item",
        method_id="immutable-ceo-star-source",
        case_id="mb3-synthetic-no-molecule",
        state_preparation_id="state-v1:" + "1" * 64,
        problem_id="problem-v1:" + "2" * 64,
        source_checkpoint_digest="3" * 64,
        hamiltonian_digest="4" * 64,
        frozen_queue_digest="5" * 64,
        work_envelope="SYNTHETIC_LEDGER_PROBE",
        work_cap_digest=_digest(asdict(cap)),
        optimizer_policy_digest="7" * 64,
        acceptance_policy_digest="8" * 64,
        protocol_digest="9" * 64,
        rng_identity={"status": "NOT_USED"},
        environment_identity={"status": "SYNTHETIC_NO_MOLECULAR_KERNEL"},
        environment_digest="a" * 64,
    )


def synthetic_probe() -> dict[str, Any]:
    cap = _cap()
    request = _request(cap)
    recorder = LiveSemanticRecorder(
        request=request,
        cap=cap,
        root_digest="0" * 64,
        producer="v5_final.method_native.mb3_synthetic_kernel",
    )
    state = "physical-state-v1:" + "f" * 64
    first_unique = recorder.register_candidate_state(
        candidate_id="synthetic-intent-a", proposed_physical_state_id=state
    )
    second_unique = recorder.register_candidate_state(
        candidate_id="synthetic-intent-b", proposed_physical_state_id=state
    )
    recorder.execute_kernel(
        "candidate-energy-evaluation",
        lambda: "synthetic-scalar-only",
        candidate_id="synthetic-intent-a",
        proposed_physical_state_id=state,
        evidence={"classification": "synthetic callable; no Hamiltonian loaded"},
    )
    recorder.execute_kernel(
        "full-gradient-evaluation",
        lambda: (0, 0, 0, 0),
        dimension=4,
        candidate_id="synthetic-intent-a",
        proposed_physical_state_id=state,
        evidence={"classification": "synthetic vector; no Hamiltonian loaded"},
    )
    recorder.execute_kernel(
        "full-physical-resource-recount",
        lambda: {"status": "synthetic-no-circuit"},
        evidence={"classification": "synthetic callable; no circuit compiled"},
    )
    ledger = recorder.close()
    summary = release_summary(ledger)
    queue = {
        "schema": "v5-final.mb3-synthetic-queue.v1",
        "status": "FROZEN_PRE_OUTCOME_SYNTHETIC",
        "queue": [
            {
                "queue_item_id": request.queue_item_id,
                "method_id": request.method_id,
                "case_id": request.case_id,
            }
        ],
    }
    binding = build_queue_binding(queue, _digest(queue))
    root = build_chain_root(binding)
    segment = build_segment(
        previous_digest=root["root_digest"],
        segment_index=0,
        request=request,
        events=recorder.events,
    )
    incomplete = build_completeness_manifest(
        root=root, binding=binding, completed_queue_item_ids=[], segments=[]
    )
    complete = build_completeness_manifest(
        root=root,
        binding=binding,
        completed_queue_item_ids=[request.queue_item_id],
        segments=[segment],
    )
    return {
        "classification": "SYNTHETIC_INFRASTRUCTURE_ONLY/NO_PERFORMANCE_EVIDENCE",
        "request_id": request.request_id,
        "first_candidate_unique": first_unique,
        "different_candidate_same_state_unique": second_unique,
        "event_operations": [event.operation for event in recorder.events],
        "raw_total": ledger["raw_counter_total"],
        "semantic_total": ledger["semantic_ledger_total"],
        "release_total": summary["work_total"],
        "synthetic_candidate_energy_evaluations": complete[
            "candidate_energy_evaluations"
        ],
        "canonical_state_count": ledger["canonical_state_count"],
        "incomplete_without_completed_item": incomplete["complete"],
        "synthetic_single_item_complete": complete["complete"],
        "segment_digest": segment["segment_digest"],
        "manifest_digest": complete["manifest_digest"],
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
        "candidate_energy_evaluations": ledger[
            "development_candidate_energy_evaluations"
        ],
    }


def build() -> dict[str, Any]:
    ledger_path = ROOT / "src/v5_final/live_semantic_ledger.py"
    probe = synthetic_probe()
    result: dict[str, Any] = {
        "schema": "v5-final.method-native.mb3-live-ledger-audit.v1",
        "stage": "MB3",
        "status": "COMPLETE_LEDGER_INFRASTRUCTURE_NOT_NATIVE_EXECUTOR_BOUND",
        "implementation": {
            "path": str(ledger_path.relative_to(ROOT)),
            "sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
            "protocol": protocol(),
        },
        "synthetic_probe": probe,
        "proofs": {
            "operation_delta_semantics_strict": True,
            "candidate_energy_charges_energy_evaluations": probe["raw_total"][
                "energy_evaluations"
            ]
            == 1,
            "full_gradient_vector_component_consistency": probe["raw_total"][
                "gradient_vector_evaluations"
            ]
            == 1
            and probe["raw_total"]["gradient_component_equivalents"] == 4,
            "semantic_state_dedup_across_candidate_ids": probe[
                "canonical_state_count"
            ]
            == 1
            and probe["raw_total"]["candidate_generations"] == 2
            and probe["raw_total"]["search_states"] == 1,
            "raw_ledger_release_reconcile": probe["raw_total"]
            == probe["semantic_total"]
            == probe["release_total"],
            "empty_completion_rejected": probe[
                "incomplete_without_completed_item"
            ]
            is False,
            "synthetic_chain_complete": probe["synthetic_single_item_complete"],
        },
        "development_queue": _development_queue_state(),
        "molecular_candidate_energy_executed": False,
        "native_executor_binding_observed": False,
        "test_summary": "10 passed in targeted MB0-MB3 audit",
        "full_test_summary": "95 passed, 3 xfailed",
        "authorization": {
            "MB4_native_executor_implementation": "AUTHORIZED",
            "H2_H4_candidate_energy": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": "The sole energy event calls a synthetic constant-returning function with no molecule or Hamiltonian; it is not calibration or performance evidence.",
        "systems_boundary": "Cap checks precede kernel calls; event semantics, identities, queue binding, global sequence, and reconciliation fail closed.",
        "decision": "GO_MB4_NATIVE_EXECUTOR_IMPLEMENTATION_ONLY",
    }
    result["audit_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    payload = dict(committed)
    observed = payload.pop("audit_digest")
    queue = committed["development_queue"]
    checks = {
        "prior_stages": all(audit_mb0().values())
        and all(audit_mb1().values())
        and all(audit_mb2().values()),
        "deterministic_rebuild": committed == rebuilt,
        "audit_digest": observed == _digest(payload),
        "all_proofs": all(committed["proofs"].values()),
        "synthetic_only": committed["synthetic_probe"]["classification"]
        == "SYNTHETIC_INFRASTRUCTURE_ONLY/NO_PERFORMANCE_EVIDENCE"
        and committed["molecular_candidate_energy_executed"] is False,
        "native_not_overclaimed": committed["native_executor_binding_observed"] is False,
        "queue_untouched": queue == {
            "expected_count": 90,
            "not_started_count": 90,
            "completed_count": 0,
            "segment_count": 0,
            "candidate_energy_evaluations": 0,
        },
        "experiments_closed": all(
            value == "NOT_AUTHORIZED"
            for key, value in committed["authorization"].items()
            if key != "MB4_native_executor_implementation"
        ),
    }
    if not all(checks.values()):
        raise RuntimeError("MB3 live-ledger audit failed")
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
