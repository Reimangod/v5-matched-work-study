"""Append-only recovery policy for interrupted S11 queue item 028.

This additive module reuses the already-audited item-017 recovery mechanics
without modifying that historically bound implementation.  Every delegated
operation is scoped to the exact frozen item-028 identity and artifact paths.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import s11_interruption_recovery_v1 as base
from .s0_successor import ROOT


QUEUE_INDEX = 28
ITEM_KEY = "028-d37d71eb9ae63c6b6d90e26850e8cc845172577cb2e2f7b457dec40d2b0315b9"
RECOVERY_DIR = base.EXECUTION_DIR / "interruption-recovery" / ITEM_KEY
DECLARATION_PATH = RECOVERY_DIR / "incident-declaration-v1.json"
AUTHORIZATION_PATH = RECOVERY_DIR / "owner-recovery-authorization-v1.json"
PREPARATION_RECEIPT_PATH = RECOVERY_DIR / "rollback-retry-preparation-v1.json"
RAW_LEDGER_ROOT = base.RAW_DIR / ITEM_KEY
CHECKPOINT_PATH = base.RAW_DIR / f"{ITEM_KEY}.outcome.json"
RESULT_PATH = base.RESULT_DIR / f"{ITEM_KEY}.json"
RECEIPT_PATH = base.RECEIPT_DIR / f"{ITEM_KEY}.json"
DISPATCH_PATH = base.DISPATCH_DIR / f"{ITEM_KEY}.json"
RECOVERY_SOURCES = (
    ROOT / "src/v5_final/s11_interruption_recovery_item028_v1.py",
    ROOT / "tests/test_v5_final_s11_interruption_recovery_item028_v1.py",
    ROOT / ".github/workflows/v5-s11-interruption-recovery-item028-gate.yml",
)
EXPECTED_INTERRUPTED_OPERATIONS = (
    "full-physical-resource-recount",
    "statevector-recomputation",
)
RETRY_NONCE = "s11-item-028-system-interruption-retry-2"
DECISION = "GO_EXACT_ITEM_028_SYSTEM_RETRY_ONLY"

S11InterruptionRecoveryError = base.S11InterruptionRecoveryError


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(path: Path) -> dict[str, Any]:
    return base._canonical(path)


def _item() -> dict[str, Any]:
    item = dict(base._plan()["items"][QUEUE_INDEX])
    if (
        item.get("queue_item_id")
        != "development-queue-item-v4:d37d71eb9ae63c6b6d90e26850e8cc845172577cb2e2f7b457dec40d2b0315b9"
        or item.get("method_id") != "v5-fixed-source-whitelist-no-replenishment"
        or item.get("case_id") != "h6-1.5"
        or item.get("work_envelope") != "MEDIUM"
        or item.get("retry_policy")
        != "system-failure-only; preserve prior attempt and link digest"
    ):
        raise S11InterruptionRecoveryError("frozen recovery item identity drifted")
    return item


@contextmanager
def _configured() -> Iterator[None]:
    replacements = {
        "QUEUE_INDEX": QUEUE_INDEX,
        "ITEM_KEY": ITEM_KEY,
        "RECOVERY_DIR": RECOVERY_DIR,
        "DECLARATION_PATH": DECLARATION_PATH,
        "AUTHORIZATION_PATH": AUTHORIZATION_PATH,
        "PREPARATION_RECEIPT_PATH": PREPARATION_RECEIPT_PATH,
        "RAW_LEDGER_ROOT": RAW_LEDGER_ROOT,
        "CHECKPOINT_PATH": CHECKPOINT_PATH,
        "RESULT_PATH": RESULT_PATH,
        "RECEIPT_PATH": RECEIPT_PATH,
        "DISPATCH_PATH": DISPATCH_PATH,
        "RECOVERY_SOURCES": RECOVERY_SOURCES,
        "EXPECTED_INTERRUPTED_OPERATIONS": EXPECTED_INTERRUPTED_OPERATIONS,
        "RETRY_NONCE": RETRY_NONCE,
        "_item": _item,
    }
    previous = {name: getattr(base, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(base, name, value)
        yield
    finally:
        for name, value in previous.items():
            setattr(base, name, value)


def build_declaration() -> dict[str, Any]:
    with _configured():
        return base.build_declaration()


def audit_declaration(record: Mapping[str, Any] | None = None) -> dict[str, bool]:
    with _configured():
        return base.audit_declaration(record)


def build_static_report() -> dict[str, Any]:
    checks = audit_declaration()
    report = {
        "schema": "v5-final.s11-item028-interruption-recovery-static-ci.v1",
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
        report.get("schema")
        != "v5-final.s11-item028-interruption-recovery-static-ci.v1"
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
        "decision": DECISION,
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


def _audit_recovery_authorization_impl(*, require_current_incident: bool) -> dict[str, bool]:
    declaration_checks = base.audit_declaration()
    authorization = base._canonical(AUTHORIZATION_PATH)
    body = dict(authorization)
    observed_digest = body.pop("authorization_digest", None)
    ci = authorization["static_exact_ci"]
    report = ci["report"]
    checks = {
        "authorization_digest_valid": observed_digest == _digest(body),
        "schema_decision_owner_exact": authorization.get("schema")
        == "v5-final.s11-item-interruption-owner-authorization.v1"
        and authorization.get("decision") == DECISION
        and authorization.get("owner") == "Reimangod",
        "declaration_bound": authorization.get("declaration_sha256")
        == _sha(DECLARATION_PATH)
        and authorization.get("declaration_digest")
        == _canonical(DECLARATION_PATH)["declaration_digest"]
        and all(declaration_checks.values()),
        "exact_ci_embedded": report.get("schema")
        == "v5-final.s11-item028-interruption-recovery-static-ci.v1"
        and report.get("status") == "PASS_OUTCOME_FREE_INTERRUPTION_RECOVERY_DESIGN"
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
        request, cap = base._request_cap()
        state = base.replay_raw_ledger(RAW_LEDGER_ROOT, request=request, cap=cap)
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


def audit_recovery_authorization(*, require_current_incident: bool) -> dict[str, bool]:
    with _configured():
        return _audit_recovery_authorization_impl(
            require_current_incident=require_current_incident
        )


def _delegate_with_authorization(function: Any) -> dict[str, Any]:
    with _configured():
        original = base.audit_recovery_authorization
        base.audit_recovery_authorization = _audit_recovery_authorization_impl
        try:
            return function()
        finally:
            base.audit_recovery_authorization = original


def prepare_retry() -> dict[str, Any]:
    return _delegate_with_authorization(base.prepare_retry)


def execute_retry() -> dict[str, Any]:
    return _delegate_with_authorization(base.execute_retry)


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
        required = (
            args.ci_report,
            args.ci_report_sha256,
            args.run_id,
            args.job_id,
            args.run_url,
        )
        if any(value is None for value in required):
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
