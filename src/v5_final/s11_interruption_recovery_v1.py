"""Append-only recovery for one interrupted S11 development item.

The normal S11 runner intentionally refuses to guess how an active raw ledger
should be resumed after process loss.  This module implements the narrower
frozen policy: declare the exact interruption, require exact CI and repository
owner authorization, roll the active attempt back without deleting records,
start one digest-linked system retry, and execute the same frozen queue item.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import tempfile
from typing import Any, Mapping

import numpy as np

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import manifest_matches_artifact_commit, manifest_matches_commit
from . import parent_native_execution_services as services
from . import s9_h2_h4_calibration_runner as core
from .parent_native_development_execution_v1 import development_runtime_scope
from .parent_native_persistent_runner import (
    ParentNativePersistentRunner,
    ParentNativePersistentRunnerError,
    make_attempt_id,
    replay_raw_ledger,
)
from .parent_native_work_accounting import ComponentwiseCapRejected, work_cap_digest
from .parent_native_zero_dimensional_v2 import zero_dimensional_boundary_scope
from .semantic_contract_v2 import WorkDelta
from .s0_successor import ROOT
from .s11_development_runner_v1 import (
    AUTHORIZATION_PATH as S11_AUTHORIZATION_PATH,
    DISPATCH_DIR,
    EXECUTION_DIR,
    FREEZE_OUTPUT,
    PLAN_PATH,
    RAW_DIR,
    READINESS_PATH,
    RECEIPT_DIR,
    RESULT_DIR,
    RUNNER_SOURCES,
    _json,
    _plan,
    _require_local_preflight,
    audit_authorization as audit_s11_authorization,
    audit_progress,
)


QUEUE_INDEX = 17
ITEM_KEY = "017-d8029902227d0abbe463f322e708c2c4cfaecb5bebb1b6025b3a1470a9ac08f0"
RECOVERY_DIR = EXECUTION_DIR / "interruption-recovery" / ITEM_KEY
DECLARATION_PATH = RECOVERY_DIR / "incident-declaration-v1.json"
AUTHORIZATION_PATH = RECOVERY_DIR / "owner-recovery-authorization-v1.json"
PREPARATION_RECEIPT_PATH = RECOVERY_DIR / "rollback-retry-preparation-v1.json"
RAW_LEDGER_ROOT = RAW_DIR / ITEM_KEY
CHECKPOINT_PATH = RAW_DIR / f"{ITEM_KEY}.outcome.json"
RESULT_PATH = RESULT_DIR / f"{ITEM_KEY}.json"
RECEIPT_PATH = RECEIPT_DIR / f"{ITEM_KEY}.json"
DISPATCH_PATH = DISPATCH_DIR / f"{ITEM_KEY}.json"
RECOVERY_SOURCES = (
    ROOT / "src/v5_final/s11_interruption_recovery_v1.py",
    ROOT / "tests/test_v5_final_s11_interruption_recovery_v1.py",
    ROOT / ".github/workflows/v5-s11-interruption-recovery-gate.yml",
)
EXPECTED_INTERRUPTED_OPERATIONS = (
    "full-physical-resource-recount",
    "statevector-recomputation",
)
RETRY_NONCE = "s11-item-017-system-interruption-retry-2"


class S11InterruptionRecoveryError(RuntimeError):
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
        raise S11InterruptionRecoveryError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11InterruptionRecoveryError(f"noncanonical JSON: {path}")
    return value


def _item() -> dict[str, Any]:
    plan = _plan()
    item = dict(plan["items"][QUEUE_INDEX])
    if (
        item.get("queue_item_id")
        != "development-queue-item-v4:d8029902227d0abbe463f322e708c2c4cfaecb5bebb1b6025b3a1470a9ac08f0"
        or item.get("method_id") != "v5-sequential-with-rebuilding"
        or item.get("work_envelope") != "HIGH"
        or item.get("retry_policy")
        != "system-failure-only; preserve prior attempt and link digest"
    ):
        raise S11InterruptionRecoveryError("frozen recovery item identity drifted")
    return item


def _request_cap() -> tuple[Any, WorkDelta]:
    plan = _plan()
    item = _item()
    cap = WorkDelta(**dict(item["componentwise_work_cap"]))
    request = services._work_request(item, plan)
    if work_cap_digest(cap) != item["work_cap_digest"]:
        raise S11InterruptionRecoveryError("frozen recovery cap digest drifted")
    return request, cap


def _initial_record_paths() -> list[Path]:
    if not RAW_LEDGER_ROOT.is_dir():
        raise S11InterruptionRecoveryError("interrupted raw ledger is absent")
    paths = sorted(RAW_LEDGER_ROOT.glob("*.json"))
    if len(paths) < 4:
        raise S11InterruptionRecoveryError("interrupted ledger prefix is incomplete")
    return paths[:4]


def _embedded_replay(record: Mapping[str, Any]) -> Any:
    request, cap = _request_cap()
    with tempfile.TemporaryDirectory(prefix="s11-interruption-declaration-") as tmp:
        root = Path(tmp) / ITEM_KEY
        root.mkdir()
        for entry in record["interrupted_ledger_prefix"]:
            write_json_exclusive(root / entry["name"], entry["record"])
        try:
            return replay_raw_ledger(root, request=request, cap=cap)
        except ParentNativePersistentRunnerError as error:
            raise S11InterruptionRecoveryError(
                "embedded interrupted ledger does not replay exactly"
            ) from error


def build_declaration() -> dict[str, Any]:
    progress = audit_progress(allow_inflight=True)["progress"]
    if progress["completed_terminal_count"] != QUEUE_INDEX:
        raise S11InterruptionRecoveryError("recovery requires an exact 17-item prefix")
    request, cap = _request_cap()
    state = replay_raw_ledger(RAW_LEDGER_ROOT, request=request, cap=cap)
    paths = sorted(RAW_LEDGER_ROOT.glob("*.json"))
    if (
        len(paths) != 4
        or state.terminal is not None
        or state.active_attempt_id is None
        or len(state.attempt_ids) != 1
        or tuple(event.operation for event in state.work_events)
        != EXPECTED_INTERRUPTED_OPERATIONS
        or any(event.operation == "candidate-energy-evaluation" for event in state.work_events)
        or CHECKPOINT_PATH.exists()
        or RESULT_PATH.exists()
        or RECEIPT_PATH.exists()
    ):
        raise S11InterruptionRecoveryError("local incident is not the exact declared interruption")
    dispatch = _canonical(DISPATCH_PATH)
    declaration: dict[str, Any] = {
        "schema": "v5-final.s11-item-interruption-declaration.v1",
        "status": "DECLARED_OUTCOME_FREE_SYSTEM_INTERRUPTION",
        "decision": "NO_EXECUTION_PENDING_EXACT_CI_AND_OWNER_RECOVERY_AUTHORIZATION",
        "queue_index": QUEUE_INDEX,
        "item_key": ITEM_KEY,
        "plan_digest": _plan()["plan_digest"],
        "plan_sha256": _sha(PLAN_PATH),
        "freeze_sha256": _sha(FREEZE_OUTPUT),
        "s11_authorization_sha256": _sha(S11_AUTHORIZATION_PATH),
        "frozen_item": _item(),
        "dispatch": dispatch,
        "dispatch_sha256": _sha(DISPATCH_PATH),
        "interrupted_ledger_prefix": [
            {"name": path.name, "sha256": _sha(path), "record": _canonical(path)}
            for path in paths
        ],
        "observed_state": {
            "attempt_count": 1,
            "active_attempt_id": state.active_attempt_id,
            "terminal_absent": True,
            "outcome_checkpoint_absent": True,
            "result_absent": True,
            "receipt_absent": True,
            "durable_work_total": asdict(state.work_total),
            "durable_operations": [event.operation for event in state.work_events],
            "candidate_energy_evaluations": 0,
        },
        "interruption_class": "UNEXPECTED_PROCESS_TERMINATION_WITHOUT_TERMINAL_CHECKPOINT",
        "recovery_policy": {
            "append_only": True,
            "delete_or_replace_prior_records": False,
            "retry_reason": "SYSTEM_PROCESS_INTERRUPTION",
            "retry_ordinal": 2,
            "retry_nonce": RETRY_NONCE,
            "preserve_all_prior_work": True,
            "require_exact_component_rollback": True,
            "same_frozen_item_only": True,
            "queue_reordering": False,
        },
        "frozen_runner_source_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in RUNNER_SOURCES
        ],
        "recovery_source_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in RECOVERY_SOURCES
        ],
        "authorization": {
            "rollback_or_retry": "NOT_AUTHORIZED_PENDING_EXACT_CI_AND_OWNER_ARTIFACT",
            "candidate_energy": "NOT_AUTHORIZED_BY_THIS_DECLARATION",
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
    state = _embedded_replay(declaration)
    checks = {
        "declaration_digest_valid": observed_digest == _digest(body),
        "schema_status_decision_exact": declaration.get("schema")
        == "v5-final.s11-item-interruption-declaration.v1"
        and declaration.get("status") == "DECLARED_OUTCOME_FREE_SYSTEM_INTERRUPTION"
        and declaration.get("decision")
        == "NO_EXECUTION_PENDING_EXACT_CI_AND_OWNER_RECOVERY_AUTHORIZATION",
        "exact_frozen_item_bound": declaration.get("queue_index") == QUEUE_INDEX
        and declaration.get("item_key") == ITEM_KEY
        and declaration.get("frozen_item") == _item()
        and declaration.get("plan_digest") == _plan()["plan_digest"]
        and declaration.get("plan_sha256") == _sha(PLAN_PATH)
        and declaration.get("freeze_sha256") == _sha(FREEZE_OUTPUT),
        "dispatch_bound": declaration.get("dispatch", {}).get("queue_index")
        == QUEUE_INDEX
        and declaration.get("dispatch", {}).get("queue_item_id")
        == _item()["queue_item_id"]
        and declaration.get("dispatch_sha256")
        == hashlib.sha256(canonical_json_bytes(declaration.get("dispatch"))).hexdigest(),
        "interrupted_chain_replays": state.terminal is None
        and state.active_attempt_id == declaration["observed_state"]["active_attempt_id"]
        and len(state.attempt_ids) == 1
        and len(state.records) == 4,
        "embedded_file_hashes_exact": all(
            entry["sha256"] == hashlib.sha256(
                canonical_json_bytes(entry["record"])
            ).hexdigest()
            for entry in declaration["interrupted_ledger_prefix"]
        ),
        "durable_work_exact": asdict(state.work_total)
        == declaration["observed_state"]["durable_work_total"]
        and [event.operation for event in state.work_events]
        == list(EXPECTED_INTERRUPTED_OPERATIONS),
        "candidate_energy_zero": declaration["observed_state"][
            "candidate_energy_evaluations"
        ]
        == 0
        and all(
            event.operation != "candidate-energy-evaluation"
            for event in state.work_events
        ),
        "retry_policy_exact": declaration.get("recovery_policy")
        == {
            "append_only": True,
            "delete_or_replace_prior_records": False,
            "retry_reason": "SYSTEM_PROCESS_INTERRUPTION",
            "retry_ordinal": 2,
            "retry_nonce": RETRY_NONCE,
            "preserve_all_prior_work": True,
            "require_exact_component_rollback": True,
            "same_frozen_item_only": True,
            "queue_reordering": False,
        },
        "frozen_sources_unchanged": [
            entry["path"]
            for entry in declaration["frozen_runner_source_manifest"]
        ]
        == [str(path.relative_to(ROOT)) for path in RUNNER_SOURCES]
        and manifest_matches_commit(
            declaration["frozen_runner_source_manifest"],
            _json(READINESS_PATH)["validated_runner_commit"],
        ),
        "recovery_sources_unchanged": [
            entry["path"] for entry in declaration["recovery_source_manifest"]
        ]
        == [str(path.relative_to(ROOT)) for path in RECOVERY_SOURCES]
        and manifest_matches_artifact_commit(
            DECLARATION_PATH, declaration["recovery_source_manifest"]
        ),
        "claims_blocked": declaration.get("authorization")
        == {
            "rollback_or_retry": "NOT_AUTHORIZED_PENDING_EXACT_CI_AND_OWNER_ARTIFACT",
            "candidate_energy": "NOT_AUTHORIZED_BY_THIS_DECLARATION",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
            "release": "NOT_AUTHORIZED",
        },
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11InterruptionRecoveryError(
            "interruption declaration audit failed: " + ", ".join(failures)
        )
    return checks


def build_static_report() -> dict[str, Any]:
    checks = audit_declaration()
    report = {
        "schema": "v5-final.s11-interruption-recovery-static-ci.v1",
        "validated_exact_commit": __import__("subprocess").check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "status": "PASS_OUTCOME_FREE_INTERRUPTION_RECOVERY_DESIGN",
        "decision": "READY_AWAITING_OWNER_RECOVERY_AUTHORIZATION",
        "declaration_sha256": _sha(DECLARATION_PATH),
        "declaration_digest": _canonical(DECLARATION_PATH)["declaration_digest"],
        "checks": checks,
        "authorization": {
            "rollback_or_retry": "NOT_AUTHORIZED",
            "candidate_energy": "NOT_AUTHORIZED",
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
        report.get("schema") != "v5-final.s11-interruption-recovery-static-ci.v1"
        or report.get("status") != "PASS_OUTCOME_FREE_INTERRUPTION_RECOVERY_DESIGN"
        or report.get("decision") != "READY_AWAITING_OWNER_RECOVERY_AUTHORIZATION"
        or not all(report.get("checks", {}).values())
        or report.get("declaration_sha256") != _sha(DECLARATION_PATH)
        or report_sha256 != hashlib.sha256(canonical_json_bytes(report)).hexdigest()
        or run_id < 1
        or job_id < 1
        or run_url
        != f"https://github.com/Reimangod/v5-matched-work-study/actions/runs/{run_id}"
    ):
        raise S11InterruptionRecoveryError("exact recovery CI evidence is invalid")
    authorization = {
        "schema": "v5-final.s11-item-interruption-owner-authorization.v1",
        "decision": "GO_EXACT_ITEM_017_SYSTEM_RETRY_ONLY",
        "owner": "Reimangod",
        "owner_directive": (
            "終わるまで続けて行って。常に学術的な価値とシステム"
            "エンジニアリング的な安全性を確認しながら進めて。"
        ),
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
            "exact_component_rollback_attempt_1": True,
            "digest_linked_system_retry_attempt_2": True,
            "execute_same_frozen_item_once": True,
            "preserve_all_prior_records_and_work": True,
            "delete_or_replace_prior_records": False,
            "queue_reordering": False,
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
            "release": "NOT_AUTHORIZED",
        },
    }
    authorization["authorization_digest"] = _digest(authorization)
    return authorization


def audit_recovery_authorization(*, require_current_incident: bool) -> dict[str, bool]:
    declaration_checks = audit_declaration()
    authorization = _canonical(AUTHORIZATION_PATH)
    body = dict(authorization)
    observed_digest = body.pop("authorization_digest", None)
    report = authorization["static_exact_ci"]["report"]
    ci = authorization["static_exact_ci"]
    checks = {
        "authorization_digest_valid": observed_digest == _digest(body),
        "schema_decision_owner_exact": authorization.get("schema")
        == "v5-final.s11-item-interruption-owner-authorization.v1"
        and authorization.get("decision") == "GO_EXACT_ITEM_017_SYSTEM_RETRY_ONLY"
        and authorization.get("owner") == "Reimangod",
        "declaration_bound": authorization.get("declaration_sha256")
        == _sha(DECLARATION_PATH)
        and authorization.get("declaration_digest")
        == _canonical(DECLARATION_PATH)["declaration_digest"]
        and all(declaration_checks.values()),
        "exact_ci_embedded": report.get("schema")
        == "v5-final.s11-interruption-recovery-static-ci.v1"
        and report.get("status")
        == "PASS_OUTCOME_FREE_INTERRUPTION_RECOVERY_DESIGN"
        and report.get("decision") == "READY_AWAITING_OWNER_RECOVERY_AUTHORIZATION"
        and all(report.get("checks", {}).values())
        and ci.get("report_sha256")
        == hashlib.sha256(canonical_json_bytes(report)).hexdigest()
        and ci.get("run_url")
        == f"https://github.com/Reimangod/v5-matched-work-study/actions/runs/{ci.get('run_id')}"
        and isinstance(ci.get("job_id"), int)
        and ci["job_id"] > 0,
        "recovery_scope_exact": authorization.get("authorization")
        == {
            "exact_component_rollback_attempt_1": True,
            "digest_linked_system_retry_attempt_2": True,
            "execute_same_frozen_item_once": True,
            "preserve_all_prior_records_and_work": True,
            "delete_or_replace_prior_records": False,
            "queue_reordering": False,
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
            "release": "NOT_AUTHORIZED",
        },
        "current_incident_exact_if_required": True,
    }
    if require_current_incident:
        request, cap = _request_cap()
        state = replay_raw_ledger(RAW_LEDGER_ROOT, request=request, cap=cap)
        prefix = _canonical(DECLARATION_PATH)["interrupted_ledger_prefix"]
        current = sorted(RAW_LEDGER_ROOT.glob("*.json"))
        checks["current_incident_exact_if_required"] = (
            len(current) == 4
            and all(_sha(path) == entry["sha256"] for path, entry in zip(current, prefix))
            and state.active_attempt_id is not None
            and state.terminal is None
            and not CHECKPOINT_PATH.exists()
            and not RESULT_PATH.exists()
            and not RECEIPT_PATH.exists()
        )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11InterruptionRecoveryError(
            "recovery authorization audit failed: " + ", ".join(failures)
        )
    return checks


def prepare_retry() -> dict[str, Any]:
    _require_local_preflight()
    audit_s11_authorization(require_current_preflight=True)
    audit_recovery_authorization(require_current_incident=True)
    if PREPARATION_RECEIPT_PATH.exists():
        raise S11InterruptionRecoveryError("retry preparation already exists")
    capacity_before = core._current_capacity()
    if not capacity_before["passed"]:
        raise S11InterruptionRecoveryError("capacity failed before rollback preparation")
    plan = _plan()
    item = _item()
    request, cap = _request_cap()
    runner = ParentNativePersistentRunner.open(
        RAW_LEDGER_ROOT, request=request, cap=cap
    )
    recorder = runner.resume_work_recorder()
    boundary = services.DurableWorkBoundary(runner, recorder)
    random.seed(int(item["RNG_identity"]["python_seed"]))
    np.random.seed(int(item["RNG_identity"]["numpy_seed"]))
    with development_runtime_scope(), zero_dimensional_boundary_scope():
        context = services.build_queue_bound_runtime_v2(
            str(item["queue_item_id"]), plan_record=plan, work_recorder=boundary
        )
        before = services._component_snapshot_digest(context.runtime)
        snapshot = context.runtime.snapshot()
        context.runtime.restore(snapshot)
        after = services._component_snapshot_digest(context.runtime)
    if before != after:
        raise S11InterruptionRecoveryError("reconstructed component rollback is not exact")
    state_before = runner.state()
    runner.rollback_active_attempt(
        component_digests_before=before,
        component_digests_after=after,
        reason="SYSTEM_PROCESS_INTERRUPTION_EXACT_RECONSTRUCTED_ROLLBACK",
    )
    retry_id = make_attempt_id(request, ordinal=2, nonce=RETRY_NONCE)
    runner.start_retry(retry_id)
    state_after = runner.state()
    capacity_after = core._current_capacity()
    receipt = {
        "schema": "v5-final.s11-interruption-rollback-retry-preparation.v1",
        "queue_index": QUEUE_INDEX,
        "queue_item_id": item["queue_item_id"],
        "declaration_sha256": _sha(DECLARATION_PATH),
        "authorization_sha256": _sha(AUTHORIZATION_PATH),
        "prior_attempt_id": state_before.active_attempt_id,
        "retry_attempt_id": retry_id,
        "record_count_before_rollback": len(state_before.records),
        "record_count_after_retry_start": len(state_after.records),
        "all_prior_work_preserved": asdict(state_after.work_total)
        == asdict(state_before.work_total),
        "component_digests_before": before,
        "component_digests_after": after,
        "capacity_before": capacity_before,
        "capacity_after": capacity_after,
        "candidate_energy_before_retry": sum(
            event.operation == "candidate-energy-evaluation"
            for event in state_before.work_events
        ),
        "FCI_reporting_performed": False,
        "performance_claim": False,
    }
    receipt["preparation_digest"] = _digest(receipt)
    RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(PREPARATION_RECEIPT_PATH, receipt)
    if not capacity_after["passed"]:
        raise S11InterruptionRecoveryError("capacity failed after retry preparation")
    return receipt


def execute_retry() -> dict[str, Any]:
    _require_local_preflight()
    audit_s11_authorization(require_current_preflight=True)
    audit_recovery_authorization(require_current_incident=False)
    preparation = _canonical(PREPARATION_RECEIPT_PATH)
    body = dict(preparation)
    observed = body.pop("preparation_digest", None)
    if observed != _digest(body) or preparation.get("all_prior_work_preserved") is not True:
        raise S11InterruptionRecoveryError("retry preparation receipt is invalid")
    if CHECKPOINT_PATH.exists() or RESULT_PATH.exists() or RECEIPT_PATH.exists():
        raise S11InterruptionRecoveryError("retry output already exists")
    plan = _plan()
    item = _item()
    request, cap = _request_cap()
    runner = ParentNativePersistentRunner.open(
        RAW_LEDGER_ROOT, request=request, cap=cap
    )
    if runner.state().active_attempt_id != preparation["retry_attempt_id"]:
        raise S11InterruptionRecoveryError("exact authorized retry attempt is not active")
    random.seed(int(item["RNG_identity"]["python_seed"]))
    np.random.seed(int(item["RNG_identity"]["numpy_seed"]))
    recorder = runner.resume_work_recorder()
    boundary = services.DurableWorkBoundary(runner, recorder)
    context = None
    snapshots = None
    source_snapshot = None
    try:
        with development_runtime_scope(), zero_dimensional_boundary_scope():
            context = services.build_queue_bound_runtime_v2(
                str(item["queue_item_id"]), plan_record=plan, work_recorder=boundary
            )
            snapshots = services._component_snapshot_digest(context.runtime)
            source_snapshot = context.runtime.snapshot()
            algorithm = context.release_for_h2_h4_execution()
            binding = item["candidate_work_binding"]
            expected_binding = dict(binding)
            observed_binding = expected_binding.pop("binding_digest")
            if observed_binding != services._digest(expected_binding):
                raise S11InterruptionRecoveryError("candidate work binding digest mismatch")
            projected = WorkDelta(
                candidate_generations=int(binding["candidate_generation_count"]),
                search_states=int(binding["unique_search_state_count"]),
                resource_recounts=int(binding["resource_recounts"]),
                rewrite_verifications=int(binding["rewrite_verifications"]),
            )
            recorder._precheck(projected, "candidate-generation")
            if binding.get("schema") != "v5-final.parent-native-candidate-work-binding.v2":
                raise S11InterruptionRecoveryError("candidate work binding schema mismatch")
            context.runtime.metadata["candidate_work_binding"] = dict(binding)
            prepared = services.prepare_method_executor(context, item)
            boundary.persist_structural_binding(binding)
            executor_services = services.ParentNativeExecutionServices(
                item=item,
                plan=plan,
                runner=runner,
                boundary=boundary,
                algorithm=algorithm,
            )
            result = prepared.execute(executor_services)
            outcome_payload = {
                "queue_item_id": item["queue_item_id"],
                "method_id": item["method_id"],
                "case_id": item["case_id"],
                "work_envelope": item["work_envelope"],
                "result": result,
                "work_total": asdict(boundary.total),
                "telemetry": boundary.telemetry,
            }
            write_json_exclusive(
                CHECKPOINT_PATH, services._outcome_checkpoint(request, outcome_payload)
            )
            services._terminalize_checkpoint(
                runner, services._read_outcome_checkpoint(CHECKPOINT_PATH, request)
            )
    except ComponentwiseCapRejected:
        outcome_payload = {
            "queue_item_id": item["queue_item_id"],
            "terminal_status": "CAP_REJECTED",
            "work_total": asdict(boundary.total),
            "telemetry": boundary.telemetry,
        }
        write_json_exclusive(
            CHECKPOINT_PATH, services._outcome_checkpoint(request, outcome_payload)
        )
        services._terminalize_checkpoint(
            runner, services._read_outcome_checkpoint(CHECKPOINT_PATH, request)
        )
    except BaseException as error:
        if CHECKPOINT_PATH.is_file():
            raise S11InterruptionRecoveryError(
                "outcome checkpoint is durable; recover without molecular rerun"
            ) from error
        try:
            runner.persist_new_work_events(recorder.events)
            if not any(event.outcome == "failed" for event in recorder.events):
                try:
                    recorder.invoke(
                        "rewrite-verification",
                        lambda: (_ for _ in ()).throw(
                            S11InterruptionRecoveryError(str(error))
                        ),
                        evidence={
                            "phase": "interruption-retry-integrity-validation",
                            "original_exception_type": type(error).__name__,
                        },
                    )
                except S11InterruptionRecoveryError:
                    pass
                runner.persist_new_work_events(recorder.events)
            if snapshots is None:
                seed = _digest(
                    {
                        "StatePreparationID": item["StatePreparationID"],
                        "source_checkpoint_digest": item["source_checkpoint_digest"],
                    }
                )
                snapshots = {
                    name: seed
                    for name in (
                        "ansatz",
                        "parameters",
                        "optimizer_inverse_hessian",
                        "resources",
                        "ledger_transaction",
                    )
                }
            after = snapshots
            if context is not None and source_snapshot is not None:
                context.runtime.restore(source_snapshot)
                after = services._component_snapshot_digest(context.runtime)
            runner.rollback_active_attempt(
                component_digests_before=snapshots,
                component_digests_after=after,
                reason=type(error).__name__,
            )
            runner.finish("KERNEL_FAILURE", rejection_reason=type(error).__name__)
        except BaseException as terminal_error:
            raise S11InterruptionRecoveryError(
                "retry failed and exact terminalization also failed"
            ) from terminal_error
        raise
    return services.recover_frozen_item_result(
        plan=plan,
        item=item,
        raw_ledger_root=RAW_LEDGER_ROOT,
        result_output=RESULT_PATH,
    )


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
    parser.add_argument("--prepare-retry", action="store_true")
    parser.add_argument("--execute-retry", action="store_true")
    args = parser.parse_args()
    if args.write_declaration:
        RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
        write_json_exclusive(DECLARATION_PATH, build_declaration())
        print(DECLARATION_PATH)
        return
    if args.audit_declaration:
        print(json.dumps(audit_declaration(), sort_keys=True))
        return
    if args.static_report_output is not None:
        write_json_exclusive(args.static_report_output, build_static_report())
        print(args.static_report_output)
        return
    if args.write_authorization:
        if (
            args.ci_report is None
            or args.ci_report_sha256 is None
            or args.run_id is None
            or args.job_id is None
            or args.run_url is None
        ):
            raise S11InterruptionRecoveryError("authorization requires exact CI metadata")
        report = _canonical(args.ci_report)
        if _sha(args.ci_report) != args.ci_report_sha256:
            raise S11InterruptionRecoveryError("provided CI report SHA-256 differs")
        write_json_exclusive(
            AUTHORIZATION_PATH,
            build_authorization(
                report,
                report_sha256=args.ci_report_sha256,
                run_id=args.run_id,
                job_id=args.job_id,
                run_url=args.run_url,
            ),
        )
        print(AUTHORIZATION_PATH)
        return
    if args.prepare_retry:
        print(json.dumps(prepare_retry(), sort_keys=True))
        return
    if args.execute_retry:
        print(json.dumps(execute_retry(), sort_keys=True))
        return
    print(json.dumps(build_static_report(), sort_keys=True))


if __name__ == "__main__":
    main()
