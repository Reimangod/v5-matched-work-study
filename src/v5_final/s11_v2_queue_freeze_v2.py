"""Additive S11-v2 queue successor with pre-outcome caps and complete counters."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import (
    canonical_json_bytes,
    write_bytes_exclusive,
    write_json_exclusive,
)

from .semantic_contract_v2 import WORK_COMPONENTS
from .s0_successor import ROOT
from .s11_v2_outcome_cap_freeze import (
    CROSSWALK_OUTPUT,
    OUTPUT as CAP_FREEZE,
)


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v2"
QUEUE_OUTPUT = OUTPUT_DIR / "s11-v2-queue-v2.json"
IDENTITY_OUTPUT = OUTPUT_DIR / "queue-byte-identity-v2.json"
DIFF_OUTPUT = OUTPUT_DIR / "queue-v1-v2-semantic-diff-v1.json"
MANIFEST = OUTPUT_DIR / "MANIFEST.sha256"
V1_QUEUE = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v1/s11-v2-queue-v1.json"
)

EXECUTION_SOURCES = tuple(
    ROOT / value
    for value in (
        "src/v5_final/parent_native_work_accounting.py",
        "src/v5_final/parent_native_execution_services.py",
        "src/v5_final/parent_native_persistent_runner.py",
        "src/v5_final/parent_native_development_execution_v1.py",
        "src/v5_final/parent_native_development_runtime_factory_v1.py",
    )
)


class S11V2QueueFreezeV2Error(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise S11V2QueueFreezeV2Error(f"expected object: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _with_digest(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result[field] = _digest(result)
    return result


def _combined_caps(
    verifier: Mapping[str, int], outcome: Mapping[str, int]
) -> tuple[dict[str, int], dict[str, int]]:
    live = {}
    for field in WORK_COMPONENTS:
        live[field] = int(outcome[field]) + int(verifier.get(field, 0))
    complete = {key: int(value) for key, value in verifier.items()}
    complete.update(live)
    return live, complete


def build_queue() -> dict[str, Any]:
    predecessor = _load(V1_QUEUE)
    cap_freeze = _load(CAP_FREEZE)
    crosswalk = _load(CROSSWALK_OUTPUT)
    if predecessor.get("frozen_item_count") != 90:
        raise S11V2QueueFreezeV2Error("predecessor queue is not 90 items")
    items = []
    for old in predecessor["items"]:
        envelope = str(old["work_envelope"])
        profile = cap_freeze["profiles"][envelope]
        outcome = dict(profile["componentwise_outcome_cap"])
        verifier = dict(old["verifier_componentwise_cap"])
        combined_live, combined_complete = _combined_caps(verifier, outcome)
        body = copy.deepcopy(old)
        predecessor_id = body.pop("queue_item_id")
        body["predecessor_queue_item_id"] = predecessor_id
        body["predecessor_queue_item_digest"] = _digest(old)
        body["outcome_work_cap"] = {
            "componentwise_cap": outcome,
            "cap_digest": profile["cap_digest"],
            "source_freeze_digest": cap_freeze["freeze_digest"],
            "status": "FROZEN_PRE_OUTCOME_HARD_CEILING",
        }
        body["combined_live_ledger_cap"] = combined_live
        body["combined_live_ledger_cap_digest"] = _digest(combined_live)
        body["combined_all_counter_cap"] = combined_complete
        body["combined_all_counter_cap_digest"] = _digest(combined_complete)
        body["complete_counter_schema_digest"] = crosswalk[
            "complete_counter_schema_digest"
        ]
        body["authorization"] = "NOT_AUTHORIZED_PENDING_P7_V4_ALL_GATES"
        body["terminal_status"] = "NOT_STARTED"
        body["candidate_energy_evaluations"] = 0
        body["optimizer_iterations"] = 0
        body["FCI_evaluations"] = 0
        item = copy.deepcopy(body)
        item["queue_item_id"] = "s11-v2-item-v2:" + _digest(body)
        items.append(item)
    executor_sources = {
        str(path.relative_to(ROOT)): _sha(path) for path in EXECUTION_SOURCES
    }
    body = {
        "schema": "v5-final.s11-v2-fresh-90-item-queue.v2",
        "stage": "Q5_S11_V2_QUEUE_FREEZE",
        "status": "FROZEN_NOT_AUTHORIZED_PENDING_P7_V4",
        "generation_order": predecessor["generation_order"],
        "frozen_item_count": 90,
        "items": items,
        "method_order": predecessor["method_order"],
        "case_order": predecessor["case_order"],
        "work_envelope_order": predecessor["work_envelope_order"],
        "source_catalog": predecessor["source_catalog"],
        "executor_code_binding": predecessor["executor_code_binding"],
        "executor_bundle_digest": predecessor["executor_bundle_digest"],
        "execution_source_sha256": executor_sources,
        "execution_source_bundle_digest": _digest(executor_sources),
        "counter_schema_digest": predecessor["counter_schema_digest"],
        "complete_counter_schema": crosswalk["complete_counter_schema"],
        "complete_counter_schema_digest": crosswalk[
            "complete_counter_schema_digest"
        ],
        "verifier_cap_namespace": "verifier_componentwise_cap",
        "outcome_cap_namespace": "outcome_work_cap.componentwise_cap",
        "combined_cap_namespace": "combined_all_counter_cap",
        "predecessor_queue": {
            "path": str(V1_QUEUE.relative_to(ROOT)),
            "sha256": _sha(V1_QUEUE),
            "queue_digest": predecessor["queue_digest"],
            "immutable": True,
        },
        "outcome_cap_freeze": {
            "path": str(CAP_FREEZE.relative_to(ROOT)),
            "sha256": _sha(CAP_FREEZE),
            "freeze_digest": cap_freeze["freeze_digest"],
        },
        "accounting_crosswalk": {
            "path": str(CROSSWALK_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(CROSSWALK_OUTPUT),
            "crosswalk_digest": crosswalk["crosswalk_digest"],
        },
        "semantic_change_scope": [
            "replace null outcome cap with pre-outcome componentwise cap",
            "add complete counter schema and mechanically derived combined caps",
            "version queue and item identities while preserving order and scientific policy",
        ],
        "scientific_boundary": {
            "candidate_outcomes_used": False,
            "S11_v1_results_copied": 0,
            "candidate_outcome_execution": "NOT_AUTHORIZED_PENDING_P7_V4_ALL_GATES",
            "performance_claim": "NOT_AUTHORIZED",
            "FCI_reporting": "NOT_AUTHORIZED_UNTIL_ALL_90_TERMINAL",
        },
        "candidate_energy_evaluations": 0,
        "optimizer_iterations": 0,
        "FCI_evaluations": 0,
    }
    return _with_digest(body, "queue_digest")


def build_identity(first: Mapping[str, Any], second: Mapping[str, Any]) -> dict[str, Any]:
    first_bytes = canonical_json_bytes(first)
    second_bytes = canonical_json_bytes(second)
    return _with_digest(
        {
            "schema": "v5-final.s11-v2-queue-byte-identity.v2",
            "first_generation_sha256": hashlib.sha256(first_bytes).hexdigest(),
            "second_generation_sha256": hashlib.sha256(second_bytes).hexdigest(),
            "byte_identical": first_bytes == second_bytes,
            "queue_digest": first["queue_digest"],
            "candidate_outcomes_used": False,
        },
        "identity_audit_digest",
    )


def _scientific_view(item: Mapping[str, Any]) -> dict[str, Any]:
    ignored = {
        "queue_item_id",
        "predecessor_queue_item_id",
        "predecessor_queue_item_digest",
        "outcome_work_cap",
        "combined_live_ledger_cap",
        "combined_live_ledger_cap_digest",
        "combined_all_counter_cap",
        "combined_all_counter_cap_digest",
        "complete_counter_schema_digest",
        "authorization",
    }
    return {key: copy.deepcopy(value) for key, value in item.items() if key not in ignored}


def build_diff(queue: Mapping[str, Any]) -> dict[str, Any]:
    predecessor = _load(V1_QUEUE)
    pairs = list(zip(predecessor["items"], queue["items"]))
    checks = {
        "item_count_unchanged": len(pairs) == 90,
        "order_unchanged": all(
            (old["case_id"], old["work_envelope"], old["method_id"])
            == (new["case_id"], new["work_envelope"], new["method_id"])
            for old, new in pairs
        ),
        "scientific_policy_unchanged": all(
            _scientific_view(old) == _scientific_view(new) for old, new in pairs
        ),
        "all_v1_item_ids_bound": all(
            new["predecessor_queue_item_id"] == old["queue_item_id"]
            for old, new in pairs
        ),
        "only_cap_counter_authorization_identity_changes": True,
        "candidate_outcomes_zero_both": all(
            old["candidate_energy_evaluations"] == new["candidate_energy_evaluations"] == 0
            and old["optimizer_iterations"] == new["optimizer_iterations"] == 0
            and old["FCI_evaluations"] == new["FCI_evaluations"] == 0
            for old, new in pairs
        ),
    }
    body = {
        "schema": "v5-final.s11-v2-queue-v1-v2-semantic-diff.v1",
        "predecessor_sha256": _sha(V1_QUEUE),
        "predecessor_queue_digest": predecessor["queue_digest"],
        "successor_queue_digest": queue["queue_digest"],
        "allowed_change_classes": [
            "outcome cap",
            "complete and combined counter cap",
            "additive predecessor binding",
            "authorization remains blocked pending P7 v4",
            "versioned identity",
        ],
        "checks": checks,
        "scientific_semantics_changed": not checks["scientific_policy_unchanged"],
    }
    return _with_digest(body, "diff_audit_digest")


def _manifest_bytes(paths: tuple[Path, ...]) -> bytes:
    return ("".join(f"{_sha(path)}  {path.name}\n" for path in paths)).encode()


def write_artifacts() -> None:
    first = build_queue()
    second = build_queue()
    identity = build_identity(first, second)
    diff = build_diff(first)
    if not identity["byte_identical"] or not all(diff["checks"].values()):
        raise S11V2QueueFreezeV2Error("queue identity or semantic diff failed")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(QUEUE_OUTPUT, first)
    write_json_exclusive(IDENTITY_OUTPUT, identity)
    write_json_exclusive(DIFF_OUTPUT, diff)
    write_bytes_exclusive(
        MANIFEST, _manifest_bytes((QUEUE_OUTPUT, IDENTITY_OUTPUT, DIFF_OUTPUT))
    )


def audit() -> dict[str, Any]:
    first = build_queue()
    second = build_queue()
    identity = build_identity(first, second)
    diff = build_diff(first)
    checks = {
        "queue_exact": QUEUE_OUTPUT.exists() and _load(QUEUE_OUTPUT) == first,
        "generated_twice_byte_identical": identity["byte_identical"],
        "identity_exact": IDENTITY_OUTPUT.exists() and _load(IDENTITY_OUTPUT) == identity,
        "semantic_diff_exact": DIFF_OUTPUT.exists() and _load(DIFF_OUTPUT) == diff,
        "semantic_diff_passed": all(diff["checks"].values()) and not diff["scientific_semantics_changed"],
        "manifest_exact": MANIFEST.exists() and MANIFEST.read_bytes() == _manifest_bytes((QUEUE_OUTPUT, IDENTITY_OUTPUT, DIFF_OUTPUT)),
        "queue_count_90": len(first["items"]) == 90,
        "queue_ids_unique": len({item["queue_item_id"] for item in first["items"]}) == 90,
        "all_not_started": all(item["terminal_status"] == "NOT_STARTED" for item in first["items"]),
        "all_outcomes_zero": all(
            item["candidate_energy_evaluations"] == item["optimizer_iterations"] == item["FCI_evaluations"] == 0
            for item in first["items"]
        ),
        "all_outcome_caps_complete": all(
            set(item["outcome_work_cap"]["componentwise_cap"]) == set(WORK_COMPONENTS)
            for item in first["items"]
        ),
        "production_dense_expm_zero": all(
            item["combined_all_counter_cap"]["N_dense_expm"] == 0
            for item in first["items"]
        ),
        "performance_claim_blocked": first["scientific_boundary"]["performance_claim"] == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise S11V2QueueFreezeV2Error([name for name, passed in checks.items() if not passed])
    return {
        "status": "PASS_Q5_S11_V2_QUEUE_V2_FROZEN_NOT_AUTHORIZED",
        "checks": checks,
        "queue_digest": first["queue_digest"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.write:
        write_artifacts()
    if args.audit or not args.write:
        print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
