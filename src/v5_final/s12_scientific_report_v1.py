"""Generate the versioned scientific interpretation of the frozen matched-work study."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .s0_successor import ROOT
from .s11_v2_execution_readiness_v4 import _digest, _embedded_digest, _load, _sha
from .s12_matched_work_aggregation_v1 import (
    LONG_JSON,
    MANIFEST as AGGREGATION_MANIFEST,
    METHOD_SOURCE,
    PAIRED_JSON,
    PARETO_JSON,
    audit_frozen as audit_aggregation,
)
from .s12_matched_work_figures_v1 import (
    MANIFEST_NAME as FIGURE_MANIFEST_NAME,
    OUTPUT_DIR as FIGURE_DIR,
    audit_frozen as audit_figures,
)
from .s12_offline_fci_reference_v1 import RESULT as FCI_RESULT
from .s12_offline_fci_result_audit_v1 import OUTPUT as FCI_RESULT_AUDIT


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s12-scientific-report-v1"
SUMMARY_NAME = "scientific-summary-v1.json"
REPORT_NAME = "scientific-report-v1.md"
MANIFEST_NAME = "scientific-report-manifest-v1.json"
SOURCE_PATHS = (
    "src/v5_final/s12_scientific_report_v1.py",
    "tests/test_v5_final_s12_scientific_report_v1.py",
)
METHOD_ORDER = (
    "immutable-ceo-star-source", "same-structure-reoptimization",
    "structural-magnitude-pruning", "v4.1-one-shot-joint-compression",
    "v5-fixed-source-whitelist-no-replenishment",
    "v5-sequential-with-rebuilding",
)
METHOD_LABEL = {
    "immutable-ceo-star-source": "Immutable CEO* source",
    "same-structure-reoptimization": "Same-structure reoptimization",
    "structural-magnitude-pruning": "Magnitude pruning",
    "v4.1-one-shot-joint-compression": "V4.1 One-Shot Joint",
    "v5-fixed-source-whitelist-no-replenishment": "V5 fixed-source whitelist",
    "v5-sequential-with-rebuilding": "V5 sequential rebuild",
}
STATUS_ABBREVIATION = {
    "COMPLETED": "C", "ALGORITHM_REJECTED": "A",
    "CAP_REJECTED": "K", "FAILED_ENGINEERING_PRESERVED": "E",
}


class S12ScientificReportV1Error(RuntimeError):
    pass


def _stats(values: Sequence[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "mean": sum(values) / len(values),
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def build_summary() -> dict[str, Any]:
    aggregation_audit = audit_aggregation()
    figure_audit = audit_figures()
    rows = list(_load(LONG_JSON)["rows"])
    paired = list(_load(PAIRED_JSON)["records"])
    pareto = _load(PARETO_JSON)
    fci = _load(FCI_RESULT)
    method_status = []
    for method in METHOD_ORDER:
        subset = [row for row in rows if row["method_id"] == method]
        counts = Counter(row["terminal_status"] for row in subset)
        method_status.append({
            "method_id": method,
            "n": len(subset),
            "COMPLETED": counts["COMPLETED"],
            "ALGORITHM_REJECTED": counts["ALGORITHM_REJECTED"],
            "CAP_REJECTED": counts["CAP_REJECTED"],
            "FAILED_ENGINEERING_PRESERVED": counts["FAILED_ENGINEERING_PRESERVED"],
        })
    paired_summary = []
    paired_budget_summary = []
    metrics = (
        "parameter_count", "cnot_count", "cnot_depth", "total_depth",
    )
    for method in METHOD_ORDER[1:]:
        all_method = [record for record in paired if record["method_id"] == method]
        eligible = [record for record in all_method if record["paired_eligible"]]
        record: dict[str, Any] = {
            "method_id": method, "paired_n": len(eligible), "possible_n": len(all_method),
            "delta_absolute_fci_error_hartree": _stats([
                float(item["delta_absolute_fci_error_hartree"]) for item in eligible
            ]),
        }
        for metric in metrics:
            record[f"reduction_{metric}_percent"] = _stats([
                float(item[f"reduction_{metric}_percent"]) for item in eligible
            ])
        paired_summary.append(record)
        for budget in ("LOW", "MEDIUM", "HIGH"):
            cell = [item for item in eligible if item["budget"] == budget]
            budget_record: dict[str, Any] = {
                "method_id": method, "budget": budget, "paired_n": len(cell),
            }
            for metric in metrics:
                budget_record[f"mean_reduction_{metric}_percent"] = (
                    None if not cell else sum(float(item[f"reduction_{metric}_percent"]) for item in cell) / len(cell)
                )
            paired_budget_summary.append(budget_record)
    paired_dominance = []
    for method in METHOD_ORDER[1:]:
        subset = [record for record in pareto["paired_source_dominance"] if record["method_id"] == method]
        counts = Counter(record["classification"] for record in subset if record["paired_eligible"])
        paired_dominance.append({
            "method_id": method,
            "paired_n": sum(counts.values()),
            "COMPARATOR_DOMINATES_SOURCE": counts["COMPARATOR_DOMINATES_SOURCE"],
            "SOURCE_DOMINATES_COMPARATOR": counts["SOURCE_DOMINATES_COMPARATOR"],
            "NONDOMINATED_TRADEOFF_OR_TIE": counts["NONDOMINATED_TRADEOFF_OR_TIE"],
        })
    fixed = {
        (row["case_id"], row["budget"]): row for row in rows
        if row["method_id"] == "v5-fixed-source-whitelist-no-replenishment"
    }
    sequential = {
        (row["case_id"], row["budget"]): row for row in rows
        if row["method_id"] == "v5-sequential-with-rebuilding"
    }
    identity_fields = (
        "terminal_status", "energy_hartree", "parameter_count", "cnot_count",
        "cnot_depth", "total_depth",
    )
    identity_equal = all(
        all(fixed[key][field] == sequential[key][field] for field in identity_fields)
        for key in fixed
    )
    work_differences = [
        {
            "case_id": key[0], "budget": key[1],
            "fixed_total_registered_work": fixed[key]["total_registered_work"],
            "sequential_total_registered_work": sequential[key]["total_registered_work"],
        }
        for key in fixed
        if fixed[key]["total_registered_work"] != sequential[key]["total_registered_work"]
    ]
    completed = [row for row in rows if row["comparison_eligible"]]
    summary: dict[str, Any] = {
        "schema": "v5-final.s12-scientific-summary.v1",
        "population": {
            "queue_items": 90,
            "cases": 5,
            "budgets": 3,
            "methods": 6,
            "terminal_status_counts": dict(sorted(Counter(row["terminal_status"] for row in rows).items())),
            "completed_error_range_hartree": {
                "minimum": min(row["absolute_fci_error_hartree"] for row in completed),
                "maximum": max(row["absolute_fci_error_hartree"] for row in completed),
            },
        },
        "FCI_references": fci["cases"],
        "method_status": method_status,
        "paired_summary": paired_summary,
        "paired_budget_summary": paired_budget_summary,
        "pareto": {
            "definition": pareto["definition"],
            "front_membership_counts": dict(sorted(Counter(
                record["method_id"] for record in pareto["front_members"]
            ).items())),
            "front_member_count": len(pareto["front_members"]),
            "numeric_exclusion_count": len(pareto["exclusions"]),
            "paired_source_dominance": paired_dominance,
        },
        "fixed_vs_sequential": {
            "terminal_energy_and_physical_resources_equal_all_15_cells": identity_equal,
            "registered_work_difference_cells": work_differences,
        },
        "direct_findings": [
            "Same-structure reoptimization completed all 15 cells, but its 14 valid CEO*-paired cells changed neither energy nor physical resources; CEO* source dominated it because reoptimization added registered work.",
            "Magnitude pruning completed 9 of 15 cells; its valid paired reductions were modest and accompanied by small positive absolute-FCI-error changes.",
            "Both V5 methods completed 10 of 15 cells and had 9 valid CEO*-paired cells; they reduced several circuit resources but did not dominate CEO* under the five-objective definition.",
            "V4.1 One-Shot Joint had zero COMPLETED cells (12 algorithm rejections and 3 cap rejections); this does not establish inferior energy performance.",
            "The two V5 methods had identical terminal status, energy, and physical-resource values in all 15 cells; only registered work differed in four cells.",
        ],
        "claim_boundary": {
            "allowed": [
                "Exact terminal-rate statements for the frozen 90-item population.",
                "Status-aware COMPLETED-only physical-resource summaries.",
                "Verified paired reductions with the reported paired sample size.",
                "Case- and budget-specific non-scalar Pareto tradeoffs.",
                "Negative results and infrastructure limitations documented here.",
            ],
            "not_allowed": [
                "General superiority outside this frozen matched-work population.",
                "Independent generalization: H4 is known development and no unseen molecule was run.",
                "Calling One-Shot the worst-energy method from zero accepted completions.",
                "Replacing missing/rejected/cap values with zero or an imputed success.",
                "Calling registered work the paper Measurement Cost.",
                "Hardware/noise/runtime superiority claims or retrospective protocol tuning.",
            ],
        },
        "bindings": {
            "aggregation_manifest_sha256": _sha(AGGREGATION_MANIFEST),
            "aggregation_manifest_digest": _load(AGGREGATION_MANIFEST)["manifest_digest"],
            "figure_manifest_sha256": _sha(FIGURE_DIR / FIGURE_MANIFEST_NAME),
            "figure_manifest_digest": _load(FIGURE_DIR / FIGURE_MANIFEST_NAME)["manifest_digest"],
            "FCI_result_sha256": _sha(FCI_RESULT),
            "FCI_result_digest": fci["result_digest"],
            "FCI_result_audit_sha256": _sha(FCI_RESULT_AUDIT),
            "FCI_result_audit_digest": _load(FCI_RESULT_AUDIT)["audit_digest"],
            "aggregation_audit_all_pass": all(aggregation_audit["checks"].values()),
            "figure_audit_all_pass": all(figure_audit["checks"].values()),
            "source_sha256": {path: _sha(ROOT / path) for path in SOURCE_PATHS},
        },
    }
    summary["summary_digest"] = _digest(summary)
    return summary


def _fmt(value: float | None, digits: int = 3) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def render_report(summary: Mapping[str, Any]) -> str:
    rows = list(_load(LONG_JSON)["rows"])
    lines = [
        "# V5 frozen matched-work study — final scientific report v1",
        "",
        "## Scope and conclusion",
        "",
        "This report covers the exact frozen 90-item development population (5 cases × 3 budgets × 6 methods). The protocol, queue, caps, ranking, threshold, method semantics, and case set were not changed after outcomes. Results support case- and budget-specific resource/accuracy tradeoffs inside this population; they do not support general superiority or independent molecular generalization.",
        "",
        "The central result is mixed rather than universally positive: V5 compression produced verified circuit-resource reductions in nine CEO*-paired cells, while absolute FCI error increased slightly and total registered work prevented five-objective dominance over the immutable CEO* source. V4.1 One-Shot produced no accepted compression under the frozen rule/caps. These negative and tradeoff results are retained.",
        "",
        "## Offline FCI references",
        "",
        "FCI was executed once, after S11 completion, for the five case identities frozen before outcomes. It was never used for selection, ranking, thresholds, method choice, or reruns.",
        "",
        "| Case | FCI energy (Hartree) | ProblemID | Hamiltonian digest |",
        "|---|---:|---|---|",
    ]
    for case in summary["FCI_references"]:
        lines.append(f"| {case['case_id']} | {case['FCI_energy_hartree']:.15f} | `{case['ProblemID']}` | `{case['Hamiltonian_digest']}` |")
    lines.extend([
        "",
        "Audit counters: FCI evaluations = 5; S11 reruns = 0; S12 candidate-energy evaluations = 0; S12 optimizer starts = 0; production `N_dense_expm` = 0.",
        "",
        "## Terminal outcomes",
        "",
        "| Method | COMPLETED | ALGORITHM_REJECTED | CAP_REJECTED | Engineering NA | Total |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for record in summary["method_status"]:
        lines.append(
            f"| {METHOD_LABEL[record['method_id']]} | {record['COMPLETED']} | "
            f"{record['ALGORITHM_REJECTED']} | {record['CAP_REJECTED']} | "
            f"{record['FAILED_ENGINEERING_PRESERVED']} | {record['n']} |"
        )
    lines.extend([
        "",
        "Status codes below: C = COMPLETED, A = ALGORITHM_REJECTED, K = CAP_REJECTED, E = preserved engineering NA.",
        "",
        "| Case / budget | CEO* | Same | Magnitude | One-Shot | V5 fixed | V5 sequential |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ])
    for case in ("lih-3.0", "h6-1.5", "h6-3.0", "beh2-3.0", "h4-1.5-known-development"):
        for budget in ("LOW", "MEDIUM", "HIGH"):
            cells = []
            for method in METHOD_ORDER:
                row = next(item for item in rows if item["case_id"] == case and item["budget"] == budget and item["method_id"] == method)
                cells.append(STATUS_ABBREVIATION[row["terminal_status"]])
            lines.append(f"| {case} / {budget} | " + " | ".join(cells) + " |")
    lines.extend([
        "",
        "`lih-3.0 / LOW / CEO*` is the permanent pre-outcome thread-environment engineering failure. It was not rerun or imputed; consequently, paired sample counts are below the number of comparator completions where that source is required.",
        "",
        "## Verified CEO*-paired physical-resource reductions",
        "",
        "Only pairs where both source and comparator are COMPLETED with verified numeric metrics are included. Means are descriptive over the stated `n`, not population-general estimates.",
        "",
        "| Method | paired n / 15 | Parameters mean % | CNOT mean % | CNOT depth mean % | Total depth mean % | Mean Δ absolute FCI error (Hartree) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for record in summary["paired_summary"]:
        def mean(key: str) -> float | None:
            value = record[key]
            return None if value is None else value["mean"]
        delta_error = mean("delta_absolute_fci_error_hartree")
        delta_error_text = "NA" if delta_error is None else f"{delta_error:.3e}"
        lines.append(
            f"| {METHOD_LABEL[record['method_id']]} | {record['paired_n']} / {record['possible_n']} | "
            f"{_fmt(mean('reduction_parameter_count_percent'))} | "
            f"{_fmt(mean('reduction_cnot_count_percent'))} | "
            f"{_fmt(mean('reduction_cnot_depth_percent'))} | "
            f"{_fmt(mean('reduction_total_depth_percent'))} | "
            f"{delta_error_text} |"
        )
    lines.extend([
        "",
        "### Budget-stratified means",
        "",
        "| Method | Budget | paired n | Parameters % | CNOT % | CNOT depth % | Total depth % |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for record in summary["paired_budget_summary"]:
        lines.append(
            f"| {METHOD_LABEL[record['method_id']]} | {record['budget']} | {record['paired_n']} | "
            f"{_fmt(record['mean_reduction_parameter_count_percent'])} | "
            f"{_fmt(record['mean_reduction_cnot_count_percent'])} | "
            f"{_fmt(record['mean_reduction_cnot_depth_percent'])} | "
            f"{_fmt(record['mean_reduction_total_depth_percent'])} |"
        )
    lines.extend([
        "",
        "The 58 COMPLETED rows have absolute FCI errors from "
        f"{summary['population']['completed_error_range_hartree']['minimum']:.6e} to "
        f"{summary['population']['completed_error_range_hartree']['maximum']:.6e} Hartree.",
        "",
        "## Pareto result",
        "",
        "Dominance minimizes five objectives simultaneously: absolute FCI error, CNOT count, total depth, parameter count, and total registered work. No scalar weighting was introduced. Non-COMPLETED or numerically incomplete rows are listed as exclusions rather than assigned artificial values.",
        "",
        "| Comparator | paired n | Comparator dominates CEO* | CEO* dominates comparator | Nondominated tradeoff/tie |",
        "|---|---:|---:|---:|---:|",
    ])
    for record in summary["pareto"]["paired_source_dominance"]:
        lines.append(
            f"| {METHOD_LABEL[record['method_id']]} | {record['paired_n']} | "
            f"{record['COMPARATOR_DOMINATES_SOURCE']} | {record['SOURCE_DOMINATES_COMPARATOR']} | "
            f"{record['NONDOMINATED_TRADEOFF_OR_TIE']} |"
        )
    lines.extend([
        "",
        f"There are {summary['pareto']['front_member_count']} front memberships across the 15 case-budget fronts and {summary['pareto']['numeric_exclusion_count']} explicit numeric exclusions. Front membership is case/budget-specific and is not a global method ranking.",
        "",
        "## Direct findings and negative results",
        "",
    ])
    for finding in summary["direct_findings"]:
        lines.append(f"- {finding}")
    lines.extend([
        "",
        "Magnitude pruning's nine valid pairs averaged 1.967% fewer parameters, 1.082% fewer CNOTs, 1.809% lower CNOT depth, and 1.125% lower total depth, with mean absolute-FCI-error increase 1.789e-7 Hartree.",
        "",
        "Each V5 method's nine valid pairs averaged 5.714% fewer parameters, 3.952% fewer CNOTs, 1.300% lower CNOT depth, and 4.490% lower total depth, with mean absolute-FCI-error increase 1.293e-6 Hartree. These are tradeoffs, not dominance or general superiority.",
        "",
        "Fixed-source and sequential-rebuild produced identical terminal status, energy, and physical resources in all 15 cells. Registered work differed in only four cells; therefore this grid does not establish a scientific/resource advantage from rebuilding.",
        "",
        "On the known-development H4 case, CEO* source and same-structure completed at every budget, while the four compression methods were algorithm-rejected at every budget. This is a case-specific frozen-rule result, not evidence against those methods generally.",
        "",
        "## Claim boundary",
        "",
        "Allowed:",
        "",
    ])
    lines.extend(f"- {claim}" for claim in summary["claim_boundary"]["allowed"])
    lines.extend(["", "Not allowed:", ""])
    lines.extend(f"- {claim}" for claim in summary["claim_boundary"]["not_allowed"])
    lines.extend([
        "",
        "## Reproducible artifacts",
        "",
        "- Long-form JSON/CSV: `../s12-matched-work-aggregation-v1/matched-work-long-form-v1.*`",
        "- Status summary: `../s12-matched-work-aggregation-v1/terminal-status-summary-v1.*`",
        "- Paired comparisons: `../s12-matched-work-aggregation-v1/paired-comparisons-v1.*`",
        "- Pareto fronts and exclusions: `../s12-matched-work-aggregation-v1/pareto-fronts-v1.*`",
        "- Figures (PNG/PDF) and progression data: `../s12-matched-work-figures-v1/`",
        "- FCI result and audit: `../s12-offline-fci-reference-v1/`",
        "",
        "Paper Fig. 11/14/15 correspondence figures are endpoint/axis correspondences only. They do not reconstruct unavailable ADAPT growth trajectories, and registered-work counters are not substituted for paper Measurement Cost.",
        "",
        f"Scientific-summary digest: `{summary['summary_digest']}`",
        "",
    ])
    return "\n".join(lines)


def _git_status() -> list[str]:
    output = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.rstrip("\r\n")
    return [] if not output else output.splitlines()


def generate() -> dict[str, Any]:
    if OUTPUT_DIR.exists():
        raise S12ScientificReportV1Error("scientific report already exists")
    dirty = _git_status()
    if {line[3:] for line in dirty} != set(SOURCE_PATHS) or any(not line.startswith("?? ") for line in dirty):
        raise S12ScientificReportV1Error("generation permits only report source and test")
    summary = build_summary()
    report = render_report(summary).encode("utf-8")
    OUTPUT_DIR.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".s12-report-staging-", dir=OUTPUT_DIR.parent))
    try:
        (staging / SUMMARY_NAME).write_bytes(canonical_json_bytes(summary))
        (staging / REPORT_NAME).write_bytes(report)
        files = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(staging.iterdir())
        }
        manifest: dict[str, Any] = {
            "schema": "v5-final.s12-scientific-report-manifest.v1",
            "status": "PASS_SCIENTIFIC_REPORT_COMPLETE",
            "summary_digest": summary["summary_digest"],
            "bindings": summary["bindings"],
            "files": files,
            "checks": {
                "population_exact_90": summary["population"]["queue_items"] == 90,
                "FCI_exact_5": len(summary["FCI_references"]) == 5,
                "one_shot_completed_zero": next(
                    item for item in summary["method_status"]
                    if item["method_id"] == "v4.1-one-shot-joint-compression"
                )["COMPLETED"] == 0,
                "fixed_sequential_identity_recorded": summary["fixed_vs_sequential"]
                ["terminal_energy_and_physical_resources_equal_all_15_cells"],
                "general_superiority_forbidden": any(
                    "General superiority" in value
                    for value in summary["claim_boundary"]["not_allowed"]
                ),
            },
        }
        if not all(manifest["checks"].values()):
            raise S12ScientificReportV1Error("report check failed")
        manifest["manifest_digest"] = _digest(manifest)
        (staging / MANIFEST_NAME).write_bytes(canonical_json_bytes(manifest))
        os.rename(staging, OUTPUT_DIR)
        return manifest
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def audit_frozen() -> dict[str, Any]:
    manifest = _load(OUTPUT_DIR / MANIFEST_NAME)
    summary = _load(OUTPUT_DIR / SUMMARY_NAME)
    files = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(OUTPUT_DIR.iterdir()) if path.name != MANIFEST_NAME
    }
    checks = {
        "schema_status_exact": manifest.get("schema") == "v5-final.s12-scientific-report-manifest.v1"
        and manifest.get("status") == "PASS_SCIENTIFIC_REPORT_COMPLETE",
        "manifest_digest_valid": _embedded_digest(manifest, "manifest_digest"),
        "summary_digest_valid": _embedded_digest(summary, "summary_digest")
        and manifest.get("summary_digest") == summary.get("summary_digest"),
        "files_current": manifest.get("files") == files,
        "all_checks_pass": all(manifest.get("checks", {}).values()),
        "all_artifacts_immutable_git_blobs": all(
            artifact_is_immutable_git_blob(path) for path in OUTPUT_DIR.iterdir()
            if path.is_file()
        ),
    }
    if not all(checks.values()):
        raise S12ScientificReportV1Error([name for name, passed in checks.items() if not passed])
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
