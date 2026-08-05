"""Independent static and identity audit for S2."""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from jsonschema import Draft202012Validator

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .s0_common import PARENT, ROOT, sha256


def _digest_without(value: dict[str, Any], field: str) -> str:
    content = dict(value)
    content.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


def audit() -> dict[str, Any]:
    path = ROOT / "artifacts/s2/stationary-source-protocol-v1.json"
    schema_path = ROOT / "schemas/s2-stationary-source-protocol-v1.schema.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_errors = list(Draft202012Validator(schema).iter_errors(value))
    cases = value["quantum_probe"]["cases"]
    identities = [case["identities"] for case in cases]
    checks = {
        "schema_valid": not schema_errors,
        "protocol_digest": value["protocol_digest"] == _digest_without(value, "protocol_digest"),
        "checkpoint_hashes": all(sha256(PARENT / case["checkpoint_path"]) == case["checkpoint_sha256"] for case in cases),
        "stationarity": all(case["parameter_gradient_infinity"] <= value["parameter_stationarity_threshold_infinity"] for case in cases),
        "finite_difference": all(case["finite_difference_max_absolute_difference"] <= value["finite_difference"]["agreement_tolerance"] for case in cases),
        "identity_unique": all(len({identity[field] for identity in identities}) == len(identities) for field in ("StatePreparationID", "ProblemID", "MeasurementContextID")),
        "measurement_not_in_state_identity": all("measurement_plan_version" not in identity["state_preparation_payload"] for identity in identities),
        "measurement_binds_state_and_problem": all(
            identity["measurement_context_payload"]["state_preparation_id"] == identity["StatePreparationID"]
            and identity["measurement_context_payload"]["problem_id"] == identity["ProblemID"]
            for identity in identities
        ),
        "pool_stop_separate": value["source_generation_contract"]["pool_gradient_stopping_stored_separately"] is True,
        "fci_firewall": value["source_generation_contract"]["fci_or_exact_reference_online"] is False,
        "s3_authorized": value["decision"] == "GO_S3" and value["next_stage_authorized"] == "S3",
    }
    failures = [name for name, passed in checks.items() if not passed]
    result: dict[str, Any] = {
        "schema": "v5-matched-work.s2-stationary-source-audit.v1",
        "stage": "S2",
        "passed": not failures,
        "checks": checks,
        "failed_checks": failures,
        "schema_errors": [error.message for error in schema_errors],
        "protocol_sha256": sha256(path),
        "claim_boundary": "Stationary-source protocol audit only; no compression outcome.",
    }
    result["audit_digest"] = _digest_without(result, "audit_digest")
    if failures:
        raise RuntimeError("S2 audit failed: " + ", ".join(failures))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    output = ROOT / "artifacts/s2/stationary-source-audit-v1.json"
    result = audit()
    if arguments.verify_only:
        if output.read_bytes() != canonical_json_bytes(result):
            raise RuntimeError("committed S2 audit differs from reconstruction")
    else:
        write_json_exclusive(output, result)
    print(json.dumps({"passed": result["passed"], "checks": len(result["checks"])}, sort_keys=True))


if __name__ == "__main__":
    main()
