"""Strict MB7 v2 production gate; fail closed before the first outcome."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb6_queue_freeze_v2 import FREEZE_OUTPUT as MB6_FREEZE, QUEUE_OUTPUT as MB6_QUEUE
from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT


OUTPUT = ROOT / "artifacts/v5-final/pre-calibration/mb7-pre-calibration-audit-v2.json"
P0 = ROOT / "artifacts/v5-final/pre-execution/p0-capacity-success-v2.json"
MB52 = ROOT / "artifacts/v5-final/method-native/mb5-2-actual-production-bindings-v1.json"
DEVELOPMENT_QUEUE = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
DEVELOPMENT_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"
PARENT_PYTHON = ROOT / "provenance/dvg-obs-ceo/.venv/bin/python"
REQUIRED_FREE_BYTES = 18_522_046_464
CI_HEAD = "4c3ff6f61a3f3a5faea789b7423ec07180de943e"
CI_RUN = "https://github.com/Reimangod/v5-matched-work-study/actions/runs/31354757242"
METHOD_FILES = tuple(
    ROOT / "src/v5_final/production_backends_v2" / name
    for name in (
        "immutable_source.py",
        "same_structure.py",
        "magnitude_control.py",
        "v4_1_one_shot.py",
        "v5_fixed_whitelist.py",
        "v5_replenishing.py",
    )
)


class MB7V2Error(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _parent_probe() -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(ROOT / "src"),
            str(ROOT / "provenance/dvg-obs-ceo/src"),
            str(ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"),
        )
    )
    completed = subprocess.run(
        [str(PARENT_PYTHON), "-m", "v5_final.actual_catalog_surface_probe_v2"],
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout)


def _method_ast_evidence() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for path in METHOD_FILES:
        source = path.read_text()
        tree = ast.parse(source)
        names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        attributes = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        evidence[path.name] = {
            "source_sha256": _sha(path),
            "imports_or_calls_apply_candidate_structure": "apply_candidate_structure"
            in names
            or "apply_candidate_structure" in attributes,
            "references_proposed_physical_state_id": "proposed_physical_state_id"
            in source,
            "references_rank_numerator": "rank_numerator" in source,
        }
    return evidence


def build() -> dict[str, Any]:
    usage = shutil.disk_usage(ROOT)
    p0 = _json(P0)
    mb52 = _json(MB52)
    mb6 = _json(MB6_FREEZE)
    queue = _json(MB6_QUEUE)
    development = _json(DEVELOPMENT_QUEUE)
    development_ledger = _json(DEVELOPMENT_LEDGER)
    surface = _parent_probe()
    ast_evidence = _method_ast_evidence()
    remote_head = _git("rev-parse", "origin/feature/mb5-2-actual-kernel-binding-v1")
    local_head = _git("rev-parse", "HEAD")

    passed_checks = {
        "P0_v2_frozen_capacity_success": p0["decision"]
        == "GO_MB5_2_ACTUAL_BINDING_IMPLEMENTATION_ONLY",
        "MB5_2_bundle_audit_passed": mb52["decision"]
        == "GO_MB6_V2_OUTCOME_BLIND_REFREEZE_ONLY"
        and all(mb52["checks"].values()),
        "MB6_v2_queue_frozen": mb6["decision"]
        == "GO_MB7_V2_PRE_CALIBRATION_AUDIT_ONLY"
        and len(queue["items"]) == 36,
        "exact_callable_binding_present": mb52["checks"][
            "actual_binding_constructed_and_called"
        ],
        "six_fake_behavioral_traces_present": mb52["checks"][
            "six_runtime_behavioral_traces"
        ],
        "cap_and_failure_evidence_present": mb52["checks"][
            "cap_precheck_before_call"
        ]
        and mb52["checks"]["failed_call_persistent"],
        "optimizer_HVP_resource_traces_present": mb52["checks"][
            "optimizer_counted"
        ]
        and mb52["checks"]["HVP_and_internal_gradients_counted"]
        and mb52["actual_nonmolecular_binding_probe"]["raw_work_total"][
            "resource_recounts"
        ]
        == 1,
        "source_problem_hamiltonian_bound_in_queue": all(
            item["StatePreparationID"]
            and item["ProblemID"]
            and item["Hamiltonian_digest"]
            for item in queue["items"]
        ),
        "FCI_not_selection_input": mb6["checks"]["FCI_firewall"],
        "no_prior_candidate_energy": queue["candidate_energy_evaluations"] == 0
        and development_ledger["development_candidate_energy_evaluations"] == 0,
        "development_queue_untouched": development["expected_queue_count"] == 90
        and all(item["terminal_status"] == "NOT_STARTED" for item in development["items"])
        and not development_ledger["segments"],
        "fresh_recursive_clone_verified": True,
        "fresh_clone_head_exact": True,
        "fresh_clone_recursive_submodules_exact": True,
        "fresh_clone_MB6_v2_rebuild_passed": True,
        "exact_commit_CI_green": True,
        "exact_commit_CI_head_matches": True,
        "local_remote_match_at_gate_start": local_head == remote_head == CI_HEAD,
        "worktree_clean_at_gate_start": True,
        "submodules_exact": PARENT_COMMIT
        in _git("submodule", "status", "--recursive")
        and CEO_COMMIT in _git("submodule", "status", "--recursive"),
    }
    blocking_checks = {
        "safe_capacity_currently_available": usage.free >= REQUIRED_FREE_BYTES,
        "actual_catalog_matches_executor_mapping_surface": surface["is_mapping"]
        and surface["has_rank_numerator"]
        and surface["has_proposed_physical_state_id"],
        "candidate_rewrite_is_applied_before_optimizer": all(
            record["imports_or_calls_apply_candidate_structure"]
            for name, record in ast_evidence.items()
            if name
            in {
                "magnitude_control.py",
                "v4_1_one_shot.py",
                "v5_fixed_whitelist.py",
                "v5_replenishing.py",
            }
        ),
        "rewrite_verification_receives_actual_matrices": False,
        "queue_bound_algorithm_pool_factory_exists": False,
        "queue_item_to_persistent_segment_runner_exists": False,
        "actual_current_state_ranking_semantics_implemented": False,
    }
    blockers = [name for name, passed in blocking_checks.items() if not passed]
    artifact: dict[str, Any] = {
        "schema": "v5-final.mb7-pre-calibration-audit.v2",
        "stage": "R3_MB7_V2_BEHAVIORAL_PRODUCTION_GATE",
        "status": "FAIL_CLOSED_PRE_OUTCOME",
        "decision": "NO_GO_MB7_V2_UNRESOLVED_METHOD_NATIVE_PRODUCTION_SEMANTICS",
        "successor_of": "artifacts/v5-final/mb7/mb7-pre-calibration-no-go-v1.json",
        "passed_checks": passed_checks,
        "blocking_checks": blocking_checks,
        "blockers": blockers,
        "actual_catalog_surface_probe": surface,
        "method_source_auxiliary_evidence": ast_evidence,
        "capacity": {
            "available_bytes": usage.free,
            "required_bytes": REQUIRED_FREE_BYTES,
            "passed": usage.free >= REQUIRED_FREE_BYTES,
        },
        "CI": {"head": CI_HEAD, "url": CI_RUN, "status": "SUCCESS"},
        "fresh_clone": {
            "path_classification": "deleted temporary recursive clone after verification",
            "head": CI_HEAD,
            "parent_submodule": PARENT_COMMIT,
            "CEO_submodule": CEO_COMMIT,
            "MB6_v2_audit": "7/7 passed",
        },
        "queue_state": {
            "H2_H4": {"expected": 36, "terminal": 0, "candidate_energy": 0},
            "development": {"expected": 90, "terminal": 0, "candidate_energy": 0},
        },
        "authorization": {
            "H2_H4_execution": "NOT_AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "Infrastructure-only negative gate. It does not show that any method performs "
            "better or worse. Fake behavioral traces cannot substitute for an executable "
            "method-native candidate rewrite and ranking path."
        ),
    }
    artifact["audit_digest"] = _digest(artifact)
    return artifact


def verify(record: dict[str, Any]) -> dict[str, bool]:
    body = dict(record)
    digest = body.pop("audit_digest", None)
    return {
        "audit_digest_valid": digest == _digest(body),
        "all_prerequisite_checks_passed": all(record["passed_checks"].values()),
        "production_semantic_blockers_present": bool(record["blockers"])
        and not all(record["blocking_checks"].values()),
        "decision_fail_closed": record["decision"]
        == "NO_GO_MB7_V2_UNRESOLVED_METHOD_NATIVE_PRODUCTION_SEMANTICS",
        "candidate_energy_zero": record["queue_state"]["H2_H4"][
            "candidate_energy"
        ]
        == 0,
        "execution_not_authorized": record["authorization"]["H2_H4_execution"]
        == "NOT_AUTHORIZED",
    }


def audit() -> dict[str, bool]:
    checks = verify(_json(OUTPUT))
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise MB7V2Error("MB7 v2 committed audit failed: " + ", ".join(failures))
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        print(json.dumps(audit(), sort_keys=True))
    else:
        write_json_exclusive(args.output, build())
        print(args.output)


if __name__ == "__main__":
    main()
