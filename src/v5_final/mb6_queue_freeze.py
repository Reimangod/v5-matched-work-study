"""MB6 outcome-blind H2/H4 calibration queue freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb4_2_owner_protocol_freeze import CANONICAL_METHOD_IDS, OUTPUT as MB42_OUTPUT
from .historical_artifact_audit import (
    artifact_binding_commit,
    artifact_is_immutable_git_blob,
    is_ancestor,
)
from .mb5_1_production_backend_audit import OUTPUT as MB51_OUTPUT
from .p0_preexecution_audit import OUTPUT as P0_OUTPUT
from .production_kernel_bindings import PARENT_PYTHON
from .s0_successor import ROOT


OUTPUT_DIR = ROOT / "artifacts/v5-final/mb6"
ENV_OUTPUT = OUTPUT_DIR / "execution-environment-v1.json"
CATALOG_OUTPUT = OUTPUT_DIR / "h2-h4-source-catalog-v1.json"
QUEUE_OUTPUT = OUTPUT_DIR / "h2-h4-calibration-queue-v1.json"
LEDGER_OUTPUT = OUTPUT_DIR / "h2-h4-calibration-ledger-root-v1.json"
FREEZE_OUTPUT = OUTPUT_DIR / "mb6-outcome-blind-freeze-v1.json"
S5_FREEZE = ROOT / "artifacts/v5-final/s5/development-protocol-freeze-v3.json"
S5_QUEUE = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
S5_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"
WORK_ORDER = ("LOW", "MEDIUM", "HIGH")


class MB6Error(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _probe_digest(value: Any) -> str:
    """Match the parent identity package's canonical JSON (no trailing LF)."""

    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _with_digest(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result[field] = _digest(result)
    return result


def capture_environment() -> dict[str, Any]:
    code = (
        "import json,platform,sys;print(json.dumps({"
        "'python_version':platform.python_version(),"
        "'python_implementation':platform.python_implementation().lower(),"
        "'byte_order':sys.byteorder,'system':platform.system().lower(),"
        "'machine':platform.machine().lower()}))"
    )
    completed = subprocess.run(
        [str(PARENT_PYTHON), "-c", code],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    runtime = json.loads(completed.stdout)
    mb51 = json.loads(MB51_OUTPUT.read_text())
    result = {
        "schema": "v5-final.mb6-execution-environment.v1",
        "runtime": runtime,
        "required_threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
        "dependency_locks": {
            "root_uv_lock_sha256": _sha(ROOT / "uv.lock"),
            "parent_uv_lock_sha256": _sha(ROOT / "provenance/dvg-obs-ceo/uv.lock"),
        },
        "parent_commit": mb51["production_kernel_API"]["parent_commit"],
        "CEO_commit": mb51["production_kernel_API"]["CEO_commit"],
        "execution_rule": "MB7 must match every frozen field before any molecular kernel call",
    }
    return _with_digest(result, "environment_digest")


def build_catalog() -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(ROOT / "src"),
            str(ROOT / "provenance/dvg-obs-ceo/src"),
            str(ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"),
        )
    )
    temporary_root = Path(tempfile.gettempdir())
    environment["MPLCONFIGDIR"] = str(temporary_root / "v5-mb6-mpl")
    completed = subprocess.run(
        [str(PARENT_PYTHON), "-m", "v5_final.mb6_source_catalog_probe"],
        cwd=temporary_root,
        env=environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout)


def _v4_sentinels(case: dict[str, Any]) -> list[dict[str, Any]]:
    representatives: dict[str, dict[str, Any]] = {}
    for candidate in case["source_structural_catalog"]:
        if candidate["structurally_eligible"] is not True:
            continue
        key = candidate["equivalence_class_id"]
        previous = representatives.get(key)
        if previous is None or candidate["candidate_structural_id"] < previous["candidate_structural_id"]:
            representatives[key] = candidate
    selected = [representatives[key] for key in sorted(representatives)][:4]
    return [
        {
            "candidate_structural_id": item["candidate_structural_id"],
            "equivalence_class_id": item["equivalence_class_id"],
            "canonical_order": index,
            "structurally_eligible": True,
        }
        for index, item in enumerate(selected)
    ]


def _candidate_binding(method_id: str, case: dict[str, Any]) -> dict[str, Any]:
    eligible = [
        {
            "candidate_structural_id": item["candidate_structural_id"],
            "equivalence_class_id": item["equivalence_class_id"],
            "canonical_order": index,
        }
        for index, item in enumerate(case["source_structural_catalog"])
        if item["structurally_eligible"] is True
    ]
    if method_id in {"immutable-ceo-star-source", "same-structure-reoptimization"}:
        return {"candidate_set": [], "rule": "no structural candidate"}
    if method_id == "structural-magnitude-pruning":
        return {
            "candidate_set": case["magnitude_candidates"],
            "rule": "single-coordinate theta_i->0; ascending theta_i^2 then structural ID",
        }
    if method_id == "v4.1-one-shot-joint-compression":
        return {
            "candidate_set": _v4_sentinels(case),
            "rule": "one lowest structural ID per equivalence class; maximum four; canonical class order",
            "predictor_used": False,
            "FCI_used": False,
            "candidate_energy_used": False,
            "historical_rank_used": False,
            "development_outcome_used": False,
        }
    if method_id == "v5-fixed-source-whitelist-no-replenishment":
        return {
            "candidate_set": eligible,
            "source_whitelist_digest": _digest(eligible),
            "rule": "current-child reranking restricted to source structural whitelist",
            "replenishment_allowed": False,
        }
    return {
        "candidate_set": eligible,
        "initial_catalog_digest": _digest(eligible),
        "rule": "current-child structural catalog rebuilt after every accepted commit",
        "replenishment_allowed": True,
    }


def build_queue(catalog: dict[str, Any], environment: dict[str, Any]) -> dict[str, Any]:
    mb42 = json.loads(MB42_OUTPUT.read_text())
    mb51 = json.loads(MB51_OUTPUT.read_text())
    s5 = json.loads(S5_FREEZE.read_text())
    optimizer = s5["policy"]["optimizer"]
    acceptance = s5["policy"]["acceptance"]
    items = []
    for case in catalog["cases"]:
        for work_name in WORK_ORDER:
            profile = s5["policy"]["work_profiles"][work_name]
            for method_id in CANONICAL_METHOD_IDS:
                executor = mb51["executor_identities"][method_id]
                binding = _candidate_binding(method_id, case)
                body = {
                    "case_id": case["case_id"],
                    "method_id": method_id,
                    "work_envelope": work_name,
                    "source_checkpoint_digest": case["source_checkpoint_digest"],
                    "source_checkpoint_sha256": case["source_checkpoint_sha256"],
                    "StatePreparationID": case["StatePreparationID"],
                    "ProblemID": case["ProblemID"],
                    "Hamiltonian_digest": case["Hamiltonian_digest"],
                    "executor_id": executor["executor_id"],
                    "executor_source_sha256": executor["source_sha256"],
                    "protocol_digest": mb42["protocol_digests"][method_id],
                    "candidate_binding": binding,
                    "optimizer_policy_digest": _digest(optimizer),
                    "acceptance_policy_digest": _digest(acceptance),
                    "componentwise_work_cap": profile["semantic_work_cap"],
                    "work_cap_digest": _digest(profile["semantic_work_cap"]),
                    "work_cap_provenance": {
                        "source": str(S5_FREEZE.relative_to(ROOT)),
                        "profile": work_name,
                        "derivation": profile["derivation"],
                        "classification": "pre-existing pre-outcome hard ceiling; not an empirical runtime estimate",
                    },
                    "RNG_identity": {"python_seed": 0, "numpy_seed": 0},
                    "environment_digest": environment["environment_digest"],
                    "resource_policy": {
                        "counter": "paper-era-full-circuit-resource-v1:paper-era-qasm-counter-a3f89d0",
                        "full_ansatz_recount": True,
                        "barrier_free_full_ansatz_compilation": False,
                    },
                    "retry_policy": "system-failure-only; preserve prior attempt and link digest",
                    "systemic_abort_policy": "stop entire queue on identity/counter/schema violation",
                    "terminal_status": "NOT_STARTED",
                }
                item = dict(body)
                item["queue_item_id"] = "mb6-calibration-item-v1:" + _digest(body)
                items.append(item)
    queue_body = {
        "schema": "v5-final.mb6-h2-h4-calibration-queue.v1",
        "schema_digest": _digest({"schema": "v5-final.mb6-h2-h4-calibration-queue.v1"}),
        "stage": "MB6_OUTCOME_BLIND_QUEUE_FREEZE",
        "status": "FROZEN_NOT_AUTHORIZED_FOR_EXECUTION",
        "generation_order": "case, LOW/MEDIUM/HIGH, canonical method order",
        "items": items,
        "frozen_item_count": len(items),
        "executor_digest": _digest(mb51["executor_identities"]),
        "catalog_digest": catalog["probe_digest"],
        "environment_digest": environment["environment_digest"],
        "existing_development_queue": {
            "path": str(S5_QUEUE.relative_to(ROOT)),
            "sha256": _sha(S5_QUEUE),
            "separate_and_untouched": True,
        },
        "candidate_energy_evaluations": 0,
    }
    queue_body["queue_digest"] = _digest(queue_body)
    return queue_body


def build_ledger(queue: dict[str, Any]) -> dict[str, Any]:
    body = {
        "schema": "v5-final.mb6-calibration-ledger-root.v1",
        "queue_digest": queue["queue_digest"],
        "expected_queue_item_ids": [item["queue_item_id"] for item in queue["items"]],
        "expected_queue_count": queue["frozen_item_count"],
        "completed_queue_item_ids": [],
        "segments": [],
        "candidate_energy_evaluations": 0,
        "completeness_contract": {
            "expected_queue_nonempty": True,
            "frozen_queue_artifact_sha256_required": True,
            "every_and_only_expected_item_terminal": True,
            "one_terminal_segment_per_item_after_linked_retries": True,
        },
    }
    return _with_digest(body, "ledger_root_digest")


def build_freeze(
    catalog: dict[str, Any], queue: dict[str, Any], ledger: dict[str, Any], environment: dict[str, Any]
) -> dict[str, Any]:
    development = json.loads(S5_QUEUE.read_text())
    development_ledger = json.loads(S5_LEDGER.read_text())
    p0 = json.loads(P0_OUTPUT.read_text())
    checks = {
        "two_stationary_sources": len(catalog["cases"]) == 2
        and all(case["stationary_source_audit"]["passed"] for case in catalog["cases"]),
        "no_molecular_kernel_called": not any(catalog["molecular_kernel_guard_calls"].values()),
        "no_candidate_energy": catalog["candidate_energy_evaluations"] == 0,
        "queue_nonempty_and_count_exact": queue["frozen_item_count"] == 36,
        "six_methods_three_caps_two_cases": len(queue["items"]) == 2 * 3 * 6,
        "v4_sentinel_max_four_and_outcome_free": all(
            len(item["candidate_binding"]["candidate_set"]) <= 4
            and item["candidate_binding"]["FCI_used"] is False
            and item["candidate_binding"]["candidate_energy_used"] is False
            for item in queue["items"]
            if item["method_id"] == "v4.1-one-shot-joint-compression"
        ),
        "magnitude_physical_deletion_and_recount": all(
            candidate["physical_generator_deleted"]
            and candidate["coefficient_zeroing_only"] is False
            and candidate["full_circuit_rebuild_and_recount"]
            and candidate["zero_reduction_is_success"] is False
            for item in queue["items"]
            if item["method_id"] == "structural-magnitude-pruning"
            for candidate in item["candidate_binding"]["candidate_set"]
        ),
        "development_queue_untouched": development["expected_queue_count"] == 90
        and all(item["terminal_status"] == "NOT_STARTED" for item in development["items"])
        and development_ledger["development_candidate_energy_evaluations"] == 0,
        "empty_calibration_ledger_bound_to_queue": ledger["expected_queue_count"] == 36
        and not ledger["completed_queue_item_ids"]
        and not ledger["segments"],
        "p0_capacity_no_go_preserved": p0["status"] == "NO_GO_INSUFFICIENT_SAFE_DISK_CAPACITY",
    }
    result = {
        "schema": "v5-final.mb6-outcome-blind-freeze.v1",
        "stage": "MB6_OUTCOME_BLIND_QUEUE_FREEZE",
        "status": "PASS_QUEUE_FREEZE_EXECUTION_STILL_BLOCKED",
        "decision": "GO_MB7_PRE_CALIBRATION_AUDIT_ONLY",
        "artifacts": {
            "environment": {"path": str(ENV_OUTPUT.relative_to(ROOT)), "digest": environment["environment_digest"]},
            "catalog": {"path": str(CATALOG_OUTPUT.relative_to(ROOT)), "digest": catalog["probe_digest"]},
            "queue": {"path": str(QUEUE_OUTPUT.relative_to(ROOT)), "digest": queue["queue_digest"]},
            "ledger": {"path": str(LEDGER_OUTPUT.relative_to(ROOT)), "digest": ledger["ledger_root_digest"]},
        },
        "checks": checks,
        "authorization": {
            "MB7_pre_calibration_audit": "AUTHORIZED_ONLY",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": "H2/H4 source identities and structural candidates only; prior candidate outcomes, FCI, and candidate energy were excluded from selection.",
        "systems_boundary": "Exact executors are digest-bound but must pass behavioral kernel-binding audit at MB7; P0 capacity No-Go remains active.",
    }
    if not all(checks.values()):
        raise MB6Error("MB6 freeze checks failed")
    return _with_digest(result, "freeze_digest")


def audit() -> dict[str, bool]:
    environment = json.loads(ENV_OUTPUT.read_text())
    committed_catalog = json.loads(CATALOG_OUTPUT.read_text())
    committed_queue = json.loads(QUEUE_OUTPUT.read_text())
    committed_ledger = json.loads(LEDGER_OUTPUT.read_text())
    committed_freeze = json.loads(FREEZE_OUTPUT.read_text())
    frozen_artifacts = (
        ENV_OUTPUT,
        CATALOG_OUTPUT,
        QUEUE_OUTPUT,
        LEDGER_OUTPUT,
        FREEZE_OUTPUT,
    )
    binding_commit = artifact_binding_commit(FREEZE_OUTPUT)
    checks = {
        "environment_digest_valid": environment["environment_digest"]
        == _digest({key: value for key, value in environment.items() if key != "environment_digest"}),
        "catalog_content_digest_valid": committed_catalog["probe_digest"]
        == _probe_digest({key: value for key, value in committed_catalog.items() if key != "probe_digest"}),
        "queue_content_digest_valid": committed_queue["queue_digest"]
        == _digest({key: value for key, value in committed_queue.items() if key != "queue_digest"}),
        "ledger_content_digest_valid": committed_ledger["ledger_root_digest"]
        == _digest({key: value for key, value in committed_ledger.items() if key != "ledger_root_digest"}),
        "freeze_content_digest_valid": committed_freeze["freeze_digest"]
        == _digest({key: value for key, value in committed_freeze.items() if key != "freeze_digest"}),
        "cross_artifact_bindings_valid": committed_queue["catalog_digest"]
        == committed_catalog["probe_digest"]
        and committed_ledger["queue_digest"] == committed_queue["queue_digest"]
        and committed_freeze["artifacts"]["catalog"]["digest"] == committed_catalog["probe_digest"]
        and committed_freeze["artifacts"]["queue"]["digest"] == committed_queue["queue_digest"]
        and committed_freeze["artifacts"]["ledger"]["digest"] == committed_ledger["ledger_root_digest"],
        "historical_artifacts_are_exact_git_blobs": all(
            artifact_is_immutable_git_blob(path) for path in frozen_artifacts
        ),
        "historical_freeze_commit_is_ancestor": is_ancestor(binding_commit),
        "historical_rebuild_not_attempted_from_current_source": True,
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise MB6Error("MB6 deterministic audit failed: " + ", ".join(failures))
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not args.write:
        print(json.dumps(audit(), sort_keys=True))
        return
    environment = capture_environment()
    catalog_a = build_catalog()
    catalog_b = build_catalog()
    if canonical_json_bytes(catalog_a) != canonical_json_bytes(catalog_b):
        raise MB6Error("source catalog was not byte-identical across two builds")
    queue_a = build_queue(catalog_a, environment)
    queue_b = build_queue(catalog_b, environment)
    if canonical_json_bytes(queue_a) != canonical_json_bytes(queue_b):
        raise MB6Error("queue was not byte-identical across two builds")
    ledger = build_ledger(queue_a)
    freeze = build_freeze(catalog_a, queue_a, ledger, environment)
    for path, value in (
        (ENV_OUTPUT, environment),
        (CATALOG_OUTPUT, catalog_a),
        (QUEUE_OUTPUT, queue_a),
        (LEDGER_OUTPUT, ledger),
        (FREEZE_OUTPUT, freeze),
    ):
        write_json_exclusive(path, value)


if __name__ == "__main__":
    main()
