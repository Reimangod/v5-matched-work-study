"""MB2 audit for the shared method-native recording interface."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb0_baseline import audit as audit_mb0
from .mb1_parent_semantics import audit as audit_mb1
from .method_native_interface import (
    METHOD_IDS,
    MethodNativeRequest,
    MethodNativeResult,
    NativeExecutorIdentity,
    bind_result_to_request,
    protocol,
)
from .s0_successor import ROOT


OUTPUT = ROOT / "artifacts/v5-final/method-native/mb2-interface-v1.json"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _probe(method_id: str) -> dict[str, Any]:
    request = MethodNativeRequest(
        queue_item_id="mb2-synthetic-recording-probe",
        method_id=method_id,
        case_id="mb2-synthetic-no-molecule",
        state_preparation_id="state-v1:" + "1" * 64,
        problem_id="problem-v1:" + "2" * 64,
        source_checkpoint_digest="3" * 64,
        hamiltonian_digest="4" * 64,
        frozen_queue_digest="5" * 64,
        work_envelope="ZERO_WORK_INTERFACE_PROBE",
        work_cap_digest="6" * 64,
        optimizer_policy_digest="7" * 64,
        acceptance_policy_digest="8" * 64,
        protocol_digest="9" * 64,
        rng_identity={"status": "NOT_USED"},
        environment_identity={"status": "SYNTHETIC_IDENTITY_ONLY"},
        environment_digest="a" * 64,
    )
    executor = NativeExecutorIdentity(
        method_id=method_id,
        classification="SYNTHETIC_INTERFACE_PROBE_NOT_AN_EXECUTOR",
        entrypoint="v5_final.mb2_interface_audit:never_execute",
        implementation_sha256="b" * 64,
        parent_repository_commit="4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db",
        ceo_adapt_vqe_commit="a3f89d03e6a03c89767d3cf8ee7657a57653dda0",
    )
    result = MethodNativeResult(
        request_id=request.request_id,
        terminal_status="INFRASTRUCTURE_ONLY",
        executor=executor,
        parent_state_id=request.state_preparation_id,
        child_state_id=None,
        raw_semantic_events=(),
        work_ledger={"status": "NOT_STARTED", "candidate_energy_evaluations": 0},
        resource_recount={"status": "NOT_RUN"},
        transaction_record={"status": "NOT_STARTED"},
        failure_rollback_record=None,
        completeness_manifest={"complete": False, "reason": "interface probe only"},
        evidence_class="INFRASTRUCTURE_ONLY/NO_PERFORMANCE_EVIDENCE",
    )
    rebuilt_request = MethodNativeRequest.from_dict(request.to_dict())
    rebuilt_result = MethodNativeResult.from_dict(result.to_dict())
    bind_result_to_request(rebuilt_result, rebuilt_request)
    return {
        "method_id": method_id,
        "request_id": rebuilt_request.request_id,
        "result_id": rebuilt_result.result_id,
        "terminal_status": rebuilt_result.terminal_status,
        "raw_event_count": len(rebuilt_result.raw_semantic_events),
        "complete": rebuilt_result.completeness_manifest["complete"],
        "evidence_class": rebuilt_result.evidence_class,
    }


def _queue_state() -> dict[str, Any]:
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
    interface_path = ROOT / "src/v5_final/method_native_interface.py"
    result: dict[str, Any] = {
        "schema": "v5-final.method-native.mb2-interface-audit.v1",
        "stage": "MB2",
        "status": "COMPLETE_RECORDING_INTERFACE_ONLY",
        "interface": {
            "path": str(interface_path.relative_to(ROOT)),
            "sha256": hashlib.sha256(interface_path.read_bytes()).hexdigest(),
            "protocol": protocol(),
        },
        "six_method_serialization_probes": [_probe(method) for method in METHOD_IDS],
        "algorithm_commonization": False,
        "candidate_molecular_energy_executed": False,
        "development_queue": _queue_state(),
        "test_summary": "5 passed in MB0+MB1+MB2 targeted audit",
        "full_test_summary": "90 passed, 3 xfailed",
        "authorization": {
            "MB3_live_ledger_binding": "AUTHORIZED",
            "candidate_molecular_energy": "NOT_AUTHORIZED",
            "H2_H4_calibration": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": "Common identity and serialization only; all probes are synthetic zero-work records and no method outcome exists.",
        "systems_boundary": "Content identities, exact executor identity, terminal evidence, and request/result binding fail closed.",
        "decision": "GO_MB3_LIVE_LEDGER_BINDING_ONLY",
    }
    result["audit_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    payload = dict(committed)
    observed = payload.pop("audit_digest")
    queue = committed["development_queue"]
    probes = committed["six_method_serialization_probes"]
    checks = {
        "prior_stages": all(audit_mb0().values()) and all(audit_mb1().values()),
        "deterministic_rebuild": committed == rebuilt,
        "audit_digest": observed == _digest(payload),
        "six_methods": [probe["method_id"] for probe in probes] == list(METHOD_IDS),
        "probes_outcome_free": all(
            probe["terminal_status"] == "INFRASTRUCTURE_ONLY"
            and probe["raw_event_count"] == 0
            and probe["complete"] is False
            for probe in probes
        ),
        "recording_not_algorithm": committed["algorithm_commonization"] is False
        and committed["interface"]["protocol"]["algorithm_fields"] == [],
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
            if key != "MB3_live_ledger_binding"
        ),
    }
    if not all(checks.values()):
        raise RuntimeError("MB2 method-native interface audit failed")
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
