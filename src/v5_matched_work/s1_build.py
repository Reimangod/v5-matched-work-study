"""Replay historical V5 evidence and build the versioned S1 correctness view."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .s0_common import PARENT, PARENT_COMMIT, ROOT, git, sha256
from .s1_correctness import GRADIENT_FIELD_DICTIONARY, accepted_pareto_frontier, risk_semantics


S9_SUMMARY = PARENT / "artifacts/v5/s9/summary-v1.json"
ERRATA = PARENT / "artifacts/v5/release/correctness-errata-v1.json"
RELEASE_SUMMARY = PARENT / "artifacts/v5/release/summary-v1.json"


def _digest_without(record: dict[str, Any], field: str) -> str:
    payload = dict(record)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.update(
        {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    )
    return subprocess.run(
        command,
        cwd=PARENT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def historical_replay(*, full_regression: bool) -> dict[str, Any]:
    python = PARENT / ".venv" / "bin" / "python"
    if not python.is_file():
        raise RuntimeError("historical venv is absent; run uv sync --extra baseline --extra test")
    release = _run([str(python), "-m", "dvg_obs_ceo.v5_release_audit"])
    if release.returncode != 0:
        raise RuntimeError("historical V5 release audit failed: " + release.stderr[-2000:])
    release_value = json.loads(release.stdout)
    regression: dict[str, Any] = {
        "executed": full_regression,
        "command": "OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run pytest -q",
        "passed": None,
        "test_count": None,
        "summary": None,
    }
    if full_regression:
        completed = _run([str(python), "-m", "pytest", "-q"])
        combined = completed.stdout + completed.stderr
        match = re.search(r"(?P<count>\d+) passed in (?P<duration>[^\n]+)", combined)
        regression.update(
            {
                "passed": completed.returncode == 0 and match is not None,
                "test_count": int(match.group("count")) if match else None,
                "summary": match.group(0) if match else combined[-2000:],
                "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
                "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
            }
        )
        if not regression["passed"]:
            raise RuntimeError("historical full regression failed: " + combined[-2000:])
    return {
        "parent_commit": git(PARENT, "rev-parse", "HEAD"),
        "release_audit": release_value,
        "full_regression": regression,
        "environment_incidents": [
            {
                "id": "s1-env-pyscf-source-build-v1",
                "scientific_result_affected": False,
                "initial_failure": "cmake executable absent",
                "second_failure": "CMake 4 incompatible with bundled libxc minimum policy",
                "resolution": "build-only CMake 3.31.10 supplied on PATH; uv.lock unchanged",
            }
        ],
    }


def _accepted_points(case: dict[str, Any]) -> list[dict[str, Any]]:
    case_id = case["case_id"]
    if case_id == "lih-3.0":
        return [{"id": "historical-lih-v5-raw-winner", **case["v5_raw_winner"]}]
    audit_path = PARENT / f"artifacts/v5/s9/{case_id}-v1-audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    return list(audit["v5_accepted_frontier_inputs"])


def build_baseline(replay: dict[str, Any]) -> dict[str, Any]:
    if replay["parent_commit"] != PARENT_COMMIT:
        raise RuntimeError("historical replay did not use the pinned parent")
    s9 = json.loads(S9_SUMMARY.read_text(encoding="utf-8"))
    errata = json.loads(ERRATA.read_text(encoding="utf-8"))
    release = json.loads(RELEASE_SUMMARY.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    for case in s9["cases"]:
        points = _accepted_points(case)
        cases.append(
            {
                "case_id": case["case_id"],
                "source": case["source"],
                "v4_1_reference": case["v4_1_reference"],
                "historical_raw_winner": case["v5_raw_winner"],
                "historical_strict_primary_success": case["strict_primary_success"],
                "accepted_points": points,
                "accepted_pareto_frontier": accepted_pareto_frontier(points),
                "reporting_policy": "all-accepted-energy-physical-resource-frontier-v1",
            }
        )
    result: dict[str, Any] = {
        "schema": "v5-matched-work.s1-correctness-baseline.v1",
        "stage": "S1",
        "status": "COMPLETE",
        "version": "correctness-baseline-v1",
        "historical_replay": replay,
        "immutable_inputs": [
            {"path": str(path.relative_to(PARENT)), "sha256": sha256(path)}
            for path in (S9_SUMMARY, ERRATA, RELEASE_SUMMARY)
        ],
        "historical_errata": errata["corrections"],
        "historical_artifacts_modified": False,
        "cases": cases,
        "corrected_runtime_contract": {
            "energy_budget": "source-relative-only; exact/FCI reference forbidden online",
            "source_relative_total_budget_hartree": 0.0001,
            "primary_output": "all accepted nondominated energy-physical-resource points",
            "historical_raw_winner_preserved": True,
            "candidate_order_changed": False,
            "winner_selection_changed": False,
            "runtime_endpoint_provenance_required": True,
            "endpoint_inference_from_rank_forbidden": True,
            "uncertainty_margin_hartree": 0.0,
            "risk_semantics": risk_semantics(0.0),
            "gradient_fields": GRADIENT_FIELD_DICTIONARY,
            "failed_candidate_parent_commit_allowed": False,
            "rollback_and_parent_immutability_required": True,
        },
        "change_classification": {
            "outcome_independent_correctness_only": True,
            "reporting_frontier_does_not_rerank_or_mutate_historical_results": True,
            "candidate_order_change_is_separate_scientific_version": True,
        },
        "release_context": {
            "core_v5_gate": release["core_v5_gate"],
            "v5_1_extension_gate": release["v5_1_extension_gate"],
        },
        "decision": "GO_S2",
        "next_stage_authorized": "S2",
        "claim_boundary": (
            "Historical development replay and outcome-independent correctness/reporting "
            "baseline only. No matched-work, prospective, general-superiority, hardware, "
            "noise, or paper Measurement Cost claim."
        ),
        "paper_measurement_cost": None,
    }
    result["baseline_digest"] = _digest_without(result, "baseline_digest")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-full-regression", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    output = ROOT / "artifacts" / "s1" / "correctness-baseline-v1.json"
    if arguments.verify_only:
        stored = json.loads(output.read_text(encoding="utf-8"))
        replay = dict(stored["historical_replay"])
        fresh_release = historical_replay(full_regression=False)["release_audit"]
        if fresh_release != replay["release_audit"]:
            raise RuntimeError("historical release audit drift")
        rebuilt = build_baseline(replay)
        if output.read_bytes() != canonical_json_bytes(rebuilt):
            raise RuntimeError("committed S1 baseline does not match reconstruction")
    else:
        if not arguments.with_full_regression:
            raise RuntimeError("initial S1 publication requires --with-full-regression")
        result = build_baseline(historical_replay(full_regression=True))
        write_json_exclusive(output, result)
    print(json.dumps({"path": str(output), "verified": arguments.verify_only}, sort_keys=True))


if __name__ == "__main__":
    main()
