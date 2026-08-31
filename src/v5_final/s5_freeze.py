"""S5 pre-outcome source, policy, queue, and empty-ledger freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .production_bundle import build_production_bundle
from .s0_successor import ROOT
from .s4_strict_audit_v3 import audit as audit_s4_strict


PARENT = ROOT / "provenance" / "dvg-obs-ceo"
S5_DIR = ROOT / "artifacts/v5-final/s5"
SOURCE_OUTPUT = S5_DIR / "source-checkpoint-registry-v3.json"
QUEUE_OUTPUT = S5_DIR / "development-queue-v3.json"
LEDGER_ROOT_OUTPUT = S5_DIR / "development-ledger-root-v3.json"
FREEZE_OUTPUT = S5_DIR / "development-protocol-freeze-v3.json"
AUDIT_OUTPUT = S5_DIR / "strict-development-freeze-audit-v3.json"

CASES = (
    "lih-3.0",
    "h6-1.5",
    "h6-3.0",
    "beh2-3.0",
    "h4-1.5-known-development",
)
WORK_ENVELOPES = ("LOW", "MEDIUM", "HIGH")
METHODS = (
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
    "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression",
    "v5-sequential-without-rebuilding",
    "v5-sequential-with-rebuilding",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _digest(value: Any) -> str:
    return _sha256_bytes(canonical_json_bytes(value))


def _with_digest(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result[field] = _digest(result)
    return result


def build_source_registry() -> dict[str, Any]:
    historical_path = ROOT / "artifacts/s2/stationary-source-protocol-v2.json"
    historical = json.loads(historical_path.read_text())
    if not all(historical["checks"].values()):
        raise RuntimeError("historical stationary-source reconstruction is invalid")
    cases_by_id = {
        value["case_id"]: value for value in historical["quantum_probe"]["cases"]
    }
    if set(cases_by_id) != set(CASES):
        raise RuntimeError("stationary-source case set differs from the S5 registry")
    sources = []
    for case_id in CASES:
        evidence = cases_by_id[case_id]
        checkpoint = PARENT / evidence["checkpoint_path"]
        observed_sha = _sha256_path(checkpoint)
        if observed_sha != evidence["checkpoint_sha256"]:
            raise RuntimeError(f"source checkpoint drift: {case_id}")
        checkpoint_value = json.loads(checkpoint.read_text())
        source_work = checkpoint_value.get("work")
        sources.append(
            {
                "case_id": case_id,
                "role": "known-development",
                "checkpoint_path": str(checkpoint.relative_to(ROOT)),
                "checkpoint_sha256": observed_sha,
                "ProblemID": evidence["identities"]["ProblemID"],
                "StatePreparationID": evidence["identities"]["StatePreparationID"],
                "MeasurementContextID": evidence["identities"]["MeasurementContextID"],
                "statevector_sha256": evidence["statevector_sha256"],
                "parameter_gradient_infinity": str(
                    evidence["parameter_gradient_infinity"]
                ),
                "parameter_stationarity_threshold_infinity": "1e-8",
                "pool_gradient_stopping": evidence["pool_gradient_stopping"],
                "resources": evidence["resources"],
                "source_generation_work": {
                    "classification": (
                        "historical checkpoint record; separate from all compression work"
                    ),
                    "available": source_work is not None,
                    "record": source_work,
                    "record_digest": _digest(source_work) if source_work is not None else None,
                },
                "optimizer_status": {
                    "available_as_explicit_status_field": "optimizer_status"
                    in checkpoint_value,
                    "value": checkpoint_value.get("optimizer_status"),
                    "stationarity_is_independently_reconstructed": True,
                },
                "block_catalog": {
                    "ansatz_indices_count": len(checkpoint_value["ansatz_indices"]),
                    "ansatz_indices_digest": _digest(checkpoint_value["ansatz_indices"]),
                    "structure_digest": evidence["resources"]["structure_digest"],
                },
            }
        )
    payload = {
        "schema": "v5-final.s5-source-checkpoint-registry.v3",
        "stage": "S5",
        "status": "FROZEN_PRE_OUTCOME",
        "historical_stationarity_evidence": {
            "path": str(historical_path.relative_to(ROOT)),
            "sha256": _sha256_path(historical_path),
            "protocol_digest": historical["protocol_digest"],
        },
        "source_rule": (
            "Every compared method starts from the byte-identical registered checkpoint "
            "for its case. Pool-gradient stopping and existing-parameter stationarity are "
            "separate fields; source-generation work is never compression work."
        ),
        "sources": sources,
        "source_count": len(sources),
        "academic_boundary": (
            "All five sources were previously observed and are development data. They are "
            "not prospective molecular evidence."
        ),
    }
    return _with_digest(payload, "registry_digest")


def _method_contracts() -> dict[str, Any]:
    return {
        "immutable-ceo-star-source": {
            "role": "source control",
            "optimization": False,
            "catalog_policy": "none",
        },
        "same-structure-reoptimization": {
            "role": "additional-optimizer-work control",
            "optimization": True,
            "catalog_policy": "source structure only",
        },
        "structural-magnitude-pruning": {
            "role": "simple-deletion control",
            "optimization": True,
            "catalog_policy": "frozen magnitude order",
        },
        "v4.1-one-shot-joint-compression": {
            "role": "one-shot baseline",
            "optimization": True,
            "catalog_policy": "one source catalog; no post-commit rebuild",
        },
        "v5-sequential-without-rebuilding": {
            "role": "causal ablation",
            "optimization": True,
            "catalog_policy": "one source catalog reused after commit",
            "sequential_commits": True,
            "post_commit_catalog_rebuild": False,
        },
        "v5-sequential-with-rebuilding": {
            "role": "primary V5-Core treatment",
            "optimization": True,
            "catalog_policy": "full catalog rebuilt from every committed state",
            "sequential_commits": True,
            "post_commit_catalog_rebuild": True,
        },
    }


def _semantic_work_profiles() -> dict[str, Any]:
    legacy = {
        "LOW": {
            "N_E": 300,
            "N_G": 200,
            "N_gradcomp": 10000,
            "N_HVP": 0,
            "N_exact": 4,
            "N_recount": 80,
            "N_rewrite": 10000,
            "N_rounds": 4,
            "N_states": 10000,
        },
        "MEDIUM": {
            "N_E": 5000,
            "N_G": 500,
            "N_gradcomp": 200000,
            "N_HVP": 0,
            "N_exact": 4,
            "N_recount": 2000,
            "N_rewrite": 20000,
            "N_rounds": 6,
            "N_states": 20000,
        },
        "HIGH": {
            "N_E": 40000,
            "N_G": 900,
            "N_gradcomp": 4000000,
            "N_HVP": 200,
            "N_exact": 6,
            "N_recount": 5000,
            "N_rewrite": 50000,
            "N_rounds": 10,
            "N_states": 50000,
        },
    }
    profiles = {}
    for name in WORK_ENVELOPES:
        cap = legacy[name]
        profiles[name] = {
            "semantic_work_cap": {
                "candidate_generations": cap["N_states"],
                "energy_evaluations": cap["N_E"],
                "gradient_component_equivalents": cap["N_gradcomp"],
                "gradient_vector_evaluations": cap["N_G"],
                "hvp_evaluations": cap["N_HVP"],
                "optimizer_iterations": cap["N_exact"] * 1000,
                "optimizer_starts": cap["N_exact"],
                "resource_recounts": cap["N_recount"],
                "rewrite_verifications": cap["N_rewrite"],
                "search_states": cap["N_states"],
                "statevector_recomputations": cap["N_E"],
            },
            "maximum_rounds": cap["N_rounds"],
            "derivation": {
                "legacy_componentwise_cap": cap,
                "optimizer_iterations": "N_exact * frozen maximum_iterations(1000)",
                "statevector_recomputations": (
                    "conservative hard ceiling N_E; reported independently, never merged"
                ),
                "candidate_generations_and_search_states": (
                    "both independently hard-capped by historical N_states"
                ),
            },
        }
    return profiles


def build_policy(source_registry: dict[str, Any]) -> dict[str, Any]:
    bundle = build_production_bundle()
    environment_files = (
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
        PARENT / "pyproject.toml",
        PARENT / "uv.lock",
    )
    environment = {
        "files": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha256_path(path)}
            for path in environment_files
        ],
        "required_threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
        "pinned_upstream_commit": "a3f89d03e6a03c89767d3cf8ee7657a57653dda0",
    }
    environment["environment_digest"] = _digest(environment)
    policy = {
        "schema": "v5-final.s5-development-policy.v3",
        "central_hypothesis": (
            "After a certified compression commit, rebuilding the circuit-derived "
            "candidate catalog exposes matched-work nondominated points unavailable to "
            "the otherwise identical sequential no-rebuild ablation."
        ),
        "primary_causal_contrast": {
            "treatment": "v5-sequential-with-rebuilding",
            "control": "v5-sequential-without-rebuilding",
            "only_intended_difference": "post_commit_catalog_rebuild",
        },
        "case_order": list(CASES),
        "method_order": list(METHODS),
        "work_envelope_order": list(WORK_ENVELOPES),
        "method_contracts": _method_contracts(),
        "work_profiles": _semantic_work_profiles(),
        "optimizer": {
            "primary": "pinned parent BFGS",
            "maximum_iterations": 1000,
            "gradient_tolerance": "1e-8",
            "fallback": "registered parent fallback only",
        },
        "acceptance": {
            "source_relative_energy_budget_hartree": "1e-4",
            "parameter_stationarity_infinity": "1e-8",
            "independent_energy_agreement_hartree": "1e-10",
            "constraint_residual_maximum": "1e-10",
            "resource_recount_required": True,
            "statevector_recomputation_required": True,
            "work_ledger_closure_required": True,
            "atomic_transaction_required": True,
        },
        "pareto": {
            "axes": [
                "energy_increase_hartree",
                "cnot_count",
                "cnot_depth",
                "total_depth",
                "parameter_count",
                "logical_block_count",
            ],
            "weighted_scalar_primary": False,
            "retain_all_nondominated_points": True,
            "context_unit": "case_id + work_envelope",
        },
        "failure_policy": {
            "rerun_only_documented_engineering_incident": True,
            "threshold_optimizer_catalog_budget_change_after_outcome": False,
            "exact_source_rollback_required": True,
            "scientific_failure_is_reported_and_not_rerun": True,
            "work_cap_exhaustion_is_terminal": True,
        },
        "fci_firewall": {
            "runtime_inputs_allowed": False,
            "ranking_allowed": False,
            "source_stopping_allowed": False,
            "acceptance_allowed": False,
            "winner_selection_allowed": False,
            "offline_reporting_after_all_runs_only": True,
        },
        "source_registry_digest": source_registry["registry_digest"],
        "production_bundle_digest": bundle["bundle_digest"],
        "environment": environment,
        "go_gate": {
            "minimum_development_contexts_new_vs_v4_1": 2,
            "minimum_development_contexts_new_vs_no_rebuild": 1,
            "raw_ledger_release_reconciliation_all_items": True,
            "negative_and_no_candidate_contexts_retained": True,
        },
        "claim_downgrade_rules": [
            "matched-work difference from V4.1 disappears",
            "Full V5 and no-rebuild do not differ",
            "improvement is explained by same-structure reoptimization",
            "benefit appears in only one source context",
        ],
    }
    return _with_digest(policy, "policy_digest")


def build_queue(
    source_registry: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    source_sha = {
        source["case_id"]: source["checkpoint_sha256"]
        for source in source_registry["sources"]
    }
    items = []
    for case_id in CASES:
        for envelope in WORK_ENVELOPES:
            for method in METHODS:
                identity_payload = {
                    "case_id": case_id,
                    "source_checkpoint_sha256": source_sha[case_id],
                    "work_envelope": envelope,
                    "method_id": method,
                    "policy_digest": policy["policy_digest"],
                }
                items.append(
                    {
                        "queue_item_id": "development-queue-item-v3:"
                        + _digest(identity_payload),
                        **identity_payload,
                        "terminal_status": "NOT_STARTED",
                    }
                )
    payload = {
        "schema": "v5-final.s5-development-queue.v3",
        "stage": "S5",
        "status": "FROZEN_PRE_OUTCOME",
        "source_registry_digest": source_registry["registry_digest"],
        "policy_digest": policy["policy_digest"],
        "expected_queue_count": len(CASES) * len(WORK_ENVELOPES) * len(METHODS),
        "queue_generation_rule": (
            "case order x work-envelope order x method order; no outcome-based omission"
        ),
        "items": items,
    }
    return _with_digest(payload, "queue_digest")


def build_ledger_root(queue: dict[str, Any], queue_artifact_sha256: str) -> dict[str, Any]:
    payload = {
        "schema": "v5-final.s5-development-ledger-root.v3",
        "stage": "S5",
        "status": "INITIALIZED_NO_EXECUTION",
        "queue_digest": queue["queue_digest"],
        "queue_artifact_sha256": queue_artifact_sha256,
        "expected_queue_count": queue["expected_queue_count"],
        "expected_queue_item_ids": [item["queue_item_id"] for item in queue["items"]],
        "segments": [],
        "completed_queue_item_ids": [],
        "development_candidate_energy_evaluations": 0,
        "completeness": {
            "complete": False,
            "reason": "S5 freezes the queue before execution; zero completed items is not completeness",
        },
    }
    return _with_digest(payload, "ledger_root_digest")


def build_documents() -> dict[Path, dict[str, Any]]:
    if not all(audit_s4_strict().values()):
        raise RuntimeError("S5 requires strict S4-v3 authorization")
    source_registry = build_source_registry()
    policy = build_policy(source_registry)
    queue = build_queue(source_registry, policy)
    source_sha = _sha256_bytes(canonical_json_bytes(source_registry))
    queue_sha = _sha256_bytes(canonical_json_bytes(queue))
    ledger_root = build_ledger_root(queue, queue_sha)
    ledger_sha = _sha256_bytes(canonical_json_bytes(ledger_root))
    freeze_payload = {
        "schema": "v5-final.s5-development-protocol-freeze.v3",
        "stage": "S5",
        "status": "FROZEN_PRE_OUTCOME",
        "strict_s4_authorization": {
            "path": "artifacts/v5-final/s4/strict-production-semantic-audit-v3.json",
            "audit_digest": json.loads(
                (ROOT / "artifacts/v5-final/s4/strict-production-semantic-audit-v3.json").read_text()
            )["audit_digest"],
        },
        "source_registry": {
            "path": str(SOURCE_OUTPUT.relative_to(ROOT)),
            "artifact_sha256": source_sha,
            "registry_digest": source_registry["registry_digest"],
            "source_count": source_registry["source_count"],
        },
        "policy": policy,
        "frozen_queue": {
            "path": str(QUEUE_OUTPUT.relative_to(ROOT)),
            "artifact_sha256": queue_sha,
            "queue_digest": queue["queue_digest"],
            "expected_queue_count": queue["expected_queue_count"],
        },
        "development_ledger_root": {
            "path": str(LEDGER_ROOT_OUTPUT.relative_to(ROOT)),
            "artifact_sha256": ledger_sha,
            "ledger_root_digest": ledger_root["ledger_root_digest"],
            "candidate_energy_evaluations": 0,
            "scope": "the frozen 90-item development queue only",
        },
        "pre_outcome_assertions": {
            "queue_nonempty": bool(queue["items"]),
            "queue_count_90": len(queue["items"]) == 90,
            "no_queue_item_started": all(
                item["terminal_status"] == "NOT_STARTED" for item in queue["items"]
            ),
            "no_development_execution_segment": not ledger_root["segments"],
            "H2_S4_smoke_excluded_from_development_outcomes": True,
        },
        "authorization": {
            "S6_algorithm_implementation": "AUTHORIZED",
            "S6_candidate_molecular_execution": "NOT_AUTHORIZED_PENDING_METHOD_NATIVE_PARITY",
            "S7_or_later": "NOT_AUTHORIZED",
            "performance_experiment": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "Five known development sources and a 90-item execution plan are frozen. "
            "No development candidate has been executed and no matched-work result exists."
        ),
        "systems_boundary": (
            "S6 may implement and test method-native executors only. Molecular candidate "
            "execution requires a later parity gate bound to this exact queue artifact."
        ),
        "decision": "GO_S6_IMPLEMENTATION_ONLY",
    }
    freeze = _with_digest(freeze_payload, "freeze_digest")
    documents = {
        SOURCE_OUTPUT: source_registry,
        QUEUE_OUTPUT: queue,
        LEDGER_ROOT_OUTPUT: ledger_root,
        FREEZE_OUTPUT: freeze,
    }
    audit_value = audit_documents(documents)
    documents[AUDIT_OUTPUT] = audit_value
    return documents


def audit_documents(documents: dict[Path, dict[str, Any]]) -> dict[str, Any]:
    source_registry = documents[SOURCE_OUTPUT]
    queue = documents[QUEUE_OUTPUT]
    ledger_root = documents[LEDGER_ROOT_OUTPUT]
    freeze = documents[FREEZE_OUTPUT]
    source_ids = {source["case_id"] for source in source_registry["sources"]}
    item_ids = [item["queue_item_id"] for item in queue["items"]]
    queue_pairs = {
        (item["case_id"], item["work_envelope"], item["method_id"])
        for item in queue["items"]
    }
    expected_pairs = {
        (case, envelope, method)
        for case in CASES
        for envelope in WORK_ENVELOPES
        for method in METHODS
    }
    queue_bytes = canonical_json_bytes(queue)
    source_bytes = canonical_json_bytes(source_registry)
    ledger_bytes = canonical_json_bytes(ledger_root)
    policy_text = json.dumps(freeze["policy"], sort_keys=True).lower()
    queue_text = json.dumps(queue, sort_keys=True).lower()
    checks = {
        "strict_s4_authorized_freeze_only": all(audit_s4_strict().values()),
        "five_sources_exact": source_ids == set(CASES)
        and source_registry["source_count"] == 5,
        "all_source_hashes_current": all(
            _sha256_path(ROOT / source["checkpoint_path"])
            == source["checkpoint_sha256"]
            for source in source_registry["sources"]
        ),
        "all_sources_stationary": all(
            float(source["parameter_gradient_infinity"]) <= 1e-8
            for source in source_registry["sources"]
        ),
        "source_work_separate": all(
            source["source_generation_work"]["classification"].endswith(
                "separate from all compression work"
            )
            for source in source_registry["sources"]
        ),
        "queue_expected_nonempty": queue["expected_queue_count"] > 0,
        "queue_90_exact_cartesian": queue_pairs == expected_pairs
        and queue["expected_queue_count"] == 90
        and len(queue["items"]) == 90,
        "queue_item_ids_unique": len(item_ids) == len(set(item_ids)),
        "queue_digest_valid": queue["queue_digest"]
        == _digest({key: value for key, value in queue.items() if key != "queue_digest"}),
        "queue_artifact_sha_bound": freeze["frozen_queue"]["artifact_sha256"]
        == _sha256_bytes(queue_bytes),
        "source_artifact_sha_bound": freeze["source_registry"]["artifact_sha256"]
        == _sha256_bytes(source_bytes),
        "ledger_artifact_sha_bound": freeze["development_ledger_root"][
            "artifact_sha256"
        ]
        == _sha256_bytes(ledger_bytes),
        "ledger_bound_to_exact_queue": ledger_root["queue_digest"]
        == queue["queue_digest"]
        and ledger_root["queue_artifact_sha256"] == _sha256_bytes(queue_bytes)
        and ledger_root["expected_queue_item_ids"] == item_ids,
        "empty_is_not_complete": ledger_root["completeness"]["complete"] is False
        and ledger_root["expected_queue_count"] == 90
        and not ledger_root["completed_queue_item_ids"],
        "development_candidate_energy_zero_scoped": ledger_root[
            "development_candidate_energy_evaluations"
        ]
        == 0
        and not ledger_root["segments"],
        "primary_ablation_differs_only_in_rebuild": freeze["policy"][
            "primary_causal_contrast"
        ]["only_intended_difference"]
        == "post_commit_catalog_rebuild",
        "componentwise_caps_complete": all(
            len(profile["semantic_work_cap"]) == 11
            and all(value >= 0 for value in profile["semantic_work_cap"].values())
            for profile in freeze["policy"]["work_profiles"].values()
        ),
        "fci_absent_from_queue": "fci" not in queue_text,
        "fci_runtime_firewall_explicit": "runtime_inputs_allowed\": false"
        in policy_text,
        "performance_closed": freeze["authorization"]["performance_experiment"]
        == "NOT_AUTHORIZED"
        and freeze["authorization"]["S6_candidate_molecular_execution"].startswith(
            "NOT_AUTHORIZED"
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "v5-final.s5-strict-development-freeze-audit.v3",
        "stage": "S5",
        "passed": not failures,
        "checks": checks,
        "failed_checks": failures,
        "queue_digest": queue["queue_digest"],
        "freeze_digest": freeze["freeze_digest"],
        "academic_boundary": "Pre-outcome protocol audit only; no performance evidence.",
        "decision": "GO_S6_IMPLEMENTATION_ONLY" if not failures else "NO_GO",
    }
    result["audit_digest"] = _digest(result)
    if failures:
        raise RuntimeError("S5-v3 freeze audit failed: " + ", ".join(failures))
    return result


def audit_committed() -> dict[str, bool]:
    committed = {
        path: json.loads(path.read_text())
        for path in (
            SOURCE_OUTPUT,
            QUEUE_OUTPUT,
            LEDGER_ROOT_OUTPUT,
            FREEZE_OUTPUT,
            AUDIT_OUTPUT,
        )
    }
    rebuilt = build_documents()
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "strict_audit_passed": committed[AUDIT_OUTPUT]["passed"] is True
        and all(committed[AUDIT_OUTPUT]["checks"].values()),
        "freeze_digest_valid": committed[FREEZE_OUTPUT]["freeze_digest"]
        == _digest(
            {
                key: value
                for key, value in committed[FREEZE_OUTPUT].items()
                if key != "freeze_digest"
            }
        ),
        "performance_closed": committed[FREEZE_OUTPUT]["authorization"][
            "performance_experiment"
        ]
        == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise RuntimeError("committed S5-v3 artifacts drifted")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args()
    if args.action == "build":
        for path, value in build_documents().items():
            write_json_exclusive(path, value)
    else:
        audit_committed()
    print(json.dumps({"action": args.action, "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()
