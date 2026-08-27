"""Build the outcome-free MB5.2 runtime-binding audit artifact."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .mb5_1_production_backend_audit import fixture as fixture_v1
from .production_backends.common import CapRejected, WORK_COMPONENTS, digest
from .production_backends_v2 import ENTRYPOINTS_V2
from .production_backends_v2.common import PersistentBoundaryRecorderV2, validate_request_v2
from .production_kernel_bindings_v2 import FakeBehavioralKernelBindings
from .s0_successor import CEO_COMMIT, LOCK_SHA256, PARENT_COMMIT, ROOT


OUTPUT = ROOT / "artifacts/v5-final/method-native/mb5-2-actual-production-bindings-v1.json"
P0 = ROOT / "artifacts/v5-final/pre-execution/p0-capacity-success-v2.json"
DEVELOPMENT_QUEUE = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
DEVELOPMENT_LEDGER = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"
PARENT_PYTHON = ROOT / "provenance/dvg-obs-ceo/.venv/bin/python"

BUNDLE_FILES = (
    "src/v5_final/production_kernel_bindings_v2.py",
    "src/v5_final/production_import_probe_v2.py",
    "src/v5_final/actual_binding_nonmolecular_probe_v2.py",
    "src/v5_final/production_backends_v2/common.py",
    "src/v5_final/production_backends_v2/immutable_source.py",
    "src/v5_final/production_backends_v2/same_structure.py",
    "src/v5_final/production_backends_v2/magnitude_control.py",
    "src/v5_final/production_backends_v2/v4_1_one_shot.py",
    "src/v5_final/production_backends_v2/v5_fixed_whitelist.py",
    "src/v5_final/production_backends_v2/v5_replenishing.py",
    "src/v5_final/production_backends_v2/__init__.py",
    "src/v5_final/live_semantic_ledger.py",
    "uv.lock",
    "provenance/dvg-obs-ceo/uv.lock",
)


class MB52AuditError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _fixture(method_id: str, **updates: Any) -> dict[str, Any]:
    request = fixture_v1(method_id)
    request["schema"] = "v5-final.mb5-2-production-backend-request.v1"
    request["qubit_count"] = 4
    request["maximum_optimizer_iterations"] = 1
    request.update(updates)
    request["request_digest"] = digest(
        {key: value for key, value in request.items() if key != "request_digest"}
    )
    return request


def _parent_probe(module: str) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(ROOT / "src"),
            str(ROOT / "provenance/dvg-obs-ceo/src"),
            str(ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"),
        )
    )
    completed = subprocess.run(
        [str(PARENT_PYTHON), "-m", module],
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout)


def _entrypoint_identities() -> dict[str, Any]:
    identities: dict[str, Any] = {}
    for method_id, entrypoint in ENTRYPOINTS_V2.items():
        source = Path(inspect.getsourcefile(entrypoint) or "").resolve()
        if source.parent != (ROOT / "src/v5_final/production_backends_v2").resolve():
            raise MB52AuditError("entrypoint is outside successor package")
        module = importlib.import_module(entrypoint.__module__)
        identity = {
            "qualified_entrypoint": f"{entrypoint.__module__}:{entrypoint.__name__}",
            "source_path": str(source.relative_to(ROOT)),
            "source_sha256": _sha(source),
            "callable": callable(entrypoint),
            "module_imported": module is not None,
        }
        identity["executor_id"] = "method-native-production-executor-v2:" + digest(identity)
        identities[method_id] = identity
    return identities


def _behavioral_evidence() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        results = {
            method_id: entrypoint(
                _fixture(method_id), ledger_path=root / f"{index:02d}-{method_id}.jsonl"
            )
            for index, (method_id, entrypoint) in enumerate(ENTRYPOINTS_V2.items())
        }

        failed = ENTRYPOINTS_V2["same-structure-reoptimization"](
            _fixture(
                "same-structure-reoptimization",
                fake_fail_operation="candidate-energy-evaluation",
            ),
            ledger_path=root / "failed.jsonl",
        )

        cap_request = _fixture("immutable-ceo-star-source")
        cap_request["componentwise_work_cap"]["resource_recounts"] = 0
        cap_request["work_cap_digest"] = digest(cap_request["componentwise_work_cap"])
        cap_request["request_digest"] = digest(
            {key: value for key, value in cap_request.items() if key != "request_digest"}
        )
        cap_bound = validate_request_v2(cap_request, "immutable-ceo-star-source")
        cap_recorder = PersistentBoundaryRecorderV2(
            cap_bound, "v5_final.mb5_2.cap_probe", root / "cap.jsonl"
        )
        called = False

        def forbidden_call() -> None:
            nonlocal called
            called = True

        try:
            cap_recorder.invoke("full-physical-resource-recount", forbidden_call)
        except CapRejected:
            pass
        else:
            raise MB52AuditError("cap probe did not reject")

        hvp_bound = validate_request_v2(
            _fixture("same-structure-reoptimization"),
            "same-structure-reoptimization",
        )
        hvp_recorder = PersistentBoundaryRecorderV2(
            hvp_bound, "v5_final.mb5_2.hvp_probe", root / "hvp.jsonl"
        )
        hvp_binding = FakeBehavioralKernelBindings(recorder=hvp_recorder, catalog=[])
        hvp_binding.hessian_vector_product([0.1, 0.2], [0.0, 0.1], [1, 2])

        return {
            "method_results": results,
            "failed_call_probe": failed,
            "cap_probe": {
                "call_executed": called,
                "events": cap_recorder.events,
                "raw_work_total": cap_recorder.total,
            },
            "hvp_probe": {
                "trace": hvp_binding.trace,
                "raw_work_total": hvp_recorder.total,
                "events": hvp_recorder.events,
            },
        }


def build() -> dict[str, Any]:
    p0 = _json(P0)
    development_queue = _json(DEVELOPMENT_QUEUE)
    development_ledger = _json(DEVELOPMENT_LEDGER)
    identities = _entrypoint_identities()
    behavior = _behavioral_evidence()
    api = _parent_probe("v5_final.production_import_probe_v2")
    actual_probe = _parent_probe("v5_final.actual_binding_nonmolecular_probe_v2")
    bundle_files = {path: _sha(ROOT / path) for path in BUNDLE_FILES}
    bundle = {
        "files": bundle_files,
        "parent_API_manifest": api,
        "parent_commit": PARENT_COMMIT,
        "CEO_commit": CEO_COMMIT,
        "dependency_lock_sha256": LOCK_SHA256,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "parent_python": api["python"],
        },
    }
    bundle_digest = digest(bundle)
    traces = {
        method_id: [record["operation"] for record in result["binding_runtime_trace"]]
        for method_id, result in behavior["method_results"].items()
    }
    checks = {
        "P0_v2_capacity_success": p0["decision"] == "GO_MB5_2_ACTUAL_BINDING_IMPLEMENTATION_ONLY",
        "six_distinct_entrypoints": len(identities) == 6
        and len({record["source_path"] for record in identities.values()}) == 6,
        "six_runtime_behavioral_traces": len(traces) == 6
        and all(traces.values()),
        "six_control_flows_distinct": len({tuple(trace) for trace in traces.values()}) == 6,
        "actual_binding_constructed_and_called": actual_probe["binding_kind"]
        == "PINNED_ACTUAL_CEO_DVG_KERNELS"
        and actual_probe["raw_work_total"]["resource_recounts"] == 1,
        "actual_parent_APIs_imported": all(record["callable"] for record in api["APIs"].values()),
        "cap_precheck_before_call": behavior["cap_probe"]["call_executed"] is False
        and behavior["cap_probe"]["events"][-1]["outcome"] == "rejected",
        "failed_call_persistent": any(
            event["outcome"] == "failed"
            for event in behavior["failed_call_probe"]["raw_boundary_events"]
        ),
        "failed_work_retained": behavior["failed_call_probe"]["raw_work_total"]["energy_evaluations"] == 1,
        "rollback_exact": behavior["failed_call_probe"]["rollback_record"]["exact"] is True,
        "optimizer_counted": behavior["method_results"]["same-structure-reoptimization"]["raw_work_total"]["optimizer_starts"] == 1
        and behavior["method_results"]["same-structure-reoptimization"]["raw_work_total"]["optimizer_iterations"] == 1,
        "HVP_and_internal_gradients_counted": behavior["hvp_probe"]["raw_work_total"]["hvp_evaluations"] == 1
        and behavior["hvp_probe"]["raw_work_total"]["gradient_vector_evaluations"] == 2
        and behavior["hvp_probe"]["raw_work_total"]["gradient_component_equivalents"] == 4,
        "magnitude_physical_deletion": behavior["method_results"]["structural-magnitude-pruning"]["method_evidence"]["physical_generator_deleted"] is True
        and behavior["method_results"]["structural-magnitude-pruning"]["method_evidence"]["coefficient_zeroing_only"] is False,
        "magnitude_zero_reduction_not_success": behavior["method_results"]["structural-magnitude-pruning"]["method_evidence"]["zero_resource_reduction_is_success"] is False,
        "V4_1_frozen_sentinel_only": behavior["method_results"]["v4.1-one-shot-joint-compression"]["method_evidence"]["frozen_sentinel_only"] is True,
        "fixed_whitelist_no_replenishment": behavior["method_results"]["v5-fixed-source-whitelist-no-replenishment"]["method_evidence"]["runtime_new_candidates_admitted"] is False,
        "full_V5_child_replenishment": behavior["method_results"]["v5-sequential-with-rebuilding"]["method_evidence"]["catalog_calls"] == 2,
        "semantic_dedup_key": behavior["method_results"]["v5-sequential-with-rebuilding"]["method_evidence"]["deduplication_key"] == "ProposedPhysicalStateID",
        "candidate_energy_zero": all(result["scientific_candidate_energy_evaluations"] == 0 for result in behavior["method_results"].values())
        and actual_probe["candidate_energy_evaluations"] == 0,
        "development_queue_untouched": development_queue["expected_queue_count"] == 90
        and len(development_ledger["segments"]) == 0
        and development_ledger["development_candidate_energy_evaluations"] == 0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    decision = "GO_MB6_V2_OUTCOME_BLIND_REFREEZE_ONLY" if not failures else "NO_GO_MB5_2_RUNTIME_BINDING_AUDIT"
    artifact: dict[str, Any] = {
        "schema": "v5-final.mb5-2-actual-production-binding-audit.v1",
        "stage": "R1_MB5_2_ACTUAL_PRODUCTION_BINDING",
        "status": "PASS" if not failures else "FAIL_CLOSED",
        "decision": decision,
        "successor_of": "artifacts/v5-final/method-native/mb5-1-production-backends-v3.json",
        "P0_capacity_success_sha256": _sha(P0),
        "executor_identities": identities,
        "implementation_bundle": bundle,
        "implementation_bundle_digest": bundle_digest,
        "runtime_behavioral_evidence": behavior,
        "actual_nonmolecular_binding_probe": actual_probe,
        "runtime_trace_operations": traces,
        "checks": checks,
        "failures": failures,
        "scientific_state": {
            "candidate_molecular_energy_evaluations": 0,
            "H2_H4_terminal_items": 0,
            "development_terminal_items": 0,
            "performance_claim": "NOT_AUTHORIZED",
        },
        "authorization": {
            "MB6_v2_outcome_blind_refreeze": "AUTHORIZED" if not failures else "NOT_AUTHORIZED",
            "H2_H4_execution": "NOT_AUTHORIZED",
            "development_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": (
            "Actual pinned callability and nonmolecular resource recount plus synthetic behavioral "
            "traces only. Fake values are not molecular outcomes or performance evidence."
        ),
    }
    artifact["audit_digest"] = digest(artifact)
    return artifact


def verify(record: dict[str, Any]) -> dict[str, bool]:
    body = dict(record)
    observed = body.pop("audit_digest", None)
    return {
        "audit_digest_valid": observed == digest(body),
        "bundle_files_unchanged": record["implementation_bundle"]["files"]
        == {path: _sha(ROOT / path) for path in BUNDLE_FILES},
        "bundle_digest_valid": record["implementation_bundle_digest"]
        == digest(record["implementation_bundle"]),
        "all_checks_passed": all(record["checks"].values()),
        "decision_is_scoped_GO": record["decision"]
        == "GO_MB6_V2_OUTCOME_BLIND_REFREEZE_ONLY",
        "candidate_energy_zero": record["scientific_state"]["candidate_molecular_energy_evaluations"] == 0,
    }


def audit() -> dict[str, bool]:
    checks = verify(_json(OUTPUT))
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise MB52AuditError("MB5.2 committed audit failed: " + ", ".join(failures))
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
