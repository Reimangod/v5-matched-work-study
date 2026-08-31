"""Freeze the pre-outcome item-023 relation-metadata engineering incident."""

from __future__ import annotations

import argparse
from dataclasses import asdict, fields
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from dvg_obs_ceo.block_ir import CompressionCandidate
from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .parent_native_persistent_runner import replay_raw_ledger
from .s0_successor import ROOT
from .s11_v2_execution_readiness_v7 import OUTPUT as READINESS_V7
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-item023-incident-v1"
OUTPUT = OUTPUT_DIR / "relation-metadata-incident-v1.json"
PRODUCTION_ROOT = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1"
)
CAP_FREEZE = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-outcome-cap-freeze-v1"
    / "outcome-cap-freeze-v1.json"
)
P7_V5 = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-preexecution-gate-v5"
    / "p7-go-v5.json"
)
FAILING_SOURCE = ROOT / "src/v5_final/s11_v2_relation_aware_symbolic_precheck_v1.py"
STEM = "0023-dc3c97796d359265"
DISPATCH = PRODUCTION_ROOT / "dispatch" / f"{STEM}.json"
RAW_ROOT = PRODUCTION_ROOT / "raw-ledgers" / STEM
OUTCOME_CHECKPOINT = RAW_ROOT.with_suffix(".outcome.json")
VERIFIER_ROOT = PRODUCTION_ROOT / "verifier-ledgers" / STEM
RESULT = PRODUCTION_ROOT / "results" / f"{STEM}.json"
RECEIPT = PRODUCTION_ROOT / "receipts" / f"{STEM}.json"
PROGRESS = PRODUCTION_ROOT / "progress/0024-terminal.json"
QUEUE_INDEX = 23
DECISION = "NO_GO_S11_V2_ITEM023_RELATION_METADATA_PRECHECK"


class S11V2Item023RelationMetadataIncidentError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S11V2Item023RelationMetadataIncidentError(
            f"invalid JSON: {path}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S11V2Item023RelationMetadataIncidentError(
            f"noncanonical JSON: {path}"
        )
    return value


