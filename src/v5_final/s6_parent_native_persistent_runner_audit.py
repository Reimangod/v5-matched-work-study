"""S6 fail-closed audit of the parent-native persistent item runner."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .parent_native_persistent_runner_probe import run_probe
from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT


OUTPUT = ROOT / "artifacts/v5-final/parent-native/s6-parent-native-persistent-runner-v1.json"
PRIMARY_SOURCES = tuple(
    ROOT / value
    for value in (
        "src/v5_matched_work/atomic_artifacts.py",
        "src/v5_final/semantic_contract_v2.py",
        "src/v5_final/parent_native_work_accounting.py",
    )
)
IMPLEMENTATION = tuple(
    ROOT / value
    for value in (
        "src/v5_final/parent_native_persistent_runner.py",
        "src/v5_final/parent_native_persistent_runner_probe.py",
    )
)
FROZEN_INPUTS = (
    ROOT / "artifacts/v5-final/parent-native/s5-parent-native-work-accounting-v1.json",
)


class S6ParentNativePersistentRunnerError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build() -> dict[str, Any]:
    probe = run_probe()
    checks = {
        "four_terminal_statuses_distinct": probe["terminal_statuses"]
        == {
            "accepted": "ACCEPTED",
            "algorithm_rejected": "ALGORITHM_REJECTED",
            "cap_rejected": "CAP_REJECTED",
            "kernel_failure": "KERNEL_FAILURE",
        },
        "exactly_one_item_terminal": probe["accepted_terminal_count"] == 1,
        "interruption_resumes_without_counter_reset": (
            probe["process_interruption_resume_work_total"]["energy_evaluations"]
            == 1
            and probe["process_interruption_resume_work_total"][
                "optimizer_iterations"
            ]
            == 1
        ),
        "publication_failure_recovers_without_rerun": (
            probe["publication_failure_observed"] is True
            and probe["recovery_identical_after_publication_failure"] is True
            and probe["successful_publication_recovered_digest"]
            == probe["raw_recovery_digest"]
        ),
        "cap_rejection_precedes_kernel": probe["cap_rejection_kernel_calls"] == 0,
        "retry_requires_rollback_and_preserves_work": (
            probe["retry_attempt_count"] == 2
            and probe["retry_rollback_count"] == 1
            and probe["retry_preserved_failed_and_successful_work"] is True
            and probe["invalid_rollback_rejected_before_append"] is True
        ),
        "exclusive_raw_ledger_root": probe["duplicate_root_rejected"] is True,
        "orphan_attempt_fail_closed": probe["orphan_attempt_rejected"] is True,
        "duplicate_terminal_fail_closed": probe["duplicate_terminal_rejected"] is True,
        "digest_mismatch_fail_closed": probe["digest_mismatch_rejected"] is True,
        "pre_go_scientific_boundary_intact": (
            probe["probe_kind"]
            == "synthetic_non_molecular_filesystem_control"
            and probe["molecular_candidate_energy_evaluations"] == 0
            and probe["H2_H4_queue_executed"] is False
            and probe["performance_evidence"] is False
        ),
    }
    if not all(checks.values()):
        raise S6ParentNativePersistentRunnerError(
            "S6 persistent-runner behavioral proof failed"
        )
    artifact: dict[str, Any] = {
        "schema": "v5-final.s6-parent-native-persistent-runner-audit.v1",
        "stage": "S6_PERSISTENT_ONE_ITEM_RUNNER",
        "status": "PASS_SYNTHETIC_FILESYSTEM_FAULT_PROOF_NO_MOLECULAR_OUTCOME",
        "decision": "GO_S7_OUTCOME_BLIND_MB6_V3_REFREEZE_ONLY",
        "pinned_commits": {"parent": PARENT_COMMIT, "CEO": CEO_COMMIT},
        "primary_source_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in PRIMARY_SOURCES
        ],
        "implementation_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in IMPLEMENTATION
        ],
        "frozen_input_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in FROZEN_INPUTS
        ],
        "probe": probe,
        "checks": checks,
        "raw_ledger_protocol": {
            "publication": "one canonical JSON record per atomic exclusive-create file",
            "chains": "record digest chain plus strict parent-native kernel-event chain",
            "terminal_cardinality": "exactly one terminal per queue item",
            "resume": "all work and physical-state deduplication reconstructed from raw events",
            "result_publication": "derived from terminal raw ledger; never reruns kernels",
        },
        "authorization": {
            "S7_MB6_v3_outcome_blind_refreeze": "AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED_BEFORE_S8_GO",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "All persistence and failure probes use synthetic non-molecular kernels. "
            "Raw work survives failure and retry, but no scientific outcome or "
            "performance evidence has been produced."
        ),
    }
    artifact["audit_digest"] = _digest(artifact)
    return artifact


def verify(record: dict[str, Any]) -> dict[str, bool]:
    body = dict(record)
    observed = body.pop("audit_digest", None)
    return {
        "audit_digest_valid": observed == _digest(body),
        "primary_sources_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in record["primary_source_manifest"]
        ),
        "implementation_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in record["implementation_manifest"]
        ),
        "frozen_inputs_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in record["frozen_input_manifest"]
        ),
        "all_checks_passed": all(record["checks"].values()),
        "decision_scoped": record["decision"]
        == "GO_S7_OUTCOME_BLIND_MB6_V3_REFREEZE_ONLY",
        "candidate_energy_zero": record["probe"][
            "molecular_candidate_energy_evaluations"
        ]
        == 0,
        "H2_H4_still_blocked": record["authorization"]["H2_H4_execution"]
        == "NOT_AUTHORIZED_BEFORE_S8_GO",
    }


def audit() -> dict[str, bool]:
    record = json.loads(OUTPUT.read_text())
    checks = verify(record)
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S6ParentNativePersistentRunnerError(
            "S6 audit failed: " + ", ".join(failures)
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
