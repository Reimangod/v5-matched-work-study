"""Append-only zero-kernel recovery for the exact S11 item-023 incident.

This module deliberately leaves the frozen runner and the completed item-022
recovery implementation unchanged.  It may only persist the deterministic
zero-delta cap-rejection that was lost by the direct precheck call and bind the
already durable CAP_REJECTED checkpoint into a terminal record.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import manifest_matches_artifact_commit
from . import parent_native_execution_services as services
from .parent_native_persistent_runner import ParentNativePersistentRunner, replay_raw_ledger
from .parent_native_work_accounting import ComponentwiseCapRejected, work_cap_digest
from .semantic_contract_v2 import WORK_COMPONENTS, WorkDelta
from .s0_successor import ROOT
from .s11_development_runner_v1 import (
    AUTHORIZATION_PATH as S11_AUTHORIZATION_PATH,
    DISPATCH_DIR,
    EXECUTION_DIR,
    FREEZE_OUTPUT,
    PLAN_PATH,
    RAW_DIR,
    RECEIPT_DIR,
    RESULT_DIR,
    _plan,
    _require_local_preflight,
    audit_authorization as audit_s11_authorization,
    audit_progress,
)

QUEUE_INDEX = 23
ITEM_KEY = "023-7d3a964d137a65b8c373a5a85362e1265ccf9fb941757cb44c99804e3ea98cdb"
RECOVERY_DIR = EXECUTION_DIR / "cap-precheck-recovery" / ITEM_KEY
DECLARATION_PATH = RECOVERY_DIR / "incident-declaration-v1.json"
AUTHORIZATION_PATH = RECOVERY_DIR / "owner-recovery-authorization-v1.json"
COMPLETION_PATH = RECOVERY_DIR / "terminal-recovery-completion-v1.json"
RAW_LEDGER_ROOT = RAW_DIR / ITEM_KEY
CHECKPOINT_PATH = RAW_DIR / f"{ITEM_KEY}.outcome.json"
RESULT_PATH = RESULT_DIR / f"{ITEM_KEY}.json"
RECEIPT_PATH = RECEIPT_DIR / f"{ITEM_KEY}.json"
DISPATCH_PATH = DISPATCH_DIR / f"{ITEM_KEY}.json"
RECOVERY_SOURCES = (
    ROOT / "src/v5_final/s11_cap_precheck_recovery_item023_v1.py",
    ROOT / "tests/test_v5_final_s11_cap_precheck_recovery_item023_v1.py",
    ROOT / ".github/workflows/v5-s11-cap-precheck-recovery-item023-gate.yml",
)
EXPECTED_OPERATIONS = ("full-physical-resource-recount", "statevector-recomputation")


class S11Item023RecoveryError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S11Item023RecoveryError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11Item023RecoveryError(f"noncanonical JSON: {path}")
    return value


def _item() -> dict[str, Any]:
    item = dict(_plan()["items"][QUEUE_INDEX])
    if (
        item.get("queue_item_id")
        != "development-queue-item-v4:7d3a964d137a65b8c373a5a85362e1265ccf9fb941757cb44c99804e3ea98cdb"
        or item.get("method_id") != "v5-sequential-with-rebuilding"
        or item.get("case_id") != "h6-1.5"
        or item.get("work_envelope") != "LOW"
    ):
        raise S11Item023RecoveryError("frozen item-023 identity drifted")
    return item


def _request_cap() -> tuple[Any, WorkDelta]:
    item = _item()
    cap = WorkDelta(**dict(item["componentwise_work_cap"]))
    request = services._work_request(item, _plan())
    if work_cap_digest(cap) != item["work_cap_digest"]:
        raise S11Item023RecoveryError("frozen work cap drifted")
    return request, cap


def _binding_delta() -> WorkDelta:
    binding = _item()["candidate_work_binding"]
    body = dict(binding)
    observed = body.pop("binding_digest", None)
    if observed != _digest(body):
        raise S11Item023RecoveryError("candidate binding digest mismatch")
    return WorkDelta(
        candidate_generations=int(binding["candidate_generation_count"]),
        search_states=int(binding["unique_search_state_count"]),
        resource_recounts=int(binding["resource_recounts"]),
        rewrite_verifications=int(binding["rewrite_verifications"]),
    )


def _add(left: WorkDelta, right: WorkDelta) -> WorkDelta:
    return WorkDelta(**{
        name: getattr(left, name) + getattr(right, name) for name in WORK_COMPONENTS
    })


def _embedded_state(declaration: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    request, cap = _request_cap()
    with tempfile.TemporaryDirectory(prefix="s11-item023-cap-") as temporary:
        root = Path(temporary) / ITEM_KEY
        root.mkdir()
        for entry in declaration["raw_ledger_prefix"]:
            write_json_exclusive(root / entry["name"], entry["record"])
        checkpoint_path = root.parent / f"{ITEM_KEY}.outcome.json"
        write_json_exclusive(checkpoint_path, declaration["outcome_checkpoint"])
        state = replay_raw_ledger(root, request=request, cap=cap)
        checkpoint = services._read_outcome_checkpoint(checkpoint_path, request)
    return state, checkpoint


def build_declaration() -> dict[str, Any]:
    progress = audit_progress(allow_inflight=True)["progress"]
    request, cap = _request_cap()
    state = replay_raw_ledger(RAW_LEDGER_ROOT, request=request, cap=cap)
    paths = sorted(RAW_LEDGER_ROOT.glob("*.json"))
    checkpoint = services._read_outcome_checkpoint(CHECKPOINT_PATH, request)
    projected = _add(state.work_total, _binding_delta())
    exceeded = [
        name for name in WORK_COMPONENTS if getattr(projected, name) > getattr(cap, name)
    ]
    if (
        progress["completed_terminal_count"] != QUEUE_INDEX
        or len(paths) != 4
        or state.terminal is not None
        or state.active_attempt_id is None
        or tuple(event.operation for event in state.work_events) != EXPECTED_OPERATIONS
        or checkpoint["outcome_payload"].get("terminal_status") != "CAP_REJECTED"
        or checkpoint["outcome_payload"].get("work_total") != asdict(state.work_total)
        or exceeded != ["resource_recounts"]
        or RESULT_PATH.exists()
        or RECEIPT_PATH.exists()
    ):
        raise S11Item023RecoveryError("local item-023 incident differs from declaration")
    declaration: dict[str, Any] = {
        "schema": "v5-final.s11-cap-precheck-item023-incident.v1",
        "status": "DECLARED_DURABLE_CAP_PRECHECK_TERMINALIZATION_GAP",
        "decision": "NO_RECOVERY_PENDING_EXACT_CI_AND_OWNER_AUTHORIZATION",
        "queue_index": QUEUE_INDEX,
        "item_key": ITEM_KEY,
        "plan_digest": _plan()["plan_digest"],
        "plan_sha256": _sha(PLAN_PATH),
        "freeze_sha256": _sha(FREEZE_OUTPUT),
        "s11_authorization_sha256": _sha(S11_AUTHORIZATION_PATH),
        "frozen_item": _item(),
        "dispatch": _canonical(DISPATCH_PATH),
        "dispatch_sha256": _sha(DISPATCH_PATH),
        "raw_ledger_prefix": [
            {"name": path.name, "sha256": _sha(path), "record": _canonical(path)}
            for path in paths
        ],
        "outcome_checkpoint": checkpoint,
        "outcome_checkpoint_sha256": _sha(CHECKPOINT_PATH),
        "observed_state": {
            "active_attempt_id": state.active_attempt_id,
            "record_count": len(state.records),
            "work_total": asdict(state.work_total),
            "operations": [event.operation for event in state.work_events],
            "candidate_energy_evaluations": 0,
            "terminal_absent": True,
            "result_absent": True,
            "receipt_absent": True,
        },
        "deterministic_precheck": {
            "rejected_operation": "candidate-generation",
            "projected_delta": asdict(_binding_delta()),
            "projected_total": asdict(projected),
            "exceeded_components": exceeded,
            "required_new_event": {
                "operation": "cap-rejection",
                "outcome": "cap-rejected",
                "units": 0,
                "kernel_executed": False,
            },
        },
        "recovery_policy": {
            "append_only": True,
            "preserve_all_four_records": True,
            "reuse_existing_checkpoint": True,
            "append_exact_zero_delta_cap_rejection": True,
            "append_cap_rejected_terminal": True,
            "retry_or_molecular_kernel": False,
            "candidate_energy": False,
            "queue_reordering": False,
        },
        "recovery_source_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in RECOVERY_SOURCES
        ],
        "authorization": {
            "terminal_recovery": "NOT_AUTHORIZED_PENDING_EXACT_CI_AND_OWNER_ARTIFACT",
            "molecular_kernel": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
            "release": "NOT_AUTHORIZED",
        },
    }
    declaration["declaration_digest"] = _digest(declaration)
    return declaration


def audit_declaration(record: Mapping[str, Any] | None = None) -> dict[str, bool]:
    declaration = _canonical(DECLARATION_PATH) if record is None else dict(record)
    body = dict(declaration)
    observed_digest = body.pop("declaration_digest", None)
    state, checkpoint = _embedded_state(declaration)
    _, cap = _request_cap()
    projected = _add(state.work_total, _binding_delta())
    exceeded = [
        name for name in WORK_COMPONENTS if getattr(projected, name) > getattr(cap, name)
    ]
    checks = {
        "declaration_digest_valid": observed_digest == _digest(body),
        "schema_status_decision_exact": declaration.get("schema")
        == "v5-final.s11-cap-precheck-item023-incident.v1"
        and declaration.get("status") == "DECLARED_DURABLE_CAP_PRECHECK_TERMINALIZATION_GAP"
        and declaration.get("decision") == "NO_RECOVERY_PENDING_EXACT_CI_AND_OWNER_AUTHORIZATION",
        "frozen_item_exact": declaration.get("queue_index") == QUEUE_INDEX
        and declaration.get("item_key") == ITEM_KEY
        and declaration.get("frozen_item") == _item(),
        "embedded_chain_exact": len(state.records) == 4
        and state.terminal is None
        and [event.operation for event in state.work_events] == list(EXPECTED_OPERATIONS),
        "embedded_hashes_exact": all(
            entry["sha256"] == hashlib.sha256(canonical_json_bytes(entry["record"])).hexdigest()
            for entry in declaration["raw_ledger_prefix"]
        ),
        "checkpoint_exact": checkpoint == declaration["outcome_checkpoint"]
        and declaration["outcome_checkpoint_sha256"]
        == hashlib.sha256(canonical_json_bytes(checkpoint)).hexdigest()
        and checkpoint["outcome_payload"].get("terminal_status") == "CAP_REJECTED"
        and checkpoint["outcome_payload"].get("work_total") == asdict(state.work_total),
        "deterministic_resource_recount_rejection": exceeded == ["resource_recounts"]
        and declaration["deterministic_precheck"]["projected_total"] == asdict(projected),
        "candidate_energy_zero": all(
            event.operation != "candidate-energy-evaluation" for event in state.work_events
        ),
        "append_only_no_kernel_policy": declaration.get("recovery_policy", {}).get(
            "retry_or_molecular_kernel"
        ) is False,
        "recovery_sources_unchanged": manifest_matches_artifact_commit(
            DECLARATION_PATH, declaration["recovery_source_manifest"]
        ),
        "claims_blocked": declaration.get("authorization", {}).get("performance_claim")
        == "NOT_AUTHORIZED"
        and declaration.get("authorization", {}).get("FCI_reporting") == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11Item023RecoveryError("declaration audit failed: " + ", ".join(failures))
    return checks


def build_static_report() -> dict[str, Any]:
    report = {
        "schema": "v5-final.s11-cap-precheck-item023-static-ci.v1",
        "validated_exact_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "status": "PASS_OUTCOME_FREE_ITEM023_RECOVERY_DESIGN",
        "decision": "READY_AWAITING_OWNER_TERMINAL_RECOVERY_AUTHORIZATION",
        "declaration_sha256": _sha(DECLARATION_PATH),
        "checks": audit_declaration(),
        "authorization": {
            "terminal_recovery": "NOT_AUTHORIZED",
            "molecular_kernel": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    report["report_digest"] = _digest(report)
    return report


def build_authorization(
    report: Mapping[str, Any], *, report_sha256: str, run_id: int, job_id: int, run_url: str
) -> dict[str, Any]:
    if (
        report.get("schema") != "v5-final.s11-cap-precheck-item023-static-ci.v1"
        or report.get("status") != "PASS_OUTCOME_FREE_ITEM023_RECOVERY_DESIGN"
        or not all(report.get("checks", {}).values())
        or report.get("declaration_sha256") != _sha(DECLARATION_PATH)
        or report_sha256 != hashlib.sha256(canonical_json_bytes(report)).hexdigest()
        or run_id < 1
        or job_id < 1
        or run_url != f"https://github.com/Reimangod/v5-matched-work-study/actions/runs/{run_id}"
    ):
        raise S11Item023RecoveryError("exact CI evidence is invalid")
    authorization = {
        "schema": "v5-final.s11-cap-precheck-item023-owner-authorization.v1",
        "decision": "GO_EXACT_ITEM_023_ZERO_KERNEL_TERMINAL_RECOVERY_ONLY",
        "owner": "Reimangod",
        "declaration_sha256": _sha(DECLARATION_PATH),
        "declaration_digest": _canonical(DECLARATION_PATH)["declaration_digest"],
        "static_exact_ci": {
            "run_id": run_id,
            "job_id": job_id,
            "run_url": run_url,
            "report_sha256": report_sha256,
            "report": dict(report),
        },
        "authorization": {
            "append_exact_cap_rejection_event": True,
            "terminalize_existing_checkpoint": True,
            "publish_result_without_molecular_kernel": True,
            "preserve_prior_records": True,
            "retry": False,
            "candidate_energy": False,
            "queue_reordering": False,
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
            "release": "NOT_AUTHORIZED",
        },
    }
    authorization["authorization_digest"] = _digest(authorization)
    return authorization


def audit_authorization(*, require_live_incident: bool) -> dict[str, bool]:
    authorization = _canonical(AUTHORIZATION_PATH)
    body = dict(authorization)
    observed = body.pop("authorization_digest", None)
    ci = authorization.get("static_exact_ci", {})
    report = ci.get("report", {})
    checks = {
        "authorization_digest_valid": observed == _digest(body),
        "schema_decision_owner_exact": authorization.get("schema")
        == "v5-final.s11-cap-precheck-item023-owner-authorization.v1"
        and authorization.get("decision")
        == "GO_EXACT_ITEM_023_ZERO_KERNEL_TERMINAL_RECOVERY_ONLY"
        and authorization.get("owner") == "Reimangod",
        "declaration_bound": authorization.get("declaration_sha256") == _sha(DECLARATION_PATH)
        and authorization.get("declaration_digest")
        == _canonical(DECLARATION_PATH)["declaration_digest"],
        "exact_ci_embedded": report.get("schema")
        == "v5-final.s11-cap-precheck-item023-static-ci.v1"
        and report.get("status") == "PASS_OUTCOME_FREE_ITEM023_RECOVERY_DESIGN"
        and all(report.get("checks", {}).values())
        and ci.get("report_sha256")
        == hashlib.sha256(canonical_json_bytes(report)).hexdigest(),
        "scope_exact": authorization.get("authorization", {}).get("retry") is False
        and authorization.get("authorization", {}).get("candidate_energy") is False
        and authorization.get("authorization", {}).get("performance_claim")
        == "NOT_AUTHORIZED",
    }
    if require_live_incident:
        declaration = _canonical(DECLARATION_PATH)
        checks["live_incident_exact"] = (
            not RESULT_PATH.exists()
            and not RECEIPT_PATH.exists()
            and [path.name for path in sorted(RAW_LEDGER_ROOT.glob("*.json"))]
            == [entry["name"] for entry in declaration["raw_ledger_prefix"]]
            and all(
                _sha(RAW_LEDGER_ROOT / entry["name"]) == entry["sha256"]
                for entry in declaration["raw_ledger_prefix"]
            )
            and _sha(CHECKPOINT_PATH) == declaration["outcome_checkpoint_sha256"]
        )
    if not all(checks.values()):
        raise S11Item023RecoveryError("authorization audit failed")
    return checks


def execute_terminal_recovery() -> dict[str, Any]:
    _require_local_preflight()
    audit_s11_authorization(require_current_preflight=True)
    audit_authorization(require_live_incident=True)
    request, cap = _request_cap()
    runner = ParentNativePersistentRunner.open(RAW_LEDGER_ROOT, request=request, cap=cap)
    before = runner.state()
    recorder = runner.resume_work_recorder()
    try:
        recorder._precheck(_binding_delta(), "candidate-generation")
    except ComponentwiseCapRejected:
        pass
    else:
        raise S11Item023RecoveryError("frozen precheck unexpectedly passed")
    runner.persist_new_work_events(recorder.events)
    after_event = runner.state()
    if (
        len(after_event.records) != len(before.records) + 1
        or after_event.work_events[-1].operation != "cap-rejection"
        or after_event.work_events[-1].delta != WorkDelta()
        or after_event.work_total != before.work_total
    ):
        raise S11Item023RecoveryError("exact zero-delta cap event was not appended")
    result = services.recover_frozen_item_result(
        plan=_plan(), item=_item(), raw_ledger_root=RAW_LEDGER_ROOT, result_output=RESULT_PATH
    )
    final_state = runner.state(require_terminal=True)
    completion = {
        "schema": "v5-final.s11-cap-precheck-item023-completion.v1",
        "queue_index": QUEUE_INDEX,
        "item_key": ITEM_KEY,
        "declaration_sha256": _sha(DECLARATION_PATH),
        "authorization_sha256": _sha(AUTHORIZATION_PATH),
        "records_before": len(before.records),
        "records_after": len(final_state.records),
        "work_total_before": asdict(before.work_total),
        "work_total_after": asdict(final_state.work_total),
        "appended_operation": "cap-rejection",
        "appended_delta": asdict(WorkDelta()),
        "terminal": final_state.terminal,
        "result_artifact_digest": result["artifact_digest"],
        "molecular_kernel_executed": False,
        "candidate_energy_evaluations": 0,
        "FCI_reporting_performed": False,
        "performance_claim": False,
    }
    completion["completion_digest"] = _digest(completion)
    write_json_exclusive(COMPLETION_PATH, completion)
    return completion


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-declaration", action="store_true")
    parser.add_argument("--audit-declaration", action="store_true")
    parser.add_argument("--static-report-output", type=Path)
    parser.add_argument("--write-authorization", action="store_true")
    parser.add_argument("--ci-report", type=Path)
    parser.add_argument("--ci-report-sha256")
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--run-url")
    parser.add_argument("--audit-authorization", action="store_true")
    parser.add_argument("--execute-terminal-recovery", action="store_true")
    args = parser.parse_args()
    if args.write_declaration:
        RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
        write_json_exclusive(DECLARATION_PATH, build_declaration())
        print(DECLARATION_PATH)
    elif args.audit_declaration:
        print(json.dumps(audit_declaration(), sort_keys=True))
    elif args.static_report_output:
        write_json_exclusive(args.static_report_output, build_static_report())
        print(args.static_report_output)
    elif args.write_authorization:
        if not all((args.ci_report, args.ci_report_sha256, args.run_id, args.job_id, args.run_url)):
            raise S11Item023RecoveryError("authorization requires exact CI arguments")
        write_json_exclusive(
            AUTHORIZATION_PATH,
            build_authorization(
                _canonical(args.ci_report),
                report_sha256=args.ci_report_sha256,
                run_id=args.run_id,
                job_id=args.job_id,
                run_url=args.run_url,
            ),
        )
        print(AUTHORIZATION_PATH)
    elif args.audit_authorization:
        print(json.dumps(audit_authorization(require_live_incident=False), sort_keys=True))
    elif args.execute_terminal_recovery:
        print(json.dumps(execute_terminal_recovery(), sort_keys=True))
    else:
        parser.error("one action is required")


if __name__ == "__main__":
    main()
