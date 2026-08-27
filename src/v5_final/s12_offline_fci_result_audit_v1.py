"""Append-only audit successor for the single published S12 FCI result."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .historical_artifact_audit import artifact_is_immutable_git_blob
from .s0_successor import ROOT
from .s11_v2_execution_readiness_v4 import _digest, _embedded_digest, _git, _load, _sha
from .s12_offline_fci_reference_v1 import (
    EXPECTED_CASES,
    READINESS,
    RESULT,
    RESULT_STATUS,
    _case_bindings,
    audit_result,
)
from .s12_offline_reporting_gate_v1 import (
    OUTPUT as REPORTING_GATE,
    audit_frozen as audit_reporting_gate,
    inspect_completion,
)


OUTPUT = RESULT.parent / "offline-fci-result-audit-pass-v1.json"
DECISION = "PASS_S12_OFFLINE_FCI_RESULT_AUDIT_AGGREGATION_REMAINS_CLOSED"
SOURCE_PATHS = (
    "src/v5_final/s12_offline_fci_result_audit_v1.py",
    "tests/test_v5_final_s12_offline_fci_result_audit_v1.py",
)
RESULT_RELATIVE = str(RESULT.relative_to(ROOT))


class S12OfflineFCIResultAuditV1Error(RuntimeError):
    pass


def _git_lines(*args: str) -> list[str]:
    output = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.rstrip("\r\n")
    return [] if not output else output.splitlines()


def _result_commit_evidence() -> dict[str, Any]:
    commits = _git_lines("log", "--format=%H", "--", RESULT_RELATIVE)
    if len(commits) != 1:
        raise S12OfflineFCIResultAuditV1Error("result must have exactly one Git commit")
    commit = commits[0]
    changed_paths = _git_lines(
        "diff-tree", "--no-commit-id", "--name-only", "-r", commit
    )
    parent_has_result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^:{RESULT_RELATIVE}"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0
    return {
        "commit": commit,
        "commit_changed_paths": changed_paths,
        "result_is_only_path_in_commit": changed_paths == [RESULT_RELATIVE],
        "parent_had_no_result": not parent_has_result,
        "git_blob_oid": _git("hash-object", RESULT_RELATIVE),
    }


def inspect_result() -> dict[str, Any]:
    readiness = _load(READINESS)
    result = _load(RESULT)
    reporting = _load(REPORTING_GATE)
    result_audit = audit_result()
    reporting_audit = audit_reporting_gate()
    completion = inspect_completion()
    cases = list(result.get("cases", ()))
    frozen_bindings = list(readiness["bindings"]["case_bindings"])
    expected_bindings = _case_bindings()
    commit_evidence = _result_commit_evidence()
    raw = RESULT.read_bytes()
    payload_keys = {
        "geometry_angstrom", "basis_set", "active_space", "frozen_orbitals",
        "fermion_to_qubit_mapping_convention", "hamiltonian_digest", "molecule",
    }
    expected_counters = {
        "FCI_evaluations": 5,
        "candidate_energy_evaluations": 0,
        "optimizer_starts": 0,
        "S11_items_rerun": 0,
        "production_N_dense_expm": 0,
    }
    exact_authorization = {
        "FCI_reexecution": "NOT_AUTHORIZED",
        "aggregation": "NOT_AUTHORIZED_UNTIL_RESULT_AUDIT_SUCCESSOR",
        "performance_claim": "NOT_AUTHORIZED",
    }
    checks = {
        "reference_result_audit_all_pass": all(result_audit["checks"].values()),
        "reporting_gate_frozen_all_pass": all(reporting_audit["checks"].values()),
        "schema_status_and_digest_exact": result.get("schema")
        == "v5-final.s12-offline-fci-reference-result.v1"
        and result.get("status") == RESULT_STATUS
        and _embedded_digest(result, "result_digest"),
        "canonical_json_bytes_exact": raw == canonical_json_bytes(result),
        "result_is_immutable_git_blob": artifact_is_immutable_git_blob(RESULT),
        "atomic_single_commit_publication": commit_evidence[
            "result_is_only_path_in_commit"
        ] and commit_evidence["parent_had_no_result"],
        "case_order_and_count_exact": len(cases) == 5
        and tuple(case.get("case_id") for case in cases) == EXPECTED_CASES,
        "problem_and_hamiltonian_identity_exact": all(
            case.get("ProblemID") == binding.get("ProblemID")
            and case.get("Hamiltonian_digest") == binding.get("Hamiltonian_digest")
            for case, binding in zip(cases, frozen_bindings)
        ),
        "problem_payload_bindings_exact": frozen_bindings == expected_bindings
        and all(
            set(binding.get("problem_payload", {})) == payload_keys
            and binding["problem_payload"]["basis_set"] == "sto-3g"
            and isinstance(binding["problem_payload"]["geometry_angstrom"], list)
            and isinstance(binding["problem_payload"]["active_space"], list)
            and binding["problem_payload"]["fermion_to_qubit_mapping_convention"]
            == "openfermion-jordan-wigner-v1"
            for binding in frozen_bindings
        ),
        "solver_and_package_contract_exact": result.get("solver_contract")
        == readiness.get("solver_contract"),
        "readiness_binding_exact": result.get("bindings", {}).get(
            "readiness_digest"
        ) == readiness.get("readiness_digest")
        and result.get("bindings", {}).get("readiness_sha256") == _sha(READINESS),
        "exact_one_finite_FCI_per_case": all(
            case.get("FCI_evaluations") == 1
            and math.isfinite(float(case.get("FCI_energy_hartree")))
            for case in cases
        ),
        "counters_and_firewalls_exact": result.get("counters") == expected_counters
        and result.get("authorization_after_publication") == exact_authorization,
        "outcome_independent_control_exact": result.get("control_inputs")
        == "exact frozen case identities only; no S11 outcomes"
        and readiness["execution_contract"]["case_order_or_control_from_S11_outcomes"]
        is False
        and reporting["frozen_reporting_scope"][
            "candidate_outcomes_used_to_select_cases"
        ] is False,
        "S11_manifests_and_counts_unchanged": all(
            completion["bindings"].get(name) == reporting["bindings"].get(name)
            for name in (
                "result_manifest_digest", "receipt_manifest_digest",
                "production_manifest_digest",
            )
        )
        and completion["observed"]["terminal_count"] == 90
        and completion["observed"]["FCI_evaluations"] == 0
        and completion["observed"]["N_dense_expm"] == 0,
        "aggregation_still_closed": result["authorization_after_publication"][
            "aggregation"
        ] == "NOT_AUTHORIZED_UNTIL_RESULT_AUDIT_SUCCESSOR",
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise S12OfflineFCIResultAuditV1Error(failures)
    return {
        "checks": checks,
        "observed": {
            "case_ids": [case["case_id"] for case in cases],
            "FCI_energies_hartree": {
                case["case_id"]: case["FCI_energy_hartree"] for case in cases
            },
            "counters": result["counters"],
            "terminal_status_counts": completion["observed"][
                "terminal_status_counts"
            ],
        },
        "bindings": {
            "result_path": RESULT_RELATIVE,
            "result_sha256": hashlib.sha256(raw).hexdigest(),
            "result_digest": result["result_digest"],
            "readiness_sha256": _sha(READINESS),
            "readiness_digest": readiness["readiness_digest"],
            "reporting_gate_sha256": _sha(REPORTING_GATE),
            "reporting_gate_digest": reporting["gate_digest"],
            "S11_result_manifest_digest": completion["bindings"][
                "result_manifest_digest"
            ],
            "S11_receipt_manifest_digest": completion["bindings"][
                "receipt_manifest_digest"
            ],
            "S11_production_manifest_digest": completion["bindings"][
                "production_manifest_digest"
            ],
            "result_commit_evidence": commit_evidence,
            "source_sha256": {path: _sha(ROOT / path) for path in SOURCE_PATHS},
        },
    }


def build_artifact(base_head: str) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "schema": "v5-final.s12-offline-fci-result-audit.v1",
        "stage": "S12_OFFLINE_FCI_RESULT_AUDIT",
        "status": DECISION,
        "decision": DECISION,
        "base_head_with_atomic_result": base_head,
        **inspect_result(),
        "authorization": {
            "result_audit": "COMPLETE",
            "aggregation_gate_creation": "AUTHORIZED",
            "aggregation": "NOT_AUTHORIZED_UNTIL_SEPARATE_GATE",
            "S11_rerun": "NOT_AUTHORIZED",
            "FCI_reexecution": "NOT_AUTHORIZED",
            "candidate_reselection": "NOT_AUTHORIZED",
            "threshold_or_method_change": "NOT_AUTHORIZED",
            "case_exclusion_from_outcomes": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "scientific_boundary": {
            "supported": (
                "Exactly one offline FCI reference was atomically published for each "
                "of the five case identities frozen before S11 outcomes."
            ),
            "not_yet_supported": (
                "Any matched-work performance, Pareto, or superiority claim."
            ),
        },
    }
    artifact["audit_digest"] = _digest(artifact)
    return artifact


def capture() -> dict[str, Any]:
    if OUTPUT.exists():
        raise S12OfflineFCIResultAuditV1Error("result-audit artifact already exists")
    dirty = _git("status", "--porcelain").splitlines()
    if {line[3:] for line in dirty} != set(SOURCE_PATHS) or any(
        not line.startswith("?? ") for line in dirty
    ):
        raise S12OfflineFCIResultAuditV1Error(
            "capture permits only the new result-audit source and test"
        )
    artifact = build_artifact(_git("rev-parse", "HEAD"))
    write_json_exclusive(OUTPUT, artifact)
    return artifact


def audit_frozen() -> dict[str, Any]:
    artifact = _load(OUTPUT)
    live = inspect_result()
    checks = {
        "schema_decision_exact": artifact.get("schema")
        == "v5-final.s12-offline-fci-result-audit.v1"
        and artifact.get("decision") == DECISION
        and artifact.get("status") == DECISION,
        "audit_digest_valid": _embedded_digest(artifact, "audit_digest"),
        "all_captured_and_live_checks_pass": all(artifact.get("checks", {}).values())
        and all(live["checks"].values()),
        "bindings_current": artifact.get("bindings") == live["bindings"],
        "observations_current": artifact.get("observed") == live["observed"],
        "artifact_is_immutable_git_blob": artifact_is_immutable_git_blob(OUTPUT),
        "authorization_exact": artifact.get("authorization") == {
            "result_audit": "COMPLETE",
            "aggregation_gate_creation": "AUTHORIZED",
            "aggregation": "NOT_AUTHORIZED_UNTIL_SEPARATE_GATE",
            "S11_rerun": "NOT_AUTHORIZED",
            "FCI_reexecution": "NOT_AUTHORIZED",
            "candidate_reselection": "NOT_AUTHORIZED",
            "threshold_or_method_change": "NOT_AUTHORIZED",
            "case_exclusion_from_outcomes": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
    }
    if not all(checks.values()):
        raise S12OfflineFCIResultAuditV1Error(
            [name for name, passed in checks.items() if not passed]
        )
    return {
        "decision": DECISION,
        "checks": checks,
        "audit_digest": artifact["audit_digest"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args(argv)
    value = capture() if args.capture else audit_frozen()
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
