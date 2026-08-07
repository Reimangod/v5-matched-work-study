"""MB5.1 outcome-free audit of six production molecular backend call graphs."""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb4_2_owner_protocol_freeze import (
    CANONICAL_METHOD_IDS,
    LEGACY_QUEUE_METHOD_IDS,
    OUTPUT as FREEZE_OUTPUT,
)
from .p0_preexecution_audit import OUTPUT as P0_OUTPUT, audit as audit_p0
from .production_backends import ENTRYPOINTS
from .production_backends.common import (
    BoundaryRecorder,
    CapRejected,
    DRY_RUN_MODE,
    OutcomeLeakageBlocked,
    PRODUCTION_MODE,
    ProductionBackendError,
    ProductionNotAuthorized,
    WORK_COMPONENTS,
    digest,
    validate_request,
)
from .production_kernel_bindings import PARENT_PYTHON
from .s0_successor import CEO_COMMIT, LOCK_SHA256, PARENT_COMMIT, ROOT


DIRECTIVE_OUTPUT = (
    ROOT / "artifacts/v5-final/method-native/mb5-1-owner-directive-v1.json"
)
OUTPUT = ROOT / "artifacts/v5-final/method-native/mb5-1-production-backends-v1.json"
V1_OUTPUT = OUTPUT
V2_OUTPUT = ROOT / "artifacts/v5-final/method-native/mb5-1-production-backends-v2.json"
OUTPUT = ROOT / "artifacts/v5-final/method-native/mb5-1-production-backends-v3.json"
OWNER_DIRECTIVE = (
    "GO_MB5_1_PRODUCTION_BACKEND_IMPLEMENTATION_WITHOUT_MOLECULAR_OUTCOME: "
    "implement and audit six distinct production molecular entrypoints, pinned imports, "
    "kernel-bound counters, rollback, failure injection, and outcome-free dry-runs only. "
    "Do not evaluate molecular candidate energy, run H2/H4, touch the 90-item queue, or "
    "make a performance claim."
)
METHOD_SPECIFIC_MARKERS = {
    "immutable-ceo-star-source": ("candidate_construction", "child_state"),
    "same-structure-reoptimization": ("optimizer-lifecycle-prepared", "structure_preserved"),
    "structural-magnitude-pruning": ("single-coordinate-delete", "coefficient_zeroing_only"),
    "v4.1-one-shot-joint-compression": ("equivalence_class_id", "maximum_candidates"),
    "v5-fixed-source-whitelist-no-replenishment": (
        "source_candidate_whitelist",
        "replenishment_allowed",
    ),
    "v5-sequential-with-rebuilding": (
        "catalog_parent_digest",
        "child_dependent_replenishment_path_exists",
    ),
}


