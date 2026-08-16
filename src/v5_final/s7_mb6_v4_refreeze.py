"""Outcome-blind MB6-v4 refreeze bound to the remediated production stack."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import (
    artifact_is_immutable_git_blob,
    manifest_matches_artifact_commit,
)
from .parent_native_candidate_work_bindings import (
    CandidateWorkBinding,
    _magnitude_bindings,
    _single_candidate_bindings,
    candidate_structural_whitelist_key,
)
from .parent_native_executors import prepare_method_executor
from .parent_native_physical_identity import canonical_proposed_physical_state_id
from .parent_native_runtime_factory_v2 import build_queue_bound_runtime_v2
from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/mb6-v4"
EXECUTOR_OUTPUT = OUTPUT_DIR / "parent-native-executor-manifest-v2.json"
PLAN_OUTPUT = OUTPUT_DIR / "h2-h4-calibration-plan-v4.json"
LEDGER_OUTPUT = OUTPUT_DIR / "h2-h4-calibration-ledger-root-v4.json"
DIFF_OUTPUT = OUTPUT_DIR / "mb6-v3-v4-semantic-diff-audit-v1.json"
FREEZE_OUTPUT = OUTPUT_DIR / "mb6-outcome-blind-freeze-v4.json"

V3_DIR = ROOT / "artifacts/v5-final/parent-native/mb6-v3"
V3_ENV = V3_DIR / "execution-environment-v3.json"
V3_EXECUTORS = V3_DIR / "parent-native-executor-manifest-v1.json"
V3_PLAN = V3_DIR / "h2-h4-calibration-plan-v3.json"
V3_FREEZE = V3_DIR / "mb6-outcome-blind-freeze-v3.json"
S81 = ROOT / "artifacts/v5-final/parent-native/s8-1-runtime-release-remediation-v1.json"
DEVELOPMENT_PLAN = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
DEVELOPMENT_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"

RUNTIME_SOURCES = tuple(
    ROOT / value
    for value in (
        "src/v5_final/parent_native_candidate_adapter.py",
        "src/v5_final/parent_native_physical_identity.py",
        "src/v5_final/parent_native_rewrite.py",
        "src/v5_final/parent_native_executors.py",
        "src/v5_final/parent_native_work_accounting.py",
        "src/v5_final/parent_native_persistent_runner.py",
        "src/v5_final/parent_native_runtime_factory_v2.py",
        "src/v5_final/parent_native_candidate_work_bindings.py",
        "src/v5_final/parent_native_execution_services.py",
        "src/v5_final/parent_native_execution_control_probe.py",
    )
)
METHOD_IDS = (
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
    "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression",
    "v5-fixed-source-whitelist-no-replenishment",
    "v5-sequential-with-rebuilding",
)


class S7MB6V4RefreezeError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _with_digest(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result[field] = _digest(result)
    return result


def build_executor_manifest() -> dict[str, Any]:
    source_manifest = [
        {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
        for path in RUNTIME_SOURCES
    ]
    gate_manifest = [
        {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
        for path in (V3_FREEZE, S81)
    ]
    bundle = _digest(
        {
            "parent_commit": PARENT_COMMIT,
            "CEO_commit": CEO_COMMIT,
            "sources": source_manifest,
            "gates": gate_manifest,
            "environment_path": str(V3_ENV.relative_to(ROOT)),
            "environment_sha256": _sha(V3_ENV),
        }
    )
    implementation = ROOT / "src/v5_final/parent_native_execution_services.py"
    identities: dict[str, Any] = {}
    for method in METHOD_IDS:
        identity = {
            "schema": "v5-final.parent-native-executor-identity.v2",
            "method_id": method,
            "entrypoint": "v5_final.parent_native_execution_services:execute_frozen_item",
            "prepared_executor_entrypoint": (
                "v5_final.parent_native_executors:PreparedMethodNativeExecutor.execute"
            ),
            "implementation_path": str(implementation.relative_to(ROOT)),
            "implementation_sha256": _sha(implementation),
            "implementation_bundle_digest": bundle,
            "parent_commit": PARENT_COMMIT,
            "CEO_commit": CEO_COMMIT,
        }
        identity["executor_id"] = "parent-native-executor-v2:" + _digest(identity)
        identities[method] = identity
    return _with_digest(
        {
            "schema": "v5-final.parent-native-executor-manifest.v2",
            "status": "OUTCOME_FREE_ACTUAL_EXECUTION_SERVICE_BOUND",
            "implementation_bundle_digest": bundle,
            "source_manifest": source_manifest,
            "gate_manifest": gate_manifest,
            "executor_identities": identities,
            "physical_state_identity": "physical-state-v3",
            "candidate_work_binding_schema": (
                "v5-final.parent-native-candidate-work-binding.v2"
            ),
            "outcome_checkpoint_schema": (
                "v5-final.parent-native-outcome-checkpoint.v1"
            ),
            "molecular_candidate_energy_evaluations": 0,
        },
        "manifest_digest",
    )


def _candidate_work_binding(
    item: Mapping[str, Any], v3_plan: Mapping[str, Any]
) -> dict[str, Any]:
    context = build_queue_bound_runtime_v2(
        str(item["queue_item_id"]), plan_record=v3_plan
    )
    prepared = prepare_method_executor(context, item)
    method = str(item["method_id"])
    if method in {"immutable-ceo-star-source", "same-structure-reoptimization"}:
        generated: tuple[tuple[str, str], ...] = ()
        expanded: tuple[str, ...] = ()
        recounts = rewrites = dynamic_upper = 0
        whitelist: tuple[str, ...] = ()
    elif method == "structural-magnitude-pruning":
        generated = _magnitude_bindings(context, item)
        if prepared.magnitude_deletion is None:
            raise S7MB6V4RefreezeError("magnitude preparation is absent")
        expanded = (dict(generated)[prepared.magnitude_deletion.candidate_id],)
        recounts, rewrites, dynamic_upper = 3, 1, len(generated)
        whitelist = ()
    else:
        if prepared.source_catalog is None:
            raise S7MB6V4RefreezeError("structural source catalog is absent")
        generated = _single_candidate_bindings(context, prepared.source_catalog)
        if method == "v4.1-one-shot-joint-compression":
            expanded = tuple(
                canonical_proposed_physical_state_id(
                    problem_id=context.problem_id,
                    state_preparation_spec=plan.proposed_state_preparation_spec,
                )
                for plan in prepared.candidate_plans
            )
            recounts = 3 * len(prepared.prepared_rewrites)
            rewrites = sum(len(plan.candidates) for plan in prepared.candidate_plans)
            dynamic_upper = 0
            whitelist = ()
        else:
            expanded = tuple(physical_id for _, physical_id in generated)
            recounts, rewrites = 3 * len(generated), len(generated)
            dynamic_upper = len(generated)
            whitelist = (
                tuple(
                    sorted(
                        candidate_structural_whitelist_key(candidate)
                        for candidate in prepared.source_catalog.candidates
                    )
                )
                if method == "v5-fixed-source-whitelist-no-replenishment"
                else ()
            )
    binding = CandidateWorkBinding(
        generated,
        tuple(dict.fromkeys(expanded)),
        recounts,
        rewrites,
        dynamic_upper,
        whitelist,
    ).to_dict()
    if len(generated) != prepared.generated_candidate_intents:
        raise S7MB6V4RefreezeError("candidate intent count differs from executor")
    if len(set(expanded)) != prepared.unique_proposed_physical_states:
        raise S7MB6V4RefreezeError("physical-state count differs from executor")
    return binding


def build_plan(executors: Mapping[str, Any]) -> dict[str, Any]:
    v3 = _json(V3_PLAN)
    work_bindings: dict[tuple[str, str], dict[str, Any]] = {}
    for item in v3["items"]:
        key = (str(item["case_id"]), str(item["method_id"]))
        if key not in work_bindings:
            work_bindings[key] = _candidate_work_binding(item, v3)
    items: list[dict[str, Any]] = []
    for old in v3["items"]:
        item = copy.deepcopy(old)
        identity = executors["executor_identities"][item["method_id"]]
        item["executor_id"] = identity["executor_id"]
        item["executor_source_sha256"] = identity["implementation_sha256"]
        item["executor_bundle_digest"] = executors["implementation_bundle_digest"]
        item["authorization_reference"] = {
            "path": str(S81.relative_to(ROOT)),
            "sha256": _sha(S81),
            "decision": _json(S81)["decision"],
            "scope": "MB6_V4_OUTCOME_BLIND_EXECUTOR_REFREEZE_ONLY",
        }
        item["candidate_work_binding"] = copy.deepcopy(
            work_bindings[(str(item["case_id"]), str(item["method_id"]))]
        )
        body = {key: value for key, value in item.items() if key != "queue_item_id"}
        item["queue_item_id"] = "mb6-calibration-item-v4:" + _digest(body)
        items.append(item)
    result = {
        "schema": "v5-final.mb6-h2-h4-calibration-plan.v4",
        "stage": v3["stage"],
        "status": "FROZEN_NOT_AUTHORIZED_FOR_EXECUTION",
        "generation_order": v3["generation_order"],
        "items": items,
        "frozen_item_count": len(items),
        "executor_manifest_digest": executors["manifest_digest"],
        "executor_bundle_digest": executors["implementation_bundle_digest"],
        "catalog_path": v3["catalog_path"],
        "catalog_sha256": v3["catalog_sha256"],
        "catalog_digest": v3["catalog_digest"],
        "environment_digest": v3["environment_digest"],
        "environment_path": str(V3_ENV.relative_to(ROOT)),
        "environment_sha256": _sha(V3_ENV),
        "persistent_runner_sha256": _sha(
            ROOT / "src/v5_final/parent_native_persistent_runner.py"
        ),
        "existing_development_queue": copy.deepcopy(v3["existing_development_queue"]),
        "candidate_energy_evaluations": 0,
        "successor_provenance": {
            "v3_path": str(V3_PLAN.relative_to(ROOT)),
            "v3_sha256": _sha(V3_PLAN),
            "allowed_changes": [
                "schema/version and queue/item IDs",
                "remediated execution-service identities and bundle digest",
                "S8.1 authorization reference",
                "outcome-free exact candidate-work binding",
            ],
            "scientific_protocol_changed": False,
            "candidate_outcome_used": False,
        },
    }
    result["plan_digest"] = _digest(result)
    return result


def build_ledger(plan: Mapping[str, Any]) -> dict[str, Any]:
    return _with_digest(
        {
            "schema": "v5-final.mb6-calibration-ledger-root.v4",
            "plan_path": str(PLAN_OUTPUT.relative_to(ROOT)),
            "plan_artifact_sha256": "BOUND_AFTER_EXCLUSIVE_WRITE",
            "plan_digest": plan["plan_digest"],
            "expected_queue_item_ids": [item["queue_item_id"] for item in plan["items"]],
            "expected_queue_count": 36,
            "completed_queue_item_ids": [],
            "raw_ledger_directories": [],
            "terminal_segments": [],
            "candidate_energy_evaluations": 0,
            "completeness_contract": {
                "expected_queue_nonempty": True,
                "frozen_queue_count": 36,
                "frozen_plan_artifact_sha256_required": True,
                "expected_plan_digest_must_match": True,
                "every_and_only_expected_item_terminal": True,
                "exactly_one_terminal_per_item_after_linked_retries": True,
                "raw_work_reconstructs_every_summary": True,
                "outcome_checkpoint_bound_before_terminal": True,
            },
        },
        "ledger_root_digest",
    )


def bind_ledger_plan_sha(
    ledger: Mapping[str, Any], plan_sha256: str
) -> dict[str, Any]:
    result = dict(ledger)
    result.pop("ledger_root_digest", None)
    result["plan_artifact_sha256"] = plan_sha256
    return _with_digest(result, "ledger_root_digest")


def _identity_free(item: Mapping[str, Any]) -> dict[str, Any]:
    ignored = {
        "queue_item_id",
        "executor_id",
        "executor_source_sha256",
        "executor_bundle_digest",
        "authorization_reference",
        "candidate_work_binding",
    }
    return {
        key: copy.deepcopy(value) for key, value in item.items() if key not in ignored
    }


def build_semantic_diff(plan: Mapping[str, Any]) -> dict[str, Any]:
    v3 = _json(V3_PLAN)
    pairs = list(zip(v3["items"], plan["items"], strict=True))
    bindings = [new["candidate_work_binding"] for _, new in pairs]
    by_case_method: dict[tuple[str, str], set[str]] = {}
    for _, item in pairs:
        binding = item["candidate_work_binding"]
        body = dict(binding)
        observed = body.pop("binding_digest")
        if observed != _digest(body):
            raise S7MB6V4RefreezeError("candidate work binding digest is invalid")
        by_case_method.setdefault(
            (str(item["case_id"]), str(item["method_id"])), set()
        ).add(observed)
    h4_full = next(
        item["candidate_work_binding"]
        for item in plan["items"]
        if item["case_id"] == "h4-1.5-first-chemical-accuracy"
        and item["method_id"] == "v5-sequential-with-rebuilding"
    )
    h4_fixed = next(
        item["candidate_work_binding"]
        for item in plan["items"]
        if item["case_id"] == "h4-1.5-first-chemical-accuracy"
        and item["method_id"] == "v5-fixed-source-whitelist-no-replenishment"
    )
    checks = {
        "item_count_36": len(pairs) == 36,
        "two_cases_three_budgets_six_methods": (
            len({item["case_id"] for item in plan["items"]}) == 2
            and len({item["work_envelope"] for item in plan["items"]}) == 3
            and {item["method_id"] for item in plan["items"]} == set(METHOD_IDS)
        ),
        "item_order_identical": [
            (item["case_id"], item["work_envelope"], item["method_id"])
            for item in v3["items"]
        ]
        == [
            (item["case_id"], item["work_envelope"], item["method_id"])
            for item in plan["items"]
        ],
        "all_scientific_item_fields_identical": all(
            _identity_free(old) == _identity_free(new) for old, new in pairs
        ),
        "candidate_binding_policy_identical": all(
            old["candidate_binding"] == new["candidate_binding"] for old, new in pairs
        ),
        "candidate_work_binding_digest_valid": len(bindings) == 36,
        "candidate_work_binding_budget_invariant": len(by_case_method) == 12
        and all(len(values) == 1 for values in by_case_method.values()),
        "H4_semantic_state_dedup_exact": (
            h4_full["candidate_generation_count"] == 20
            and h4_full["unique_search_state_count"] == 16
        ),
        "H4_fixed_source_whitelist_exact": len(h4_fixed["source_whitelist_keys"])
        == 20,
        "all_not_started_candidate_energy_zero": all(
            item["terminal_status"] == "NOT_STARTED" for item in plan["items"]
        )
        and plan["candidate_energy_evaluations"] == 0,
        "no_outcome_or_FCI_input": all(
            not item["candidate_binding"].get("candidate_energy_used", False)
            and not item["candidate_binding"].get("FCI_used", False)
            and not item["candidate_binding"].get("development_outcome_used", False)
            and not item["candidate_binding"].get("historical_rank_used", False)
            for item in plan["items"]
        ),
    }
    if not all(checks.values()):
        raise S7MB6V4RefreezeError("MB6-v4 semantic diff exceeded allowed scope")
    return _with_digest(
        {
            "schema": "v5-final.mb6-v3-v4-semantic-diff-audit.v1",
            "v3_plan_path": str(V3_PLAN.relative_to(ROOT)),
            "v3_plan_sha256": _sha(V3_PLAN),
            "v4_plan_digest": plan["plan_digest"],
            "checks": checks,
            "allowed_changes_only": True,
            "academic_boundary": (
                "No source, case, method policy, threshold, cap, RNG, resource policy, "
                "candidate rule, or ordering changed. V4 adds only the remediated "
                "execution identity and outcome-free work/whitelist evidence."
            ),
        },
        "audit_digest",
    )


def _build_unbound() -> tuple[dict[str, Any], ...]:
    executors = build_executor_manifest()
    plan = build_plan(executors)
    ledger = build_ledger(plan)
    semantic_diff = build_semantic_diff(plan)
    return executors, plan, ledger, semantic_diff


def build_freeze(
    executors: Mapping[str, Any],
    plan: Mapping[str, Any],
    ledger: Mapping[str, Any],
    semantic_diff: Mapping[str, Any],
    independently_rebuilt_plan: Mapping[str, Any],
) -> dict[str, Any]:
    development = _json(DEVELOPMENT_PLAN)
    development_ledger = _json(DEVELOPMENT_LEDGER)
    checks = {
        "S8_1_authorized_v4_refreeze_only": _json(S81)["decision"]
        == "GO_MB6_V4_EXECUTOR_REFREEZE_ONLY",
        "semantic_diff_exact": all(semantic_diff["checks"].values()),
        "plan_exact_36_unique": len(plan["items"]) == 36
        and len({item["queue_item_id"] for item in plan["items"]}) == 36,
        "plan_byte_rebuild_proof": canonical_json_bytes(plan)
        == canonical_json_bytes(independently_rebuilt_plan),
        "all_not_started": all(
            item["terminal_status"] == "NOT_STARTED" for item in plan["items"]
        ),
        "candidate_energy_zero": plan["candidate_energy_evaluations"] == 0
        and ledger["candidate_energy_evaluations"] == 0,
        "raw_ledgers_and_terminals_zero": not ledger["raw_ledger_directories"]
        and not ledger["terminal_segments"],
        "frozen_plan_binding_complete": ledger["expected_queue_count"] == 36
        and ledger["plan_digest"] == plan["plan_digest"]
        and ledger["plan_artifact_sha256"] == _sha(PLAN_OUTPUT),
        "executor_manifest_bound": plan["executor_manifest_digest"]
        == executors["manifest_digest"],
        "environment_v3_unchanged_and_bound": plan["environment_digest"]
        == _json(V3_ENV)["environment_digest"]
        and plan["environment_sha256"] == _sha(V3_ENV),
        "development_90_untouched": development["expected_queue_count"] == 90
        and all(item["terminal_status"] == "NOT_STARTED" for item in development["items"])
        and not development_ledger["segments"]
        and development_ledger["development_candidate_energy_evaluations"] == 0,
        "barrier_free_forbidden": all(
            item["resource_policy"]["barrier_free_full_ansatz_compilation"] is False
            for item in plan["items"]
        ),
    }
    if not all(checks.values()):
        raise S7MB6V4RefreezeError("MB6-v4 freeze checks failed")
    return _with_digest(
        {
            "schema": "v5-final.mb6-outcome-blind-freeze.v4",
            "stage": "S7_SUCCESSOR_MB6_V4_OUTCOME_BLIND_EXECUTOR_REFREEZE",
            "status": "PASS_PLAN_FROZEN_EXECUTION_STILL_BLOCKED",
            "decision": "GO_S8_V2_BEHAVIORAL_PRODUCTION_GATE_ONLY",
            "artifacts": {
                "environment": {
                    "path": str(V3_ENV.relative_to(ROOT)),
                    "digest": _json(V3_ENV)["environment_digest"],
                    "sha256": _sha(V3_ENV),
                    "unchanged_from_v3": True,
                },
                "executors": {
                    "path": str(EXECUTOR_OUTPUT.relative_to(ROOT)),
                    "digest": executors["manifest_digest"],
                    "sha256": _sha(EXECUTOR_OUTPUT),
                },
                "plan": {
                    "path": str(PLAN_OUTPUT.relative_to(ROOT)),
                    "digest": plan["plan_digest"],
                    "sha256": _sha(PLAN_OUTPUT),
                },
                "ledger": {
                    "path": str(LEDGER_OUTPUT.relative_to(ROOT)),
                    "digest": ledger["ledger_root_digest"],
                    "sha256": _sha(LEDGER_OUTPUT),
                },
                "semantic_diff": {
                    "path": str(DIFF_OUTPUT.relative_to(ROOT)),
                    "digest": semantic_diff["audit_digest"],
                    "sha256": _sha(DIFF_OUTPUT),
                },
            },
            "checks": checks,
            "authorization": {
                "S8_v2_behavioral_production_gate": "AUTHORIZED_ONLY",
                "molecular_candidate_energy": "NOT_AUTHORIZED",
                "H2_H4_execution": "NOT_AUTHORIZED",
                "development_queue_execution": "NOT_AUTHORIZED",
                "performance_claim": "NOT_AUTHORIZED",
            },
            "academic_boundary": (
                "This is an outcome-blind executor/work-binding freeze. No molecular "
                "candidate energy, optimizer outcome, FCI-guided choice, calibration "
                "result, or performance evidence exists."
            ),
        },
        "freeze_digest",
    )


def audit() -> dict[str, bool]:
    committed_executors = _json(EXECUTOR_OUTPUT)
    committed_plan = _json(PLAN_OUTPUT)
    committed_ledger = _json(LEDGER_OUTPUT)
    committed_diff = _json(DIFF_OUTPUT)
    committed_freeze = _json(FREEZE_OUTPUT)
    checks = {
        "executor_manifest_rebuild_identical": artifact_is_immutable_git_blob(
            EXECUTOR_OUTPUT
        )
        and manifest_matches_artifact_commit(
            EXECUTOR_OUTPUT, committed_executors["source_manifest"]
        ),
        "plan_rebuild_identical": artifact_is_immutable_git_blob(PLAN_OUTPUT),
        "ledger_rebuild_identical": artifact_is_immutable_git_blob(LEDGER_OUTPUT),
        "semantic_diff_rebuild_identical": artifact_is_immutable_git_blob(DIFF_OUTPUT),
        "freeze_rebuild_identical": artifact_is_immutable_git_blob(FREEZE_OUTPUT),
        "candidate_energy_zero": committed_plan["candidate_energy_evaluations"] == 0,
        "H2_H4_still_blocked": committed_freeze["authorization"]["H2_H4_execution"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S7MB6V4RefreezeError("MB6-v4 audit failed: " + ", ".join(failures))
    return checks


def audit_static() -> dict[str, bool]:
    """Platform-neutral integrity audit for exact CI on non-frozen hosts."""

    executors = _json(EXECUTOR_OUTPUT)
    plan = _json(PLAN_OUTPUT)
    ledger = _json(LEDGER_OUTPUT)
    semantic_diff = _json(DIFF_OUTPUT)
    freeze = _json(FREEZE_OUTPUT)
    executor_body = dict(executors)
    executor_digest = executor_body.pop("manifest_digest", None)
    plan_body = dict(plan)
    plan_digest = plan_body.pop("plan_digest", None)
    ledger_body = dict(ledger)
    ledger_digest = ledger_body.pop("ledger_root_digest", None)
    diff_body = dict(semantic_diff)
    diff_digest = diff_body.pop("audit_digest", None)
    freeze_body = dict(freeze)
    freeze_digest = freeze_body.pop("freeze_digest", None)
    checks = {
        "executor_digest_valid": executor_digest == _digest(executor_body),
        "executor_sources_unchanged": manifest_matches_artifact_commit(
            EXECUTOR_OUTPUT, executors["source_manifest"]
        ),
        "executor_gates_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in executors["gate_manifest"]
        ),
        "plan_digest_valid": plan_digest == _digest(plan_body),
        "plan_exact_36_unique_unstarted": len(plan["items"]) == 36
        and len({item["queue_item_id"] for item in plan["items"]}) == 36
        and all(item["terminal_status"] == "NOT_STARTED" for item in plan["items"]),
        "plan_items_content_addressed": all(
            item["queue_item_id"]
            == "mb6-calibration-item-v4:"
            + _digest({key: value for key, value in item.items() if key != "queue_item_id"})
            for item in plan["items"]
        ),
        "candidate_work_bindings_content_addressed": all(
            item["candidate_work_binding"]["binding_digest"]
            == _digest(
                {
                    key: value
                    for key, value in item["candidate_work_binding"].items()
                    if key != "binding_digest"
                }
            )
            for item in plan["items"]
        ),
        "ledger_digest_valid": ledger_digest == _digest(ledger_body),
        "ledger_plan_bound_empty": ledger["plan_digest"] == plan["plan_digest"]
        and ledger["plan_artifact_sha256"] == _sha(PLAN_OUTPUT)
        and ledger["expected_queue_item_ids"]
        == [item["queue_item_id"] for item in plan["items"]]
        and not ledger["completed_queue_item_ids"]
        and not ledger["raw_ledger_directories"]
        and not ledger["terminal_segments"],
        "semantic_diff_digest_and_checks_valid": diff_digest == _digest(diff_body)
        and all(semantic_diff["checks"].values()),
        "freeze_digest_and_checks_valid": freeze_digest == _digest(freeze_body)
        and all(freeze["checks"].values()),
        "freeze_artifacts_bound": all(
            _sha(ROOT / value["path"]) == value["sha256"]
            for value in freeze["artifacts"].values()
        ),
        "candidate_energy_zero_execution_blocked": plan["candidate_energy_evaluations"]
        == 0
        and ledger["candidate_energy_evaluations"] == 0
        and freeze["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S7MB6V4RefreezeError(
            "MB6-v4 static audit failed: " + ", ".join(failures)
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not args.write:
        print(json.dumps(audit(), sort_keys=True))
        return
    first = _build_unbound()
    second = _build_unbound()
    if any(
        canonical_json_bytes(left) != canonical_json_bytes(right)
        for left, right in zip(first, second, strict=True)
    ):
        raise S7MB6V4RefreezeError("two independent MB6-v4 builds differ")
    executors, plan, ledger_unbound, semantic_diff = first
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(EXECUTOR_OUTPUT, executors)
    write_json_exclusive(PLAN_OUTPUT, plan)
    ledger = bind_ledger_plan_sha(ledger_unbound, _sha(PLAN_OUTPUT))
    write_json_exclusive(LEDGER_OUTPUT, ledger)
    write_json_exclusive(DIFF_OUTPUT, semantic_diff)
    freeze = build_freeze(executors, plan, ledger, semantic_diff, second[1])
    write_json_exclusive(FREEZE_OUTPUT, freeze)


if __name__ == "__main__":
    main()
