"""Freeze the outcome-independent A100 protocol and local CPU references."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
from typing import Any

import numpy as np

from .common import (
    ARTIFACT_ROOT,
    ROOT,
    A100PilotError,
    digest,
    embedded_digest_valid,
    git,
    load_json,
    publish,
    sha256_file,
    tree_inventory_digest,
)


P0 = ARTIFACT_ROOT / "p0-baseline"
PROTOCOL = P0 / "a100-parity-protocol-v1.json"
REFERENCE = P0 / "cpu-reference-bundle-v1.json"
BASELINE_HEAD = "bca77f26aad98937e69e824cb8024960c6994e60"
PARENT_COMMIT = "4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db"
CEO_COMMIT = "a3f89d03e6a03c89767d3cf8ee7657a57653dda0"
THREAD_KEYS = ("MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS")
PROTECTED_ROOTS = (
    ROOT / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v2",
    ROOT / "artifacts/v5-final/parent-native/s11-v2-production-execution-v1",
    ROOT / "artifacts/v5-final/parent-native/s12-matched-work-aggregation-v1",
    ROOT / "artifacts/v5-final/parent-native/s12-scientific-report-v1",
)
CALIBRATION_PLAN = (
    ROOT
    / "artifacts/v5-final/parent-native/mb6-v4/h2-h4-calibration-plan-v4.json"
)
DEVELOPMENT_PLAN = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-queue-v4/development-plan-v4.json"
)
CASE_SPECS: dict[str, dict[str, Any]] = {
    "h2": {
        "case_id": "h2-1.5-iteration-1",
        "plan": "calibration",
        "threads": 2,
        "role": "exact-positive-control",
    },
    "h4": {
        "case_id": "h4-1.5-known-development",
        "plan": "development",
        "threads": 1,
        "role": "no-safe-compression-negative-control",
    },
    "lih": {
        "case_id": "lih-3.0",
        "plan": "development",
        "threads": 1,
        "role": "representative-12-qubit",
    },
    "h6": {
        "case_id": "h6-1.5",
        "plan": "development",
        "threads": 1,
        "role": "mvp-heavy-12-qubit",
    },
    "beh2": {
        "case_id": "beh2-3.0",
        "plan": "development",
        "threads": 1,
        "role": "largest-current-14-qubit",
    },
}


def _float_hex(value: float) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise A100PilotError("non-finite reference value")
    if number == 0.0:
        number = 0.0
    return struct.pack(">d", number).hex()


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _select_item(plan: dict[str, Any], case_id: str) -> dict[str, Any]:
    matches = [
        item
        for item in plan["items"]
        if item["case_id"] == case_id
        and item["method_id"] == "immutable-ceo-star-source"
        and item["work_envelope"] == "LOW"
    ]
    if len(matches) != 1:
        raise A100PilotError(f"source selector is not unique: {case_id}")
    return matches[0]


def protocol_body() -> dict[str, Any]:
    return {
        "schema": "aic-a100-pilot.parity-protocol.v1",
        "status": "FROZEN_BEFORE_REGISTERED_P0_REFERENCE_AND_GPU_OUTCOMES",
        "prefreeze_diagnostics": {
            "registered_pilot_outcome": False,
            "case_alias": "h2",
            "purpose": "local runtime-factory and pinned-environment smoke only",
            "observed_fields": [
                "source_energy_hartree",
                "source_resource_vector",
                "source_state_sha256",
                "gradient_dimension",
            ],
            "used_to_set_tolerances_or_case_order": False,
            "disclosure": (
                "One H2 source-runtime diagnostic was executed before this freeze. "
                "No compression candidate, candidate energy, optimizer, FCI result, "
                "GPU result, or benchmark timing was evaluated."
            ),
        },
        "source_baseline_commit": BASELINE_HEAD,
        "parent_commit": PARENT_COMMIT,
        "CEO_commit": CEO_COMMIT,
        "case_order": list(CASE_SPECS),
        "case_specs": CASE_SPECS,
        "backend_policy": {
            "cpu": "immutable-current-qiskit-statevector-scipy-openfermion",
            "gpu": "qiskit-aer-gpu-statevector",
            "gpu_device": "GPU",
            "precision": "double",
            "gpu_count_per_job": 1,
            "cpu_fallback_is_success": False,
            "resource_counter": "shared-paper-era-cpu-counter",
        },
        "tolerances": {
            "phase_aligned_state_error_max": 1e-10,
            "absolute_energy_hartree_max": 1e-10,
            "max_gradient_component_max": 1e-8,
            "resource_vector": "EXACT_INTEGER_EQUALITY",
            "terminal_decision": "EXACT_EQUALITY",
            "candidate_semantic_order": "EXACT_EQUALITY",
        },
        "benchmark_policy": {
            "warmup_repetitions_min": 1,
            "measured_repetitions": 5,
            "current_system_end_to_end_speedup_min": 1.20,
            "same_aic_node_cpu_gpu_required": True,
            "synthetic_scaling_qubits": [16, 18, 20],
        },
        "route_counters": [
            "N_gpu_statevector",
            "N_gpu_energy",
            "N_gpu_gradient_component",
            "N_cpu_statevector",
            "N_cpu_energy",
            "N_cpu_gradient_component",
            "N_cpu_fallback",
        ],
        "scientific_boundaries": {
            "existing_90_item_study_mutable": False,
            "full_90_item_rerun_authorized": False,
            "FCI_for_selection_authorized": False,
            "measurement_cost_claim_authorized": False,
            "maximum_limited_pilot_items": 6,
        },
        "protected_artifact_snapshot": tree_inventory_digest(PROTECTED_ROOTS),
        "protected_roots": [path.relative_to(ROOT).as_posix() for path in PROTECTED_ROOTS],
        "key_artifacts": {
            "queue_v2": {
                "path": CALIBRATION_PLAN.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(CALIBRATION_PLAN),
            },
            "development_plan": {
                "path": DEVELOPMENT_PLAN.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(DEVELOPMENT_PLAN),
            },
            "s11_queue_v2": {
                "path": "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v2/s11-v2-queue-v2.json",
                "sha256": sha256_file(
                    ROOT
                    / "artifacts/v5-final/parent-native/s11-v2-queue-freeze-v2/s11-v2-queue-v2.json"
                ),
            },
            "s12_scientific_report": {
                "path": "artifacts/v5-final/parent-native/s12-scientific-report-v1/scientific-report-v1.md",
                "sha256": sha256_file(
                    ROOT
                    / "artifacts/v5-final/parent-native/s12-scientific-report-v1/scientific-report-v1.md"
                ),
            },
        },
    }


def freeze_protocol() -> dict[str, Any]:
    return publish(PROTOCOL, protocol_body(), "protocol_digest")


def _candidate_summary(candidate: Any) -> dict[str, Any]:
    relation = getattr(candidate, "exact_generator_relation", None)
    return {
        "candidate_id": str(candidate.candidate_id),
        "equivalence_class_id": str(candidate.equivalence_class_id),
        "kind": str(candidate.kind),
        "target_family": str(candidate.target_family),
        "source_block_id": str(candidate.source_block_id),
        "source_pool_indices": [int(value) for value in candidate.source_pool_indices],
        "target_pool_indices": [int(value) for value in candidate.target_pool_indices],
        "removed_source_slots": [int(value) for value in candidate.removed_source_slots],
        "exact_generator_relation": (
            None if relation is None else [float(value) for value in relation]
        ),
    }


def build_case_reference(alias: str) -> dict[str, Any]:
    if alias not in CASE_SPECS:
        raise A100PilotError(f"unknown case alias: {alias}")
    spec = CASE_SPECS[alias]
    if spec["plan"] == "calibration":
        from v5_final.parent_native_runtime_factory_v2 import build_queue_bound_runtime_v2

        plan = load_json(CALIBRATION_PLAN)
        item = _select_item(plan, str(spec["case_id"]))
        context = build_queue_bound_runtime_v2(item["queue_item_id"], plan_record=plan)
    else:
        from v5_final.parent_native_development_runtime_factory_v1 import (
            build_queue_bound_development_runtime_v1,
        )

        plan = load_json(DEVELOPMENT_PLAN)
        item = _select_item(plan, str(spec["case_id"]))
        context = build_queue_bound_development_runtime_v1(
            item["queue_item_id"], plan_record=plan
        )
    from v5_final.parent_native_candidate_adapter import build_typed_catalog

    catalog = build_typed_catalog(context.pool, context.runtime.ansatz)
    exact = [
        candidate
        for candidate in catalog.candidates
        if candidate.exact_generator_relation is not None
    ]
    approximate = [
        candidate
        for candidate in catalog.candidates
        if candidate.exact_generator_relation is None
    ]
    circuit = context.pool.get_circuit(
        list(context.runtime.ansatz.indices),
        list(context.runtime.ansatz.coefficients),
    )
    qasm = circuit.qasm()
    state = np.asarray(context.runtime.statevector, dtype=np.complex128).ravel()
    return {
        "alias": alias,
        "case_id": context.case_id,
        "role": spec["role"],
        "queue_item_id": context.queue_item_id,
        "plan_digest": context.plan_digest,
        "source_checkpoint_digest": context.source_checkpoint_digest,
        "StatePreparationID": context.state_preparation_id,
        "ProblemID": context.problem_id,
        "Hamiltonian_digest": context.hamiltonian_digest,
        "qubit_count": int(context.pool.n),
        "state_dimension": int(state.size),
        "statevector_norm_float64_hex": _float_hex(float(np.linalg.norm(state))),
        "statevector_sha256": hashlib.sha256(
            np.asarray(state, dtype=">c16").tobytes()
        ).hexdigest(),
        "energy_hartree_float64_hex": _float_hex(context.runtime.energy_hartree),
        "gradient_float64_hex": [_float_hex(value) for value in context.runtime.gradient],
        "gradient_infinity_norm_float64_hex": _float_hex(
            float(np.max(np.abs(context.runtime.gradient), initial=0.0))
        ),
        "coefficients_float64_hex": [
            _float_hex(value) for value in context.runtime.ansatz.coefficients
        ],
        "ansatz_indices": [int(value) for value in context.runtime.ansatz.indices],
        "iteration_counts": [
            int(value) for value in context.runtime.ansatz.cumulative_parameter_counts
        ],
        "resources": {key: int(value) for key, value in context.source_resources.items()},
        "source_qasm_sha256": hashlib.sha256(qasm.encode("utf-8")).hexdigest(),
        "candidate_count": len(catalog.candidates),
        "candidate_ids": [str(candidate.candidate_id) for candidate in catalog.candidates],
        "candidate_order_digest": digest(
            [str(candidate.candidate_id) for candidate in catalog.candidates]
        ),
        "exact_candidate_count": len(exact),
        "approximate_candidate_count": len(approximate),
        "representative_exact_candidate": (
            None if not exact else _candidate_summary(exact[0])
        ),
        "representative_approximate_candidate": (
            None if not approximate else _candidate_summary(approximate[0])
        ),
        "candidate_outcomes_evaluated": 0,
        "FCI_evaluations": 0,
    }


def _worker_command(alias: str, output: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "aic_a100_pilot.p0_baseline",
        "--case",
        alias,
        "--case-output",
        str(output),
    ]


def _build_cases() -> list[dict[str, Any]]:
    import tempfile

    results: list[dict[str, Any]] = []
    for alias, spec in CASE_SPECS.items():
        with tempfile.TemporaryDirectory(prefix=f"a100-p0-{alias}-") as directory:
            output = Path(directory) / "case.json"
            environment = os.environ.copy()
            for key in THREAD_KEYS:
                environment[key] = str(spec["threads"])
            completed = subprocess.run(
                _worker_command(alias, output),
                cwd=ROOT,
                env=environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if completed.returncode != 0:
                raise A100PilotError(
                    f"CPU reference worker failed for {alias}: {completed.stderr[-2000:]}"
                )
            results.append(load_json(output))
    return results


def build_reference() -> dict[str, Any]:
    if not PROTOCOL.is_file():
        raise A100PilotError("protocol must be frozen before CPU reference outcomes")
    protocol = load_json(PROTOCOL)
    if not embedded_digest_valid(protocol, "protocol_digest"):
        raise A100PilotError("frozen protocol digest is invalid")
    packages = {
        name: _distribution_version(name)
        for name in (
            "numpy",
            "scipy",
            "qiskit",
            "qiskit-terra",
            "qiskit-aer",
            "openfermion",
            "openfermionpyscf",
            "pyscf",
        )
    }
    body = {
        "schema": "aic-a100-pilot.cpu-reference-bundle.v1",
        "status": "FROZEN_LOCAL_CPU_REFERENCE",
        "protocol_digest": protocol["protocol_digest"],
        "source_baseline_commit": BASELINE_HEAD,
        "observed_branch": git("branch", "--show-current"),
        "observed_parent_commit": git("rev-parse", "HEAD", root=ROOT / "provenance/dvg-obs-ceo"),
        "observed_CEO_commit": git(
            "rev-parse", "HEAD", root=ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"
        ),
        "runtime": {
            "python_version": platform.python_version(),
            "implementation": platform.python_implementation().lower(),
            "system": platform.system().lower(),
            "machine": platform.machine().lower(),
            "byte_order": sys.byteorder,
            "packages": packages,
        },
        "cases": _build_cases(),
        "candidate_molecular_energy_evaluations": 0,
        "FCI_evaluations": 0,
        "protected_artifact_snapshot_after": tree_inventory_digest(PROTECTED_ROOTS),
    }
    if body["protected_artifact_snapshot_after"] != protocol["protected_artifact_snapshot"]:
        raise A100PilotError("protected artifacts changed during P0")
    return publish(REFERENCE, body, "reference_digest")


def verify() -> dict[str, Any]:
    protocol = load_json(PROTOCOL)
    reference = load_json(REFERENCE)
    checks = {
        "protocol_digest": embedded_digest_valid(protocol, "protocol_digest"),
        "reference_digest": embedded_digest_valid(reference, "reference_digest"),
        "protocol_reference_binding": reference.get("protocol_digest")
        == protocol.get("protocol_digest"),
        "five_cases_exact_order": [case.get("alias") for case in reference.get("cases", [])]
        == list(CASE_SPECS),
        "all_states_normalized": all(
            abs(struct.unpack(">d", bytes.fromhex(case["statevector_norm_float64_hex"]))[0] - 1.0)
            <= protocol["tolerances"]["phase_aligned_state_error_max"]
            for case in reference.get("cases", [])
        ),
        "no_candidate_or_fci_outcome": reference.get(
            "candidate_molecular_energy_evaluations"
        )
        == 0
        and reference.get("FCI_evaluations") == 0
        and all(case.get("candidate_outcomes_evaluated") == 0 for case in reference.get("cases", [])),
        "protected_artifacts_unchanged": tree_inventory_digest(PROTECTED_ROOTS)
        == protocol.get("protected_artifact_snapshot"),
        "submodules_pinned": reference.get("observed_parent_commit") == PARENT_COMMIT
        and reference.get("observed_CEO_commit") == CEO_COMMIT,
    }
    return {
        "decision": "GO_P1_AIC_PREFLIGHT" if all(checks.values()) else "NO_GO_P0_CPU_REFERENCE",
        "checks": checks,
        "protocol_digest": protocol.get("protocol_digest"),
        "reference_digest": reference.get("reference_digest"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-protocol", action="store_true")
    parser.add_argument("--build-reference", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--case", choices=tuple(CASE_SPECS))
    parser.add_argument("--case-output", type=Path)
    arguments = parser.parse_args()
    if arguments.case is not None:
        if arguments.case_output is None:
            raise A100PilotError("--case-output is required")
        record = build_case_reference(arguments.case)
        arguments.case_output.write_text(
            json.dumps(record, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return
    selected = sum((arguments.freeze_protocol, arguments.build_reference, arguments.verify))
    if selected != 1:
        raise A100PilotError("select exactly one P0 action")
    if arguments.freeze_protocol:
        result = freeze_protocol()
    elif arguments.build_reference:
        result = build_reference()
    else:
        result = verify()
    print(json.dumps(result, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
