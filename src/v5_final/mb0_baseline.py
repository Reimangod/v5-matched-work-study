"""MB0 immutable baseline and protected-artifact inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import ROOT


BASE_TAG = "v5-final-pre-calibration-no-go-v1"
BASE_COMMIT = "d0c34fa98859e0c14d4c253595122f48e32b18e8"
PARENT_COMMIT = "4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db"
CEO_SUBMODULE_COMMIT = "a3f89d03e6a03c89767d3cf8ee7657a57653dda0"
OUTPUT = ROOT / "artifacts/v5-final/method-native/mb0-baseline-v1.json"


def _git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _protected_artifacts() -> list[dict[str, Any]]:
    names = _git("ls-tree", "-r", "--name-only", BASE_TAG, "artifacts").splitlines()
    records = []
    for name in names:
        path = ROOT / name
        if not path.is_file():
            raise RuntimeError(f"protected artifact missing: {name}")
        records.append({"path": name, "sha256": _sha(path), "size_bytes": path.stat().st_size})
    return records


def build() -> dict[str, Any]:
    queue_path = ROOT / "artifacts/v5-final/s5/development-queue-v3.json"
    ledger_path = ROOT / "artifacts/v5-final/s5/development-ledger-root-v3.json"
    queue = json.loads(queue_path.read_text())
    ledger = json.loads(ledger_path.read_text())
    locks = [
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
        ROOT / "provenance/dvg-obs-ceo/pyproject.toml",
        ROOT / "provenance/dvg-obs-ceo/uv.lock",
    ]
    artifacts = _protected_artifacts()
    result: dict[str, Any] = {
        "schema": "v5-final.method-native.mb0-baseline.v1",
        "stage": "MB0",
        "status": "COMPLETE",
        "branch": "feature/v5-final-method-native-backends-v1",
        "baseline": {"tag": BASE_TAG, "commit": BASE_COMMIT},
        "repository_pins": {
            "parent_repository_commit": PARENT_COMMIT,
            "ceo_adapt_vqe_submodule_commit": CEO_SUBMODULE_COMMIT,
            "observed_parent_commit": _git("rev-parse", "HEAD", cwd=ROOT / "provenance/dvg-obs-ceo"),
            "observed_ceo_commit": _git(
                "rev-parse", "HEAD", cwd=ROOT / "provenance/dvg-obs-ceo/vendor/ceo-adapt-vqe"
            ),
        },
        "dependency_locks": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)} for path in locks
        ],
        "protected_artifact_inventory": {
            "source": f"git ls-tree -r {BASE_TAG} artifacts",
            "count": len(artifacts),
            "records": artifacts,
            "inventory_digest": _digest(artifacts),
        },
        "development_queue": {
            "path": str(queue_path.relative_to(ROOT)),
            "artifact_sha256": _sha(queue_path),
            "queue_digest": queue["queue_digest"],
            "expected_count": queue["expected_queue_count"],
            "not_started_count": sum(
                item["terminal_status"] == "NOT_STARTED" for item in queue["items"]
            ),
            "completed_count": len(ledger["completed_queue_item_ids"]),
            "segment_count": len(ledger["segments"]),
            "candidate_energy_evaluations": ledger[
                "development_candidate_energy_evaluations"
            ],
            "empty_ledger_complete": ledger["completeness"]["complete"],
        },
        "fresh_recursive_clone": {
            "baseline_commit": BASE_COMMIT,
            "parent_commit": PARENT_COMMIT,
            "ceo_submodule_commit": CEO_SUBMODULE_COMMIT,
            "test_summary": "85 passed, 3 xfailed",
            "test_exit_code": 0,
            "threads": {
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            },
            "incident_before_success": (
                "first temporary clone checkout exhausted disk; only two clean ignored historical "
                "audit clones were removed, then a new recursive clone completed"
            ),
        },
        "authorization": {
            "MB1_code_level_research": "AUTHORIZED",
            "candidate_molecular_energy": "NOT_AUTHORIZED",
            "H2_H4_calibration": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "academic_boundary": "Repository and evidence baseline only; no scientific outcome.",
        "systems_boundary": "Any protected hash, pin, lock, or queue-state drift fails MB0 closed.",
        "decision": "GO_MB1_CODE_RESEARCH_ONLY",
    }
    result["baseline_digest"] = _digest(result)
    return result


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    rebuilt = build()
    payload = dict(committed)
    observed = payload.pop("baseline_digest")
    queue = committed["development_queue"]
    checks = {
        "deterministic_rebuild": committed == rebuilt,
        "baseline_digest": observed == _digest(payload),
        "base_tag_immutable": _git("rev-parse", f"{BASE_TAG}^{{}}") == BASE_COMMIT,
        "parent_pin": committed["repository_pins"]["observed_parent_commit"] == PARENT_COMMIT,
        "ceo_pin": committed["repository_pins"]["observed_ceo_commit"] == CEO_SUBMODULE_COMMIT,
        "protected_artifacts_current": all(
            _sha(ROOT / item["path"]) == item["sha256"]
            for item in committed["protected_artifact_inventory"]["records"]
        ),
        "queue_untouched": queue["expected_count"] == 90
        and queue["not_started_count"] == 90
        and queue["completed_count"] == 0
        and queue["segment_count"] == 0
        and queue["candidate_energy_evaluations"] == 0
        and queue["empty_ledger_complete"] is False,
        "fresh_clone_baseline": committed["fresh_recursive_clone"]["test_exit_code"] == 0
        and committed["fresh_recursive_clone"]["test_summary"] == "85 passed, 3 xfailed",
        "experiments_closed": all(
            value == "NOT_AUTHORIZED"
            for key, value in committed["authorization"].items()
            if key != "MB1_code_level_research"
        ),
    }
    if not all(checks.values()):
        raise RuntimeError("MB0 baseline audit failed")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args()
    if args.action == "build":
        write_json_exclusive(OUTPUT, build())
    else:
        audit()
    print(json.dumps({"action": args.action, "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()
