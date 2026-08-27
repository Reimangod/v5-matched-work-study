"""Terminal versioned successor release for the MB7 v2 infrastructure No-Go."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT


OUTPUT = ROOT / "artifacts/v5-final/release/v5-infrastructure-no-go-release-v2.json"
HISTORICAL_RELEASE = ROOT / "artifacts/v5-final/release/v5-infrastructure-no-go-release-v1.json"
P0 = ROOT / "artifacts/v5-final/pre-execution/p0-capacity-success-v2.json"
MB52 = ROOT / "artifacts/v5-final/method-native/mb5-2-actual-production-bindings-v1.json"
MB6_DIR = ROOT / "artifacts/v5-final/mb6-v2"
MB7 = ROOT / "artifacts/v5-final/pre-calibration/mb7-pre-calibration-audit-v2.json"
DEVELOPMENT_QUEUE = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
DEVELOPMENT_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"
EVIDENCE_COMMIT = "c1c17ec43005680c45f0fe227a64bc160480b53e"
CI_RUN = "https://github.com/Reimangod/v5-matched-work-study/actions/runs/31355175215"
TAG = "v5-matched-work-infrastructure-no-go-v2"

SUCCESSOR_ARTIFACTS = (
    P0,
    MB52,
    MB6_DIR / "execution-environment-v2.json",
    MB6_DIR / "h2-h4-source-catalog-v2.json",
    MB6_DIR / "h2-h4-calibration-queue-v2.json",
    MB6_DIR / "h2-h4-calibration-ledger-root-v2.json",
    MB6_DIR / "mb6-v1-v2-semantic-diff-audit-v1.json",
    MB6_DIR / "mb6-outcome-blind-freeze-v2.json",
    MB7,
    DEVELOPMENT_QUEUE,
    DEVELOPMENT_LEDGER,
)


class InfrastructureNoGoReleaseV2Error(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def build() -> dict[str, Any]:
    historical = _json(HISTORICAL_RELEASE)
    p0 = _json(P0)
    mb52 = _json(MB52)
    mb6 = _json(MB6_DIR / "mb6-outcome-blind-freeze-v2.json")
    queue = _json(MB6_DIR / "h2-h4-calibration-queue-v2.json")
    ledger = _json(MB6_DIR / "h2-h4-calibration-ledger-root-v2.json")
    mb7 = _json(MB7)
    development = _json(DEVELOPMENT_QUEUE)
    development_ledger = _json(DEVELOPMENT_LEDGER)
    checks = {
        "historical_v1_release_preserved": historical["decision"]
        == "NO_GO_V5_MATCHED_WORK_UNRESOLVED_INFRASTRUCTURE_V1",
        "R0_capacity_success_was_recorded": p0["decision"]
        == "GO_MB5_2_ACTUAL_BINDING_IMPLEMENTATION_ONLY",
        "MB5_2_outcome_free_runtime_audit_passed": mb52["decision"]
        == "GO_MB6_V2_OUTCOME_BLIND_REFREEZE_ONLY",
        "MB6_v2_identity_only_queue_frozen": mb6["decision"]
        == "GO_MB7_V2_PRE_CALIBRATION_AUDIT_ONLY",
        "MB7_v2_failed_closed": mb7["decision"]
        == "NO_GO_MB7_V2_UNRESOLVED_METHOD_NATIVE_PRODUCTION_SEMANTICS"
        and bool(mb7["blockers"]),
        "H2_H4_36_unexecuted": len(queue["items"]) == 36
        and not ledger["completed_queue_item_ids"]
        and not ledger["segments"],
        "development_90_unexecuted": development["expected_queue_count"] == 90
        and not development_ledger["completed_queue_item_ids"]
        and not development_ledger["segments"],
        "candidate_energy_zero": ledger["candidate_energy_evaluations"] == 0
        and development_ledger["development_candidate_energy_evaluations"] == 0,
        "performance_results_absent": True,
        "independent_review_not_claimed": True,
    }
    if not all(checks.values()):
        raise InfrastructureNoGoReleaseV2Error("terminal v2 evidence is inconsistent")
    artifact: dict[str, Any] = {
        "schema": "v5-final.infrastructure-no-go-release.v2",
        "decision": "NO_GO_V5_MATCHED_WORK_INFRASTRUCTURE_V2",
        "terminal_classification": "FORMAL_PRE_OUTCOME_INFRASTRUCTURE_NO_GO",
        "successor_of": {
            "path": str(HISTORICAL_RELEASE.relative_to(ROOT)),
            "sha256": _sha(HISTORICAL_RELEASE),
            "decision": historical["decision"],
            "unchanged": True,
        },
        "repository": "https://github.com/Reimangod/v5-matched-work-study",
        "release_evidence_commit": EVIDENCE_COMMIT,
        "planned_immutable_tag": TAG,
        "CI": {
            "url": CI_RUN,
            "status": "SUCCESS",
            "head": EVIDENCE_COMMIT,
            "scope": "exact successor evidence commit before release-manifest commit",
        },
        "submodules": {"parent": PARENT_COMMIT, "CEO": CEO_COMMIT},
        "stage_results": {
            "R0": "PASS_SAFE_CAPACITY_RECORDED_THEN_LATER_REGRESSED",
            "R1_MB5_2": "PASS_OUTCOME_FREE_RUNTIME_BINDING_AUDIT",
            "R2_MB6_V2": "PASS_IDENTITY_ONLY_QUEUE_FREEZE_NOT_EXECUTED",
            "R3_MB7_V2": "NO_GO_UNRESOLVED_METHOD_NATIVE_PRODUCTION_SEMANTICS_AND_CAPACITY",
            "R4_through_R8_performance_path": "NOT_AUTHORIZED_NOT_EXECUTED",
        },
        "blocking_conditions": mb7["blocking_checks"],
        "blocker_names": mb7["blockers"],
        "queue_completion": {
            "H2_H4_calibration_v2": {"expected": 36, "terminal": 0},
            "development": {"expected": 90, "terminal": 0},
        },
        "candidate_molecular_energy_evaluations": 0,
        "raw_work_totals": {
            "calibration": {"semantic_segments": 0, "all_components": 0},
            "development": {"semantic_segments": 0, "all_components": 0},
        },
        "scientific_results": {
            "method_case_result_table": [],
            "energy_or_error_results": [],
            "resource_reductions": [],
            "Pareto_results": [],
            "time_series_telemetry": [],
            "figures": [],
            "negative_performance_result": None,
            "reason": "performance experiment never became authorized",
        },
        "capacity": mb7["capacity"],
        "successor_artifact_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in SUCCESSOR_ARTIFACTS
        ],
        "reproduction_commands": [
            "uv sync --extra test",
            "uv run pytest -q",
            "uv run python -m v5_final.mb5_2_actual_binding_audit",
            "uv run python -m v5_final.mb6_queue_freeze_v2",
            "uv run python -m v5_final.mb7_pre_calibration_audit_v2",
            "uv run python -m v5_final.infrastructure_no_go_release_v2",
        ],
        "allowed_claims": [
            "The actual pinned catalog surface and method-native executor contract remained incompatible at MB7 v2.",
            "The MB6 v2 36-item H2/H4 queue was frozen outcome-blind and not executed.",
            "The 90-item development queue remained untouched.",
            "No candidate molecular energy or performance evidence was generated.",
            "The automated gate stopped the study before an invalid performance comparison.",
        ],
        "prohibited_claims": [
            "V5 improved or failed to improve performance under matched work.",
            "H2/H4 calibration or the 90-item study was completed.",
            "The fake behavioral traces prove production molecular execution semantics.",
            "This is a negative performance result.",
            "Independent or third-party scientific approval occurred.",
        ],
        "known_limitations": [
            "Actual CompressionCandidate objects lack fields assumed by the successor method executors.",
            "Candidate rewrites, actual verification matrices, current-state ranking, and queue-bound segment execution remain unimplemented.",
            "Safe free capacity regressed below the frozen requirement before MB7 v2 capture.",
            "Any continuation must use additive versioned successors and must not move or overwrite this release tag.",
        ],
        "checks": checks,
    }
    artifact["release_manifest_digest"] = _digest(artifact)
    return artifact


def verify(record: dict[str, Any]) -> dict[str, bool]:
    body = dict(record)
    observed = body.pop("release_manifest_digest", None)
    return {
        "release_manifest_digest_valid": observed == _digest(body),
        "historical_release_unchanged": record["successor_of"]["sha256"]
        == _sha(HISTORICAL_RELEASE),
        "successor_artifact_manifest_valid": all(
            (ROOT / item["path"]).is_file()
            and _sha(ROOT / item["path"]) == item["sha256"]
            for item in record["successor_artifact_manifest"]
        ),
        "terminal_decision_exact": record["decision"]
        == "NO_GO_V5_MATCHED_WORK_INFRASTRUCTURE_V2",
        "zero_outcome_work": record["candidate_molecular_energy_evaluations"] == 0
        and record["raw_work_totals"]["calibration"]["all_components"] == 0
        and record["raw_work_totals"]["development"]["all_components"] == 0,
        "no_performance_result": record["scientific_results"][
            "method_case_result_table"
        ]
        == []
        and record["scientific_results"]["negative_performance_result"] is None,
        "all_checks_passed": all(record["checks"].values()),
    }


def audit() -> dict[str, bool]:
    checks = verify(_json(OUTPUT))
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise InfrastructureNoGoReleaseV2Error(
            "v2 release manifest failed: " + ", ".join(failures)
        )
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
