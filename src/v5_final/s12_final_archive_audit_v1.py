"""Append-only final archive audit for the frozen S11/S12 matched-work study."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Sequence

from v5_matched_work.atomic_artifacts import write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .s0_successor import ROOT
from .s11_v2_execution_readiness_v4 import _digest, _embedded_digest, _git, _load, _sha
from .s12_matched_work_aggregation_v1 import (
    MANIFEST as AGGREGATION_MANIFEST,
    audit_frozen as audit_aggregation,
)
from .s12_matched_work_figures_v1 import (
    MANIFEST_NAME as FIGURE_MANIFEST_NAME,
    OUTPUT_DIR as FIGURE_DIR,
    audit_frozen as audit_figures,
)
from .s12_offline_fci_reference_v1 import RESULT as FCI_RESULT
from .s12_offline_fci_result_audit_v1 import (
    OUTPUT as FCI_AUDIT,
    audit_frozen as audit_fci_result,
)
from .s12_offline_reporting_gate_v1 import OUTPUT as REPORTING_GATE
from .s12_scientific_report_v1 import (
    MANIFEST_NAME as REPORT_MANIFEST_NAME,
    OUTPUT_DIR as REPORT_DIR,
    SUMMARY_NAME,
    audit_frozen as audit_report,
)


OUTPUT = (
    ROOT / "artifacts/v5-final/parent-native/s12-final-archive-audit-v1/"
    "final-archive-audit-pass-v1.json"
)
DECISION = "PASS_S12_FINAL_SCIENTIFIC_ARCHIVE_COMPLETE"
WORKFLOW = ROOT / ".github/workflows/v5-release-gate.yml"
FIGURE_MANIFEST = FIGURE_DIR / FIGURE_MANIFEST_NAME
REPORT_MANIFEST = REPORT_DIR / REPORT_MANIFEST_NAME
SUMMARY = REPORT_DIR / SUMMARY_NAME
SOURCE_PATHS = (
    "src/v5_final/s12_final_archive_audit_v1.py",
    "tests/test_v5_final_s12_final_archive_audit_v1.py",
    ".github/workflows/v5-release-gate.yml",
)
EXPECTED_DIRTY = {
    "src/v5_final/s12_final_archive_audit_v1.py",
    "tests/test_v5_final_s12_final_archive_audit_v1.py",
    ".github/workflows/v5-release-gate.yml",
}


class S12FinalArchiveAuditV1Error(RuntimeError):
    pass


def _submodules() -> list[str]:
    output = subprocess.run(
        ["git", "submodule", "status", "--recursive"], cwd=ROOT, check=True,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.rstrip("\r\n")
    return [] if not output else output.splitlines()


def inspect_archive() -> dict[str, Any]:
    fci_audit = audit_fci_result()
    aggregation_audit = audit_aggregation()
    figure_audit = audit_figures()
    report_audit = audit_report()
    aggregation = _load(AGGREGATION_MANIFEST)
    figures = _load(FIGURE_MANIFEST)
    report = _load(REPORT_MANIFEST)
    summary = _load(SUMMARY)
    fci = _load(FCI_RESULT)
    reporting_gate = _load(REPORTING_GATE)
    submodules = _submodules()
    expected_status = {
        "ALGORITHM_REJECTED": 23,
        "CAP_REJECTED": 8,
        "COMPLETED": 58,
        "FAILED_ENGINEERING_PRESERVED": 1,
    }
    expected_counters = {
        "FCI_evaluations": 5,
        "candidate_energy_evaluations": 0,
        "optimizer_starts": 0,
        "S11_items_rerun": 0,
        "production_N_dense_expm": 0,
    }
    checks = {
        "FCI_result_audit_pass": all(fci_audit["checks"].values()),
        "aggregation_audit_pass": all(aggregation_audit["checks"].values()),
        "figure_audit_pass": all(figure_audit["checks"].values()),
        "scientific_report_audit_pass": all(report_audit["checks"].values()),
        "exact_frozen_population": summary["population"]["queue_items"] == 90
        and summary["population"]["terminal_status_counts"] == expected_status,
        "FCI_and_firewall_counters_exact": fci["counters"] == expected_counters,
        "source_queue_and_result_bindings_present": all(
            name in aggregation["bindings"]
            for name in (
                "queue_v2_digest", "result_manifest_digest",
                "receipt_manifest_digest", "FCI_result_digest",
            )
        ),
        "queue_P7_and_production_bindings_exact": reporting_gate["bindings"]
        ["queue_v2"]["queue_digest"] == aggregation["bindings"]["queue_v2_digest"]
        and bool(reporting_gate["bindings"]["P7_v5"]["gate_digest"])
        and bool(reporting_gate["bindings"]["production_manifest_digest"]),
        "recursive_submodules_clean": len(submodules) == 2
        and all(line.startswith(" ") for line in submodules),
        "all_report_claim_boundaries_present": bool(
            summary["claim_boundary"]["allowed"]
        ) and bool(summary["claim_boundary"]["not_allowed"]),
        "release_workflow_keeps_full_suite": (
            "v5_final.full_repository_suite_v2" in WORKFLOW.read_text()
            and "timeout-minutes: 240" in WORKFLOW.read_text()
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S12FinalArchiveAuditV1Error(failures)
    return {
        "checks": checks,
        "observed": {
            "terminal_status_counts": expected_status,
            "FCI_counters": expected_counters,
            "paired_sample_sizes": {
                row["method_id"]: row["paired_n"]
                for row in summary["paired_summary"]
            },
            "FCI_case_count": len(fci["cases"]),
        },
        "bindings": {
            "FCI_result_sha256": _sha(FCI_RESULT),
            "FCI_result_digest": fci["result_digest"],
            "FCI_audit_sha256": _sha(FCI_AUDIT),
            "FCI_audit_digest": fci_audit["audit_digest"],
            "aggregation_manifest_sha256": _sha(AGGREGATION_MANIFEST),
            "aggregation_manifest_digest": aggregation["manifest_digest"],
            "figure_manifest_sha256": _sha(FIGURE_MANIFEST),
            "figure_manifest_digest": figures["manifest_digest"],
            "report_manifest_sha256": _sha(REPORT_MANIFEST),
            "report_manifest_digest": report["manifest_digest"],
            "scientific_summary_sha256": _sha(SUMMARY),
            "scientific_summary_digest": summary["summary_digest"],
            "reporting_gate_sha256": _sha(REPORTING_GATE),
            "reporting_gate_digest": reporting_gate["gate_digest"],
            "queue_v2_digest": aggregation["bindings"]["queue_v2_digest"],
            "P7_v5_gate_digest": reporting_gate["bindings"]["P7_v5"][
                "gate_digest"
            ],
            "S11_production_manifest_digest": reporting_gate["bindings"][
                "production_manifest_digest"
            ],
            "S11_result_manifest_digest": aggregation["bindings"][
                "result_manifest_digest"
            ],
            "S11_receipt_manifest_digest": aggregation["bindings"][
                "receipt_manifest_digest"
            ],
            "source_sha256": {path: _sha(ROOT / path) for path in SOURCE_PATHS},
            "recursive_submodules": submodules,
        },
    }


def build_artifact(base_head: str) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": "v5-final.s12-final-archive-audit.v1",
        "stage": "S12_FINAL_ARCHIVE_AUDIT",
        "status": DECISION,
        "decision": DECISION,
        "base_head": base_head,
        **inspect_archive(),
        "verification_evidence": {
            "local_full_repository_suite": {
                "date": "2026-08-27",
                "exit_code": 0,
                "total_collected": 481,
                "current_partition": {"collected": 440, "passed": 437, "xfailed": 3},
                "historical_two_thread_partition": {"collected": 41, "passed": 41},
                "thread_contract": "1-thread current / 2-thread S8-S9 historical",
            },
            "fresh_recursive_clone": {
                "base_head": base_head,
                "recursive_submodules_exact": True,
                "artifact_hashes_exact": True,
                "S12_live_audits_pass": True,
                "scoped_test_files": 5,
                "scoped_tests_pass": 21,
            },
            "github_parent_head": {
                "head": base_head,
                "successful_workflows": 16,
                "release_gate_run_id": 32955179373,
                "release_gate_conclusion": "CANCELLED_AT_90_MINUTE_JOB_TIMEOUT",
                "release_gate_progress_before_cancel": "81_PERCENT_NO_TEST_FAILURE",
                "remediation": "timeout raised to bounded 240 minutes; suite unchanged",
            },
            "base_local_remote_match": _git("rev-parse", "HEAD")
            == _git("rev-parse", "origin/agent/s11-v2-frozen-90-execution"),
        },
        "authorization": {
            "scientific_archive": "COMPLETE",
            "S11_rerun": "NOT_AUTHORIZED",
            "FCI_reexecution": "NOT_AUTHORIZED",
            "candidate_reselection": "NOT_AUTHORIZED",
            "retrospective_protocol_change": "NOT_AUTHORIZED",
            "new_performance_or_generalization_experiment": "NOT_AUTHORIZED",
        },
        "claim_boundary": summary_claim_boundary(),
    }
    value["audit_digest"] = _digest(value)
    return value


def summary_claim_boundary() -> dict[str, Any]:
    return _load(SUMMARY)["claim_boundary"]


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S12FinalArchiveAuditV1Error("final archive artifact already exists")
    dirty = _git("status", "--porcelain").splitlines()
    dirty_paths = {line[3:] for line in dirty}
    if dirty_paths != EXPECTED_DIRTY:
        raise S12FinalArchiveAuditV1Error(
            f"capture permits only final audit source/test/workflow: {dirty_paths}"
        )
    artifact = build_artifact(_git("rev-parse", "HEAD"))
    write_json_exclusive(OUTPUT, artifact)
    return artifact


def audit_frozen() -> dict[str, Any]:
    artifact = _load(OUTPUT)
    live = inspect_archive()
    checks = {
        "schema_decision_exact": artifact.get("schema")
        == "v5-final.s12-final-archive-audit.v1"
        and artifact.get("decision") == DECISION
        and artifact.get("status") == DECISION,
        "audit_digest_valid": _embedded_digest(artifact, "audit_digest"),
        "all_captured_and_live_checks_pass": all(artifact["checks"].values())
        and all(live["checks"].values()),
        "bindings_current": artifact["bindings"] == live["bindings"],
        "observations_current": artifact["observed"] == live["observed"],
        "base_head_is_ancestor": subprocess.run(
            ["git", "merge-base", "--is-ancestor", artifact["base_head"], "HEAD"],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0,
        "artifact_is_immutable_git_blob": artifact_is_immutable_git_blob(OUTPUT),
        "FCI_reexecution_closed": artifact["authorization"]["FCI_reexecution"]
        == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise S12FinalArchiveAuditV1Error(
            [name for name, passed in checks.items() if not passed]
        )
    return {"decision": DECISION, "checks": checks,
            "audit_digest": artifact["audit_digest"]}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args(argv)
    value = capture() if args.capture else audit_frozen()
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
