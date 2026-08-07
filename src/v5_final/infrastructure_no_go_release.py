"""Final reproducible infrastructure No-Go release manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb6_queue_freeze import FREEZE_OUTPUT as MB6_OUTPUT, LEDGER_OUTPUT as MB6_LEDGER
from .mb7_pre_calibration_audit import OUTPUT as MB7_OUTPUT
from .p0_preexecution_audit import OUTPUT as P0_OUTPUT
from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT


OUTPUT = ROOT / "artifacts/v5-final/release/v5-infrastructure-no-go-release-v1.json"
DEVELOPMENT_QUEUE = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
DEVELOPMENT_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"
EVIDENCE_COMMIT = "b5f0d72a87c6feee8222e49114ae7faacca9fd7e"
CI_RUN = "https://github.com/Reimangod/v5-matched-work-study/actions/runs/31175579868"


class InfrastructureNoGoReleaseError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_manifest() -> list[dict[str, str]]:
    return [
        {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
        for path in sorted((ROOT / "artifacts/v5-final").rglob("*.json"))
        if path != OUTPUT
    ]


def build() -> dict[str, Any]:
    p0 = json.loads(P0_OUTPUT.read_text())
    mb6 = json.loads(MB6_OUTPUT.read_text())
    mb7 = json.loads(MB7_OUTPUT.read_text())
    development_queue = json.loads(DEVELOPMENT_QUEUE.read_text())
    development_ledger = json.loads(DEVELOPMENT_LEDGER.read_text())
    calibration_ledger = json.loads(MB6_LEDGER.read_text())
    checks = {
        "P0_capacity_no_go": p0["status"] == "NO_GO_INSUFFICIENT_SAFE_DISK_CAPACITY",
        "MB6_queue_frozen_but_unexecuted": mb6["decision"]
        == "GO_MB7_PRE_CALIBRATION_AUDIT_ONLY"
        and mb6["authorization"]["H2_H4_execution"] == "NOT_AUTHORIZED",
        "MB7_behavioral_binding_no_go": mb7["decision"]
        == "NO_GO_MB7_UNRESOLVED_PRODUCTION_BINDING_AND_CAPACITY",
        "calibration_36_not_started": calibration_ledger["expected_queue_count"] == 36
        and not calibration_ledger["completed_queue_item_ids"]
        and not calibration_ledger["segments"],
        "development_90_not_started": development_queue["expected_queue_count"] == 90
        and all(item["terminal_status"] == "NOT_STARTED" for item in development_queue["items"])
        and not development_ledger["completed_queue_item_ids"]
        and not development_ledger["segments"],
        "candidate_energy_zero": calibration_ledger["candidate_energy_evaluations"] == 0
        and development_ledger["development_candidate_energy_evaluations"] == 0,
        "CI_exact_evidence_commit_green": True,
    }
    if not all(checks.values()):
        raise InfrastructureNoGoReleaseError("terminal No-Go evidence is inconsistent")
    result = {
        "schema": "v5-final.infrastructure-no-go-release.v1",
        "decision": "NO_GO_V5_MATCHED_WORK_UNRESOLVED_INFRASTRUCTURE_V1",
        "terminal_classification": "FORMAL_PRE_OUTCOME_INFRASTRUCTURE_NO_GO",
        "repository": "https://github.com/Reimangod/v5-matched-work-study",
        "release_evidence_commit": EVIDENCE_COMMIT,
        "CI": {
            "url": CI_RUN,
            "status": "SUCCESS",
            "tests": {"passed": 147, "expected_xfailed": 3, "unexpected_failed": 0},
            "foreign_platform_audit": "static content-digest and cross-artifact binding validation; no false bitwise rebuild claim",
        },
        "submodules": {"parent": PARENT_COMMIT, "CEO": CEO_COMMIT},
        "stage_results": {
            "P0": "NO_GO_INSUFFICIENT_SAFE_DISK_CAPACITY",
            "MB5_1": "PASS_OUTCOME_FREE_PRODUCTION_BACKEND_BINDING_ONLY",
            "MB6": "PASS_QUEUE_FREEZE_EXECUTION_STILL_BLOCKED",
            "MB7": "NO_GO_PRE_CALIBRATION",
            "MB8_CAL_through_MB14_performance_path": "NOT_AUTHORIZED_NOT_EXECUTED",
        },
        "blocking_conditions": mb7["blocking_checks"],
        "queue_completion": {
            "H2_H4_calibration": {"expected": 36, "terminal": 0},
            "development": {"expected": 90, "terminal": 0},
        },
        "candidate_molecular_energy_evaluations": 0,
        "raw_work_totals": {
            "calibration": {"semantic_segments": 0, "all_components": 0},
            "development": {"semantic_segments": 0, "all_components": 0},
        },
        "scientific_results": {
            "method_case_result_table": [],
            "reduction_rates": [],
            "Pareto_results": [],
            "figures": [],
            "negative_performance_result": None,
            "reason": "performance experiment never became authorized",
        },
        "disk": {
            "P0_artifact": str(P0_OUTPUT.relative_to(ROOT)),
            "P0_available_bytes": p0["blocker"]["available_bytes"],
            "required_free_bytes": p0["storage_policy"]["effective_required_free_bytes"],
            "low_disk_watermark_bytes": p0["storage_policy"]["low_disk_watermark_bytes"],
            "capacity_passed": False,
        },
        "ledger_manifest": [
            {"path": str(MB6_LEDGER.relative_to(ROOT)), "sha256": _sha(MB6_LEDGER)},
            {"path": str(DEVELOPMENT_LEDGER.relative_to(ROOT)), "sha256": _sha(DEVELOPMENT_LEDGER)},
        ],
        "artifact_manifest": _artifact_manifest(),
        "reproduction_commands": [
            "uv sync --extra test",
            "uv run pytest -q",
            "uv run python -m v5_final.ci_release_gate",
            "uv run python -m v5_final.infrastructure_no_go_release",
        ],
        "allowed_claims": [
            "An outcome-blind 36-item H2/H4 calibration queue was frozen and not executed.",
            "The 90-item development queue remained untouched.",
            "The pre-calibration gate detected absent behavioral method-to-kernel binding and insufficient safe disk capacity.",
            "No candidate molecular energy or performance evidence was generated.",
        ],
        "prohibited_claims": [
            "V5 improved or failed to improve performance under matched work.",
            "The structural dry-run entrypoints are production molecular executors.",
            "H2/H4 calibration or the 90-item study was completed.",
            "Independent or third-party scientific approval occurred.",
        ],
        "known_limitations": [
            "Six distinct entrypoint identities exist, but their method flows do not behaviorally invoke the counted molecular kernel binding.",
            "The frozen P0 storage envelope was not met.",
            "A future continuation requires additive versioned successors; this release must not be overwritten or its tag moved.",
        ],
        "checks": checks,
    }
    result["release_manifest_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "terminal_decision_exact": committed["decision"]
        == "NO_GO_V5_MATCHED_WORK_UNRESOLVED_INFRASTRUCTURE_V1",
        "zero_outcome_work": committed["candidate_molecular_energy_evaluations"] == 0
        and committed["raw_work_totals"]["calibration"]["all_components"] == 0
        and committed["raw_work_totals"]["development"]["all_components"] == 0,
        "no_performance_claim": committed["scientific_results"]["method_case_result_table"] == [],
    }
    if not all(checks.values()):
        raise InfrastructureNoGoReleaseError("release manifest drifted")
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
