"""S5 fail-closed audit for kernel-boundary work accounting."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .parent_native_work_accounting_probe import run_probe
from .s0_successor import CEO_COMMIT, PARENT_COMMIT, ROOT


OUTPUT = ROOT / "artifacts/v5-final/parent-native/s5-parent-native-work-accounting-v1.json"
PRIMARY_SOURCES = tuple(
    ROOT / value
    for value in (
        "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe/adaptvqe/minimize.py",
        "provenance/dvg-obs-ceo/src/dvg_obs_ceo/transaction.py",
        "src/v5_final/semantic_contract_v2.py",
    )
)
IMPLEMENTATION = tuple(
    ROOT / value
    for value in (
        "src/v5_final/parent_native_work_accounting.py",
        "src/v5_final/parent_native_work_accounting_probe.py",
    )
)
FROZEN_INPUTS = (
    ROOT / "artifacts/v5-final/parent-native/s4-parent-native-executors-v1.json",
)


class S5ParentNativeWorkAccountingError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build() -> dict[str, Any]:
    probe = run_probe()
    expected = probe["expected_total"]
    checks = {
        "raw_reconstructed_release_exact": (
            probe["raw_total"] == expected
            and probe["reconstructed_total"] == expected
            and probe["release_total"] == expected
        ),
        "candidate_intents_preserved_physical_states_deduplicated": (
            probe["candidate_intent_uniqueness"] == [True, False, True]
            and expected["candidate_generations"] == 3
            and expected["search_states"] == 2
            and probe["duplicate_event_count"] == 1
            and probe["duplicate_events_zero_delta"] is True
        ),
        "gradient_vectors_and_components_exact": (
            expected["gradient_vector_evaluations"] == 3
            and expected["gradient_component_equivalents"] == 12
            and expected["hvp_evaluations"] == 1
        ),
        "failed_kernel_work_preserved": (
            probe["failed_kernel_recorded"] is True
            and probe["failed_kernel_work_preserved"] is True
        ),
        "cap_rejection_precedes_kernel": (
            probe["componentwise_cap_rejected"] is True
            and probe["cap_rejection_kernel_calls"] == 0
            and probe["cap_rejection_event"]["outcome"] == "cap-rejected"
            and not any(probe["cap_rejection_event"]["delta"].values())
        ),
        "resume_restores_work_and_physical_deduplication": (
            probe["resume_alias_unique"] is False
            and probe["resume_cap_rejected"] is True
            and probe["resume_rejected_kernel_calls"] == 0
            and probe["resume_raw_total"]["energy_evaluations"] == 1
            and probe["resume_raw_total"]["candidate_generations"] == 2
            and probe["resume_raw_total"]["search_states"] == 1
        ),
        "rehashed_semantic_tamper_rejected": probe[
            "semantic_rehash_tamper_rejected"
        ]
        is True,
        "paper_cost_non_equivalence_explicit": (
            probe["paper_measurement_cost"] is None
            and probe["paper_measurement_cost_claimed_equivalent"] is False
        ),
        "pre_go_scientific_boundary_intact": (
            probe["probe_kind"] == "synthetic_non_molecular_control"
            and probe["molecular_candidate_energy_evaluations"] == 0
            and probe["H2_H4_queue_executed"] is False
            and probe["performance_evidence"] is False
        ),
    }
    if not all(checks.values()):
        raise S5ParentNativeWorkAccountingError(
            "S5 work-accounting behavioral proof failed"
        )
    artifact: dict[str, Any] = {
        "schema": "v5-final.s5-parent-native-work-accounting-audit.v1",
        "stage": "S5_KERNEL_BOUNDARY_WORK_ACCOUNTING",
        "status": "PASS_SYNTHETIC_BEHAVIORAL_PROOF_NO_MOLECULAR_OUTCOME",
        "decision": "GO_S6_PERSISTENT_RUNNER_ONLY",
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
        "authorization": {
            "S6_persistent_runner": "AUTHORIZED_OUTCOME_FREE_CONTROL_ONLY",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "MB6_v3_freeze": "NOT_AUTHORIZED_BEFORE_S6",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "The behavioral probe uses synthetic non-molecular kernels only. Its two "
            "energy counter events demonstrate accounting, not molecular candidate "
            "energies or performance. Componentwise work remains explicitly distinct "
            "from CEO* paper Measurement Cost."
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
        "decision_scoped": record["decision"] == "GO_S6_PERSISTENT_RUNNER_ONLY",
        "molecular_candidate_energy_zero": record["probe"][
            "molecular_candidate_energy_evaluations"
        ]
        == 0,
        "H2_H4_blocked": record["authorization"]["H2_H4_execution"]
        == "NOT_AUTHORIZED",
    }


def audit() -> dict[str, bool]:
    record = json.loads(OUTPUT.read_text())
    checks = verify(record)
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S5ParentNativeWorkAccountingError(
            "S5 audit failed: " + ", ".join(failures)
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
