"""Outcome-blind MB6-v3 refreeze for the actual parent-native execution stack."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/mb6-v3"
ENV_OUTPUT = OUTPUT_DIR / "execution-environment-v3.json"
EXECUTOR_OUTPUT = OUTPUT_DIR / "parent-native-executor-manifest-v1.json"
PLAN_OUTPUT = OUTPUT_DIR / "h2-h4-calibration-plan-v3.json"
LEDGER_OUTPUT = OUTPUT_DIR / "h2-h4-calibration-ledger-root-v3.json"
DIFF_OUTPUT = OUTPUT_DIR / "mb6-v2-v3-semantic-diff-audit-v1.json"
FREEZE_OUTPUT = OUTPUT_DIR / "mb6-outcome-blind-freeze-v3.json"

V2_DIR = ROOT / "artifacts/v5-final/mb6-v2"
V2_ENV = V2_DIR / "execution-environment-v2.json"
V2_CATALOG = V2_DIR / "h2-h4-source-catalog-v2.json"
V2_QUEUE = V2_DIR / "h2-h4-calibration-queue-v2.json"
S3 = ROOT / "artifacts/v5-final/parent-native/s3-parent-native-runtime-factory-v1.json"
S4 = ROOT / "artifacts/v5-final/parent-native/s4-parent-native-executors-v1.json"
S5 = ROOT / "artifacts/v5-final/parent-native/s5-parent-native-work-accounting-v1.json"
S6 = ROOT / "artifacts/v5-final/parent-native/s6-parent-native-persistent-runner-v1.json"
DEVELOPMENT_PLAN = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
DEVELOPMENT_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"

RUNTIME_SOURCES = tuple(
    ROOT / value
    for value in (
        "src/v5_final/parent_native_candidate_adapter.py",
        "src/v5_final/parent_native_physical_identity.py",
        "src/v5_final/parent_native_rewrite.py",
        "src/v5_final/parent_native_runtime_factory.py",
        "src/v5_final/parent_native_executors.py",
        "src/v5_final/parent_native_work_accounting.py",
        "src/v5_final/parent_native_persistent_runner.py",
    )
)
GATE_ARTIFACTS = (S3, S4, S5, S6)
METHOD_IDS = (
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
    "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression",
    "v5-fixed-source-whitelist-no-replenishment",
    "v5-sequential-with-rebuilding",
)


class S7MB6V3RefreezeError(RuntimeError):
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


def build_environment() -> dict[str, Any]:
    correction = _json(S3)["environment_correction"]
    result = {
        key: copy.deepcopy(value)
        for key, value in correction.items()
        if key not in {"schema", "environment_digest", "correction_provenance"}
    }
    result.update(
        schema="v5-final.mb6-execution-environment.v3",
        successor_provenance={
            "v2_path": str(V2_ENV.relative_to(ROOT)),
            "v2_sha256": _sha(V2_ENV),
            "S3_path": str(S3.relative_to(ROOT)),
            "S3_sha256": _sha(S3),
            "allowed_change": "required thread counts 1/1/1 to 2/2/2 only",
            "reason": (
                "two threads exactly reproduce both frozen Hamiltonian and ProblemID "
                "identities; one thread does not reproduce H4"
            ),
            "scientific_protocol_changed": False,
            "candidate_outcome_used": False,
        },
    )
    return _with_digest(result, "environment_digest")


def build_executor_manifest() -> dict[str, Any]:
    source_manifest = [
        {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
        for path in RUNTIME_SOURCES
    ]
    gate_manifest = [
        {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
        for path in GATE_ARTIFACTS
    ]
    bundle = _digest(
        {
            "parent_commit": PARENT_COMMIT,
            "CEO_commit": CEO_COMMIT,
            "sources": source_manifest,
            "gates": gate_manifest,
        }
    )
    implementation = ROOT / "src/v5_final/parent_native_executors.py"
    identities: dict[str, Any] = {}
    for method in METHOD_IDS:
        identity = {
            "schema": "v5-final.parent-native-executor-identity.v1",
            "method_id": method,
            "entrypoint": (
                "v5_final.parent_native_executors:PreparedMethodNativeExecutor.execute"
            ),
            "implementation_path": str(implementation.relative_to(ROOT)),
            "implementation_sha256": _sha(implementation),
            "implementation_bundle_digest": bundle,
            "parent_commit": PARENT_COMMIT,
            "CEO_commit": CEO_COMMIT,
        }
        identity["executor_id"] = "parent-native-executor-v1:" + _digest(identity)
        identities[method] = identity
    return _with_digest(
        {
            "schema": "v5-final.parent-native-executor-manifest.v1",
            "status": "OUTCOME_FREE_ACTUAL_PARENT_NATIVE_BINDING",
            "implementation_bundle_digest": bundle,
            "source_manifest": source_manifest,
            "gate_manifest": gate_manifest,
            "executor_identities": identities,
            "physical_state_identity": "physical-state-v3",
            "molecular_candidate_energy_evaluations": 0,
        },
        "manifest_digest",
    )


def _s4_v4_correction() -> tuple[tuple[str, ...], tuple[str, ...]]:
    corrections = _json(S4)["required_MB6_v3_corrections"]
    selected = tuple(corrections["H4_v4_1_compatible_sentinels"])
    rejected = tuple(corrections["H4_v4_1_rejected_incompatible_v2_sentinels"])
    if len(selected) != 2 or len(rejected) != 2 or set(selected) & set(rejected):
        raise S7MB6V3RefreezeError("S4 H4 V4.1 correction is malformed")
    return selected, rejected


def _correct_v4_binding(item: dict[str, Any]) -> None:
    if not (
        item["case_id"] == "h4-1.5-first-chemical-accuracy"
        and item["method_id"] == "v4.1-one-shot-joint-compression"
    ):
        return
    selected, rejected = _s4_v4_correction()
    original = list(item["candidate_binding"]["candidate_set"])
    by_id = {value["candidate_structural_id"]: value for value in original}
    if set(by_id) != set(selected) | set(rejected):
        raise S7MB6V3RefreezeError("v2 H4 V4.1 sentinels differ from S4 proof")
    item["candidate_binding"]["candidate_set"] = [
        copy.deepcopy(by_id[value]) for value in selected
    ]
    item["candidate_binding"]["structural_compatibility_correction"] = {
        "proof_path": str(S4.relative_to(ROOT)),
        "proof_sha256": _sha(S4),
        "kept_candidate_ids": list(selected),
        "removed_incompatible_candidate_ids": list(rejected),
        "candidate_outcome_used": False,
        "FCI_used": False,
        "method_policy_changed": False,
    }


def build_plan(
    environment: Mapping[str, Any], executor_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    v2 = _json(V2_QUEUE)
    items: list[dict[str, Any]] = []
    for old in v2["items"]:
        item = copy.deepcopy(old)
        identity = executor_manifest["executor_identities"][item["method_id"]]
        item["executor_id"] = identity["executor_id"]
        item["executor_source_sha256"] = identity["implementation_sha256"]
        item["executor_bundle_digest"] = executor_manifest[
            "implementation_bundle_digest"
        ]
        item["authorization_reference"] = {
            "path": str(S6.relative_to(ROOT)),
            "sha256": _sha(S6),
            "decision": _json(S6)["decision"],
            "scope": "S7_OUTCOME_BLIND_REFREEZE_ONLY",
        }
        item["environment_digest"] = environment["environment_digest"]
        _correct_v4_binding(item)
        body = {key: value for key, value in item.items() if key != "queue_item_id"}
        item["queue_item_id"] = "mb6-calibration-item-v3:" + _digest(body)
        items.append(item)
    result = {
        "schema": "v5-final.mb6-h2-h4-calibration-plan.v3",
        "stage": v2["stage"],
        "status": "FROZEN_NOT_AUTHORIZED_FOR_EXECUTION",
        "generation_order": v2["generation_order"],
        "items": items,
        "frozen_item_count": len(items),
        "executor_manifest_digest": executor_manifest["manifest_digest"],
        "executor_bundle_digest": executor_manifest["implementation_bundle_digest"],
        "catalog_path": str(V2_CATALOG.relative_to(ROOT)),
        "catalog_sha256": _sha(V2_CATALOG),
        "catalog_digest": _json(V2_CATALOG)["probe_digest"],
        "environment_digest": environment["environment_digest"],
        "persistent_runner_sha256": _sha(
            ROOT / "src/v5_final/parent_native_persistent_runner.py"
        ),
        "existing_development_queue": copy.deepcopy(v2["existing_development_queue"]),
        "candidate_energy_evaluations": 0,
        "successor_provenance": {
            "v2_path": str(V2_QUEUE.relative_to(ROOT)),
            "v2_sha256": _sha(V2_QUEUE),
            "allowed_identity_changes": [
                "schema/version and queue/item IDs",
                "actual parent-native executor IDs/source/bundle digests",
                "S6 gate authorization reference",
                "corrected two-thread environment digest",
            ],
            "required_outcome_blind_structural_correction": (
                "H4 V4.1 removes exactly two pairwise-incompatible v2 sentinels"
            ),
        },
    }
    result["plan_digest"] = _digest(result)
    return result


def build_ledger(plan: Mapping[str, Any]) -> dict[str, Any]:
    return _with_digest(
        {
            "schema": "v5-final.mb6-calibration-ledger-root.v3",
            "plan_path": str(PLAN_OUTPUT.relative_to(ROOT)),
            "plan_artifact_sha256": "BOUND_AFTER_EXCLUSIVE_WRITE",
            "plan_digest": plan["plan_digest"],
            "expected_queue_item_ids": [
                item["queue_item_id"] for item in plan["items"]
            ],
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
        "environment_digest",
    }
    result = {key: copy.deepcopy(value) for key, value in item.items() if key not in ignored}
    result.pop("candidate_binding", None)
    return result


def _binding_without_correction(item: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(item["candidate_binding"])
    result.pop("structural_compatibility_correction", None)
    return result


def build_semantic_diff(plan: Mapping[str, Any]) -> dict[str, Any]:
    v2 = _json(V2_QUEUE)
    pairs = list(zip(v2["items"], plan["items"], strict=True))
    selected, rejected = _s4_v4_correction()
    correction_pairs = [
        (old, new)
        for old, new in pairs
        if old["case_id"] == "h4-1.5-first-chemical-accuracy"
        and old["method_id"] == "v4.1-one-shot-joint-compression"
    ]
    ordinary_pairs = [pair for pair in pairs if pair not in correction_pairs]
    correction_exact = True
    for old, new in correction_pairs:
        old_binding = old["candidate_binding"]
        new_binding = _binding_without_correction(new)
        old_by_id = {
            value["candidate_structural_id"]: value
            for value in old_binding["candidate_set"]
        }
        correction = new["candidate_binding"]["structural_compatibility_correction"]
        correction_exact = correction_exact and (
            tuple(value["candidate_structural_id"] for value in new_binding["candidate_set"])
            == selected
            and set(old_by_id) == set(selected) | set(rejected)
            and new_binding["candidate_set"]
            == [old_by_id[value] for value in selected]
            and {
                key: value
                for key, value in old_binding.items()
                if key != "candidate_set"
            }
            == {
                key: value
                for key, value in new_binding.items()
                if key != "candidate_set"
            }
            and correction["removed_incompatible_candidate_ids"] == list(rejected)
            and correction["candidate_outcome_used"] is False
            and correction["FCI_used"] is False
            and correction["method_policy_changed"] is False
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
            for item in v2["items"]
        ]
        == [
            (item["case_id"], item["work_envelope"], item["method_id"])
            for item in plan["items"]
        ],
        "all_nonidentity_nonbinding_fields_identical": all(
            _identity_free(old) == _identity_free(new) for old, new in pairs
        ),
        "ordinary_candidate_bindings_identical": all(
            old["candidate_binding"] == new["candidate_binding"]
            for old, new in ordinary_pairs
        ),
        "H4_v4_structural_correction_exact_for_three_budgets": (
            len(correction_pairs) == 3 and correction_exact
        ),
        "source_identities_identical": all(
            all(
                old[field] == new[field]
                for field in (
                    "StatePreparationID",
                    "ProblemID",
                    "Hamiltonian_digest",
                    "source_checkpoint_digest",
                    "source_checkpoint_sha256",
                )
            )
            for old, new in pairs
        ),
        "policies_thresholds_caps_identical": all(
            all(
                old[field] == new[field]
                for field in (
                    "protocol_digest",
                    "optimizer_policy_digest",
                    "acceptance_policy_digest",
                    "componentwise_work_cap",
                    "work_cap_digest",
                    "resource_policy",
                    "retry_policy",
                    "systemic_abort_policy",
                )
            )
            for old, new in pairs
        ),
        "all_not_started_candidate_energy_zero": (
            all(item["terminal_status"] == "NOT_STARTED" for item in plan["items"])
            and plan["candidate_energy_evaluations"] == 0
        ),
        "no_outcome_inputs": all(
            not item["candidate_binding"].get("candidate_energy_used", False)
            and not item["candidate_binding"].get("FCI_used", False)
            and not item["candidate_binding"].get("development_outcome_used", False)
            and not item["candidate_binding"].get("historical_rank_used", False)
            and not item["candidate_binding"].get("predictor_used", False)
            for item in plan["items"]
        ),
    }
    if not all(checks.values()):
        raise S7MB6V3RefreezeError("MB6-v3 semantic diff exceeded allowed scope")
    return _with_digest(
        {
            "schema": "v5-final.mb6-v2-v3-semantic-diff-audit.v1",
            "v2_queue_path": str(V2_QUEUE.relative_to(ROOT)),
            "v2_queue_sha256": _sha(V2_QUEUE),
            "v3_plan_digest": plan["plan_digest"],
            "checks": checks,
            "allowed_changes_only": True,
            "required_structural_correction": {
                "case_id": "h4-1.5-first-chemical-accuracy",
                "method_id": "v4.1-one-shot-joint-compression",
                "affected_budget_count": 3,
                "kept_candidate_ids": list(selected),
                "removed_incompatible_candidate_ids": list(rejected),
                "basis": "actual parent pairwise structural compatibility",
                "candidate_outcome_used": False,
            },
            "academic_boundary": (
                "No result, FCI value, historical rank, predictor, threshold, cap, "
                "source, case, method policy, or ordering changed. The sole non-identity "
                "difference removes two structurally incompatible H4 V4.1 sentinels."
            ),
        },
        "audit_digest",
    )


def _build_unbound() -> tuple[dict[str, Any], ...]:
    environment = build_environment()
    executors = build_executor_manifest()
    plan = build_plan(environment, executors)
    ledger = build_ledger(plan)
    semantic_diff = build_semantic_diff(plan)
    return environment, executors, plan, ledger, semantic_diff


def build_freeze(
    environment: Mapping[str, Any],
    executors: Mapping[str, Any],
    plan: Mapping[str, Any],
    ledger: Mapping[str, Any],
    semantic_diff: Mapping[str, Any],
) -> dict[str, Any]:
    development = _json(DEVELOPMENT_PLAN)
    development_ledger = _json(DEVELOPMENT_LEDGER)
    independently_rebuilt_plan = build_plan(
        build_environment(), build_executor_manifest()
    )
    checks = {
        "S6_authorized_S7_only": _json(S6)["decision"]
        == "GO_S7_OUTCOME_BLIND_MB6_V3_REFREEZE_ONLY",
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
        "environment_bound": plan["environment_digest"]
        == environment["environment_digest"],
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
        raise S7MB6V3RefreezeError("MB6-v3 freeze checks failed")
    artifact = {
        "schema": "v5-final.mb6-outcome-blind-freeze.v3",
        "stage": "S7_MB6_V3_OUTCOME_BLIND_PARENT_NATIVE_REFREEZE",
        "status": "PASS_PLAN_FROZEN_EXECUTION_STILL_BLOCKED",
        "decision": "GO_S8_BEHAVIORAL_PRODUCTION_GATE_ONLY",
        "artifacts": {
            "environment": {
                "path": str(ENV_OUTPUT.relative_to(ROOT)),
                "digest": environment["environment_digest"],
                "sha256": _sha(ENV_OUTPUT),
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
            "S8_behavioral_production_gate": "AUTHORIZED_ONLY",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "This is an outcome-blind structural and identity freeze. No molecular "
            "candidate energy, FCI-guided choice, calibration result, or performance "
            "evidence exists."
        ),
    }
    return _with_digest(artifact, "freeze_digest")


def audit() -> dict[str, bool]:
    expected = _build_unbound()
    committed = tuple(
        _json(path) for path in (ENV_OUTPUT, EXECUTOR_OUTPUT, PLAN_OUTPUT)
    )
    expected_ledger = bind_ledger_plan_sha(expected[3], _sha(PLAN_OUTPUT))
    ledger = _json(LEDGER_OUTPUT)
    semantic_diff = _json(DIFF_OUTPUT)
    freeze = _json(FREEZE_OUTPUT)
    checks = {
        "environment_rebuild_identical": committed[0] == expected[0],
        "executor_manifest_rebuild_identical": committed[1] == expected[1],
        "plan_rebuild_identical": committed[2] == expected[2],
        "ledger_rebuild_identical": ledger == expected_ledger,
        "semantic_diff_rebuild_identical": semantic_diff == expected[4],
        "freeze_rebuild_identical": freeze
        == build_freeze(*expected[:3], expected_ledger, expected[4]),
        "candidate_energy_zero": freeze["authorization"]["molecular_candidate_energy"]
        == "NOT_AUTHORIZED"
        and committed[2]["candidate_energy_evaluations"] == 0,
        "H2_H4_still_blocked": freeze["authorization"]["H2_H4_execution"]
        == "NOT_AUTHORIZED",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S7MB6V3RefreezeError("MB6-v3 audit failed: " + ", ".join(failures))
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
        raise S7MB6V3RefreezeError("two independent MB6-v3 builds differ")
    environment, executors, plan, ledger_unbound, semantic_diff = first
    for path, value in (
        (ENV_OUTPUT, environment),
        (EXECUTOR_OUTPUT, executors),
        (PLAN_OUTPUT, plan),
    ):
        write_json_exclusive(path, value)
    ledger = bind_ledger_plan_sha(ledger_unbound, _sha(PLAN_OUTPUT))
    write_json_exclusive(LEDGER_OUTPUT, ledger)
    write_json_exclusive(DIFF_OUTPUT, semantic_diff)
    freeze = build_freeze(environment, executors, plan, ledger, semantic_diff)
    write_json_exclusive(FREEZE_OUTPUT, freeze)


if __name__ == "__main__":
    main()
