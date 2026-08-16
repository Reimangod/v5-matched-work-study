"""MB7 fail-closed pre-calibration production-binding audit."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import inspect
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb4_2_owner_protocol_freeze import CANONICAL_METHOD_IDS, OUTPUT as MB42_OUTPUT
from .mb5_1_production_backend_audit import OUTPUT as MB51_OUTPUT
from .mb6_queue_freeze import FREEZE_OUTPUT as MB6_OUTPUT, QUEUE_OUTPUT
from .p0_preexecution_audit import OUTPUT as P0_OUTPUT
from .production_backends import ENTRYPOINTS
from .production_backends.common import BoundaryRecorder
from .production_kernel_bindings import PinnedCEOProductionKernelBindings
from .s0_successor import ROOT


OUTPUT = ROOT / "artifacts/v5-final/mb7/mb7-pre-calibration-no-go-v1.json"
S5_QUEUE = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
S5_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"


class MB7AuditError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method_binding_evidence() -> dict[str, Any]:
    records = {}
    for method_id, entrypoint in ENTRYPOINTS.items():
        path = Path(inspect.getsourcefile(entrypoint) or "").resolve()
        tree = ast.parse(path.read_text())
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        records[method_id] = {
            "source_path": str(path.relative_to(ROOT)),
            "source_sha256": _sha(path),
            "imports_production_kernel_bindings": any(
                name.endswith("production_kernel_bindings") for name in imports
            ),
            "constructs_PinnedCEOProductionKernelBindings": (
                "PinnedCEOProductionKernelBindings" in names
            ),
            "calls_molecular_kernel_binding": bool(
                calls
                & {
                    "statevector",
                    "energy",
                    "gradient",
                    "optimize_bfgs",
                    "hessian_vector_product",
                    "catalog",
                    "verify_rewrite",
                    "resource_recount",
                }
            ),
        }
    return records


def build() -> dict[str, Any]:
    mb42 = json.loads(MB42_OUTPUT.read_text())
    mb51 = json.loads(MB51_OUTPUT.read_text())
    mb6 = json.loads(MB6_OUTPUT.read_text())
    queue = json.loads(QUEUE_OUTPUT.read_text())
    p0 = json.loads(P0_OUTPUT.read_text())
    development = json.loads(S5_QUEUE.read_text())
    development_ledger = json.loads(S5_LEDGER.read_text())
    bindings = _method_binding_evidence()
    common_source = inspect.getsource(BoundaryRecorder.molecular)
    kernel_source = Path(inspect.getsourcefile(PinnedCEOProductionKernelBindings) or "")
    checks = {
        "mb4_2_owner_freeze_valid": mb42["decision"]
        == "GO_MB5_OUTCOME_FREE_EXECUTOR_IMPLEMENTATION_ONLY",
        "mb5_1_structural_audit_present": mb51["status"]
        == "PASS_OUTCOME_FREE_PRODUCTION_BACKEND_BINDING",
        "mb6_queue_freeze_valid": mb6["decision"] == "GO_MB7_PRE_CALIBRATION_AUDIT_ONLY"
        and queue["frozen_item_count"] == 36,
        "six_exact_executor_callables": set(ENTRYPOINTS) == set(CANONICAL_METHOD_IDS)
        and all(callable(value) for value in ENTRYPOINTS.values()),
        "six_method_entrypoints_behaviorally_bind_actual_kernel": all(
            record["imports_production_kernel_bindings"]
            and record["constructs_PinnedCEOProductionKernelBindings"]
            and record["calls_molecular_kernel_binding"]
            for record in bindings.values()
        ),
        "production_recorder_delegates_instead_of_unconditionally_rejecting": (
            "production kernel calls require PinnedCEOProductionKernelBindings" not in common_source
        ),
        "production_kernel_binding_source_exists": kernel_source.is_file(),
        "componentwise_caps_frozen": all(
            len(item["componentwise_work_cap"]) == 11
            and item["work_cap_digest"] == _digest(item["componentwise_work_cap"])
            for item in queue["items"]
        ),
        "FCI_firewall_preserved": mb6["checks"]["no_candidate_energy"]
        and mb6["checks"]["no_molecular_kernel_called"],
        "development_queue_untouched": development["expected_queue_count"] == 90
        and all(item["terminal_status"] == "NOT_STARTED" for item in development["items"])
        and development_ledger["development_candidate_energy_evaluations"] == 0,
        "safe_capacity_available": p0["storage_policy"]["capacity_passed"] is True,
        "clean_fresh_recursive_clone_exact_commit": False,
        "exact_commit_CI_green": False,
    }
    blocking = [name for name, passed in checks.items() if not passed]
    expected_blocking = {
        "six_method_entrypoints_behaviorally_bind_actual_kernel",
        "production_recorder_delegates_instead_of_unconditionally_rejecting",
        "safe_capacity_available",
        "clean_fresh_recursive_clone_exact_commit",
        "exact_commit_CI_green",
    }
    if set(blocking) != expected_blocking:
        raise MB7AuditError("unexpected MB7 gate state: " + ", ".join(blocking))
    result = {
        "schema": "v5-final.mb7-pre-calibration-audit.v1",
        "stage": "MB7_PRE_CALIBRATION_AUDIT",
        "status": "NO_GO_PRE_CALIBRATION",
        "decision": "NO_GO_MB7_UNRESOLVED_PRODUCTION_BINDING_AND_CAPACITY",
        "inputs": {
            "mb4_2_sha256": _sha(MB42_OUTPUT),
            "mb5_1_sha256": _sha(MB51_OUTPUT),
            "mb6_sha256": _sha(MB6_OUTPUT),
            "queue_sha256": _sha(QUEUE_OUTPUT),
            "P0_sha256": _sha(P0_OUTPUT),
        },
        "checks": checks,
        "blocking_checks": blocking,
        "method_binding_evidence": bindings,
        "failure_analysis": {
            "production_binding": (
                "The six entrypoints are distinct structural flows, but none constructs or calls "
                "PinnedCEOProductionKernelBindings. Production BoundaryRecorder.molecular also "
                "unconditionally rejects instead of delegating to a counted kernel. A callable/source "
                "digest alone is therefore insufficient production evidence."
            ),
            "capacity": (
                "The immutable P0 audit failed its conservative free-space requirement. No new "
                "molecular call may start until a versioned successful P0 successor exists."
            ),
            "CI_and_clone": (
                "Exact-commit CI and a clean fresh recursive-clone attestation cannot turn green "
                "before the static binding and capacity gates pass."
            ),
        },
        "authorization": {
            "H2_H4_execution": "NOT_AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
            "repair_outcome_free_infrastructure": "AUTHORIZED_WITH_VERSIONED_SUCCESSOR_AUDIT",
        },
        "queue_state": {
            "calibration": {"expected": 36, "terminal": 0, "candidate_energy": 0},
            "development": {"expected": 90, "terminal": 0, "candidate_energy": 0},
        },
        "academic_boundary": "No performance observation exists; this is an infrastructure No-Go before the first candidate energy.",
        "systems_boundary": "Fail-closed on both actual-kernel reachability and safe disk capacity.",
    }
    result["audit_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "expected_no_go": committed["decision"]
        == "NO_GO_MB7_UNRESOLVED_PRODUCTION_BINDING_AND_CAPACITY",
        "no_candidate_energy": committed["queue_state"]["calibration"]["candidate_energy"]
        == 0,
        "all_execution_blocked": committed["authorization"]["H2_H4_execution"]
        == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise MB7AuditError("MB7 committed No-Go audit drifted")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        print(json.dumps(audit(), sort_keys=True))
    else:
        write_json_exclusive(args.output, build())


if __name__ == "__main__":
    main()
