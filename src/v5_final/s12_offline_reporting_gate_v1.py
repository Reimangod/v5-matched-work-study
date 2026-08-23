"""Additive post-S11 gate for one outcome-isolated offline FCI reporting pass."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from v5_matched_work.atomic_artifacts import write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .s0_successor import ROOT
from .s11_v2_execution_readiness_v4 import (
    MINIMUM_FREE_BYTES,
    P7_V5,
    PRODUCTION_ROOT,
    _digest,
    _embedded_digest,
    _git,
    _load,
    _sha,
)
from .s11_v2_execution_readiness_v11 import OUTPUT as READINESS_V11
from .s11_v2_execution_runner_v1 import _item_paths, _terminal_prefix
from .s11_v2_preexecution_gate_v5 import audit_frozen as audit_p7_v5
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s12-offline-reporting-gate-v1"
OUTPUT = OUTPUT_DIR / "s12-offline-reporting-go-v1.json"
PROGRESS_90 = PRODUCTION_ROOT / "progress/0090-terminal.json"
SOURCE_CATALOG = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-queue-v4"
    / "development-source-catalog-v1.json"
)
DECISION = "GO_S12_OFFLINE_FCI_REPORTING_EXACT_FROZEN_CASES_ONLY"
EXPECTED_CASES = (
    "beh2-3.0",
    "h4-1.5-known-development",
    "h6-1.5",
    "h6-3.0",
    "lih-3.0",
)
SOURCE_PATHS = (
    "src/v5_final/s12_offline_reporting_gate_v1.py",
    "tests/test_v5_final_s12_offline_reporting_gate_v1.py",
)


class S12OfflineReportingGateV1Error(RuntimeError):
    pass


def _run_git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def _production_manifest() -> tuple[int, str]:
    manifest = {
        str(path.relative_to(ROOT)): _sha(path)
        for path in sorted(PRODUCTION_ROOT.rglob("*.json"))
    }
    return len(manifest), _digest(manifest)


def _result_and_receipt_manifests(
    adapter: QueueV2NativeAdapter,
) -> tuple[dict[str, str], dict[str, str], list[dict[str, Any]]]:
    result_manifest: dict[str, str] = {}
    receipt_manifest: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    for index, item in enumerate(adapter.queue["items"]):
        request = adapter.request(str(item["queue_item_id"]))
        paths = _item_paths(PRODUCTION_ROOT, index, request)
        result_manifest[str(paths["result"].relative_to(ROOT))] = _sha(paths["result"])
        receipt_manifest[str(paths["receipt"].relative_to(ROOT))] = _sha(
            paths["receipt"]
        )
        results.append(_load(paths["result"]))
    return result_manifest, receipt_manifest, results


def _validate_authorization(authorization: Mapping[str, Any]) -> bool:
    return authorization == {
        "offline_FCI_reference_generation": (
            "AUTHORIZED_ONCE_FOR_EXACT_FROZEN_CASE_SET_ONLY"
        ),
        "FCI_execution_control": "OUTCOME_INDEPENDENT_CASE_IDENTITY_ONLY",
        "FCI_reexecution_after_atomic_pass": "NOT_AUTHORIZED",
        "candidate_selection": "NOT_AUTHORIZED",
        "candidate_energy": "NOT_AUTHORIZED",
        "optimizer": "NOT_AUTHORIZED",
        "S11_item_rerun": "NOT_AUTHORIZED",
        "ranking_or_threshold_change": "NOT_AUTHORIZED",
        "S12_post_outcome_aggregation": (
            "NOT_AUTHORIZED_UNTIL_OFFLINE_FCI_REFERENCE_AUDIT"
        ),
        "performance_table": "NOT_AUTHORIZED",
        "pareto_analysis": "NOT_AUTHORIZED",
        "performance_claim": "NOT_AUTHORIZED",
        "release": "NOT_AUTHORIZED",
    }


def inspect_completion() -> dict[str, Any]:
    adapter = QueueV2NativeAdapter()
    queue = adapter.queue
    readiness = _load(READINESS_V11)
    p7 = _load(P7_V5)
    progress = _load(PROGRESS_90)
    source_catalog = _load(SOURCE_CATALOG)
    prefix = _terminal_prefix(
        adapter=adapter,
        production_root=PRODUCTION_ROOT,
        readiness_digest=str(readiness["readiness_digest"]),
        predecessor_readiness_digests=tuple(
            readiness.get("accepted_predecessor_receipt_readiness_digests", ())
        ),
    )
    result_manifest, receipt_manifest, results = _result_and_receipt_manifests(
        adapter
    )
    production_file_count, production_manifest_digest = _production_manifest()
    queue_cases = tuple(sorted({str(item["case_id"]) for item in queue["items"]}))
    catalog_cases = tuple(
        sorted(str(item["case_id"]) for item in source_catalog["cases"])
    )
    statuses = dict(sorted(Counter(item["terminal_status"] for item in prefix).items()))
    checks = {
        "P7_v5_frozen_GO_valid": audit_p7_v5()["decision"]
        == "GO_S11_V2_FROZEN_90_ITEM_EXECUTION",
        "queue_is_exact_frozen_90": len(queue["items"]) == 90
        and _embedded_digest(queue, "queue_digest"),
        "terminal_prefix_is_exact_complete_90": len(prefix) == 90
        and [item["queue_item_id"] for item in prefix]
        == [item["queue_item_id"] for item in queue["items"]],
        "receipt_identity_is_unique": len(
            {item["queue_item_id"] for item in prefix}
        )
        == 90
        and len({item["receipt_digest"] for item in prefix}) == 90,
        "progress_90_is_complete_and_bound": _embedded_digest(
            progress, "progress_digest"
        )
        and progress["complete"] is True
        and progress["terminal_count"] == 90
        and progress["terminal_queue_item_ids"]
        == [item["queue_item_id"] for item in queue["items"]],
        "result_and_receipt_sets_are_exact_90": len(result_manifest) == 90
        and len(receipt_manifest) == 90
        and len(results) == 90,
        "S11_FCI_is_exactly_zero": sum(
            int(result["FCI_evaluations"]) for result in results
        )
        == 0
        and int(progress["FCI_evaluations"]) == 0,
        "production_dense_expm_is_exactly_zero": sum(
            int(result["N_dense_expm"]) for result in results
        )
        == 0
        and int(progress["N_dense_expm"]) == 0,
        "performance_claim_remains_closed": all(
            result["performance_claim"] == "NOT_AUTHORIZED" for result in results
        )
        and progress["performance_claim"] == "NOT_AUTHORIZED",
        "FCI_cases_are_outcome_independent_exact_queue_set": queue_cases
        == EXPECTED_CASES
        and catalog_cases == EXPECTED_CASES,
        "source_catalog_contains_no_FCI_or_CCSD": source_catalog[
            "FCI_or_CCSD_computed"
        ]
        is False
        and "fci_energy_hartree" in source_catalog["forbidden_inputs"],
        "storage_at_least_40_GiB": shutil.disk_usage(ROOT).free
        >= MINIMUM_FREE_BYTES,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S12OfflineReportingGateV1Error(failures)
    return {
        "checks": checks,
        "observed": {
            "terminal_count": len(prefix),
            "terminal_status_counts": statuses,
            "FCI_evaluations": 0,
            "N_dense_expm": 0,
            "performance_claim": "NOT_AUTHORIZED",
            "production_json_file_count": production_file_count,
        },
        "frozen_reporting_scope": {
            "case_ids": list(EXPECTED_CASES),
            "case_count": len(EXPECTED_CASES),
            "case_selection_source": "exact unique case_id set in frozen queue v2",
            "candidate_outcomes_used_to_select_cases": False,
            "reference_method": "FCI",
            "execution_mode": "offline-reporting-only",
            "allowed_outputs": [
                "one FCI energy per exact frozen case",
                "immutable solver provenance and counters",
                "audit-only reconciliation to the frozen case identity",
            ],
        },
        "bindings": {
            "queue_v2": {
                "sha256": _sha(QUEUE_V2),
                "queue_digest": queue["queue_digest"],
            },
            "P7_v5": {"sha256": _sha(P7_V5), "gate_digest": p7["gate_digest"]},
            "readiness_v11": {
                "sha256": _sha(READINESS_V11),
                "readiness_digest": readiness["readiness_digest"],
            },
            "progress_90": {
                "sha256": _sha(PROGRESS_90),
                "progress_digest": progress["progress_digest"],
            },
            "source_catalog": {
                "sha256": _sha(SOURCE_CATALOG),
                "catalog_digest": source_catalog["catalog_digest"],
            },
            "result_manifest_digest": _digest(result_manifest),
            "receipt_manifest_digest": _digest(receipt_manifest),
            "production_manifest_digest": production_manifest_digest,
            "source_sha256": {
                path: _sha(ROOT / path) for path in SOURCE_PATHS
            },
        },
    }


def build_artifact(base_head: str) -> dict[str, Any]:
    body = {
        "schema": "v5-final.s12-offline-reporting-gate.v1",
        "stage": "S12_POST_S11_COMPLETION_GATE",
        "status": DECISION,
        "decision": DECISION,
        "captured_repository_state": {
            "branch": _git("branch", "--show-current"),
            "base_head_with_90_terminal_evidence": base_head,
            "recursive_submodule_status": _git(
                "submodule", "status", "--recursive"
            ).splitlines(),
        },
        **inspect_completion(),
        "authorization": {
            "offline_FCI_reference_generation": (
                "AUTHORIZED_ONCE_FOR_EXACT_FROZEN_CASE_SET_ONLY"
            ),
            "FCI_execution_control": "OUTCOME_INDEPENDENT_CASE_IDENTITY_ONLY",
            "FCI_reexecution_after_atomic_pass": "NOT_AUTHORIZED",
            "candidate_selection": "NOT_AUTHORIZED",
            "candidate_energy": "NOT_AUTHORIZED",
            "optimizer": "NOT_AUTHORIZED",
            "S11_item_rerun": "NOT_AUTHORIZED",
            "ranking_or_threshold_change": "NOT_AUTHORIZED",
            "S12_post_outcome_aggregation": (
                "NOT_AUTHORIZED_UNTIL_OFFLINE_FCI_REFERENCE_AUDIT"
            ),
            "performance_table": "NOT_AUTHORIZED",
            "pareto_analysis": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
            "release": "NOT_AUTHORIZED",
        },
        "scientific_boundary": {
            "allowed": (
                "Generate exactly one outcome-isolated FCI reference for each of the "
                "five case identities fixed before S11 outcomes."
            ),
            "forbidden": (
                "Any S11 rerun, candidate selection, threshold/ranking/method change, "
                "performance table, Pareto analysis, or performance claim."
            ),
            "current_claim": (
                "S11-v2 completed its frozen queue; no S12 performance conclusion yet."
            ),
        },
        "blockers": [],
    }
    body["gate_digest"] = _digest(body)
    return body


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S12OfflineReportingGateV1Error("S12 gate artifact already exists")
    base_head = _git("rev-parse", "HEAD")
    dirty = set(_git("status", "--porcelain").splitlines())
    expected_suffixes = set(SOURCE_PATHS)
    observed_suffixes = {line[3:] for line in dirty}
    if observed_suffixes != expected_suffixes or any(
        not line.startswith("?? ") for line in dirty
    ):
        raise S12OfflineReportingGateV1Error(
            "capture permits only the two new untracked gate source files"
        )
    artifact = build_artifact(base_head)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(OUTPUT, artifact)
    return artifact


def audit_frozen() -> dict[str, Any]:
    artifact = _load(OUTPUT)
    live = inspect_completion()
    bindings = artifact.get("bindings", {})
    checks = {
        "schema_decision_exact": artifact.get("schema")
        == "v5-final.s12-offline-reporting-gate.v1"
        and artifact.get("decision") == DECISION
        and artifact.get("status") == DECISION,
        "gate_digest_valid": _embedded_digest(artifact, "gate_digest"),
        "all_frozen_checks_pass": all(artifact.get("checks", {}).values())
        and all(live["checks"].values()),
        "authorization_is_exact_fail_closed": _validate_authorization(
            artifact.get("authorization", {})
        ),
        "frozen_case_scope_is_exact": artifact.get("frozen_reporting_scope", {})
        == live["frozen_reporting_scope"],
        "queue_P7_readiness_progress_catalog_bindings_current": all(
            bindings.get(name) == live["bindings"].get(name)
            for name in (
                "queue_v2",
                "P7_v5",
                "readiness_v11",
                "progress_90",
                "source_catalog",
            )
        ),
        "production_and_terminal_manifests_current": all(
            bindings.get(name) == live["bindings"].get(name)
            for name in (
                "result_manifest_digest",
                "receipt_manifest_digest",
                "production_manifest_digest",
            )
        ),
        "gate_sources_current": bindings.get("source_sha256")
        == live["bindings"]["source_sha256"],
        "no_blockers": artifact.get("blockers") == [],
        "artifact_is_immutable_git_blob": artifact_is_immutable_git_blob(OUTPUT),
    }
    if not all(checks.values()):
        raise S12OfflineReportingGateV1Error(
            [name for name, passed in checks.items() if not passed]
        )
    return {"decision": DECISION, "checks": checks, "gate_digest": artifact["gate_digest"]}


def audit_live() -> dict[str, Any]:
    result = audit_frozen()
    artifact = _load(OUTPUT)
    base_head = artifact["captured_repository_state"][
        "base_head_with_90_terminal_evidence"
    ]
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    checks = {
        **result["checks"],
        "base_head_is_ancestor": subprocess.run(
            ["git", "merge-base", "--is-ancestor", base_head, head], cwd=ROOT
        ).returncode
        == 0,
        "local_remote_head_match": head
        == _run_git("rev-parse", f"origin/{branch}"),
        "worktree_clean": not _git("status", "--porcelain"),
        "submodules_clean": all(
            line.startswith(" ")
            for line in _git("submodule", "status", "--recursive").splitlines()
        ),
        "storage_at_least_40_GiB": shutil.disk_usage(ROOT).free
        >= MINIMUM_FREE_BYTES,
    }
    if not all(checks.values()):
        raise S12OfflineReportingGateV1Error(
            [name for name, passed in checks.items() if not passed]
        )
    return {"decision": DECISION, "checks": checks, "gate_digest": result["gate_digest"]}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--audit-live", action="store_true")
    args = parser.parse_args(argv)
    if args.capture and args.audit_live:
        parser.error("choose one action")
    if args.capture:
        result = capture()
    elif args.audit_live:
        result = audit_live()
    else:
        result = audit_frozen()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