def _embedded_digest(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return isinstance(observed, str) and observed == _digest(body)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.rstrip("\n")


def _evidence_paths() -> tuple[Path, ...]:
    return (DISPATCH, *sorted(RAW_ROOT.glob("*.json")))


def inspect_incident() -> dict[str, Any]:
    readiness = _load(READINESS_V7)
    dispatch = _load(DISPATCH)
    adapter = QueueV2NativeAdapter()
    request = adapter.request(adapter.queue["items"][QUEUE_INDEX]["queue_item_id"])
    replay = replay_raw_ledger(
        RAW_ROOT,
        request=request.work_request,
        cap=request.outcome_cap,
        require_terminal=False,
    )
    raw_records = [_load(path) for path in sorted(RAW_ROOT.glob("*.json"))]
    rollbacks = [
        record["payload"]
        for record in raw_records
        if record.get("kind") == "attempt-rollback"
    ]
    work_total = asdict(replay.work_total)
    raw_operations = [event.operation for event in replay.work_events]
    parent_fields = {field.name for field in fields(CompressionCandidate)}
    checks = {
        "readiness_v7_was_GO": readiness.get("decision")
        == "GO_S11_V2_FROZEN_QUEUE_CONTINUATION_FROM_INDEX_23"
        and _embedded_digest(readiness, "readiness_digest"),
        "dispatch_is_exact_item023": dispatch["queue_index"] == QUEUE_INDEX
        and dispatch["queue_item_id"] == request.item["queue_item_id"]
        and dispatch["execution_readiness_digest"] == readiness["readiness_digest"]
        and dispatch["outcome_cap_digest"]
        == request.item["outcome_work_cap"]["cap_digest"]
        and dispatch["verifier_cap_digest"]
        == request.item["verifier_componentwise_cap_digest"],
        "raw_chain_unterminated_and_rolled_back": replay.terminal is None
        and replay.active_attempt_id is None
        and len(raw_records) == 5
        and len(rollbacks) == 1
        and rollbacks[0]["component_digests_before"]
        == rollbacks[0]["component_digests_after"]
        and rollbacks[0]["reason"] == "RelationAwareSymbolicPrecheckError",
        "source_work_preserved_only": raw_operations
        == ["full-physical-resource-recount", "statevector-recomputation"]
        and work_total["resource_recounts"] == 1
        and work_total["statevector_recomputations"] == 1
        and work_total["energy_evaluations"] == 0
        and work_total["optimizer_starts"] == 0
        and work_total["optimizer_iterations"] == 0,
        "verifier_and_outcome_artifacts_absent": not VERIFIER_ROOT.exists()
        and not OUTCOME_CHECKPOINT.exists()
        and not RESULT.exists()
        and not RECEIPT.exists()
        and not PROGRESS.exists(),
        "actual_parent_relation_shape_is_distinct": "transformation" in parent_fields
        and "jacobian" not in parent_fields
        and hasattr(CompressionCandidate, "__dataclass_fields__"),
        "queue_cap_P7_are_unchanged": _sha(QUEUE_V2)
        == "be88c730f7ba44efd8867c0bf571ecb01afe0349d68e5fdc11733e67c779b1b4"
        and _sha(CAP_FREEZE)
        == "3f0b7c5a8c09dcfb9e5553231894a923efc1e87bd92a6dde54afd5f028a68fb9"
        and _sha(P7_V5)
        == "7ffd316208758bd4a5f63357b0e74b6b8f4df7fac0fe9a1e0b42240d70eb3a63",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item023RelationMetadataIncidentError(failures)
    return {
        "checks": checks,
        "observed": {
            "queue_index": QUEUE_INDEX,
            "queue_item_id": request.item["queue_item_id"],
            "case_id": request.item["case_id"],
            "method_id": request.method_id,
            "work_envelope": request.item["work_envelope"],
            "raw_record_count": len(raw_records),
            "raw_work_total": work_total,
            "raw_operations": raw_operations,
            "rollback_reason": rollbacks[0]["reason"],
            "rollback_component_digests": rollbacks[0][
                "component_digests_after"
            ],
            "parent_relation_fields": sorted(parent_fields),
            "candidate_energy_evaluations": 0,
            "optimizer_starts": 0,
            "FCI_evaluations": 0,
            "N_dense_expm": 0,
            "terminal_prefix": 23,
        },
        "bindings": {
            "readiness_v7_sha256": _sha(READINESS_V7),
            "readiness_v7_digest": readiness["readiness_digest"],
            "queue_sha256": _sha(QUEUE_V2),
            "queue_digest": adapter.queue["queue_digest"],
            "cap_freeze_sha256": _sha(CAP_FREEZE),
            "P7_v5_sha256": _sha(P7_V5),
            "pre_retry_last_record_digest": replay.records[-1]["record_digest"],
            "failing_source_sha256": _sha(FAILING_SOURCE),
            "evidence_sha256": {
                str(path.relative_to(ROOT)): _sha(path)
                for path in _evidence_paths()
            },
        },
    }


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S11V2Item023RelationMetadataIncidentError(
            "item023 incident artifact already exists"
        )
    if _git("status", "--porcelain"):
        raise S11V2Item023RelationMetadataIncidentError(
            "capture requires a clean worktree"
        )
    body = {
        "schema": "v5-final.s11-v2-item023-relation-metadata-incident.v1",
        "stage": "PHASE_C_ITEM023_PRE_OUTCOME_UNTERMINATED",
        "status": DECISION,
        "decision": DECISION,
        "repository_head": _git("rev-parse", "HEAD"),
        **inspect_incident(),
        "root_cause": (
            "The conservative precheck accepted only the serialized fixture shape "
            "with a direct jacobian field. Actual parent CompressionCandidate "
            "objects store the same registered relation Jacobian under "
            "transformation.jacobian, so the precheck failed closed before Verifier V2."
        ),
        "disposition": {
            "item023_partial_evidence": "PRESERVE_APPEND_ONLY",
            "item023_retry": "NOT_AUTHORIZED_PENDING_ADDITIVE_RETRY_GATE",
            "item024_and_later": "NOT_AUTHORIZED_PENDING_READINESS_SUCCESSOR",
            "readiness_v7": "SUSPENDED_AFTER_ENGINEERING_INCIDENT",
            "queue_v2": "PRESERVE_IMMUTABLE",
            "outcome_and_verifier_caps": "PRESERVE_IMMUTABLE",
            "FCI_reporting": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "required_remediation": [
            "Normalize all registered relation metadata shapes without changing arity semantics.",
            "Run the conservative invariant over actual CompressionCandidate catalogs for every frozen source case.",
            "Reject unknown, ambiguous, or inconsistent direct/nested metadata fail-closed.",
            "Freeze an additive same-item retry gate bound to this rollback digest.",
            "Freeze a readiness successor before retrying item023.",
        ],
        "scientific_boundary": (
            "No candidate energy, optimizer, Verifier V2 numeric session, FCI, "
            "dense matrix exponential, terminal result, or performance comparison "
            "was produced. This is an infrastructure-schema incident."
        ),
    }
    body["incident_digest"] = _digest(body)
    return body


def write_artifact() -> None:
    artifact = capture()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(OUTPUT, artifact)


def audit_frozen() -> dict[str, Any]:
    artifact = _load(OUTPUT)
    checks = {
        "incident_digest_valid": _embedded_digest(artifact, "incident_digest"),
        "decision_exact": artifact.get("decision") == DECISION,
        "all_checks_passed": all(artifact.get("checks", {}).values()),
        "artifact_immutable": artifact_is_immutable_git_blob(OUTPUT),
        "bound_evidence_unchanged": all(
            _sha(ROOT / path) == expected
            for path, expected in artifact["bindings"]["evidence_sha256"].items()
        ),
        "retry_and_continuation_closed": artifact["disposition"]["item023_retry"]
        == "NOT_AUTHORIZED_PENDING_ADDITIVE_RETRY_GATE"
        and artifact["disposition"]["item024_and_later"]
        == "NOT_AUTHORIZED_PENDING_READINESS_SUCCESSOR",
        "FCI_performance_closed": artifact["disposition"]["FCI_reporting"]
        == "NOT_AUTHORIZED"
        and artifact["disposition"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S11V2Item023RelationMetadataIncidentError(failures)
    return {"decision": artifact["decision"], "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.capture:
        write_artifact()
    if args.audit or not args.capture:
        print(json.dumps(audit_frozen(), sort_keys=True))


if __name__ == "__main__":
    main()
