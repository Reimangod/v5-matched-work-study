"""One-shot BeH2 diagnostic under unchanged v2 numerics after H6 failed.

This runner intentionally does not turn the H6 failure into a passing
predecessor.  It binds the complete terminal prefix, calls the unchanged v2
numerical implementation, and relabels the output as post-failure diagnostic
evidence that cannot authorize production adoption or performance claims.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from v5_matched_work.atomic_artifacts import write_json_exclusive

from .common import (
    A100PilotError,
    digest,
    embedded_digest_valid,
    load_json,
    publish,
    sha256_file,
)
from .stable_control_v2_contract import CONTRACT as V2_CONTRACT
from .stable_control_v2_h6_no_go import (
    EXPECTED_FAILED_CHECKS,
    EXPECTED_H6_RESULT_SHA256,
    NO_GO,
)
from .stable_control_v2_postfailure_contract import CONTRACT
from . import stable_control_v2_route as v2_route


EXPECTED_PREFIX_SHA256 = {
    "h2": "5058b7e972423fdab976578c985aeae5a8f87df57b5953b97cc676a8dbef0d79",
    "h4": "e92bce9f465fd80c9c67632b3a11b930b85ce78965cd3eaee048e4a38d6b73dc",
    "lih": "ba2d4ca190d94edca6613ee6c32b39d09d47deb31f78f03ae0e0807ad0f5bc2d",
    "h6": EXPECTED_H6_RESULT_SHA256,
}
EXPECTED_PREFIX_STATUS = {"h2": "PASS", "h4": "PASS", "lih": "PASS", "h6": "FAIL"}


def _terminal_prefix(
    alias: str,
    source_results: Path,
    numerical_contract: Mapping[str, Any],
    successor_contract: Mapping[str, Any],
) -> list[dict[str, str]]:
    if alias != "beh2":
        raise A100PilotError("post-failure runner authorizes only BeH2")
    no_go = load_json(NO_GO)
    if not embedded_digest_valid(no_go, "incident_digest"):
        raise A100PilotError("H6 No-Go digest is invalid")
    if no_go["incident_digest"] != successor_contract["predecessor_binding"][
        "H6_no_go"
    ]["incident_digest"]:
        raise A100PilotError("successor contract does not bind the H6 No-Go")
    evidence: list[dict[str, str]] = []
    for predecessor in ("h2", "h4", "lih", "h6"):
        path = source_results / f"{predecessor}.json"
        if not path.is_file():
            raise A100PilotError(f"missing terminal predecessor: {predecessor}")
        if sha256_file(path) != EXPECTED_PREFIX_SHA256[predecessor]:
            raise A100PilotError(f"terminal predecessor SHA differs: {predecessor}")
        value = load_json(path)
        if not embedded_digest_valid(value, "record_digest"):
            raise A100PilotError(f"terminal predecessor digest invalid: {predecessor}")
        if value.get("status") != EXPECTED_PREFIX_STATUS[predecessor]:
            raise A100PilotError(f"terminal predecessor status differs: {predecessor}")
        if value.get("contract_digest") != numerical_contract["contract_digest"]:
            raise A100PilotError(f"terminal predecessor contract differs: {predecessor}")
        if predecessor == "h6":
            failed = {key for key, passed in value["checks"].items() if not passed}
            if failed != EXPECTED_FAILED_CHECKS:
                raise A100PilotError("H6 failure identity differs")
        evidence.append(
            {
                "alias": predecessor,
                "status": value["status"],
                "record_digest": value["record_digest"],
                "sha256": sha256_file(path),
            }
        )
    return evidence


def _start_body(contract: Mapping[str, Any], output: Path) -> dict[str, Any]:
    return {
        "schema": "aic-a100-pilot.stable-control-v2-postfailure-start.v1",
        "status": "STARTED_NO_TERMINAL_DIAGNOSTIC",
        "alias": "beh2",
        "contract_digest": contract["contract_digest"],
        "expected_git_head": os.environ.get("A100_EXPECTED_HEAD"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "node": os.environ.get("SLURMD_NODENAME"),
        "output_name": output.name,
        "candidate_outcomes_before_start_record": 0,
        "FCI_evaluations_before_start_record": 0,
        "existing_90_item_execution": "UNCHANGED",
        "performance_claim": "NOT_AUTHORIZED",
    }


def _publish_incident(
    *,
    path: Path,
    contract: Mapping[str, Any],
    start: Mapping[str, Any],
    stage: str,
    error: Exception,
    capture: Mapping[str, Any],
) -> dict[str, Any]:
    return publish(
        path,
        {
            "schema": "aic-a100-pilot.stable-control-v2-postfailure-incident.v1",
            "status": "FAILED_ENGINEERING_PRESERVED",
            "alias": "beh2",
            "contract_digest": contract["contract_digest"],
            "attempt_start_digest": start["start_digest"],
            "stage": stage,
            "exception": {
                "type": f"{type(error).__module__}.{type(error).__name__}",
                "message": str(error),
            },
            "partial_execution": {
                side: v2_route._kernel_snapshot(capture.get(f"{side}_kernel"))
                for side in ("cpu", "gpu")
            },
            "scientific_boundary": {
                "partial_values_eligible_for_parity_or_performance_claim": False,
                "retry_in_same_namespace": "NOT_AUTHORIZED",
                "FCI_evaluations": 0,
                "existing_90_item_execution": "UNCHANGED",
                "performance_claim": "NOT_AUTHORIZED",
            },
        },
        "incident_digest",
    )


def run_diagnostic(
    *,
    prepared_bundle: Path,
    prepared_manifest: Path,
    source_results: Path,
    start: Mapping[str, Any],
    capture: MutableMapping[str, Any],
) -> dict[str, Any]:
    successor = load_json(CONTRACT)
    numerical = load_json(V2_CONTRACT)
    if not embedded_digest_valid(successor, "contract_digest"):
        raise A100PilotError("post-failure contract digest is invalid")
    if not embedded_digest_valid(numerical, "contract_digest"):
        raise A100PilotError("v2 numerical contract digest is invalid")
    if successor["predecessor_binding"]["stable_control_v2_contract"][
        "contract_digest"
    ] != numerical["contract_digest"]:
        raise A100PilotError("post-failure numerical contract binding differs")

    original = v2_route._require_predecessors

    def registered_prefix(alias: str, output_dir: Path, contract: Mapping[str, Any]):
        del output_dir
        return _terminal_prefix(alias, source_results, contract, successor)

    v2_route._require_predecessors = registered_prefix
    try:
        base = v2_route._run_case_impl(
            "beh2",
            output_dir=source_results,
            prepared_bundle=prepared_bundle,
            prepared_manifest=prepared_manifest,
            contract=numerical,
            start_record=start,
            capture=capture,
        )
    finally:
        v2_route._require_predecessors = original

    base_digest = base.pop("record_digest")
    base_status = base.pop("status")
    predecessor_check = base["checks"].pop("predecessor_prefix_passed")
    if not predecessor_check:
        raise A100PilotError("registered terminal prefix was not observed")
    base["checks"]["registered_postfailure_terminal_prefix"] = True
    base["schema"] = (
        "aic-a100-pilot.stable-control-v2-postfailure-diagnostic-case.v1"
    )
    base["status"] = (
        "DIAGNOSTIC_PASS" if all(base["checks"].values()) else "DIAGNOSTIC_FAIL"
    )
    base["contract_digest"] = successor["contract_digest"]
    base["numerical_contract_digest"] = numerical["contract_digest"]
    base["base_v2_record_digest_before_policy_relabel"] = base_digest
    base["base_v2_status_before_policy_relabel"] = base_status
    base["execution_policy"] = {
        "scope": "ONE_BEH2_POST_FAILURE_DIAGNOSTIC_ONLY",
        "H6_failure_was_not_reclassified_as_PASS": True,
        "H6_retry_performed": False,
        "BeH2_is_independent_confirmation": False,
        "threshold_or_numerics_changed": False,
    }
    base["scientific_boundary"].update(
        {
            "complete_item_speed_claim": "NOT_AUTHORIZED",
            "A100_production_adoption": "NOT_AUTHORIZED",
            "V5_performance_claim": "NOT_AUTHORIZED",
            "BeH2_independent_confirmation_claim": "NOT_AUTHORIZED",
        }
    )
    base["record_digest"] = digest(base)
    return base


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared-bundle", type=Path, required=True)
    parser.add_argument("--prepared-manifest", type=Path, required=True)
    parser.add_argument("--source-results", type=Path, required=True)
    parser.add_argument("--start-record", type=Path, required=True)
    parser.add_argument("--incident", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    protected = (arguments.start_record, arguments.incident, arguments.output)
    existing = [path for path in protected if path.exists()]
    if existing:
        raise RuntimeError(f"refusing to overwrite diagnostic evidence: {existing}")
    contract = load_json(CONTRACT)
    if not embedded_digest_valid(contract, "contract_digest"):
        raise A100PilotError("post-failure contract digest is invalid")
    start = publish(
        arguments.start_record,
        _start_body(contract, arguments.output),
        "start_digest",
    )
    capture: dict[str, Any] = {"stage": "preflight"}
    try:
        result = run_diagnostic(
            prepared_bundle=arguments.prepared_bundle,
            prepared_manifest=arguments.prepared_manifest,
            source_results=arguments.source_results,
            start=start,
            capture=capture,
        )
        write_json_exclusive(arguments.output, result)
    except Exception as error:
        _publish_incident(
            path=arguments.incident,
            contract=contract,
            start=start,
            stage=str(capture.get("stage", "unknown")),
            error=error,
            capture=capture,
        )
        raise
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "DIAGNOSTIC_PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