class MB51AuditError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _queue_state() -> dict[str, Any]:
    queue = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-queue-v3.json").read_text()
    )
    ledger = json.loads(
        (ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json").read_text()
    )
    queues = sorted(
        str(path.relative_to(ROOT))
        for path in (ROOT / "artifacts/v5-final").rglob("*queue*.json")
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
        "queue_artifacts": queues,
    }


def build_owner_directive() -> dict[str, Any]:
    p0 = json.loads(P0_OUTPUT.read_text())
    freeze = json.loads(FREEZE_OUTPUT.read_text())
    result = {
        "schema": "v5-final.mb5-1-owner-directive.v1",
        "stage": "MB5_1_PRODUCTION_BACKEND_IMPLEMENTATION",
        "status": "FROZEN_OUTCOME_BLIND_BY_REPOSITORY_OWNER_DIRECTIVE",
        "decision": "GO_MB5_1_PRODUCTION_BACKEND_IMPLEMENTATION_WITHOUT_MOLECULAR_OUTCOME",
        "directive": OWNER_DIRECTIVE,
        "directive_digest": digest({"directive": OWNER_DIRECTIVE}),
        "owner_freeze": {
            "path": str(FREEZE_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(FREEZE_OUTPUT),
            "freeze_digest": freeze["freeze_digest"],
        },
        "P0_capacity": {
            "path": str(P0_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(P0_OUTPUT),
            "status": p0["status"],
            "performance_execution_remains_blocked": True,
        },
        "allowed": [
            "production entrypoint code and import/call-graph validation",
            "synthetic structural fixture and blocking-sentinel dry-run",
            "source reconstruction and catalog identity",
            "counter, cap, rollback, retry, and failure-injection audit",
        ],
        "authorization": {
            "MB5_1_outcome_free_implementation_and_audit": "AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "This is repository-owner governance, not independent review and not scientific outcome evidence."
        ),
    }
    result["artifact_digest"] = digest(result)
    return result


def _physical(label: str) -> str:
    return "physical-state-v1:" + digest({"fixture_physical_state": label})


def fixture(method_id: str, *, attempt_index: int = 0) -> dict[str, Any]:
    freeze = json.loads(FREEZE_OUTPUT.read_text())
    state_digest = digest({"fixture_source": "mb5-1"})
    identity = {
        "StatePreparationID_digest": digest({"StatePreparationID": "synthetic"}),
        "ProblemID_digest": digest({"ProblemID": "synthetic"}),
        "Hamiltonian_digest": digest({"Hamiltonian": "identity-only-synthetic"}),
        "environment_digest": digest({"environment": "pinned-parent-dry-run"}),
        "dependency_lock_sha256": LOCK_SHA256,
    }
    source = {
        "source_checkpoint_digest": digest({"checkpoint": "synthetic-mb5-1"}),
        "structural_state_digest": state_digest,
        "StatePreparationID_digest": identity["StatePreparationID_digest"],
        "ProblemID_digest": identity["ProblemID_digest"],
        "Hamiltonian_digest": identity["Hamiltonian_digest"],
        "generators": [
            {"generator_id": "generator-a", "pool_index": 1, "magnitude_rank": 4},
            {"generator_id": "generator-b", "pool_index": 2, "magnitude_rank": 1},
            {"generator_id": "generator-c", "pool_index": 3, "magnitude_rank": 9},
        ],
        "source_candidate_whitelist": ["candidate-a", "candidate-b"],
        "structural_catalog": [
            {
                "candidate_id": "candidate-a",
                "equivalence_class_id": "class-1",
                "proposed_physical_state_id": _physical("state-a"),
                "structurally_eligible": True,
                "rank_numerator": 4,
                "catalog_parent_digest": digest({"historical_source": True}),
            },
            {
                "candidate_id": "candidate-a-alias",
                "equivalence_class_id": "class-1",
                "proposed_physical_state_id": _physical("state-a"),
                "structurally_eligible": True,
                "rank_numerator": 3,
                "catalog_parent_digest": state_digest,
            },
            {
                "candidate_id": "candidate-b",
                "equivalence_class_id": "class-2",
                "proposed_physical_state_id": _physical("state-b"),
                "structurally_eligible": True,
                "rank_numerator": 2,
                "catalog_parent_digest": digest({"historical_source": True}),
            },
            {
                "candidate_id": "candidate-new",
                "equivalence_class_id": "class-0",
                "proposed_physical_state_id": _physical("state-new"),
                "structurally_eligible": True,
                "rank_numerator": 1,
                "catalog_parent_digest": state_digest,
            },
        ],
        "resources_before": {
            "cnot_count": 10,
            "cnot_depth": 8,
            "total_depth": 20,
            "parameter_count": 3,
            "logical_block_count": 2,
        },
        "resources_after_single_deletion": {
            "cnot_count": 10,
            "cnot_depth": 8,
            "total_depth": 20,
            "parameter_count": 3,
            "logical_block_count": 2,
        },
    }
    cap = {component: 100 for component in WORK_COMPONENTS}
    result: dict[str, Any] = {
        "schema": "v5-final.mb5-1-production-backend-request.v1",
        "execution_mode": DRY_RUN_MODE,
        "canonical_method_id": method_id,
        "legacy_queue_method_id": LEGACY_QUEUE_METHOD_IDS[method_id],
        "owner_freeze_digest": freeze["freeze_digest"],
        "protocol_digest": freeze["protocol_digests"][method_id],
        "identity": identity,
        "source": source,
        "componentwise_work_cap": cap,
        "work_cap_digest": digest(cap),
        "optimizer_policy_digest": digest({"optimizer": "frozen-placeholder-identity"}),
        "acceptance_policy_digest": digest({"acceptance": "frozen-placeholder-identity"}),
        "candidate_energy_evaluations_before": 0,
        "energy_blocking_sentinel": True,
        "synthetic_structural_fixture": True,
        "H2_H4_queue_bound": False,
        "development_queue_bound": False,
        "production_execution_authorized": False,
        "attempt_index": attempt_index,
        "previous_attempt_digest": (
            None if attempt_index == 0 else digest({"previous_attempt": attempt_index - 1})
        ),
        "retry_reason": None if attempt_index == 0 else "linked synthetic infrastructure retry",
        "failure_injection": None,
    }
    result["request_digest"] = digest(result)
    return result


def _pinned_import_probe() -> dict[str, Any]:
    probe_environment = dict(os.environ)
    probe_environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(ROOT / "src"),
            str(ROOT / "provenance/dvg-obs-ceo/src"),
            str(ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"),
        )
    )
    completed = subprocess.run(
        [str(PARENT_PYTHON), "-m", "v5_final.production_import_probe"],
        cwd=ROOT,
        env=probe_environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout)


def _entrypoint_identity(method_id: str, entrypoint: Callable[..., Any]) -> dict[str, Any]:
    source = Path(inspect.getsourcefile(entrypoint) or "").resolve()
    if source.parent != (ROOT / "src/v5_final/production_backends").resolve():
        raise MB51AuditError("entrypoint is outside the production-backend package")
    module = importlib.import_module(entrypoint.__module__)
    qualified = f"{entrypoint.__module__}:{entrypoint.__name__}"
    result = {
        "canonical_method_id": method_id,
        "legacy_queue_method_id": LEGACY_QUEUE_METHOD_IDS[method_id],
        "qualified_entrypoint": qualified,
        "source_path": str(source.relative_to(ROOT)),
        "source_sha256": _sha(source),
        "module_imported": module is not None,
        "callable": callable(entrypoint),
        "parent_commit": PARENT_COMMIT,
        "CEO_commit": CEO_COMMIT,
        "dependency_lock_sha256": LOCK_SHA256,
    }
    result["executor_id"] = "method-native-production-executor-v1:" + digest(result)
    return result


def _raises(error_type: type[BaseException], function: Callable[[], Any]) -> bool:
    try:
        function()
    except error_type:
        return True
    return False


def _negative_checks() -> dict[str, bool]:
    base = fixture("immutable-ceo-star-source")
    fake_schema = copy.deepcopy(base)
    fake_schema["schema"] = "fake"
    fake_schema["request_digest"] = digest({k: v for k, v in fake_schema.items() if k != "request_digest"})
    wrong_method = copy.deepcopy(base)
    wrong_method["canonical_method_id"] = "same-structure-reoptimization"
    wrong_method["request_digest"] = digest({k: v for k, v in wrong_method.items() if k != "request_digest"})
    wrong_identity = copy.deepcopy(base)
    wrong_identity["source"]["Hamiltonian_digest"] = "0" * 64
    wrong_identity["request_digest"] = digest({k: v for k, v in wrong_identity.items() if k != "request_digest"})
    production = copy.deepcopy(base)
    production["execution_mode"] = PRODUCTION_MODE
    production["request_digest"] = digest({k: v for k, v in production.items() if k != "request_digest"})
    bound = validate_request(base, "immutable-ceo-star-source")
    recorder = BoundaryRecorder(bound, "v5_final.method_native.negative_probe")
    cap_zero = copy.deepcopy(base)
    cap_zero["componentwise_work_cap"]["resource_recounts"] = 0
    cap_zero["work_cap_digest"] = digest(cap_zero["componentwise_work_cap"])
    cap_zero["request_digest"] = digest({k: v for k, v in cap_zero.items() if k != "request_digest"})
    cap_bound = validate_request(cap_zero, "immutable-ceo-star-source")
    cap_recorder = BoundaryRecorder(cap_bound, "v5_final.method_native.cap_probe")
    checks = {
        "fake_schema_rejected": _raises(
            ProductionBackendError,
            lambda: ENTRYPOINTS["immutable-ceo-star-source"](fake_schema),
        ),
        "wrong_method_id_rejected": _raises(
            ProductionBackendError,
            lambda: ENTRYPOINTS["immutable-ceo-star-source"](wrong_method),
        ),
        "wrong_source_problem_hamiltonian_rejected": _raises(
            ProductionBackendError,
            lambda: ENTRYPOINTS["immutable-ceo-star-source"](wrong_identity),
        ),
        "production_mode_rejected_without_MB7": _raises(
            ProductionNotAuthorized,
            lambda: ENTRYPOINTS["immutable-ceo-star-source"](production),
        ),
        "energy_sentinel_blocks_before_call": _raises(
            OutcomeLeakageBlocked,
            lambda: recorder.molecular("candidate-energy-evaluation"),
        )
        and recorder.events == [],
        "cap_precheck_rejects_before_event": _raises(
            CapRejected,
            lambda: cap_recorder.structural(
                "full-physical-resource-recount", {"probe": True}
            ),
        )
        and cap_recorder.events == [],
    }
    return checks


def _method_source_isolation(identities: Mapping[str, Mapping[str, Any]]) -> bool:
    paths = [record["source_path"] for record in identities.values()]
    if len(paths) != len(set(paths)):
        return False
    method_module_names = {
        entrypoint.__module__ for entrypoint in ENTRYPOINTS.values()
    }
    for method_id, record in identities.items():
        source_path = ROOT / record["source_path"]
        text = source_path.read_text()
        if any(marker not in text for marker in METHOD_SPECIFIC_MARKERS[method_id]):
            return False
        tree = ast.parse(text)
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        if imported & method_module_names:
            return False
    return True


def build() -> dict[str, Any]:
    probe = _pinned_import_probe()
    identities = {
        method_id: _entrypoint_identity(method_id, ENTRYPOINTS[method_id])
        for method_id in CANONICAL_METHOD_IDS
    }
    results = {
        method_id: ENTRYPOINTS[method_id](fixture(method_id))
        for method_id in CANONICAL_METHOD_IDS
    }
    same_failure = fixture("same-structure-reoptimization")
    same_failure["failure_injection"] = "after-stage"
    same_failure["request_digest"] = digest(
        {key: value for key, value in same_failure.items() if key != "request_digest"}
    )
    rollback = ENTRYPOINTS["same-structure-reoptimization"](same_failure)
    retry = ENTRYPOINTS["same-structure-reoptimization"](
        fixture("same-structure-reoptimization", attempt_index=1)
    )
    fixed = results["v5-fixed-source-whitelist-no-replenishment"]
    replenishing = results["v5-sequential-with-rebuilding"]
    magnitude = results["structural-magnitude-pruning"]
    checks = {
        "P0_evidence_valid_and_capacity_no_go_preserved": all(audit_p0().values()),
        "six_distinct_entrypoints_imported": len(identities) == 6
        and all(record["callable"] and record["module_imported"] for record in identities.values()),
        "method_algorithms_source_isolated": _method_source_isolation(identities),
        "pinned_parent_and_CEO_API_imported": len(probe["APIs"]) == len(
            __import__("v5_final.production_kernel_bindings", fromlist=["API_SPECS"]).API_SPECS
        )
        and all(record["callable"] for record in probe["APIs"].values()),
        "optimizer_start_iteration_energy_gradient_boundaries_exposed": (
            "minimize_bfgs" in probe["APIs"]
            and "callback" in probe["APIs"]["minimize_bfgs"]["signature"]
            and "optimizer-iteration" in (
                ROOT / "src/v5_final/production_kernel_bindings.py"
            ).read_text()
        ),
        "dependency_and_environment_identity_bound": probe["parent_commit"] == PARENT_COMMIT
        and probe["CEO_commit"] == CEO_COMMIT
        and probe["parent_dependency_lock_sha256"] == LOCK_SHA256
        and bool(probe["environment"]),
        "import_probe_called_no_molecular_kernel": probe["molecular_kernel_called"] is False
        and probe["candidate_energy_evaluations"] == 0,
        "all_dry_runs_outcome_free": all(
            result["candidate_energy_evaluations"] == 0
            and result["molecular_kernel_calls"] == 0
            and result["performance_evidence"] is False
            for result in results.values()
        ),
        "semantic_dedup_uses_physical_state": all(
            result["unique_physical_state_count"]
            <= result["raw_work_total"]["candidate_generations"]
            for result in results.values()
        )
        and replenishing["unique_physical_state_count"] == 3,
        "fixed_whitelist_forbids_new_candidate": fixed["selected_candidate_ids"] == [
            "candidate-b"
        ]
        and fixed["method_evidence"]["whitelist_only_selection"] is True
        and "candidate-new" in fixed["method_evidence"]["new_candidates_filtered"],
        "full_v5_has_child_dependent_replenishment": replenishing["selected_candidate_ids"]
        == ["candidate-new"]
        and replenishing["method_evidence"]["child_dependent_replenishment_path_exists"]
        is True,
        "magnitude_physically_deletes_single_generator": magnitude["method_evidence"]
        ["physical_generator_deleted"]
        is True
        and magnitude["method_evidence"]["coefficient_zeroing_only"] is False,
        "zero_resource_reduction_not_success": magnitude["method_evidence"]
        ["resource_reduction_success"]
        is False
        and magnitude["method_evidence"]["zero_resource_reduction_is_success"] is False,
        "rollback_exact": rollback["rollback_record"]["exact"] is True
        and rollback["rollback_record"]["source_digest_before"]
        == rollback["rollback_record"]["source_digest_after"],
        "retry_chain_bound": retry["attempt_index"] == 1
        and retry["previous_attempt_digest"] is not None,
        **_negative_checks(),
    }
    queue_state = _queue_state()
    result = {
        "schema": "v5-final.mb5-1-production-backend-audit.v3",
        "stage": "MB5_1_PRODUCTION_BACKEND_IMPLEMENTATION",
        "status": "PASS_OUTCOME_FREE_PRODUCTION_BACKEND_BINDING",
        "decision": "GO_MB6_OUTCOME_BLIND_QUEUE_FREEZE_ONLY",
        "owner_directive": {
            "path": str(DIRECTIVE_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(DIRECTIVE_OUTPUT),
            "artifact_digest": json.loads(DIRECTIVE_OUTPUT.read_text())["artifact_digest"],
        },
        "supersedes_without_deletion": {
            "path": str(V2_OUTPUT.relative_to(ROOT)),
            "sha256": _sha(V2_OUTPUT),
            "status": "SUPERSEDED_PRE_COMMIT_SELF_AUDIT_CROSS_PLATFORM_DETERMINISM",
            "reason": (
                "v2 embedded the local OS platform string and could not rebuild byte-identically "
                "on Linux CI; v3 defers exact execution-platform identity to MB6"
            ),
            "prior_v1": {
                "path": str(V1_OUTPUT.relative_to(ROOT)),
                "sha256": _sha(V1_OUTPUT),
                "status": "SUPERSEDED_BY_V2_OPTIMIZER_ITERATION_BINDING",
            },
        },
        "production_kernel_API": probe,
        "executor_identities": identities,
        "dry_run_results": results,
        "checks": checks,
        "development_queue": queue_state,
        "P0_capacity_status": json.loads(P0_OUTPUT.read_text())["status"],
        "authorization": {
            "MB6_outcome_blind_queue_freeze": "AUTHORIZED_TO_CREATE_AND_AUDIT_FREEZE_ONLY",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "Pinned production callables and six method-native flows are structurally audited. "
            "No molecule, Hamiltonian value, candidate energy, optimizer outcome, or performance result was produced."
        ),
        "systems_boundary": (
            "Production mode rejects before a kernel call until an exact MB7 GO artifact exists; "
            "the P0 capacity No-Go independently remains in force."
        ),
    }
    result["audit_digest"] = digest(result)
    return result


def audit() -> dict[str, bool]:
    directive = json.loads(DIRECTIVE_OUTPUT.read_text())
    if directive != build_owner_directive():
        raise MB51AuditError("MB5.1 owner directive drifted")
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    checks = dict(rebuilt["checks"])
    checks["deterministic_rebuild"] = committed == rebuilt
    checks["queue_90_not_started"] = committed["development_queue"] == {
        "expected_count": 90,
        "not_started_count": 90,
        "completed_count": 0,
        "segment_count": 0,
        "candidate_energy_evaluations": 0,
        "queue_artifacts": ["artifacts/v5-final/s5/development-queue-v3.json"],
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise MB51AuditError("MB5.1 audit failed: " + ", ".join(failures))
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-directive", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.write_directive:
        write_json_exclusive(DIRECTIVE_OUTPUT, build_owner_directive())
    if args.output is not None:
        write_json_exclusive(args.output, build())
    if not args.write_directive and args.output is None:
        print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
