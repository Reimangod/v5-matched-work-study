"""One-thread LiH/H6 worker for outcome-free Verifier V2 calibration."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .parent_native_candidate_adapter import build_typed_catalog
from .parent_native_development_runtime_factory_v1 import (
    build_queue_bound_development_runtime_v1,
)
from .s11_development_runner_v1 import _plan as development_plan
from .s11_v2_outcome_free_calibration import (
    S11V2CalibrationError,
    THREAD_KEYS,
    _actual_bundle,
    _digest,
    _run_full_twice,
)
from .verifier_v2_structural_calibration import prepare_structural_only


def run(work: Path) -> dict[str, Any]:
    if any(os.environ.get(key) != "1" for key in THREAD_KEYS):
        raise S11V2CalibrationError(
            "development calibration worker requires frozen thread environment 1/1/1"
        )
    work.mkdir(parents=True, exist_ok=True)
    plan = development_plan()
    lih_item = plan["items"][4]
    lih_context = build_queue_bound_development_runtime_v1(
        lih_item["queue_item_id"], plan_record=plan
    )
    lih_catalog = build_typed_catalog(lih_context.pool, lih_context.runtime.ansatz)
    lih_ids = tuple(value.candidate_id for value in lih_catalog.candidates)
    lih_core, lih_identical = _run_full_twice(
        lih_context, lih_catalog, lih_ids, work, "lih"
    )
    resume_dir = work / "lih-resume"
    partial = _actual_bundle(
        context=lih_context,
        catalog=lih_catalog,
        checkpoint_dir=resume_dir,
        ids=lih_ids,
    ).run(max_new_numeric_verifications=2)
    resumed = _actual_bundle(
        context=lih_context,
        catalog=lih_catalog,
        checkpoint_dir=resume_dir,
        ids=lih_ids,
    ).run()
    lih_resume_equal = canonical_json_bytes(resumed["core"]) == canonical_json_bytes(
        lih_core
    )

    h6_item = plan["items"][28]
    h6_context = build_queue_bound_development_runtime_v1(
        h6_item["queue_item_id"], plan_record=plan
    )
    h6_catalog = build_typed_catalog(h6_context.pool, h6_context.runtime.ansatz)
    h6_ids = tuple(value.candidate_id for value in h6_catalog.candidates)
    h6_all_bundle = _actual_bundle(
        context=h6_context,
        catalog=h6_catalog,
        checkpoint_dir=work / "h6-structural",
        ids=h6_ids,
    )
    h6_structural = prepare_structural_only(
        h6_all_bundle.verifier, h6_all_bundle.candidates
    )
    h6_repeat_bundle = _actual_bundle(
        context=h6_context,
        catalog=h6_catalog,
        checkpoint_dir=work / "h6-structural-repeat",
        ids=h6_ids,
    )
    h6_structural_repeat = prepare_structural_only(
        h6_repeat_bundle.verifier, h6_repeat_bundle.candidates
    )
    h6_structural_identical = canonical_json_bytes(
        h6_structural
    ) == canonical_json_bytes(h6_structural_repeat)
    representatives = {
        value.candidate_id: value for value in h6_all_bundle.candidates
    }
    representative_ids = h6_structural["physical_representative_candidate_ids"]
    deletions = [
        value for value in representative_ids if representatives[value].deletion_shortcut
    ]
    sparse_candidates = [
        value
        for value in representative_ids
        if not representatives[value].deletion_shortcut
    ]
    hash_key = lambda value: (hashlib.sha256(value.encode()).hexdigest(), value)
    subset_ids = tuple(sorted(deletions, key=hash_key)[:2]) + tuple(
        sorted(sparse_candidates, key=hash_key)[:2]
    )
    if len(subset_ids) != 4:
        raise S11V2CalibrationError("H6 calibration subset lacks both classes")
    subset_body = {
        "schema": "v5-final.h6-verifier-v2-limited-probe-freeze.v1",
        "selection_rule": (
            "two SHA256-smallest physical representatives per deletion/nondeletion class"
        ),
        "candidate_ids": list(subset_ids),
        "candidate_outcomes_used": False,
        "production_selection_claimed": False,
    }
    subset_body["subset_digest"] = _digest(subset_body)
    h6_limited = _actual_bundle(
        context=h6_context,
        catalog=h6_catalog,
        checkpoint_dir=work / "h6-limited",
        ids=subset_ids,
    ).run()["core"]
    h6_core = {
        "schema": "v5-final.h6-verifier-v2-calibration.v1",
        "structural_core": h6_structural,
        "limited_probe_freeze": subset_body,
        "limited_probe_core": h6_limited,
        "legacy_dense_verifier_candidate_count": 0,
        "candidate_energy_evaluations": 0,
        "optimizer_iterations": 0,
        "FCI_reporting": 0,
    }
    h6_core["core_digest"] = _digest(h6_core)
    return {
        "schema": "v5-final.s11-v2-calibration-development-worker.v1",
        "lih_core": lih_core,
        "lih_identical": lih_identical,
        "lih_resume_equal": lih_resume_equal,
        "lih_ids": list(lih_ids),
        "partial_status": partial["core"]["status"],
        "h6_core": h6_core,
        "h6_structural_identical": h6_structural_identical,
        "candidate_energy_evaluations": 0,
        "optimizer_iterations": 0,
        "FCI_reporting": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-path", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    write_json_exclusive(args.result_path, run(args.work_dir))


if __name__ == "__main__":
    main()
