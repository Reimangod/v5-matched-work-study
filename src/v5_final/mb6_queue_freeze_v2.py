"""Build the MB6 v2 successor queue after the MB5.2 bundle identity changed."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import ROOT


V1_DIR = ROOT / "artifacts/v5-final/mb6"
OUTPUT_DIR = ROOT / "artifacts/v5-final/mb6-v2"
V1_ENV = V1_DIR / "execution-environment-v1.json"
V1_CATALOG = V1_DIR / "h2-h4-source-catalog-v1.json"
V1_QUEUE = V1_DIR / "h2-h4-calibration-queue-v1.json"
V1_LEDGER = V1_DIR / "h2-h4-calibration-ledger-root-v1.json"
V1_FREEZE = V1_DIR / "mb6-outcome-blind-freeze-v1.json"
ENV_OUTPUT = OUTPUT_DIR / "execution-environment-v2.json"
CATALOG_OUTPUT = OUTPUT_DIR / "h2-h4-source-catalog-v2.json"
QUEUE_OUTPUT = OUTPUT_DIR / "h2-h4-calibration-queue-v2.json"
LEDGER_OUTPUT = OUTPUT_DIR / "h2-h4-calibration-ledger-root-v2.json"
FREEZE_OUTPUT = OUTPUT_DIR / "mb6-outcome-blind-freeze-v2.json"
DIFF_OUTPUT = OUTPUT_DIR / "mb6-v1-v2-semantic-diff-audit-v1.json"
MB52 = ROOT / "artifacts/v5-final/method-native/mb5-2-actual-production-bindings-v1.json"
DEVELOPMENT_QUEUE = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
DEVELOPMENT_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"


class MB6V2Error(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _with_digest(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result[field] = _digest(result)
    return result


def build_environment() -> dict[str, Any]:
    v1 = _json(V1_ENV)
    mb52 = _json(MB52)
    result = {
        key: copy.deepcopy(value)
        for key, value in v1.items()
        if key not in {"schema", "environment_digest"}
    }
    result["schema"] = "v5-final.mb6-execution-environment.v2"
    result["successor_provenance"] = {
        "v1_path": str(V1_ENV.relative_to(ROOT)),
        "v1_sha256": _sha(V1_ENV),
        "MB5_2_bundle_digest": mb52["implementation_bundle_digest"],
        "scientific_runtime_changed": False,
    }
    return _with_digest(result, "environment_digest")


def build_catalog() -> dict[str, Any]:
    v1 = _json(V1_CATALOG)
    result = {
        key: copy.deepcopy(value)
        for key, value in v1.items()
        if key not in {"schema", "probe_digest"}
    }
    result["schema"] = "v5-final.mb6-outcome-free-source-catalog-probe.v2"
    result["successor_provenance"] = {
        "v1_path": str(V1_CATALOG.relative_to(ROOT)),
        "v1_sha256": _sha(V1_CATALOG),
        "source_case_or_candidate_change": False,
    }
    result["probe_digest"] = _digest(result)
    return result


def _scientific_item(item: dict[str, Any]) -> dict[str, Any]:
    ignored = {
        "queue_item_id",
        "executor_id",
        "executor_source_sha256",
        "executor_bundle_digest",
        "authorization_reference",
        "environment_digest",
    }
    return {key: copy.deepcopy(value) for key, value in item.items() if key not in ignored}


def build_queue(catalog: dict[str, Any], environment: dict[str, Any]) -> dict[str, Any]:
    v1 = _json(V1_QUEUE)
    mb52 = _json(MB52)
    items: list[dict[str, Any]] = []
    for old in v1["items"]:
        item = copy.deepcopy(old)
        identity = mb52["executor_identities"][old["method_id"]]
        item["executor_id"] = identity["executor_id"]
        item["executor_source_sha256"] = identity["source_sha256"]
        item["executor_bundle_digest"] = mb52["implementation_bundle_digest"]
        item["authorization_reference"] = {
            "path": str(MB52.relative_to(ROOT)),
            "sha256": _sha(MB52),
            "decision": mb52["decision"],
        }
        item["environment_digest"] = environment["environment_digest"]
        body = {key: value for key, value in item.items() if key != "queue_item_id"}
        item["queue_item_id"] = "mb6-calibration-item-v2:" + _digest(body)
        items.append(item)
    body = {
        "schema": "v5-final.mb6-h2-h4-calibration-queue.v2",
        "schema_digest": _digest({"schema": "v5-final.mb6-h2-h4-calibration-queue.v2"}),
        "stage": v1["stage"],
        "status": "FROZEN_NOT_AUTHORIZED_FOR_EXECUTION",
        "generation_order": v1["generation_order"],
        "items": items,
        "frozen_item_count": len(items),
        "executor_digest": _digest(mb52["executor_identities"]),
        "executor_bundle_digest": mb52["implementation_bundle_digest"],
        "catalog_digest": catalog["probe_digest"],
        "environment_digest": environment["environment_digest"],
        "existing_development_queue": copy.deepcopy(v1["existing_development_queue"]),
        "candidate_energy_evaluations": 0,
        "successor_provenance": {
            "v1_path": str(V1_QUEUE.relative_to(ROOT)),
            "v1_sha256": _sha(V1_QUEUE),
            "allowed_change_scope": [
                "schema/version and queue/item IDs",
                "executor IDs/source/bundle digests",
                "authorization reference",
                "successor provenance",
            ],
        },
    }
    body["queue_digest"] = _digest(body)
    return body


def build_ledger(queue: dict[str, Any]) -> dict[str, Any]:
    return _with_digest(
        {
            "schema": "v5-final.mb6-calibration-ledger-root.v2",
            "queue_path": str(QUEUE_OUTPUT.relative_to(ROOT)),
            "queue_artifact_sha256": "BOUND_AFTER_EXCLUSIVE_WRITE",
            "queue_digest": queue["queue_digest"],
            "expected_queue_item_ids": [item["queue_item_id"] for item in queue["items"]],
            "expected_queue_count": 36,
            "completed_queue_item_ids": [],
            "segments": [],
            "candidate_energy_evaluations": 0,
            "completeness_contract": {
                "expected_queue_nonempty": True,
                "frozen_queue_count": 36,
                "frozen_queue_artifact_sha256_required": True,
                "expected_queue_digest_must_match": True,
                "every_and_only_expected_item_terminal": True,
                "one_terminal_segment_per_item_after_linked_retries": True,
            },
        },
        "ledger_root_digest",
    )


def bind_ledger_queue_sha(ledger: dict[str, Any], queue_sha: str) -> dict[str, Any]:
    result = copy.deepcopy(ledger)
    result.pop("ledger_root_digest", None)
    result["queue_artifact_sha256"] = queue_sha
    return _with_digest(result, "ledger_root_digest")


def build_semantic_diff(catalog: dict[str, Any], environment: dict[str, Any], queue: dict[str, Any]) -> dict[str, Any]:
    v1_catalog = _json(V1_CATALOG)
    v1_environment = _json(V1_ENV)
    v1_queue = _json(V1_QUEUE)
    catalog_v1_science = {key: value for key, value in v1_catalog.items() if key not in {"schema", "probe_digest"}}
    catalog_v2_science = {key: value for key, value in catalog.items() if key not in {"schema", "probe_digest", "successor_provenance"}}
    env_fields = ("runtime", "required_threads", "dependency_locks", "parent_commit", "CEO_commit", "execution_rule")
    item_pairs = list(zip(v1_queue["items"], queue["items"], strict=True))
    checks = {
        "catalog_scientific_content_identical": catalog_v1_science == catalog_v2_science,
        "runtime_environment_identical": all(v1_environment[field] == environment[field] for field in env_fields),
        "item_count_36": len(item_pairs) == 36,
        "all_item_scientific_fields_identical": all(_scientific_item(old) == _scientific_item(new) for old, new in item_pairs),
        "case_order_identical": [item["case_id"] for item in v1_queue["items"]] == [item["case_id"] for item in queue["items"]],
        "method_order_identical": [item["method_id"] for item in v1_queue["items"]] == [item["method_id"] for item in queue["items"]],
        "budget_order_identical": [item["work_envelope"] for item in v1_queue["items"]] == [item["work_envelope"] for item in queue["items"]],
        "all_not_started": all(item["terminal_status"] == "NOT_STARTED" for item in queue["items"]),
        "candidate_energy_zero": queue["candidate_energy_evaluations"] == 0,
    }
    if not all(checks.values()):
        raise MB6V2Error("v1-v2 semantic diff exceeded allowed identity-only scope")
    return _with_digest(
        {
            "schema": "v5-final.mb6-v1-v2-semantic-diff-audit.v1",
            "v1_queue_sha256": _sha(V1_QUEUE),
            "v2_queue_digest": queue["queue_digest"],
            "allowed_changes_only": True,
            "allowed_change_scope": queue["successor_provenance"]["allowed_change_scope"],
            "checks": checks,
            "academic_boundary": "No case, source, candidate rule, cap, optimizer, acceptance, RNG, or resource policy changed.",
        },
        "audit_digest",
    )


def build_freeze(catalog: dict[str, Any], environment: dict[str, Any], queue: dict[str, Any], ledger: dict[str, Any], semantic_diff: dict[str, Any]) -> dict[str, Any]:
    mb52 = _json(MB52)
    development = _json(DEVELOPMENT_QUEUE)
    development_ledger = _json(DEVELOPMENT_LEDGER)
    checks = {
        "MB5_2_runtime_GO": mb52["decision"] == "GO_MB6_V2_OUTCOME_BLIND_REFREEZE_ONLY",
        "semantic_diff_allowed_only": semantic_diff["allowed_changes_only"] is True and all(semantic_diff["checks"].values()),
        "queue_exact_36_unique": len(queue["items"]) == 36 and len({item["queue_item_id"] for item in queue["items"]}) == 36,
        "all_not_started": all(item["terminal_status"] == "NOT_STARTED" for item in queue["items"]),
        "candidate_energy_zero": queue["candidate_energy_evaluations"] == 0 and ledger["candidate_energy_evaluations"] == 0,
        "segments_zero": not ledger["segments"],
        "frozen_queue_binding_complete": ledger["expected_queue_count"] == 36 and ledger["queue_digest"] == queue["queue_digest"] and ledger["queue_artifact_sha256"] == _sha(QUEUE_OUTPUT),
        "development_90_untouched": development["expected_queue_count"] == 90 and all(item["terminal_status"] == "NOT_STARTED" for item in development["items"]) and not development_ledger["segments"] and development_ledger["development_candidate_energy_evaluations"] == 0,
        "FCI_firewall": all(item["candidate_binding"].get("FCI_used") is False for item in queue["items"] if item["method_id"] == "v4.1-one-shot-joint-compression"),
        "barrier_free_forbidden": all(item["resource_policy"]["barrier_free_full_ansatz_compilation"] is False for item in queue["items"]),
    }
    if not all(checks.values()):
        raise MB6V2Error("MB6 v2 freeze checks failed")
    return _with_digest(
        {
            "schema": "v5-final.mb6-outcome-blind-freeze.v2",
            "stage": "R2_MB6_V2_OUTCOME_BLIND_SUCCESSOR_FREEZE",
            "status": "PASS_QUEUE_FREEZE_EXECUTION_STILL_BLOCKED",
            "decision": "GO_MB7_V2_PRE_CALIBRATION_AUDIT_ONLY",
            "artifacts": {
                "environment": {"path": str(ENV_OUTPUT.relative_to(ROOT)), "digest": environment["environment_digest"], "sha256": _sha(ENV_OUTPUT)},
                "catalog": {"path": str(CATALOG_OUTPUT.relative_to(ROOT)), "digest": catalog["probe_digest"], "sha256": _sha(CATALOG_OUTPUT)},
                "queue": {"path": str(QUEUE_OUTPUT.relative_to(ROOT)), "digest": queue["queue_digest"], "sha256": _sha(QUEUE_OUTPUT)},
                "ledger": {"path": str(LEDGER_OUTPUT.relative_to(ROOT)), "digest": ledger["ledger_root_digest"], "sha256": _sha(LEDGER_OUTPUT)},
                "semantic_diff": {"path": str(DIFF_OUTPUT.relative_to(ROOT)), "digest": semantic_diff["audit_digest"], "sha256": _sha(DIFF_OUTPUT)},
            },
            "checks": checks,
            "authorization": {
                "MB7_v2_pre_calibration_audit": "AUTHORIZED_ONLY",
                "H2_H4_execution": "NOT_AUTHORIZED",
                "molecular_candidate_energy": "NOT_AUTHORIZED",
                "development_queue_execution": "NOT_AUTHORIZED",
                "performance_claim": "NOT_AUTHORIZED",
            },
            "academic_boundary": "Outcome-blind executor-identity successor freeze only; no molecular outcome exists.",
        },
        "freeze_digest",
    )


def _build_all() -> tuple[dict[str, Any], ...]:
    environment = build_environment()
    catalog = build_catalog()
    queue = build_queue(catalog, environment)
    ledger = build_ledger(queue)
    semantic_diff = build_semantic_diff(catalog, environment, queue)
    return environment, catalog, queue, ledger, semantic_diff


def audit() -> dict[str, bool]:
    expected = _build_all()
    committed = tuple(_json(path) for path in (ENV_OUTPUT, CATALOG_OUTPUT, QUEUE_OUTPUT))
    queue_sha = _sha(QUEUE_OUTPUT)
    expected_ledger = bind_ledger_queue_sha(expected[3], queue_sha)
    ledger = _json(LEDGER_OUTPUT)
    semantic_diff = _json(DIFF_OUTPUT)
    freeze = _json(FREEZE_OUTPUT)
    checks = {
        "environment_rebuild_identical": committed[0] == expected[0],
        "catalog_rebuild_identical": committed[1] == expected[1],
        "queue_rebuild_identical": committed[2] == expected[2],
        "ledger_rebuild_identical": ledger == expected_ledger,
        "semantic_diff_rebuild_identical": semantic_diff == expected[4],
        "freeze_digest_valid": freeze["freeze_digest"] == _digest({key: value for key, value in freeze.items() if key != "freeze_digest"}),
        "cross_artifact_binding": freeze["artifacts"]["queue"]["sha256"] == queue_sha and ledger["queue_artifact_sha256"] == queue_sha,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise MB6V2Error("MB6 v2 audit failed: " + ", ".join(failures))
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not args.write:
        print(json.dumps(audit(), sort_keys=True))
        return
    first = _build_all()
    second = _build_all()
    if any(canonical_json_bytes(left) != canonical_json_bytes(right) for left, right in zip(first, second, strict=True)):
        raise MB6V2Error("two independent v2 queue builds were not byte-identical")
    environment, catalog, queue, ledger_unbound, semantic_diff = first
    for path, value in ((ENV_OUTPUT, environment), (CATALOG_OUTPUT, catalog), (QUEUE_OUTPUT, queue)):
        write_json_exclusive(path, value)
    ledger = bind_ledger_queue_sha(ledger_unbound, _sha(QUEUE_OUTPUT))
    write_json_exclusive(LEDGER_OUTPUT, ledger)
    write_json_exclusive(DIFF_OUTPUT, semantic_diff)
    freeze = build_freeze(catalog, environment, queue, ledger, semantic_diff)
    write_json_exclusive(FREEZE_OUTPUT, freeze)


if __name__ == "__main__":
    main()
