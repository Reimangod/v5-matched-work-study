"""Reproducible figures for the audited frozen matched-work aggregation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from v5_matched_work.atomic_artifacts import canonical_json_bytes

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .s0_successor import ROOT
from .s11_v2_execution_readiness_v4 import PRODUCTION_ROOT, _digest, _embedded_digest, _load, _sha
from .s11_v2_execution_runner_v1 import _item_paths
from .s11_v2_queue_native_adapter import QueueV2NativeAdapter
from .s12_matched_work_aggregation_v1 import (
    LONG_JSON,
    MANIFEST as AGGREGATION_MANIFEST,
    METHOD_SOURCE,
    PAIRED_JSON,
    PARETO_JSON,
    STATUS_JSON,
    audit_frozen as audit_aggregation,
)
from .s12_offline_fci_reference_v1 import RESULT as FCI_RESULT


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s12-matched-work-figures-v1"
PROGRESSION_JSON_NAME = "trial-work-progression-v1.json"
PROGRESSION_CSV_NAME = "trial-work-progression-v1.csv"
MANIFEST_NAME = "figure-manifest-v1.json"
SOURCE_PATHS = (
    "src/v5_final/s12_matched_work_figures_v1.py",
    "tests/test_v5_final_s12_matched_work_figures_v1.py",
)
METHOD_ORDER = (
    "immutable-ceo-star-source",
    "same-structure-reoptimization",
    "structural-magnitude-pruning",
    "v4.1-one-shot-joint-compression",
    "v5-fixed-source-whitelist-no-replenishment",
    "v5-sequential-with-rebuilding",
)
METHOD_LABELS = {
    "immutable-ceo-star-source": "CEO* source",
    "same-structure-reoptimization": "Same structure",
    "structural-magnitude-pruning": "Magnitude pruning",
    "v4.1-one-shot-joint-compression": "One-Shot Joint",
    "v5-fixed-source-whitelist-no-replenishment": "V5 fixed source",
    "v5-sequential-with-rebuilding": "V5 sequential",
}
CASE_ORDER = (
    "lih-3.0", "h6-1.5", "h6-3.0", "beh2-3.0",
    "h4-1.5-known-development",
)
BUDGETS = ("LOW", "MEDIUM", "HIGH")
FIGURE_STEMS = (
    "status-matrix",
    "method-terminal-status",
    "energy-error-by-case-budget",
    "paired-resource-reductions",
    "registered-work-vs-energy-error",
    "registered-work-vs-cnot",
    "pareto-fronts",
    "trial-resource-progression",
    "optimization-energy-progression",
    "fig11-matched-work-correspondence",
    "fig14-matched-work-correspondence",
    "fig15-matched-work-correspondence",
)


class S12MatchedWorkFiguresV1Error(RuntimeError):
    pass


def _rows() -> list[dict[str, Any]]:
    value = _load(LONG_JSON)
    rows = list(value["rows"])
    if len(rows) != 90:
        raise S12MatchedWorkFiguresV1Error("long-form population differs")
    return rows


def build_progression_data() -> dict[str, Any]:
    audit_aggregation()
    adapter = QueueV2NativeAdapter()
    fci = {
        case["case_id"]: float(case["FCI_energy_hartree"])
        for case in _load(FCI_RESULT)["cases"]
    }
    attempts: list[dict[str, Any]] = []
    energy_events: list[dict[str, Any]] = []
    for index, item in enumerate(adapter.queue["items"]):
        result = _load(_item_paths(
            PRODUCTION_ROOT, index, adapter.request(item["queue_item_id"])
        )["result"])
        outcome = result.get("outcome")
        native = outcome.get("result", {}) if isinstance(outcome, dict) else {}
        native_attempts = native.get("attempts", ()) if isinstance(native, dict) else ()
        cumulative_energy_index = 0
        for attempt_index, attempt in enumerate(native_attempts, start=1):
            resources = attempt.get("resources", {})
            energy = attempt.get("energy_hartree")
            attempts.append({
                "record_type": "attempt",
                "queue_index": index,
                "case_id": item["case_id"],
                "method_id": item["method_id"],
                "budget": item["work_envelope"],
                "terminal_status": result["terminal_status"],
                "attempt_index": attempt_index,
                "round": attempt.get("round", attempt_index),
                "accepted": bool(attempt.get("accepted", False)),
                "energy_hartree": energy,
                "absolute_fci_error_hartree": (
                    None if energy is None else abs(float(energy) - fci[item["case_id"]])
                ),
                "parameter_count": resources.get("parameter_count"),
                "cnot_count": resources.get("cnot_count"),
                "cnot_depth": resources.get("cnot_depth"),
                "total_depth": resources.get("total_depth"),
                "operators_blocks": resources.get("logical_block_count"),
            })
            for event in attempt.get("time_series", ()):
                if event.get("kind") != "energy":
                    continue
                cumulative_energy_index += 1
                event_energy = float(event["energy_hartree"])
                parameters = [float(value) for value in event.get("parameters", ())]
                energy_events.append({
                    "record_type": "energy_event",
                    "queue_index": index,
                    "case_id": item["case_id"],
                    "method_id": item["method_id"],
                    "budget": item["work_envelope"],
                    "terminal_status": result["terminal_status"],
                    "attempt_index": attempt_index,
                    "energy_event_index": cumulative_energy_index,
                    "energy_hartree": event_energy,
                    "absolute_fci_error_hartree": abs(event_energy - fci[item["case_id"]]),
                    "parameter_vector_length": len(parameters),
                    "parameter_l2_norm": math.sqrt(sum(value * value for value in parameters)),
                })
    return {
        "schema": "v5-final.s12-trial-work-progression.v1",
        "semantics": {
            "attempt_rows": "all recorded method-native attempts, including rejected outcomes",
            "energy_event_rows": "all recorded optimizer energy events; no interpolation",
            "resource_trajectory_limit": (
                "resource values exist at attempt boundaries, not every optimizer event"
            ),
            "missing_source_trajectories": (
                "immutable source endpoints do not contain an ADAPT growth trajectory"
            ),
        },
        "attempts": attempts,
        "energy_events": energy_events,
    }


def _progression_csv(value: Mapping[str, Any]) -> bytes:
    records = [*value["attempts"], *value["energy_events"]]
    fields = list(dict.fromkeys(key for record in records for key in record))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for record in records:
        writer.writerow({field: "NA" if record.get(field) is None else record.get(field) for field in fields})
    return stream.getvalue().encode("utf-8")


def _plot_setup() -> tuple[Any, Any]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "legend.fontsize": 7.5,
        "figure.titlesize": 13,
        "savefig.bbox": "tight",
        "axes.grid": True,
        "grid.alpha": 0.2,
    })
    return matplotlib, plt


def _palette(plt: Any) -> dict[str, Any]:
    colors = plt.get_cmap("tab10").colors
    return {method: colors[index] for index, method in enumerate(METHOD_ORDER)}


def _completed(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [row for row in rows if row["comparison_eligible"]]


def _legend(axis: Any, methods: Sequence[str] = METHOD_ORDER) -> None:
    from matplotlib.lines import Line2D
    _, plt = _plot_setup()
    palette = _palette(plt)
    handles = [Line2D([0], [0], marker="o", linestyle="", color=palette[m], label=METHOD_LABELS[m]) for m in methods]
    axis.legend(handles=handles, frameon=False, ncol=2)


def _fig_status_matrix(plt: Any, rows: Sequence[Mapping[str, Any]]) -> Any:
    import numpy as np
    status_code = {
        "COMPLETED": 0, "ALGORITHM_REJECTED": 1,
        "CAP_REJECTED": 2, "FAILED_ENGINEERING_PRESERVED": 3,
    }
    labels = [(case, budget) for case in CASE_ORDER for budget in BUDGETS]
    matrix = np.array([
        [status_code[next(row["terminal_status"] for row in rows if row["case_id"] == case and row["budget"] == budget and row["method_id"] == method)] for method in METHOD_ORDER]
        for case, budget in labels
    ])
    from matplotlib.colors import ListedColormap
    figure, axis = plt.subplots(figsize=(12, 7))
    image = axis.imshow(matrix, aspect="auto", cmap=ListedColormap(["#2a9d8f", "#e9c46a", "#e76f51", "#6c757d"]), vmin=-0.5, vmax=3.5)
    axis.set_xticks(range(6), [METHOD_LABELS[m] for m in METHOD_ORDER], rotation=28, ha="right")
    axis.set_yticks(range(15), [f"{case} | {budget}" for case, budget in labels])
    for y in range(15):
        for x in range(6):
            axis.text(x, y, ("C", "A", "K", "E")[matrix[y, x]], ha="center", va="center", color="black", fontsize=8)
    from matplotlib.patches import Patch
    axis.legend(handles=[Patch(color=color, label=label) for color, label in zip(["#2a9d8f", "#e9c46a", "#e76f51", "#6c757d"], ["COMPLETED", "ALGORITHM_REJECTED", "CAP_REJECTED", "ENGINEERING NA"])], frameon=False, ncol=2, loc="upper left", bbox_to_anchor=(1.01, 1))
    axis.set_title("Exact frozen 90-item terminal-status matrix")
    figure.tight_layout()
    return figure


def _fig_method_status(plt: Any, rows: Sequence[Mapping[str, Any]]) -> Any:
    figure, axis = plt.subplots(figsize=(11, 5.5))
    bottom = [0] * 6
    colors = {"COMPLETED": "#2a9d8f", "ALGORITHM_REJECTED": "#e9c46a", "CAP_REJECTED": "#e76f51", "FAILED_ENGINEERING_PRESERVED": "#6c757d"}
    for status in colors:
        values = [sum(row["method_id"] == method and row["terminal_status"] == status for row in rows) for method in METHOD_ORDER]
        axis.bar(range(6), values, bottom=bottom, label=status, color=colors[status])
        bottom = [a + b for a, b in zip(bottom, values)]
    axis.set_xticks(range(6), [METHOD_LABELS[m] for m in METHOD_ORDER], rotation=25, ha="right")
    axis.set_ylabel("Terminal items (n; 15 per method)")
    axis.set_title("Method-native terminal outcomes; no status is imputed as success")
    axis.legend(frameon=False, ncol=2)
    figure.tight_layout()
    return figure


def _scatter_by_method(axis: Any, rows: Sequence[Mapping[str, Any]], x: str, y: str, *, logx: bool = False, logy: bool = False) -> None:
    palette = _palette(__import__("matplotlib.pyplot", fromlist=["plt"]))
    markers = {"LOW": "o", "MEDIUM": "s", "HIGH": "^"}
    for method in METHOD_ORDER:
        subset = [row for row in rows if row["method_id"] == method and row.get(x) is not None and row.get(y) is not None]
        for row in subset:
            axis.scatter(row[x], row[y], color=palette[method], marker=markers[row["budget"]], s=40, alpha=0.8, edgecolor="black", linewidth=0.25)
    if logx:
        axis.set_xscale("log")
    if logy:
        axis.set_yscale("log")


def _fig_energy_error(plt: Any, rows: Sequence[Mapping[str, Any]]) -> Any:
    figure, axes = plt.subplots(1, 5, figsize=(18, 5), sharey=True)
    palette = _palette(plt)
    offsets = {"LOW": -0.18, "MEDIUM": 0.0, "HIGH": 0.18}
    for axis, case in zip(axes, CASE_ORDER):
        for row in rows:
            if row["case_id"] != case or row["absolute_fci_error_hartree"] is None:
                continue
            x = METHOD_ORDER.index(row["method_id"]) + offsets[row["budget"]]
            if row["terminal_status"] == "COMPLETED":
                axis.scatter(x, row["absolute_fci_error_hartree"], color=palette[row["method_id"]], marker={"LOW":"o","MEDIUM":"s","HIGH":"^"}[row["budget"]], s=34)
            else:
                axis.scatter(x, row["absolute_fci_error_hartree"], color=palette[row["method_id"]], marker="x", s=30, alpha=0.65)
        axis.set_yscale("log")
        axis.set_xticks(range(6), [str(i + 1) for i in range(6)])
        axis.set_xlabel("Method index (1–6)")
        axis.set_title(case + ("\nknown development" if case.startswith("h4-") else ""))
    axes[0].set_ylabel("Absolute FCI error (Hartree; log)")
    figure.suptitle("Energy error by case and budget (x = nonaccepted observation; filled = COMPLETED)")
    figure.text(0.5, 0.01, "Method index follows the terminal-status figure; LOW circle, MEDIUM square, HIGH triangle.", ha="center", fontsize=8)
    figure.tight_layout(rect=(0, 0.04, 1, 0.94))
    return figure


def _fig_reductions(plt: Any, paired: Sequence[Mapping[str, Any]]) -> Any:
    metrics = (("parameter_count", "Parameters"), ("cnot_count", "CNOT"), ("cnot_depth", "CNOT depth"), ("total_depth", "Total depth"))
    methods = METHOD_ORDER[1:]
    figure, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True)
    palette = _palette(plt)
    for axis, (metric, title) in zip(axes.flat, metrics):
        sample_counts: list[int] = []
        for x, method in enumerate(methods):
            values = [record[f"reduction_{metric}_percent"] for record in paired if record["method_id"] == method and record["paired_eligible"]]
            sample_counts.append(len(values))
            axis.scatter([x] * len(values), values, color=palette[method], alpha=0.75, s=28)
            if values:
                axis.plot([x - 0.18, x + 0.18], [sum(values)/len(values)] * 2, color="black", linewidth=1.5)
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_title(f"CEO* paired {title} reduction")
        axis.set_ylabel("Reduction (%)")
        axis.set_xticks(
            range(5),
            [f"{METHOD_LABELS[m]}\n(n={n})" for m, n in zip(methods, sample_counts)],
            rotation=24,
            ha="right",
        )
    figure.suptitle("Verified paired reductions only; missing/rejected pairs are absent, not zero")
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    return figure


def _fig_work_scatter(plt: Any, rows: Sequence[Mapping[str, Any]], y: str, ylabel: str, stem_title: str) -> Any:
    figure, axis = plt.subplots(figsize=(10, 6.5))
    completed = _completed(rows)
    _scatter_by_method(axis, completed, "total_registered_work", y, logx=True, logy=(y == "absolute_fci_error_hartree"))
    axis.set_xlabel("Total registered work (additive counters; log)")
    axis.set_ylabel(ylabel)
    axis.set_title(stem_title + " (COMPLETED only)")
    present = tuple(method for method in METHOD_ORDER if any(row["method_id"] == method for row in completed))
    _legend(axis, present)
    figure.tight_layout()
    return figure


def _fig_pareto(plt: Any, rows: Sequence[Mapping[str, Any]], pareto: Mapping[str, Any]) -> Any:
    figure, axes = plt.subplots(5, 3, figsize=(15, 19), squeeze=False)
    palette = _palette(plt)
    front = {(r["case_id"], r["budget"], r["method_id"]) for r in pareto["front_members"]}
    for i, case in enumerate(CASE_ORDER):
        for j, budget in enumerate(BUDGETS):
            axis = axes[i][j]
            subset = [row for row in _completed(rows) if row["case_id"] == case and row["budget"] == budget]
            for row in subset:
                on_front = (case, budget, row["method_id"]) in front
                axis.scatter(row["cnot_count"], row["absolute_fci_error_hartree"], color=palette[row["method_id"]], s=35 + 2 * math.sqrt(row["parameter_count"]), marker="D" if on_front else "o", edgecolor="black" if on_front else "none", linewidth=0.8)
            axis.set_yscale("log")
            axis.set_title(f"{case} | {budget}")
            axis.set_xlabel("CNOT count")
            axis.set_ylabel("Absolute FCI error (Ha)")
    from matplotlib.lines import Line2D
    present = tuple(method for method in METHOD_ORDER if any(row["method_id"] == method for row in _completed(rows)))
    handles = [
        Line2D([0], [0], marker="D", linestyle="", color=palette[method],
               markeredgecolor="black", label=METHOD_LABELS[method])
        for method in present
    ]
    figure.legend(handles=handles, frameon=False, ncol=len(handles), loc="lower center")
    figure.suptitle("Non-scalar Pareto membership (diamond): five objectives, no scalar weighting")
    figure.text(
        0.5, 0.018,
        "Marker area scales with parameter count; front membership also uses total depth and registered work.",
        ha="center", fontsize=8,
    )
    figure.tight_layout(rect=(0, 0.045, 1, 0.98))
    return figure


def _fig_trial_resources(plt: Any, progression: Mapping[str, Any]) -> Any:
    metrics = (("absolute_fci_error_hartree", "Absolute FCI error (Ha)"), ("cnot_count", "CNOT"), ("total_depth", "Total depth"), ("parameter_count", "Parameters"))
    figure, axes = plt.subplots(2, 2, figsize=(13, 9))
    palette = _palette(plt)
    attempts = progression["attempts"]
    queue_ids = sorted({row["queue_index"] for row in attempts})
    for axis, (metric, label) in zip(axes.flat, metrics):
        for queue_index in queue_ids:
            trace = [row for row in attempts if row["queue_index"] == queue_index and row.get(metric) is not None]
            if not trace:
                continue
            trace.sort(key=lambda row: row["attempt_index"])
            method = trace[0]["method_id"]
            axis.plot([row["attempt_index"] for row in trace], [row[metric] for row in trace], color=palette[method], alpha=0.22, linewidth=0.9, marker=".")
        if metric == "absolute_fci_error_hartree":
            axis.set_yscale("log")
        axis.set_xlabel("Method-native attempt index")
        axis.set_ylabel(label)
    figure.suptitle("All reconstructable trial-boundary trajectories; rejected trials retained")
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    return figure


def _fig_energy_progression(plt: Any, progression: Mapping[str, Any]) -> Any:
    figure, axes = plt.subplots(1, 5, figsize=(18, 5), sharey=True)
    palette = _palette(plt)
    events = progression["energy_events"]
    for axis, case in zip(axes, CASE_ORDER):
        for queue_index in sorted({row["queue_index"] for row in events if row["case_id"] == case}):
            trace = [row for row in events if row["queue_index"] == queue_index]
            trace.sort(key=lambda row: row["energy_event_index"])
            axis.plot([row["energy_event_index"] for row in trace], [row["absolute_fci_error_hartree"] for row in trace], color=palette[trace[0]["method_id"]], alpha=0.28, linewidth=0.8)
        axis.set_yscale("log")
        axis.set_xlabel("Recorded energy-event index")
        axis.set_title(case)
    axes[0].set_ylabel("Absolute FCI error (Ha; log)")
    figure.suptitle("All recorded optimizer-energy traces; no interpolation or selected-case filtering")
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    return figure


def _fig_correspondence(plt: Any, rows: Sequence[Mapping[str, Any]], number: int) -> Any:
    completed = _completed(rows)
    if number == 11:
        specs = (("accepted_candidate_count", "Accepted candidates"), ("parameter_count", "Parameters"), ("cnot_count", "CNOT"))
        title = "Fig. 11 correspondence — frozen matched-work endpoints, not ADAPT trajectories"
    elif number == 14:
        specs = (("accepted_candidate_count", "Accepted candidates"), ("cnot_count", "CNOT"), ("cnot_depth", "CNOT depth"))
        title = "Fig. 14 correspondence — frozen endpoint circuit comparison"
    else:
        figure, axes = plt.subplots(1, 2, figsize=(12, 5.2))
        _scatter_by_method(axes[0], completed, "parameter_count", "absolute_fci_error_hartree", logy=True)
        axes[0].set_xlabel("Parameter count")
        axes[0].set_ylabel("Absolute FCI error (Ha; log)")
        axes[0].set_title("Verified COMPLETED endpoints")
        present = tuple(method for method in METHOD_ORDER if any(row["method_id"] == method for row in completed))
        _legend(axes[0], present)
        axes[1].axis("off")
        axes[1].text(0.5, 0.55, "Paper Measurement Cost\nis not available for this study\n\nRegistered-work counters are reported\nin separate figures and are not substituted.", ha="center", va="center", fontsize=13)
        axes[1].set_title("Measurement-cost claim boundary")
        figure.suptitle("Fig. 15 correspondence — parameter endpoint and explicit refusal")
        figure.tight_layout(rect=(0, 0, 1, 0.94))
        return figure
    figure, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    for axis, (x, xlabel) in zip(axes, specs):
        subset = [row for row in completed if row.get(x) is not None]
        _scatter_by_method(axis, subset, x, "absolute_fci_error_hartree", logy=True)
        axis.set_xlabel(xlabel)
        axis.set_ylabel("Absolute FCI error (Ha; log)")
    present = tuple(method for method in METHOD_ORDER if any(row["method_id"] == method for row in completed))
    _legend(axes[0], present)
    figure.suptitle(title)
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    return figure


def _render_all(staging: Path, rows: Sequence[Mapping[str, Any]], progression: Mapping[str, Any]) -> None:
    _, plt = _plot_setup()
    paired = _load(PAIRED_JSON)["records"]
    pareto = _load(PARETO_JSON)
    builders: dict[str, Callable[[], Any]] = {
        "status-matrix": lambda: _fig_status_matrix(plt, rows),
        "method-terminal-status": lambda: _fig_method_status(plt, rows),
        "energy-error-by-case-budget": lambda: _fig_energy_error(plt, rows),
        "paired-resource-reductions": lambda: _fig_reductions(plt, paired),
        "registered-work-vs-energy-error": lambda: _fig_work_scatter(plt, rows, "absolute_fci_error_hartree", "Absolute FCI error (Hartree; log)", "Registered work versus energy error"),
        "registered-work-vs-cnot": lambda: _fig_work_scatter(plt, rows, "cnot_count", "CNOT count", "Registered work versus CNOT"),
        "pareto-fronts": lambda: _fig_pareto(plt, rows, pareto),
        "trial-resource-progression": lambda: _fig_trial_resources(plt, progression),
        "optimization-energy-progression": lambda: _fig_energy_progression(plt, progression),
        "fig11-matched-work-correspondence": lambda: _fig_correspondence(plt, rows, 11),
        "fig14-matched-work-correspondence": lambda: _fig_correspondence(plt, rows, 14),
        "fig15-matched-work-correspondence": lambda: _fig_correspondence(plt, rows, 15),
    }
    from matplotlib.backends.backend_pdf import PdfPages
    combined = PdfPages(staging / "fig11-14-15-matched-work-combined.pdf")
    try:
        for stem in FIGURE_STEMS:
            figure = builders[stem]()
            figure.savefig(staging / f"{stem}.png", dpi=190)
            figure.savefig(staging / f"{stem}.pdf")
            if stem.startswith(("fig11-", "fig14-", "fig15-")):
                combined.savefig(figure)
            plt.close(figure)
    finally:
        combined.close()


def generate() -> dict[str, Any]:
    if OUTPUT_DIR.exists():
        raise S12MatchedWorkFiguresV1Error("figure output already exists")
    dirty = _git_status()
    if {line[3:] for line in dirty} != set(SOURCE_PATHS) or any(not line.startswith("?? ") for line in dirty):
        raise S12MatchedWorkFiguresV1Error("generation permits only new figure source and test")
    aggregation_audit = audit_aggregation()
    rows = _rows()
    progression = build_progression_data()
    OUTPUT_DIR.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".s12-figures-staging-", dir=OUTPUT_DIR.parent))
    try:
        (staging / PROGRESSION_JSON_NAME).write_bytes(canonical_json_bytes(progression))
        (staging / PROGRESSION_CSV_NAME).write_bytes(_progression_csv(progression))
        _render_all(staging, rows, progression)
        output_hashes = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(staging.iterdir()) if path.is_file()
        }
        aggregation_manifest = _load(AGGREGATION_MANIFEST)
        manifest: dict[str, Any] = {
            "schema": "v5-final.s12-matched-work-figure-manifest.v1",
            "status": "PASS_MATCHED_WORK_FIGURES_COMPLETE",
            "bindings": {
                "aggregation_manifest_sha256": _sha(AGGREGATION_MANIFEST),
                "aggregation_manifest_digest": aggregation_manifest["manifest_digest"],
                "long_form_sha256": _sha(LONG_JSON),
                "paired_sha256": _sha(PAIRED_JSON),
                "pareto_sha256": _sha(PARETO_JSON),
                "status_sha256": _sha(STATUS_JSON),
                "source_sha256": {path: _sha(ROOT / path) for path in SOURCE_PATHS},
            },
            "checks": {
                "aggregation_audit_all_pass": all(aggregation_audit["checks"].values()),
                "exact_12_png": sum(name.endswith(".png") for name in output_hashes) == 12,
                "exact_13_pdf": sum(name.endswith(".pdf") for name in output_hashes) == 13,
                "progression_attempts_nonempty": len(progression["attempts"]) > 0,
                "progression_energy_events_nonempty": len(progression["energy_events"]) > 0,
                "all_90_population_used": len(rows) == 90,
            },
            "figure_correspondence": {
                "fig11": "endpoint error versus accepted candidates, parameters, and CNOT; not an ADAPT trajectory reproduction",
                "fig14": "endpoint error versus accepted candidates, CNOT, and CNOT depth",
                "fig15": "endpoint error versus parameters; paper Measurement Cost explicitly unavailable and not substituted",
            },
            "claim_boundary": [
                "Only COMPLETED rows enter numeric resource comparisons and Pareto fronts.",
                "Rejected observations remain visible where informative but are not accepted results.",
                "H4 1.5 A is a known-development case, not independent generalization.",
                "No paper Measurement Cost is inferred from registered-work counters.",
                "No scalar Pareto weighting is introduced.",
            ],
            "outputs": output_hashes,
        }
        if not all(manifest["checks"].values()):
            raise S12MatchedWorkFiguresV1Error("figure manifest check failed")
        manifest["manifest_digest"] = _digest(manifest)
        (staging / MANIFEST_NAME).write_bytes(canonical_json_bytes(manifest))
        os.rename(staging, OUTPUT_DIR)
        return manifest
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _git_status() -> list[str]:
    import subprocess
    output = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.rstrip("\r\n")
    return [] if not output else output.splitlines()


def audit_frozen() -> dict[str, Any]:
    manifest = _load(OUTPUT_DIR / MANIFEST_NAME)
    files = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(OUTPUT_DIR.iterdir())
        if path.is_file() and path.name != MANIFEST_NAME
    }
    checks = {
        "schema_status_exact": manifest.get("schema") == "v5-final.s12-matched-work-figure-manifest.v1"
        and manifest.get("status") == "PASS_MATCHED_WORK_FIGURES_COMPLETE",
        "manifest_digest_valid": _embedded_digest(manifest, "manifest_digest"),
        "output_hashes_current": manifest.get("outputs") == files,
        "all_checks_pass": all(manifest.get("checks", {}).values()),
        "aggregation_binding_current": manifest["bindings"]["aggregation_manifest_sha256"] == _sha(AGGREGATION_MANIFEST),
        "all_artifacts_immutable_git_blobs": artifact_is_immutable_git_blob(OUTPUT_DIR / MANIFEST_NAME)
        and all(artifact_is_immutable_git_blob(path) for path in OUTPUT_DIR.iterdir() if path.is_file()),
    }
    if not all(checks.values()):
        raise S12MatchedWorkFiguresV1Error([name for name, passed in checks.items() if not passed])
    return {"status": manifest["status"], "checks": checks, "manifest_digest": manifest["manifest_digest"]}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args(argv)
    value = generate() if args.generate else audit_frozen()
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
