"""Outcome-isolated, one-pass FCI references for the five frozen S11 cases."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .parent_native_development_runtime_factory_v1 import DEVELOPMENT_CASES
from .s0_successor import ROOT
from .s12_offline_reporting_gate_v1 import (
    EXPECTED_CASES,
    OUTPUT as S12_GATE,
    audit_frozen as audit_s12_gate_frozen,
    audit_live as audit_s12_gate_live,
)


SOURCE_CATALOG = (
    ROOT
    / "artifacts/v5-final/parent-native/s11-development-queue-v4"
    / "development-source-catalog-v1.json"
)
OUTPUT_DIR = ROOT / "artifacts/v5-final/parent-native/s12-offline-fci-reference-v1"
READINESS = OUTPUT_DIR / "offline-fci-execution-readiness-v1.json"
RESULT = OUTPUT_DIR / "offline-fci-reference-result-v1.json"
SOURCE_PATHS = (
    "src/v5_final/s12_offline_fci_reference_v1.py",
    "tests/test_v5_final_s12_offline_fci_reference_v1.py",
)
MINIMUM_FREE_BYTES = 40 * 1024**3
READINESS_DECISION = "GO_S12_EXACT_FIVE_CASE_OFFLINE_FCI_SINGLE_ATOMIC_PASS"
RESULT_STATUS = "S12_OFFLINE_FCI_REFERENCE_PASS_COMPLETE"


class S12OfflineFCIReferenceV1Error(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise S12OfflineFCIReferenceV1Error(f"expected JSON object: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _embedded_digest(value: Mapping[str, Any], field: str) -> bool:
    observed = value.get(field)
    body = {key: item for key, item in value.items() if key != field}
    return isinstance(observed, str) and observed == _digest(body)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def _package_versions() -> dict[str, str]:
    names = ("numpy", "scipy", "pyscf", "openfermion", "openfermionpyscf")
    return {name: importlib.metadata.version(name) for name in names}


def _case_bindings() -> list[dict[str, Any]]:
    catalog = _load(SOURCE_CATALOG)
    cases = list(catalog.get("cases", ()))
    if tuple(sorted(str(case.get("case_id")) for case in cases)) != EXPECTED_CASES:
        raise S12OfflineFCIReferenceV1Error("source catalog case set differs")
    bindings: list[dict[str, Any]] = []
    for case in sorted(cases, key=lambda value: str(value["case_id"])):
        case_id = str(case["case_id"])
        definition = DEVELOPMENT_CASES.get(case_id)
        if definition is None:
            raise S12OfflineFCIReferenceV1Error("unregistered frozen case")
        distance = float(definition["distance_angstrom"])
        expected_geometry = [
            [str(atom), [0.0, 0.0, distance * index]]
            for index, atom in enumerate(definition["atoms"])
        ]
        payload = case.get("problem_payload", {})
        if (
            payload.get("geometry_angstrom") != expected_geometry
            or payload.get("basis_set") != "sto-3g"
            or payload.get("hamiltonian_digest") != case.get("Hamiltonian_digest")
        ):
            raise S12OfflineFCIReferenceV1Error("case definition/catalog mismatch")
        bindings.append({
            "case_id": case_id,
            "ProblemID": case["ProblemID"],
            "Hamiltonian_digest": case["Hamiltonian_digest"],
            "problem_payload": payload,
        })
    return bindings


def build_readiness(base_head: str) -> dict[str, Any]:
    gate_audit = audit_s12_gate_frozen()
    gate = _load(S12_GATE)
    if gate_audit["decision"] != "GO_S12_OFFLINE_FCI_REPORTING_EXACT_FROZEN_CASES_ONLY":
        raise S12OfflineFCIReferenceV1Error("S12 reporting gate is not GO")
    artifact: dict[str, Any] = {
        "schema": "v5-final.s12-offline-fci-execution-readiness.v1",
        "decision": READINESS_DECISION,
        "base_head": base_head,
        "bindings": {
            "S12_gate_digest": gate["gate_digest"],
            "S12_gate_sha256": _sha(S12_GATE),
            "source_catalog_sha256": _sha(SOURCE_CATALOG),
            "source_sha256": {path: _sha(ROOT / path) for path in SOURCE_PATHS},
            "case_bindings": _case_bindings(),
        },
        "solver_contract": {
            "implementation": "openfermionpyscf.run_pyscf",
            "basis": "sto-3g",
            "run_scf": True,
            "run_fci": True,
            "run_mp2": False,
            "run_cisd": False,
            "run_ccsd": False,
            "thread_environment": {
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            },
            "package_versions": _package_versions(),
        },
        "execution_contract": {
            "case_ids": list(EXPECTED_CASES),
            "FCI_evaluations": 5,
            "publication": "all-five-results-in-memory-then-one-exclusive-atomic-JSON",
            "retry_after_published_result": "NOT_AUTHORIZED",
            "case_order_or_control_from_S11_outcomes": False,
            "candidate_energy": "NOT_AUTHORIZED",
            "optimizer": "NOT_AUTHORIZED",
            "S11_rerun": "NOT_AUTHORIZED",
            "aggregation": "NOT_AUTHORIZED_UNTIL_RESULT_AUDIT_SUCCESSOR",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    artifact["readiness_digest"] = _digest(artifact)
    return artifact


def capture_readiness() -> dict[str, Any]:
    if READINESS.exists() or RESULT.exists():
        raise S12OfflineFCIReferenceV1Error("S12 FCI artifact already exists")
    if _git("status", "--porcelain"):
        raise S12OfflineFCIReferenceV1Error("readiness capture requires clean worktree")
    artifact = build_readiness(_git("rev-parse", "HEAD"))
    write_json_exclusive(READINESS, artifact)
    return artifact


def audit_readiness(*, live: bool, require_result_absent: bool) -> dict[str, Any]:
    artifact = _load(READINESS)
    expected = build_readiness(str(artifact.get("base_head")))
    checks = {
        "schema_decision_exact": artifact.get("schema")
        == "v5-final.s12-offline-fci-execution-readiness.v1"
        and artifact.get("decision") == READINESS_DECISION,
        "readiness_digest_valid": _embedded_digest(artifact, "readiness_digest"),
        "frozen_bindings_current": artifact == expected,
        "readiness_is_immutable_git_blob": artifact_is_immutable_git_blob(READINESS),
        "exact_five_case_scope": tuple(artifact["execution_contract"]["case_ids"])
        == EXPECTED_CASES and artifact["execution_contract"]["FCI_evaluations"] == 5,
        "result_absence_contract": (not RESULT.exists()) if require_result_absent else True,
        "storage_at_least_40_GiB": shutil.disk_usage(ROOT).free >= MINIMUM_FREE_BYTES,
    }
    if live:
        branch = _git("branch", "--show-current")
        head = _git("rev-parse", "HEAD")
        checks.update({
            "S12_gate_live": all(audit_s12_gate_live()["checks"].values()),
            "base_head_is_ancestor": subprocess.run(
                ["git", "merge-base", "--is-ancestor", str(artifact["base_head"]), head],
                cwd=ROOT,
            ).returncode == 0,
            "local_remote_head_match": head == _git("rev-parse", f"origin/{branch}"),
            "worktree_clean": not _git("status", "--porcelain"),
            "submodules_clean": all(
                line.startswith(" ")
                for line in _git("submodule", "status", "--recursive").splitlines()
            ),
        })
    if not all(checks.values()):
        raise S12OfflineFCIReferenceV1Error(
            [name for name, passed in checks.items() if not passed]
        )
    return {"decision": READINESS_DECISION, "checks": checks,
            "readiness_digest": artifact["readiness_digest"]}


def _solve_case(binding: Mapping[str, Any]) -> dict[str, Any]:
    from openfermion import MolecularData
    from openfermionpyscf import run_pyscf
    from dvg_obs_ceo.baseline import _load_upstream
    from dvg_obs_ceo.molecular_identity import problem_spec

    case_id = str(binding["case_id"])
    definition = DEVELOPMENT_CASES[case_id]
    distance = float(definition["distance_angstrom"])
    geometry = [
        (str(atom), (0.0, 0.0, distance * index))
        for index, atom in enumerate(definition["atoms"])
    ]
    with tempfile.TemporaryDirectory(prefix="v5-s12-offline-fci-") as directory:
        molecule = MolecularData(
            geometry, "sto-3g", int(definition["multiplicity"]), 0,
            description=str(definition["description"]),
            filename=str(Path(directory) / case_id.replace(".", "_")),
        )
        molecule = run_pyscf(
            molecule, run_scf=True, run_mp2=False, run_cisd=False,
            run_ccsd=False, run_fci=True,
        )
        if molecule.fci_energy is None:
            raise S12OfflineFCIReferenceV1Error("FCI solver returned no energy")
        LinAlgAdapt, DVG_CEO, _, _ = _load_upstream()
        pool = DVG_CEO(molecule)
        algorithm = LinAlgAdapt(
            pool=pool, molecule=molecule, verbose=False, max_adapt_iter=100,
            max_opt_iter=10000, full_opt=True,
            threshold=float(definition["gradient_threshold"]),
            convergence_criterion="total_g_norm", tetris=True,
            progressive_opt=False, candidates=1, sel_criterion="gradient",
            recycle_hessian=True, penalize_cnots=False, rand_degenerate=False,
            shots=None,
        )
        problem = problem_spec(algorithm=algorithm, case_id=case_id)
        if (
            problem.problem_id != binding["ProblemID"]
            or problem.hamiltonian_digest != binding["Hamiltonian_digest"]
            or problem.payload() != binding["problem_payload"]
        ):
            raise S12OfflineFCIReferenceV1Error("reconstructed problem identity differs")
        energy = float(molecule.fci_energy)
        if not math.isfinite(energy):
            raise S12OfflineFCIReferenceV1Error("FCI energy is not finite")
        return {
            "case_id": case_id,
            "ProblemID": problem.problem_id,
            "Hamiltonian_digest": problem.hamiltonian_digest,
            "FCI_energy_hartree": energy,
            "FCI_evaluations": 1,
            "n_electrons": int(molecule.n_electrons),
            "n_spatial_orbitals": int(molecule.n_orbitals),
        }


def execute() -> dict[str, Any]:
    audit_readiness(live=True, require_result_absent=True)
    readiness = _load(READINESS)
    observed_threads = {
        name: os.environ.get(name)
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    }
    if observed_threads != readiness["solver_contract"]["thread_environment"]:
        raise S12OfflineFCIReferenceV1Error("thread environment differs from freeze")
    cases = [_solve_case(binding) for binding in readiness["bindings"]["case_bindings"]]
    if tuple(case["case_id"] for case in cases) != EXPECTED_CASES:
        raise S12OfflineFCIReferenceV1Error("solver case order differs")
    result: dict[str, Any] = {
        "schema": "v5-final.s12-offline-fci-reference-result.v1",
        "status": RESULT_STATUS,
        "bindings": {
            "readiness_digest": readiness["readiness_digest"],
            "readiness_sha256": _sha(READINESS),
            "S12_gate_digest": readiness["bindings"]["S12_gate_digest"],
            "source_catalog_sha256": readiness["bindings"]["source_catalog_sha256"],
        },
        "solver_contract": readiness["solver_contract"],
        "cases": cases,
        "counters": {
            "FCI_evaluations": 5,
            "candidate_energy_evaluations": 0,
            "optimizer_starts": 0,
            "S11_items_rerun": 0,
            "production_N_dense_expm": 0,
        },
        "control_inputs": "exact frozen case identities only; no S11 outcomes",
        "authorization_after_publication": {
            "FCI_reexecution": "NOT_AUTHORIZED",
            "aggregation": "NOT_AUTHORIZED_UNTIL_RESULT_AUDIT_SUCCESSOR",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    result["result_digest"] = _digest(result)
    write_json_exclusive(RESULT, result)
    return result


def audit_result() -> dict[str, Any]:
    readiness_audit = audit_readiness(live=False, require_result_absent=False)
    readiness = _load(READINESS)
    result = _load(RESULT)
    cases = list(result.get("cases", ()))
    checks = {
        "readiness_frozen_valid": all(readiness_audit["checks"].values()),
        "schema_status_exact": result.get("schema")
        == "v5-final.s12-offline-fci-reference-result.v1"
        and result.get("status") == RESULT_STATUS,
        "result_digest_valid": _embedded_digest(result, "result_digest"),
        "bindings_exact": result.get("bindings") == {
            "readiness_digest": readiness["readiness_digest"],
            "readiness_sha256": _sha(READINESS),
            "S12_gate_digest": readiness["bindings"]["S12_gate_digest"],
            "source_catalog_sha256": readiness["bindings"]["source_catalog_sha256"],
        },
        "exact_one_finite_FCI_per_case": tuple(case.get("case_id") for case in cases)
        == EXPECTED_CASES
        and len(cases) == 5
        and all(case.get("FCI_evaluations") == 1 for case in cases)
        and all(math.isfinite(float(case.get("FCI_energy_hartree"))) for case in cases),
        "problem_identities_exact": all(
            case["ProblemID"] == binding["ProblemID"]
            and case["Hamiltonian_digest"] == binding["Hamiltonian_digest"]
            for case, binding in zip(cases, readiness["bindings"]["case_bindings"])
        ),
        "counters_exact_and_firewalls_closed": result.get("counters") == {
            "FCI_evaluations": 5,
            "candidate_energy_evaluations": 0,
            "optimizer_starts": 0,
            "S11_items_rerun": 0,
            "production_N_dense_expm": 0,
        },
        "no_outcome_control": result.get("control_inputs")
        == "exact frozen case identities only; no S11 outcomes",
    }
    if not all(checks.values()):
        raise S12OfflineFCIReferenceV1Error(
            [name for name, passed in checks.items() if not passed]
        )
    return {"status": RESULT_STATUS, "checks": checks,
            "result_digest": result["result_digest"]}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--capture-readiness", action="store_true")
    actions.add_argument("--audit-live", action="store_true")
    actions.add_argument("--execute", action="store_true")
    actions.add_argument("--audit-result", action="store_true")
    args = parser.parse_args(argv)
    if args.capture_readiness:
        value = capture_readiness()
    elif args.audit_live:
        value = audit_readiness(live=True, require_result_absent=not RESULT.exists())
    elif args.execute:
        value = execute()
    elif args.audit_result:
        value = audit_result()
    else:
        value = audit_readiness(live=False, require_result_absent=not RESULT.exists())
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
