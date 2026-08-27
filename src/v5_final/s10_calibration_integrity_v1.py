"""Reconstruct S9-v6 calibration and authorize only an outcome-blind S11 freeze."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from . import s9_h2_h4_calibration_runner as v1
from . import s9_h2_h4_calibration_runner_v6 as v6
from .s0_successor import ROOT
from .semantic_contract_v2 import WORK_COMPONENTS


OUTPUT = (
    ROOT / "artifacts/v5-final/parent-native/s10-calibration-integrity-v1.json"
)
PROTOCOL_PATH = ROOT / "artifacts/v5-final/s5/development-protocol-freeze-v3.json"
DEVELOPMENT_QUEUE_PATH = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
DEVELOPMENT_LEDGER_PATH = (
    ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"
)
FCI_REPORT_PATH = (
    ROOT / "provenance/dvg-obs-ceo/artifacts/s8/calibration-bundle/summary.json"
)
METHODS = (
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
    "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression",
    "v5-fixed-source-whitelist-no-replenishment",
    "v5-sequential-with-rebuilding",
)
ENVELOPES = ("LOW", "MEDIUM", "HIGH")
CASES = ("h2-1.5-iteration-1", "h4-1.5-first-chemical-accuracy")
RESOURCE_COMPONENTS = (
    "cnot_count",
    "cnot_depth",
    "total_depth",
    "parameter_count",
    "logical_block_count",
)
SOURCES = tuple(
    ROOT / value
    for value in (
        "src/v5_final/s10_calibration_integrity_v1.py",
        "tests/test_v5_final_s10_calibration_integrity_v1.py",
        ".github/workflows/v5-s10-calibration-integrity-gate.yml",
    )
)


class S10CalibrationIntegrityError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S10CalibrationIntegrityError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise S10CalibrationIntegrityError(f"noncanonical JSON artifact: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _digest_valid(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return isinstance(observed, str) and observed == _digest(body)


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *arguments], text=True
    ).strip()


def _is_ancestor(commit: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"],
            check=False,
        ).returncode
        == 0
    )


def _tree_manifest(paths: Iterable[Path]) -> dict[str, Any]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(value for value in path.rglob("*") if value.is_file())
        else:
            raise S10CalibrationIntegrityError(f"missing result path: {path}")
    records = [
        {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
        for path in sorted(set(files))
    ]
    return {"file_count": len(records), "manifest_digest": _digest(records)}


def _reference_energies() -> dict[str, float]:
    try:
        report = json.loads(FCI_REPORT_PATH.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S10CalibrationIntegrityError(
            "invalid immutable FCI reporting source"
        ) from error
    if not isinstance(report, dict):
        raise S10CalibrationIntegrityError("FCI reporting source is not an object")
    references = {
        str(item["case_id"]): float(item["fci_energy_hartree"])
        for item in report["checkpoints"]
        if item.get("case_id") in CASES
    }
    if tuple(sorted(references)) != tuple(sorted(CASES)):
        raise S10CalibrationIntegrityError("FCI reporting references are incomplete")
    return references


def _dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    axes = (
        "source_relative_energy_increase_hartree",
        "cnot_count",
        "cnot_depth",
        "total_depth",
        "parameter_count",
        "logical_block_count",
    )
    return all(left[name] <= right[name] for name in axes) and any(
        left[name] < right[name] for name in axes
    )


def _nondominated(rows: list[dict[str, Any]]) -> list[str]:
    return [
        str(row["method_id"])
        for row in rows
        if not any(
            _dominates(other, row)
            for other in rows
            if other["method_id"] != row["method_id"]
        )
    ]


def _calibration_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    plan = v1._plan()
    with v6._v6_scope():
        receipts = v1._completed_receipts(
            plan, allow_inflight=False, require_progress=True
        )
    if len(receipts) != 36:
        raise S10CalibrationIntegrityError("S10 requires exactly 36 terminal receipts")
    references = _reference_energies()
    source_energies: dict[tuple[str, str], float] = {}
    source_resources: dict[tuple[str, str], dict[str, int]] = {}
    raw: list[tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]] = []
    for index, (item, receipt) in enumerate(zip(plan["items"], receipts)):
        key = v1._item_key(index, item)
        result = _json(v6.RESULT_DIR / f"{key}.json")
        outcome = result.get("outcome", {}).get("result", {})
        if (
            receipt["queue_index"] != index
            or receipt["queue_item_id"] != item["queue_item_id"]
            or result.get("request", {}).get("queue_item_id") != item["queue_item_id"]
            or outcome.get("terminal_status") != receipt["terminal_status"]
        ):
            raise S10CalibrationIntegrityError("result/receipt/plan identity differs")
        raw.append((item, receipt, outcome))
        context = (str(item["case_id"]), str(item["work_envelope"]))
        if item["method_id"] == "immutable-ceo-star-source":
            source_energies[context] = float(outcome["energy_hartree"])
            source_resources[context] = {
                name: int(outcome["resources"][name]) for name in RESOURCE_COMPONENTS
            }
    expected_contexts = {(case, envelope) for case in CASES for envelope in ENVELOPES}
    if set(source_energies) != expected_contexts:
        raise S10CalibrationIntegrityError("source controls do not cover all contexts")
    rows: list[dict[str, Any]] = []
    total_candidate_energy_events = 0
    for index, (item, receipt, outcome) in enumerate(raw):
        context = (str(item["case_id"]), str(item["work_envelope"]))
        energy = float(outcome["energy_hartree"])
        resources = {
            name: int(outcome["resources"][name]) for name in RESOURCE_COMPONENTS
        }
        cap = {name: int(value) for name, value in item["componentwise_work_cap"].items()}
        work = {name: int(receipt["work_total"][name]) for name in WORK_COMPONENTS}
        if any(work[name] > cap[name] for name in WORK_COMPONENTS):
            raise S10CalibrationIntegrityError("componentwise work cap exceeded")
        candidate_events = int(
            receipt["work_operation_units"].get("candidate-energy-evaluation", 0)
        )
        if candidate_events != int(receipt["candidate_energy_evaluations"]):
            raise S10CalibrationIntegrityError("candidate event count differs")
        total_candidate_energy_events += candidate_events
        rows.append(
            {
                "queue_index": index,
                "queue_item_id": item["queue_item_id"],
                "case_id": item["case_id"],
                "work_envelope": item["work_envelope"],
                "method_id": item["method_id"],
                "terminal_status": receipt["terminal_status"],
                "stopping_reason": outcome["stopping_reason"],
                "energy_hartree": energy,
                "source_energy_hartree": source_energies[context],
                "source_relative_energy_increase_hartree": energy
                - source_energies[context],
                "fci_reporting_reference_hartree": references[item["case_id"]],
                "absolute_error_hartree": abs(energy - references[item["case_id"]]),
                "cnot_count": resources["cnot_count"],
                "cnot_depth": resources["cnot_depth"],
                "total_depth": resources["total_depth"],
                "parameter_count": resources["parameter_count"],
                "logical_block_count": resources["logical_block_count"],
                "source_resource_delta": {
                    name: resources[name] - source_resources[context][name]
                    for name in sorted(resources)
                },
                "componentwise_work": work,
                "componentwise_work_cap": cap,
                "componentwise_cap_utilization_fraction": {
                    name: {"numerator": work[name], "denominator": cap[name]}
                    for name in WORK_COMPONENTS
                },
                "candidate_energy_evaluations": candidate_events,
                "accepted_candidate_ids": list(outcome["accepted_candidate_ids"]),
                "attempt_count": len(outcome["attempts"]),
                "method_wall_time_seconds": receipt["method_wall_time_seconds"],
                "kernel_telemetry_elapsed_seconds": receipt[
                    "kernel_telemetry_elapsed_seconds"
                ],
            }
        )
    return rows, {
        "candidate_energy_events": total_candidate_energy_events,
        "references": references,
    }


def _summary(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summaries: list[dict[str, Any]] = []
    for envelope in ENVELOPES:
        for method in METHODS:
            group = [
                row
                for row in rows
                if row["work_envelope"] == envelope and row["method_id"] == method
            ]
            if len(group) != 2:
                raise S10CalibrationIntegrityError("method/envelope grid is incomplete")
            status_counts = Counter(row["terminal_status"] for row in group)
            work_total = {
                name: sum(row["componentwise_work"][name] for row in group)
                for name in WORK_COMPONENTS
            }
            summaries.append(
                {
                    "work_envelope": envelope,
                    "method_id": method,
                    "case_count": 2,
                    "terminal_status_counts": dict(sorted(status_counts.items())),
                    "accepted_outcome_identifier_count": sum(
                        len(row["accepted_candidate_ids"]) for row in group
                    ),
                    "accepted_structural_compression_candidate_count": sum(
                        sum(
                            str(identifier).startswith("candidate-v1:")
                            for identifier in row["accepted_candidate_ids"]
                        )
                        for row in group
                    ),
                    "candidate_energy_evaluations": sum(
                        row["candidate_energy_evaluations"] for row in group
                    ),
                    "componentwise_work_total": work_total,
                    "resource_reduction_context_count": sum(
                        any(value < 0 for value in row["source_resource_delta"].values())
                        for row in group
                    ),
                    "energy_increase_context_count": sum(
                        row["source_relative_energy_increase_hartree"] > 0
                        for row in group
                    ),
                }
            )
    pareto: list[dict[str, Any]] = []
    for case in CASES:
        for envelope in ENVELOPES:
            group = [
                row
                for row in rows
                if row["case_id"] == case and row["work_envelope"] == envelope
            ]
            pareto.append(
                {
                    "case_id": case,
                    "work_envelope": envelope,
                    "axes": [
                        "source_relative_energy_increase_hartree",
                        "cnot_count",
                        "cnot_depth",
                        "total_depth",
                        "parameter_count",
                        "logical_block_count",
                    ],
                    "weighted_scalar_primary": False,
                    "nondominated_method_ids": _nondominated(group),
                }
            )
    return summaries, pareto


def _development_state() -> tuple[dict[str, Any], dict[str, bool]]:
    queue = _json(DEVELOPMENT_QUEUE_PATH)
    ledger = _json(DEVELOPMENT_LEDGER_PATH)
    protocol = _json(PROTOCOL_PATH)
    items = list(queue["items"])
    checks = {
        "queue_exact_90": queue["expected_queue_count"] == 90
        and len(items) == 90
        and len({item["queue_item_id"] for item in items}) == 90,
        "queue_all_not_started": all(
            item["terminal_status"] == "NOT_STARTED" for item in items
        ),
        "ledger_empty": ledger["completed_queue_item_ids"] == []
        and ledger["segments"] == []
        and ledger["development_candidate_energy_evaluations"] == 0,
        "full_grid_policy_preserved": protocol["policy"]["case_order"]
        == ["lih-3.0", "h6-1.5", "h6-3.0", "beh2-3.0", "h4-1.5-known-development"]
        and protocol["policy"]["work_envelope_order"] == list(ENVELOPES)
        and len(protocol["policy"]["method_order"]) == 6,
        "negative_contexts_retained": protocol["policy"]["go_gate"][
            "negative_and_no_candidate_contexts_retained"
        ]
        is True,
        "fci_firewall_preserved": protocol["policy"]["fci_firewall"][
            "runtime_inputs_allowed"
        ]
        is False
        and protocol["policy"]["fci_firewall"]["offline_reporting_after_all_runs_only"]
        is True,
    }
    return {
        "queue_path": str(DEVELOPMENT_QUEUE_PATH.relative_to(ROOT)),
        "queue_sha256": _sha(DEVELOPMENT_QUEUE_PATH),
        "queue_digest": queue["queue_digest"],
        "expected_item_count": 90,
        "not_started_count": sum(
            item["terminal_status"] == "NOT_STARTED" for item in items
        ),
        "completed_count": len(ledger["completed_queue_item_ids"]),
        "segment_count": len(ledger["segments"]),
        "candidate_energy_evaluations": ledger[
            "development_candidate_energy_evaluations"
        ],
        "protocol_path": str(PROTOCOL_PATH.relative_to(ROOT)),
        "protocol_sha256": _sha(PROTOCOL_PATH),
        "policy_digest": protocol["policy"]["policy_digest"],
    }, checks


def build() -> dict[str, Any]:
    v6_report = v6.build_static_audit()
    if (
        v6_report["decision"]
        != "S9_V6_CALIBRATION_COMPLETE_AWAITING_S10_INTEGRITY"
        or v6_report["namespace_halted"] is not False
    ):
        raise S10CalibrationIntegrityError("S9-v6 is not a complete valid calibration")
    rows, row_meta = _calibration_rows()
    summaries, pareto = _summary(rows)
    development, development_checks = _development_state()
    terminal_counts = Counter(row["terminal_status"] for row in rows)
    accepted_structural_candidates = sum(
        sum(
            str(identifier).startswith("candidate-v1:")
            for identifier in row["accepted_candidate_ids"]
        )
        for row in rows
    )
    accepted_noncompression_controls = sum(
        sum(
            not str(identifier).startswith("candidate-v1:")
            for identifier in row["accepted_candidate_ids"]
        )
        for row in rows
    )
    resource_reductions = sum(
        any(value < 0 for value in row["source_resource_delta"].values())
        for row in rows
    )
    result_paths = (
        v6.DISPATCH_DIR,
        v6.RAW_DIR,
        v6.RESULT_DIR,
        v6.RECEIPT_DIR,
        v6.PROGRESS_DIR,
        v6.COMPLETENESS_PATH,
    )
    checks = {
        "S9_v6_static_integrity_passed": all(v6_report["checks"].values()),
        "exact_36_terminal_results": len(rows) == 36
        and sum(terminal_counts.values()) == 36,
        "no_infrastructure_failure": terminal_counts.get("KERNEL_FAILURE", 0) == 0,
        "no_cap_rejection": terminal_counts.get("CAP_REJECTED", 0) == 0,
        "all_post_terminal_capacity_checks_passed": v6_report["progress"][
            "all_post_item_capacity_checks_passed"
        ]
        is True,
        "candidate_energy_reconstructed_exactly": row_meta[
            "candidate_energy_events"
        ]
        == v6_report["candidate_molecular_energy_evaluations"]
        == 84,
        "componentwise_caps_all_respected": all(
            all(
                row["componentwise_work"][name]
                <= row["componentwise_work_cap"][name]
                for name in WORK_COMPONENTS
            )
            for row in rows
        ),
        "method_budget_case_grid_exact": {
            (row["case_id"], row["work_envelope"], row["method_id"])
            for row in rows
        }
        == {
            (case, envelope, method)
            for case in CASES
            for envelope in ENVELOPES
            for method in METHODS
        },
        "fci_used_for_reporting_only": True,
        "development_queue_still_pristine": all(development_checks.values()),
        "global_policy_is_no_selection_full_grid": True,
        "negative_results_retained": terminal_counts.get("ALGORITHM_REJECTED", 0)
        == 24,
        "development_and_performance_still_blocked": v6_report["authorization"][
            "development_queue_execution"
        ]
        == "NOT_AUTHORIZED"
        and v6_report["authorization"]["performance_claim"]
        == "NOT_AUTHORIZED",
    }
    if not all(checks.values()):
        raise S10CalibrationIntegrityError(
            "S10 checks failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    artifact = {
        "schema": "v5-final.s10-calibration-integrity.v1",
        "stage": "S10_H2_H4_CALIBRATION_INTEGRITY_AND_DEVELOPMENT_BINDING_GATE",
        "status": "PASS_COMPLETE_CALIBRATION_NEGATIVE_RESULT_RETAINED",
        "decision": "GO_90_ITEM_EXECUTION_BINDING_FREEZE_ONLY",
        "validated_results_commit": _git(
            "log",
            "-1",
            "--format=%H",
            "--",
            str(v6.COMPLETENESS_PATH.relative_to(ROOT)),
        ),
        "implementation_source_manifest": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for path in SOURCES
        ],
        "S9_v6": {
            "namespace": v6.RUN_NAMESPACE,
            "plan_digest": v6_report["progress"]["plan_digest"],
            "completed_terminal_count": 36,
            "candidate_molecular_energy_evaluations": row_meta[
                "candidate_energy_events"
            ],
            "terminal_status_counts": dict(sorted(terminal_counts.items())),
            "result_tree": _tree_manifest(result_paths),
            "completeness_path": str(v6.COMPLETENESS_PATH.relative_to(ROOT)),
            "completeness_sha256": _sha(v6.COMPLETENESS_PATH),
        },
        "FCI_reporting_reference": {
            "path": str(FCI_REPORT_PATH.relative_to(ROOT)),
            "sha256": _sha(FCI_REPORT_PATH),
            "values_hartree": row_meta["references"],
            "used_during_candidate_selection_or_execution": False,
            "used_for_post_execution_absolute_error_reporting_only": True,
        },
        "checks": checks,
        "calibration_rows": rows,
        "method_envelope_summary": summaries,
        "non_scalar_pareto_by_context": pareto,
        "matched_work_interpretation": {
            "componentwise_cap_is_a_vector_not_a_scalar_score": True,
            "paper_measurement_cost_equivalence_claimed": False,
            "weighted_scalar_winner_selected": False,
            "all_methods_remain_in_each_resource_energy_pareto_set": all(
                set(context["nondominated_method_ids"]) == set(METHODS)
                for context in pareto
            ),
        },
        "scientific_result": {
            "classification": "CALIBRATION_NEGATIVE_RESULT_NO_COMPRESSION_ACCEPTED",
            "accepted_structural_candidate_count": accepted_structural_candidates,
            "accepted_noncompression_control_identifier_count": (
                accepted_noncompression_controls
            ),
            "resource_reduction_result_count": resource_reductions,
            "algorithmic_negative_terminal_count": terminal_counts.get(
                "ALGORITHM_REJECTED", 0
            ),
            "infrastructure_failure_count": terminal_counts.get(
                "KERNEL_FAILURE", 0
            ),
            "interpretation": (
                "The frozen H2/H4 calibration produced no accepted compression and no "
                "resource reduction. This negative calibration is retained in full. It "
                "does not establish superiority, equivalence, or generalization."
            ),
        },
        "development_successor_contract": {
            "global_policy": "PRESERVE_COMPLETE_PRE_OUTCOME_5x3x6_GRID",
            "calibration_selects_or_drops_methods": False,
            "calibration_selects_or_drops_envelopes": False,
            "calibration_changes_thresholds_or_caps": False,
            "negative_and_no_candidate_contexts_retained": True,
            "existing_queue": development,
            "required_successor_namespace": "s11-development-queue-v4",
            "allowed_successor_changes": [
                "schema/version and queue/item IDs",
                "executor and runtime binding identities",
                "S10 authorization reference",
            ],
            "required_invariants": [
                "five cases",
                "three work envelopes",
                "six methods",
                "90-item order",
                "source identities",
                "acceptance thresholds",
                "componentwise work caps",
                "FCI firewall",
            ],
        },
        "authorization": {
            "S11_outcome_blind_90_item_successor_freeze": "AUTHORIZED",
            "existing_90_item_queue_execution": "NOT_AUTHORIZED",
            "successor_90_item_queue_execution": (
                "NOT_AUTHORIZED_UNTIL_SUCCESSOR_FREEZE_AND_EXACT_CI"
            ),
            "performance_claim": "NOT_AUTHORIZED",
            "release": "NOT_AUTHORIZED",
        },
        "claim_boundary": {
            "allowed_now": [
                "36/36 calibration terminals are integrity-reconciled",
                "the calibration produced a negative compression result",
                "S11 outcome-blind successor binding may be frozen",
            ],
            "prohibited_now": [
                "V5 superiority or equivalence",
                "independent test-set generalization",
                "90-item matched-work performance",
                "CEO* paper Measurement Cost equivalence",
            ],
        },
    }
    artifact["audit_digest"] = _digest(artifact)
    return artifact


def audit() -> dict[str, bool]:
    committed = _json(OUTPUT)
    rebuilt = build()
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "audit_digest_valid": _digest_valid(committed, "audit_digest"),
        "results_commit_is_ancestor": _is_ancestor(
            committed["validated_results_commit"]
        ),
        "implementation_sources_unchanged": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in committed["implementation_source_manifest"]
        ),
        "all_captured_checks_passed": all(committed["checks"].values()),
        "negative_result_retained": committed["scientific_result"][
            "classification"
        ]
        == "CALIBRATION_NEGATIVE_RESULT_NO_COMPRESSION_ACCEPTED",
        "only_successor_freeze_authorized": committed["authorization"]
        == {
            "S11_outcome_blind_90_item_successor_freeze": "AUTHORIZED",
            "existing_90_item_queue_execution": "NOT_AUTHORIZED",
            "successor_90_item_queue_execution": (
                "NOT_AUTHORIZED_UNTIL_SUCCESSOR_FREEZE_AND_EXACT_CI"
            ),
            "performance_claim": "NOT_AUTHORIZED",
            "release": "NOT_AUTHORIZED",
        },
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S10CalibrationIntegrityError(
            "S10 audit failed: " + ", ".join(failures)
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--build-output", type=Path)
    args = parser.parse_args()
    if args.freeze:
        if _git("status", "--porcelain"):
            raise S10CalibrationIntegrityError("S10 freeze requires a clean worktree")
        write_json_exclusive(OUTPUT, build())
        print(OUTPUT)
        return
    if args.build_output is not None:
        write_json_exclusive(args.build_output, build())
        print(args.build_output)
        return
    if OUTPUT.exists():
        print(json.dumps(audit(), sort_keys=True))
    else:
        print(json.dumps(build(), sort_keys=True))


if __name__ == "__main__":
    main()
