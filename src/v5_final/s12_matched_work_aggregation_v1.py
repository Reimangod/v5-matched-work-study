"""Deterministic, status-aware aggregation of the exact frozen S11 population."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from v5_matched_work.atomic_artifacts import (
    canonical_json_bytes,
    write_bytes_exclusive,
    write_json_exclusive,
)

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .s0_successor import ROOT
from .s11_v2_execution_readiness_v4 import PRODUCTION_ROOT, _digest, _embedded_digest, _git, _load, _sha
from .s11_v2_execution_runner_v1 import _item_paths
from .s11_v2_queue_native_adapter import QUEUE_V2, QueueV2NativeAdapter
from .s12_offline_fci_reference_v1 import RESULT as FCI_RESULT
from .s12_post_outcome_aggregation_gate_v1 import (
    OUTPUT as AGGREGATION_GATE,
    audit_frozen as audit_aggregation_gate,
)


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s12-matched-work-aggregation-v1"
LONG_JSON = OUTPUT_DIR / "matched-work-long-form-v1.json"
LONG_CSV = OUTPUT_DIR / "matched-work-long-form-v1.csv"
STATUS_JSON = OUTPUT_DIR / "terminal-status-summary-v1.json"
STATUS_CSV = OUTPUT_DIR / "terminal-status-summary-v1.csv"
PAIRED_JSON = OUTPUT_DIR / "paired-comparisons-v1.json"
PAIRED_CSV = OUTPUT_DIR / "paired-comparisons-v1.csv"
PARETO_JSON = OUTPUT_DIR / "pareto-fronts-v1.json"
PARETO_CSV = OUTPUT_DIR / "pareto-fronts-v1.csv"
MANIFEST = OUTPUT_DIR / "aggregation-manifest-v1.json"
SOURCE_PATHS = (
    "src/v5_final/s12_matched_work_aggregation_v1.py",
    "tests/test_v5_final_s12_matched_work_aggregation_v1.py",
)
METHOD_SOURCE = "immutable-ceo-star-source"
EXPECTED_STATUSES = {
    "COMPLETED": 58,
    "ALGORITHM_REJECTED": 23,
    "CAP_REJECTED": 8,
    "FAILED_ENGINEERING_PRESERVED": 1,
}
RESOURCE_FIELDS = (
    "parameter_count", "logical_block_count", "cnot_count", "cnot_depth",
    "total_depth",
)
PARETO_OBJECTIVES = (
    "absolute_fci_error_hartree", "cnot_count", "total_depth",
    "parameter_count", "total_registered_work",
)
NON_ADDITIVE_METADATA = {"matrix_dimension", "qubit_count"}


class S12MatchedWorkAggregationV1Error(RuntimeError):
    pass


def _csv_bytes(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: "NA" if row.get(field) is None else row.get(field) for field in fields})
    return stream.getvalue().encode("utf-8")


def _finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise S12MatchedWorkAggregationV1Error("non-finite metric")
    return number


def _combine_work(
    raw: Mapping[str, Any], verifier: Mapping[str, Any], schema: Sequence[str],
) -> dict[str, int]:
    combined: dict[str, int] = {}
    for name in schema:
        left = int(raw.get(name, 0))
        right = int(verifier.get(name, 0))
        if left < 0 or right < 0:
            raise S12MatchedWorkAggregationV1Error("negative work counter")
        combined[name] = left + right
    return combined


def build_long_form_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gate = audit_aggregation_gate()
    adapter = QueueV2NativeAdapter()
    queue = adapter.queue
    fci_result = _load(FCI_RESULT)
    fci = {case["case_id"]: float(case["FCI_energy_hartree"]) for case in fci_result["cases"]}
    schema = tuple(queue["complete_counter_schema"])
    if set(NON_ADDITIVE_METADATA) - set(schema):
        raise S12MatchedWorkAggregationV1Error("counter schema metadata differs")
    rows: list[dict[str, Any]] = []
    result_bindings: dict[str, str] = {}
    receipt_bindings: dict[str, str] = {}
    for index, item in enumerate(queue["items"]):
        request = adapter.request(str(item["queue_item_id"]))
        paths = _item_paths(PRODUCTION_ROOT, index, request)
        result = _load(paths["result"])
        receipt = _load(paths["receipt"])
        if not _embedded_digest(result, "result_digest") or not _embedded_digest(
            receipt, "receipt_digest"
        ):
            raise S12MatchedWorkAggregationV1Error("result or receipt digest invalid")
        if (
            result["queue_item_id"] != item["queue_item_id"]
            or result["case_id"] != item["case_id"]
            or result["method_id"] != item["method_id"]
            or result["work_envelope"] != item["work_envelope"]
            or receipt["queue_item_id"] != item["queue_item_id"]
            or receipt["result_digest"] != result["result_digest"]
            or receipt["terminal_status"] != result["terminal_status"]
        ):
            raise S12MatchedWorkAggregationV1Error("queue/result/receipt identity differs")
        raw_work = dict(result["raw_work_total"])
        verifier_work = dict(result["verifier_work_total"])
        outcome = result.get("outcome")
        if isinstance(outcome, dict):
            if outcome.get("work_total") != raw_work or outcome.get(
                "verifier_work_total"
            ) != verifier_work:
                raise S12MatchedWorkAggregationV1Error("outcome/work reconciliation differs")
        combined = _combine_work(raw_work, verifier_work, schema)
        total_work = sum(
            value for name, value in combined.items() if name not in NON_ADDITIVE_METADATA
        )
        native = outcome.get("result", {}) if isinstance(outcome, dict) else {}
        if not isinstance(native, dict):
            native = {}
        energy = _finite_or_none(native.get("energy_hartree"))
        resources = native.get("resources") if isinstance(native.get("resources"), dict) else {}
        accepted_ids = native.get("accepted_candidate_ids")
        accepted_count = len(accepted_ids) if isinstance(accepted_ids, list) else None
        status = str(result["terminal_status"])
        comparison_eligible = status == "COMPLETED" and energy is not None and all(
            resources.get(name) is not None for name in RESOURCE_FIELDS
        )
        row: dict[str, Any] = {
            "queue_index": index,
            "queue_item_id": item["queue_item_id"],
            "case_id": item["case_id"],
            "method_id": item["method_id"],
            "budget": item["work_envelope"],
            "terminal_status": status,
            "metric_semantics": (
                "accepted_result" if status == "COMPLETED" else
                "nonaccepted_terminal_observation" if energy is not None else
                "not_available"
            ),
            "comparison_eligible": comparison_eligible,
            "energy_hartree": energy,
            "FCI_energy_hartree": fci[item["case_id"]],
            "absolute_fci_error_hartree": (
                None if energy is None else abs(energy - fci[item["case_id"]])
            ),
            "delta_energy_vs_immutable_ceo_source_hartree": None,
            "accepted_candidate_count": accepted_count,
            "parameter_count": resources.get("parameter_count"),
            "operators_blocks": resources.get("logical_block_count"),
            "logical_block_count": resources.get("logical_block_count"),
            "cnot_count": resources.get("cnot_count"),
            "cnot_depth": resources.get("cnot_depth"),
            "total_depth": resources.get("total_depth"),
            "candidate_energy_evaluations": int(result["candidate_energy_evaluations"]),
            "source_energy_evaluations": int(result["source_energy_evaluations"]),
            "FCI_evaluations": int(result["FCI_evaluations"]),
            "production_N_dense_expm": int(result["N_dense_expm"]),
            "total_registered_work": total_work,
            "verifier_matrix_dimension": combined["matrix_dimension"],
            "verifier_qubit_count": combined["qubit_count"],
            "result_digest": result["result_digest"],
            "receipt_digest": receipt["receipt_digest"],
        }
        for name, value in combined.items():
            if name not in NON_ADDITIVE_METADATA:
                row[name] = value
        if row["energy_evaluations"] != raw_work["energy_evaluations"] + int(
            verifier_work.get("energy_evaluations", 0)
        ) or row["candidate_energy_evaluations"] != int(
            result["raw_work_operation_units"].get("candidate-energy-evaluation", 0)
        ):
            raise S12MatchedWorkAggregationV1Error("energy accounting differs")
        rows.append(row)
        result_bindings[str(paths["result"].relative_to(ROOT))] = _sha(paths["result"])
        receipt_bindings[str(paths["receipt"].relative_to(ROOT))] = _sha(paths["receipt"])
    baseline = {
        (row["case_id"], row["budget"]): row
        for row in rows if row["method_id"] == METHOD_SOURCE
    }
    if len(baseline) != 15:
        raise S12MatchedWorkAggregationV1Error("source baseline grid is not exact 15")
    for row in rows:
        source = baseline[(row["case_id"], row["budget"])]
        if row["comparison_eligible"] and source["comparison_eligible"]:
            row["delta_energy_vs_immutable_ceo_source_hartree"] = (
                row["energy_hartree"] - source["energy_hartree"]
            )
    statuses = dict(sorted(Counter(row["terminal_status"] for row in rows).items()))
    if len(rows) != 90 or statuses != EXPECTED_STATUSES:
        raise S12MatchedWorkAggregationV1Error("population/status counts differ")
    item000 = rows[0]
    if not (
        item000["case_id"] == "lih-3.0"
        and item000["budget"] == "LOW"
        and item000["method_id"] == METHOD_SOURCE
        and item000["terminal_status"] == "FAILED_ENGINEERING_PRESERVED"
        and item000["energy_hartree"] is None
        and item000["comparison_eligible"] is False
    ):
        raise S12MatchedWorkAggregationV1Error("item000 engineering NA not preserved")
    bindings = {
        "aggregation_gate_sha256": _sha(AGGREGATION_GATE),
        "aggregation_gate_digest": gate["gate_digest"],
        "queue_v2_sha256": _sha(QUEUE_V2),
        "queue_v2_digest": queue["queue_digest"],
        "FCI_result_sha256": _sha(FCI_RESULT),
        "FCI_result_digest": fci_result["result_digest"],
        "result_manifest_digest": _digest(result_bindings),
        "receipt_manifest_digest": _digest(receipt_bindings),
        "source_sha256": {path: _sha(ROOT / path) for path in SOURCE_PATHS},
    }
    return rows, bindings


def _status_record(group_type: str, group_id: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["terminal_status"]) for row in rows)
    total = len(rows)
    record: dict[str, Any] = {"group_type": group_type, "group_id": group_id, "n": total}
    for status in EXPECTED_STATUSES:
        value = counts.get(status, 0)
        record[f"n_{status}"] = value
        record[f"rate_{status}"] = value / total
    return record


def build_status_records(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = [_status_record("overall", "all", rows)]
    methods = sorted({str(row["method_id"]) for row in rows})
    cases = sorted({str(row["case_id"]) for row in rows})
    budgets = ("LOW", "MEDIUM", "HIGH")
    for method in methods:
        subset = [row for row in rows if row["method_id"] == method]
        records.append(_status_record("method", method, subset))
        for budget in budgets:
            cell = [row for row in subset if row["budget"] == budget]
            records.append(_status_record("method_budget", f"{method}|{budget}", cell))
    for case in cases:
        for budget in budgets:
            cell = [row for row in rows if row["case_id"] == case and row["budget"] == budget]
            records.append(_status_record("case_budget", f"{case}|{budget}", cell))
    return records


def _reduction(source: float | int, comparator: float | int) -> float | None:
    base = float(source)
    return None if base == 0.0 else 100.0 * (base - float(comparator)) / base


def build_paired_records(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    source = {
        (row["case_id"], row["budget"]): row
        for row in rows if row["method_id"] == METHOD_SOURCE
    }
    records: list[dict[str, Any]] = []
    for row in rows:
        if row["method_id"] == METHOD_SOURCE:
            continue
        baseline = source[(row["case_id"], row["budget"])]
        eligible = bool(row["comparison_eligible"] and baseline["comparison_eligible"])
        if not baseline["comparison_eligible"]:
            reason = "immutable_source_not_completed"
        elif not row["comparison_eligible"]:
            reason = "comparator_not_completed"
        else:
            reason = None
        record: dict[str, Any] = {
            "case_id": row["case_id"], "budget": row["budget"],
            "method_id": row["method_id"], "paired_eligible": eligible,
            "ineligibility_reason": reason,
            "source_terminal_status": baseline["terminal_status"],
            "comparator_terminal_status": row["terminal_status"],
            "delta_energy_hartree": None,
            "delta_absolute_fci_error_hartree": None,
        }
        for name in ("parameter_count", "operators_blocks", "cnot_count", "cnot_depth", "total_depth"):
            record[f"source_{name}"] = baseline[name] if eligible else None
            record[f"comparator_{name}"] = row[name] if eligible else None
            record[f"reduction_{name}_percent"] = None
        if eligible:
            record["delta_energy_hartree"] = row["energy_hartree"] - baseline["energy_hartree"]
            record["delta_absolute_fci_error_hartree"] = (
                row["absolute_fci_error_hartree"] - baseline["absolute_fci_error_hartree"]
            )
            for name in ("parameter_count", "operators_blocks", "cnot_count", "cnot_depth", "total_depth"):
                record[f"reduction_{name}_percent"] = _reduction(baseline[name], row[name])
        records.append(record)
    if len(records) != 75:
        raise S12MatchedWorkAggregationV1Error("paired comparison grid differs")
    return records


def _dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    values = [(float(left[name]), float(right[name])) for name in PARETO_OBJECTIVES]
    return all(a <= b for a, b in values) and any(a < b for a, b in values)


def build_pareto(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fronts: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    paired: list[dict[str, Any]] = []
    for case in sorted({str(row["case_id"]) for row in rows}):
        for budget in ("LOW", "MEDIUM", "HIGH"):
            cell = [row for row in rows if row["case_id"] == case and row["budget"] == budget]
            eligible = [
                row for row in cell
                if row["comparison_eligible"]
                and all(row.get(name) is not None for name in PARETO_OBJECTIVES)
            ]
            for row in cell:
                if row not in eligible:
                    exclusions.append({
                        "case_id": case, "budget": budget,
                        "method_id": row["method_id"],
                        "terminal_status": row["terminal_status"],
                        "reason": "not_COMPLETED_or_missing_verified_objective",
                    })
            for row in eligible:
                dominated_by = [
                    other["method_id"] for other in eligible
                    if other is not row and _dominates(other, row)
                ]
                if not dominated_by:
                    fronts.append({
                        "case_id": case, "budget": budget,
                        "method_id": row["method_id"],
                        **{name: row[name] for name in PARETO_OBJECTIVES},
                    })
            source = next(row for row in cell if row["method_id"] == METHOD_SOURCE)
            for row in cell:
                if row["method_id"] == METHOD_SOURCE:
                    continue
                is_paired = source in eligible and row in eligible
                classification = None
                if is_paired:
                    classification = (
                        "COMPARATOR_DOMINATES_SOURCE" if _dominates(row, source)
                        else "SOURCE_DOMINATES_COMPARATOR" if _dominates(source, row)
                        else "NONDOMINATED_TRADEOFF_OR_TIE"
                    )
                paired.append({
                    "case_id": case, "budget": budget, "method_id": row["method_id"],
                    "paired_eligible": is_paired,
                    "classification": classification,
                    "reason": None if is_paired else (
                        "source_or_comparator_not_COMPLETED_with_all_objectives"
                    ),
                })
    return {
        "definition": {
            "sense": "minimize all objectives",
            "objectives": list(PARETO_OBJECTIVES),
            "dominance": "all objectives no worse and at least one strictly better",
            "scalar_weighting": "not used",
            "eligible_population": "COMPLETED rows with all verified objectives",
            "rejected_cap_engineering_NA": "excluded from numeric front and listed explicitly",
        },
        "front_members": fronts,
        "exclusions": exclusions,
        "paired_source_dominance": paired,
    }


def build_outputs() -> dict[str, Any]:
    rows, bindings = build_long_form_rows()
    statuses = build_status_records(rows)
    paired = build_paired_records(rows)
    pareto = build_pareto(rows)
    field_semantics = {
        "energy_and_resources": (
            "verified terminal observations; ALGORITHM_REJECTED observations are not "
            "accepted results and are never comparison-eligible"
        ),
        "NA": "JSON null and CSV NA; never replaced by zero",
        "total_registered_work": (
            "sum of all frozen complete-counter-schema counts except non-additive "
            "matrix_dimension and qubit_count metadata"
        ),
        "paired_reductions": "only both COMPLETED with verified numeric values",
        "H4_scope": "known-development case; not an independent generalization test",
        "item000": "permanent pre-outcome engineering NA; not rerun or imputed",
    }
    long_form: dict[str, Any] = {
        "schema": "v5-final.s12-matched-work-long-form.v1",
        "bindings": bindings,
        "field_semantics": field_semantics,
        "rows": rows,
    }
    long_form["long_form_digest"] = _digest(long_form)
    status_value: dict[str, Any] = {
        "schema": "v5-final.s12-terminal-status-summary.v1",
        "bindings": bindings,
        "records": statuses,
    }
    status_value["summary_digest"] = _digest(status_value)
    paired_value: dict[str, Any] = {
        "schema": "v5-final.s12-paired-comparisons.v1",
        "bindings": bindings,
        "eligibility_rule": field_semantics["paired_reductions"],
        "records": paired,
    }
    paired_value["paired_digest"] = _digest(paired_value)
    pareto_value: dict[str, Any] = {
        "schema": "v5-final.s12-pareto-fronts.v1",
        "bindings": bindings,
        **pareto,
    }
    pareto_value["pareto_digest"] = _digest(pareto_value)
    long_fields = list(rows[0])
    status_fields = list(statuses[0])
    paired_fields = list(paired[0])
    pareto_rows: list[dict[str, Any]] = []
    for record in pareto["front_members"]:
        pareto_rows.append({"record_type": "front_member", **record})
    for record in pareto["exclusions"]:
        pareto_rows.append({"record_type": "exclusion", **record})
    for record in pareto["paired_source_dominance"]:
        pareto_rows.append({"record_type": "paired_source_dominance", **record})
    pareto_fields = list(dict.fromkeys(key for row in pareto_rows for key in row))
    return {
        "bindings": bindings,
        "json": {
            LONG_JSON: long_form, STATUS_JSON: status_value,
            PAIRED_JSON: paired_value, PARETO_JSON: pareto_value,
        },
        "csv": {
            LONG_CSV: _csv_bytes(rows, long_fields),
            STATUS_CSV: _csv_bytes(statuses, status_fields),
            PAIRED_CSV: _csv_bytes(paired, paired_fields),
            PARETO_CSV: _csv_bytes(pareto_rows, pareto_fields),
        },
    }


def generate() -> dict[str, Any]:
    if OUTPUT_DIR.exists():
        raise S12MatchedWorkAggregationV1Error("aggregation output already exists")
    dirty = _git("status", "--porcelain").splitlines()
    if {line[3:] for line in dirty} != set(SOURCE_PATHS) or any(
        not line.startswith("?? ") for line in dirty
    ):
        raise S12MatchedWorkAggregationV1Error(
            "generation permits only the new aggregation source and test"
        )
    outputs = build_outputs()
    for path, value in outputs["json"].items():
        write_json_exclusive(path, value)
    for path, payload in outputs["csv"].items():
        write_bytes_exclusive(path, payload)
    files = {
        str(path.relative_to(ROOT)): _sha(path)
        for path in (*outputs["json"], *outputs["csv"])
    }
    manifest: dict[str, Any] = {
        "schema": "v5-final.s12-matched-work-aggregation-manifest.v1",
        "status": "PASS_EXACT_FROZEN_90_AGGREGATION_COMPLETE",
        "bindings": outputs["bindings"],
        "files": files,
        "checks": {
            "exact_90_rows": len(outputs["json"][LONG_JSON]["rows"]) == 90,
            "status_counts_exact": dict(Counter(
                row["terminal_status"] for row in outputs["json"][LONG_JSON]["rows"]
            )) == EXPECTED_STATUSES,
            "paired_grid_exact_75": len(outputs["json"][PAIRED_JSON]["records"]) == 75,
            "one_shot_completed_zero": sum(
                row["terminal_status"] == "COMPLETED"
                for row in outputs["json"][LONG_JSON]["rows"]
                if row["method_id"] == "v4.1-one-shot-joint-compression"
            ) == 0,
            "item000_preserved_NA": outputs["json"][LONG_JSON]["rows"][0]
            ["energy_hartree"] is None,
            "S11_FCI_zero": sum(
                row["FCI_evaluations"] for row in outputs["json"][LONG_JSON]["rows"]
            ) == 0,
            "production_dense_expm_zero": sum(
                row["production_N_dense_expm"]
                for row in outputs["json"][LONG_JSON]["rows"]
            ) == 0,
        },
    }
    if not all(manifest["checks"].values()):
        raise S12MatchedWorkAggregationV1Error("aggregation manifest check failed")
    manifest["manifest_digest"] = _digest(manifest)
    write_json_exclusive(MANIFEST, manifest)
    return manifest


def audit_frozen() -> dict[str, Any]:
    manifest = _load(MANIFEST)
    outputs = build_outputs()
    expected_files = {
        str(path.relative_to(ROOT)): hashlib.sha256(canonical_json_bytes(value)).hexdigest()
        for path, value in outputs["json"].items()
    }
    expected_files.update({
        str(path.relative_to(ROOT)): hashlib.sha256(payload).hexdigest()
        for path, payload in outputs["csv"].items()
    })
    checks = {
        "schema_status_exact": manifest.get("schema")
        == "v5-final.s12-matched-work-aggregation-manifest.v1"
        and manifest.get("status") == "PASS_EXACT_FROZEN_90_AGGREGATION_COMPLETE",
        "manifest_digest_valid": _embedded_digest(manifest, "manifest_digest"),
        "bindings_current": manifest.get("bindings") == outputs["bindings"],
        "files_exact_and_current": manifest.get("files") == expected_files
        and all(_sha(ROOT / path) == digest for path, digest in expected_files.items()),
        "all_manifest_checks_pass": all(manifest.get("checks", {}).values()),
        "all_artifacts_immutable_git_blobs": artifact_is_immutable_git_blob(MANIFEST)
        and all(artifact_is_immutable_git_blob(ROOT / path) for path in expected_files),
    }
    if not all(checks.values()):
        raise S12MatchedWorkAggregationV1Error(
            [name for name, passed in checks.items() if not passed]
        )
    return {"status": manifest["status"], "checks": checks,
            "manifest_digest": manifest["manifest_digest"]}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args(argv)
    value = generate() if args.generate else audit_frozen()
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
