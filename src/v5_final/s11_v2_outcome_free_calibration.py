"""Outcome-free correctness calibration for the frozen S11-v2 Verifier V2."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Iterator, Mapping, Sequence

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import expm_multiply

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .parent_native_candidate_adapter import (
    build_typed_catalog,
    compose_parent_native_plan,
)
from .parent_native_rewrite import prepare_rewrite_for_optimizer
from .parent_native_runtime_factory_v2 import build_queue_bound_runtime_v2
from .parent_native_verifier_v2 import build_parent_verifier_v2
from .s0_successor import ROOT
from .s9_h2_h4_calibration_runner import _plan as calibration_plan
from .verifier_v2 import CandidateV2, VerifierV2, VerifierV2Policy, _digest


OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s11-v2-verifier-calibration-v1"
SUMMARY_PATH = OUTPUT_DIR / "calibration-summary-v1.json"
MANIFEST_PATH = OUTPUT_DIR / "MANIFEST.sha256"
CORE_PATHS = {
    "toy": OUTPUT_DIR / "toy-core-v2.json",
    "h2": OUTPUT_DIR / "h2-core-v2.json",
    "h4": OUTPUT_DIR / "h4-core-v2.json",
    "lih": OUTPUT_DIR / "lih-core-v2.json",
    "h6": OUTPUT_DIR / "h6-structural-and-limited-probe-v2.json",
}
CODE_PATHS = (
    ROOT / "src/v5_final/verifier_v2.py",
    ROOT / "src/v5_final/parent_native_verifier_v2.py",
    ROOT / "src/v5_final/verifier_v2_structural_calibration.py",
    ROOT / "src/v5_final/s11_v2_calibration_development_worker.py",
    ROOT / "src/v5_final/s11_v2_outcome_free_calibration.py",
)
THREAD_KEYS = ("MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS")


class S11V2CalibrationError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def _thread_scope(count: int) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in THREAD_KEYS}
    for key in THREAD_KEYS:
        os.environ[key] = str(count)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _toy_candidates(recounts: list[str]) -> tuple[tuple[CandidateV2, ...], Any]:
    left = 1j * sparse.diags([1.0, 1.0, -1.0, -1.0], format="csr")
    right = 1j * sparse.diags([1.0, -1.0, 1.0, -1.0], format="csr")
    matrices = {"left": left, "right": right, "sum": left + right}

    def resources(label: str, vector: tuple[int, ...]):
        def recount():
            recounts.append(label)
            return vector

        return recount

    def circuit(coordinates: np.ndarray, probe: np.ndarray) -> np.ndarray:
        return expm_multiply(float(coordinates[0]) * matrices["sum"], probe)

    candidates = (
        CandidateV2(
            "toy-relation",
            "toy-semantic-relation",
            "toy-state-relation",
            ("left", "right"),
            ("sum",),
            ((1.0,), (1.0,)),
            0.2,
            4,
            2,
            resources("relation", (3, 2, 1)),
            circuit,
        ),
        CandidateV2(
            "toy-relation-alias",
            "toy-semantic-relation",
            "toy-state-relation-alias",
            ("left", "right"),
            ("sum",),
            ((1.0,), (1.0,)),
            0.3,
            4,
            2,
            resources("semantic-alias", (99, 99, 99)),
            circuit,
        ),
        CandidateV2(
            "toy-deletion",
            "toy-semantic-deletion",
            "toy-state-deletion",
            ("left",),
            (),
            ((),),
            0.1,
            4,
            2,
            resources("deletion", (1, 1, 0)),
            deletion_shortcut=True,
        ),
    )
    return candidates, lambda digest: matrices[digest]


def _toy_run(checkpoint_dir: Path) -> tuple[dict[str, Any], list[str]]:
    recounts: list[str] = []
    candidates, loader = _toy_candidates(recounts)
    verifier = VerifierV2(
        policy=VerifierV2Policy(),
        generator_loader=loader,
        checkpoint_dir=checkpoint_dir,
        source_binding={"case_id": "toy", "source_digest": "toy-source-v1"},
    )
    return verifier.run(candidates)["core"], recounts


def _actual_bundle(
    *, context: Any, catalog: Any, checkpoint_dir: Path, ids: Sequence[str]
):
    return build_parent_verifier_v2(
        context=context,
        catalog=catalog,
        admitted_candidate_ids=ids,
        policy=VerifierV2Policy(),
        checkpoint_dir=checkpoint_dir,
    )


def _legacy_verify(context: Any, catalog: Any, candidate: Any) -> dict[str, Any]:
    from dvg_obs_ceo import block_ir

    plan = compose_parent_native_plan(
        pool=context.pool,
        source=context.runtime.ansatz,
        catalog=catalog,
        candidates=(candidate,),
        gradient=context.runtime.gradient,
        inverse_hessian=context.runtime.inverse_hessian,
        problem_id=context.problem_id,
        reference_state=context._actual_algorithm.ref_det,
    )
    original = block_ir.expm
    dense_calls = 0

    def counted(value):
        nonlocal dense_calls
        dense_calls += 1
        return original(value)

    block_ir.expm = counted
    passed = False
    error_type = None
    try:
        prepare_rewrite_for_optimizer(
            pool=context.pool,
            source=context.runtime.ansatz,
            parent_plan=plan,
        )
        passed = True
    except Exception as error:  # recorded as verifier parity, never an outcome
        error_type = type(error).__name__
    finally:
        block_ir.expm = original
    return {
        "candidate_id": candidate.candidate_id,
        "kind": candidate.kind,
        "legacy_verifier_passed": passed,
        "legacy_error_type": error_type,
        "legacy_dense_expm_calls": dense_calls,
        "legacy_dense_generator_materializations": len(candidate.source_pool_indices)
        + len(candidate.target_pool_indices),
        "candidate_energy_evaluations": 0,
        "optimizer_iterations": 0,
    }


def _single_new_verify(
    context: Any, catalog: Any, candidate: Any, checkpoint_dir: Path
) -> dict[str, Any]:
    bundle = _actual_bundle(
        context=context,
        catalog=catalog,
        checkpoint_dir=checkpoint_dir,
        ids=(candidate.candidate_id,),
    )
    core = bundle.run()["core"]
    return {
        "candidate_id": candidate.candidate_id,
        "new_verifier_passed": core["status"]
        == "VERIFIED_READY_AWAITING_OUTCOME_AUTHORIZATION",
        "new_verifier_status": core["status"],
        "new_dense_expm_calls": core["deterministic_work_counters"]["N_dense_expm"],
        "new_sparse_expm_multiply": core["deterministic_work_counters"][
            "N_sparse_expm_multiply"
        ],
        "new_deletion_shortcut": core["numeric_verifications"][0]["status"]
        == "VERIFIED_ANALYTIC_DELETION_EXP_0G_IDENTITY",
        "candidate_energy_evaluations": core["deterministic_work_counters"][
            "energy_evaluations"
        ],
        "optimizer_iterations": core["deterministic_work_counters"][
            "optimizer_iterations"
        ],
    }


def _run_full_twice(
    context: Any, catalog: Any, ids: Sequence[str], root: Path, label: str
) -> tuple[dict[str, Any], bool]:
    first = _actual_bundle(
        context=context,
        catalog=catalog,
        checkpoint_dir=root / f"{label}-first",
        ids=ids,
    ).run()["core"]
    second = _actual_bundle(
        context=context,
        catalog=catalog,
        checkpoint_dir=root / f"{label}-second",
        ids=ids,
    ).run()["core"]
    return first, canonical_json_bytes(first) == canonical_json_bytes(second)


def _core_is_outcome_free(core: Mapping[str, Any]) -> bool:
    counters = core["deterministic_work_counters"]
    return (
        counters["N_dense_expm"] == 0
        and counters["energy_evaluations"] == 0
        and counters["optimizer_iterations"] == 0
    )


def run_calibration() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if any(os.environ.get(key) != "2" for key in THREAD_KEYS):
        raise S11V2CalibrationError(
            "calibration coordinator requires frozen H2/H4 thread environment 2/2/2"
        )
    design = json.loads(
        (
            ROOT
            / "artifacts/v5-final/parent-native/s11-v2-verifier-remediation/verifier-v2-design-v1.json"
        ).read_text()
    )
    with tempfile.TemporaryDirectory(prefix="v5-s11-v2-calibration-") as temporary:
        work = Path(temporary)
        toy_first, toy_recounts = _toy_run(work / "toy-first")
        toy_second, _ = _toy_run(work / "toy-second")
        toy_identical = canonical_json_bytes(toy_first) == canonical_json_bytes(toy_second)

        with _thread_scope(2):
            plan = calibration_plan()
            h2_item = plan["items"][4]
            h2_context = build_queue_bound_runtime_v2(
                h2_item["queue_item_id"], plan_record=plan
            )
            h2_catalog = build_typed_catalog(
                h2_context.pool, h2_context.runtime.ansatz
            )
            h2_ids = tuple(value.candidate_id for value in h2_catalog.candidates)
            h2_core, h2_identical = _run_full_twice(
                h2_context, h2_catalog, h2_ids, work, "h2"
            )
            h2_candidate = h2_catalog.candidates[0]
            h2_old = _legacy_verify(h2_context, h2_catalog, h2_candidate)
            h2_new = _single_new_verify(
                h2_context, h2_catalog, h2_candidate, work / "h2-parity"
            )

            h4_item = plan["items"][22]
            h4_context = build_queue_bound_runtime_v2(
                h4_item["queue_item_id"], plan_record=plan
            )
            h4_catalog = build_typed_catalog(
                h4_context.pool, h4_context.runtime.ansatz
            )
            h4_ids = tuple(value.candidate_id for value in h4_catalog.candidates)
            h4_core, h4_identical = _run_full_twice(
                h4_context, h4_catalog, h4_ids, work, "h4"
            )
            h4_parity = []
            for index, candidate in enumerate(h4_catalog.candidates):
                old = _legacy_verify(h4_context, h4_catalog, candidate)
                new = _single_new_verify(
                    h4_context,
                    h4_catalog,
                    candidate,
                    work / f"h4-parity-{index}",
                )
                h4_parity.append({**old, **new, "pass_fail_equal": old["legacy_verifier_passed"] == new["new_verifier_passed"]})

        worker_path = work / "development-worker-result.json"
        worker_environment = dict(os.environ)
        for key in THREAD_KEYS:
            worker_environment[key] = "1"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "v5_final.s11_v2_calibration_development_worker",
                "--result-path",
                str(worker_path),
                "--work-dir",
                str(work / "development-worker"),
            ],
            check=True,
            cwd=ROOT,
            env=worker_environment,
        )
        development = json.loads(worker_path.read_text())
        lih_core = development["lih_core"]
        lih_identical = development["lih_identical"]
        lih_resume_equal = development["lih_resume_equal"]
        lih_ids = tuple(development["lih_ids"])
        partial_status = development["partial_status"]
        h6_core = development["h6_core"]
        h6_structural = h6_core["structural_core"]
        h6_limited = h6_core["limited_probe_core"]
        subset_body = h6_core["limited_probe_freeze"]
        subset_ids = tuple(subset_body["candidate_ids"])
        h6_structural_identical = development["h6_structural_identical"]

        parity = [
            {
                **h2_old,
                **h2_new,
                "pass_fail_equal": h2_old["legacy_verifier_passed"]
                == h2_new["new_verifier_passed"],
            },
            *h4_parity,
        ]
        cores = {
            "toy": toy_first,
            "h2": h2_core,
            "h4": h4_core,
            "lih": lih_core,
            "h6": h6_core,
        }
        checks = {
            "toy_byte_identical": toy_identical,
            "toy_dedup_before_recount": sorted(toy_recounts)
            == ["deletion", "relation"],
            "h2_byte_identical": h2_identical,
            "h4_byte_identical": h4_identical,
            "lih_byte_identical": lih_identical,
            "lih_resume_equals_uninterrupted": lih_resume_equal,
            "lih_partial_was_checkpointed": partial_status
            == "CHECKPOINTED_INCOMPLETE_OUTCOME_FREE",
            "old_new_pass_fail_parity": all(value["pass_fail_equal"] for value in parity),
            "deletion_shortcut_parity": all(
                value["new_deletion_shortcut"]
                for value in parity
                if value["kind"] in {"block-deletion", "mvp-whole-deletion"}
            ),
            "sparse_relation_exercised": any(
                value["new_sparse_expm_multiply"] > 0 for value in parity
            ),
            "all_new_cores_dense_expm_zero": all(
                _core_is_outcome_free(cores[key]) for key in ("toy", "h2", "h4", "lih")
            )
            and _core_is_outcome_free(h6_limited),
            "H6_all_427_structurally_prepared": h6_structural[
                "deterministic_work_counters"
            ]["candidate_generations"]
            == 427,
            "H6_structural_byte_identical": h6_structural_identical,
            "H6_legacy_dense_verifier_not_run": h6_core[
                "legacy_dense_verifier_candidate_count"
            ]
            == 0,
            "candidate_energy_zero": all(
                core["deterministic_work_counters"]["energy_evaluations"] == 0
                for core in (toy_first, h2_core, h4_core, lih_core, h6_limited)
            ),
            "optimizer_zero": all(
                core["deterministic_work_counters"]["optimizer_iterations"] == 0
                for core in (toy_first, h2_core, h4_core, lih_core, h6_limited)
            ),
        }
        if not all(checks.values()):
            raise S11V2CalibrationError(
                "calibration checks failed: "
                + ", ".join(key for key, value in checks.items() if not value)
            )
        summary = {
            "schema": "v5-final.s11-v2-outcome-free-calibration.v1",
            "status": "PASS_OUTCOME_FREE_VERIFIER_V2_CALIBRATION",
            "verifier_design_freeze_digest": design["design_freeze_digest"],
            "policy_digest": design["policy"]["policy_digest"],
            "case_core_digests": {
                key: value["core_digest"] for key, value in cores.items()
            },
            "old_new_parity": parity,
            "legacy_dense_expm_calibration_only": sum(
                value["legacy_dense_expm_calls"] for value in parity
            ),
            "production_dense_expm": 0,
            "LiH": {
                "candidate_ids": list(lih_ids),
                "selected_candidate_ids": lih_core["top_k_freeze"][
                    "selected_candidate_ids"
                ],
                "semantic_aliases": lih_core["semantic_aliases"],
                "physical_aliases": lih_core["physical_aliases"],
                "resource_recounts": lih_core["deterministic_work_counters"][
                    "resource_recounts"
                ],
            },
            "H6": {
                "generated_candidates": 427,
                "unique_semantic_candidates": h6_structural[
                    "deterministic_work_counters"
                ]["unique_semantic_candidates"],
                "unique_physical_states": h6_structural[
                    "deterministic_work_counters"
                ]["unique_physical_states"],
                "limited_probe_subset_digest": subset_body["subset_digest"],
                "limited_probe_candidate_ids": list(subset_ids),
                "legacy_dense_candidate_count": 0,
            },
            "checks": checks,
            "authorization": {
                "H2_H4_work_recalibration": "AUTHORIZED",
                "S11_v2_queue_freeze": "NOT_AUTHORIZED_UNTIL_RECALIBRATION",
                "molecular_candidate_energy": "NOT_AUTHORIZED",
                "FCI_reporting": "NOT_AUTHORIZED",
                "performance_claim": "NOT_AUTHORIZED",
            },
            "scientific_boundary": {
                "established": (
                    "Verifier V2 preserves tractable legacy pass/fail semantics, "
                    "is deterministic and resumable, and performs zero production dense expm."
                ),
                "not_established": (
                    "No candidate energy, molecular performance comparison, or V5 advantage."
                ),
            },
        }
        summary["summary_digest"] = _digest(summary)
        return summary, cores


def write_calibration() -> dict[str, Any]:
    summary, cores = run_calibration()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for key, path in CORE_PATHS.items():
        write_json_exclusive(path, cores[key])
    summary = dict(summary)
    summary["case_core_sha256"] = {
        key: _sha(path) for key, path in CORE_PATHS.items()
    }
    body = dict(summary)
    body.pop("summary_digest")
    summary["summary_digest"] = _digest(body)
    write_json_exclusive(SUMMARY_PATH, summary)
    paths = (*CODE_PATHS, *CORE_PATHS.values(), SUMMARY_PATH)
    lines = [f"{_sha(path)}  {path.relative_to(ROOT)}" for path in paths]
    if MANIFEST_PATH.exists():
        raise S11V2CalibrationError("calibration manifest already exists")
    MANIFEST_PATH.write_text("\n".join(lines) + "\n")
    return summary


def audit() -> dict[str, bool]:
    summary = json.loads(SUMMARY_PATH.read_text())
    body = dict(summary)
    observed = body.pop("summary_digest", None)
    cores = {key: json.loads(path.read_text()) for key, path in CORE_PATHS.items()}
    expected_lines = [
        f"{_sha(path)}  {path.relative_to(ROOT)}"
        for path in (*CODE_PATHS, *CORE_PATHS.values(), SUMMARY_PATH)
    ]
    checks = {
        "summary_digest_valid": observed == _digest(body),
        "case_sha256_valid": summary["case_core_sha256"]
        == {key: _sha(path) for key, path in CORE_PATHS.items()},
        "case_core_digests_valid": summary["case_core_digests"]
        == {key: value["core_digest"] for key, value in cores.items()},
        "manifest_exact": MANIFEST_PATH.read_text().splitlines() == expected_lines,
        "all_calibration_checks_pass": all(summary["checks"].values()),
        "production_dense_expm_zero": summary["production_dense_expm"] == 0,
        "candidate_outcomes_blocked": all(
            value.startswith("NOT_AUTHORIZED")
            for key, value in summary["authorization"].items()
            if key != "H2_H4_work_recalibration"
        ),
    }
    if not all(checks.values()):
        raise S11V2CalibrationError("committed calibration audit failed")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.write == args.audit:
        raise S11V2CalibrationError("select exactly one operation")
    result = write_calibration() if args.write else audit()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
