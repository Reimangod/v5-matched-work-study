"""Evidence-preserving controlled termination for S11-v1 item 028.

This module is intentionally additive.  It never edits the active ledger and
does not create a scientific terminal result.  A signal is sent only after the
full process identity and the preserved append-only ledger prefix match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import ROOT


PID = 86211
PPID = 86202
PGID = 86202
EXPECTED_COMMAND = (
    "provenance/dvg-obs-ceo/.venv/bin/python -m "
    "v5_final.s11_interruption_recovery_item028_v1 --execute-retry"
)
EXPECTED_LAUNCH = "Thu Aug 13 14:30:08 2026"
REASON = "CONTROLLED_TERMINATION_UNBOUNDED_DENSE_UNITARY_VERIFICATION_COST"
ITEM_KEY = "028-d37d71eb9ae63c6b6d90e26850e8cc845172577cb2e2f7b457dec40d2b0315b9"
EXECUTION_DIR = ROOT / "artifacts/v5-final/parent-native/s11-development-execution-v1"
LEDGER_DIR = EXECUTION_DIR / "raw-ledgers" / ITEM_KEY
EVIDENCE_DIR = EXECUTION_DIR / "incident-evidence/item-028-controlled-termination-v1"
PRE_STOP_PATH = EVIDENCE_DIR / "pre-stop-snapshot-v1.json"
SAMPLE_PATH = EVIDENCE_DIR / "pre-stop-process-sample-v1.txt"
ESCALATION_PATH = EVIDENCE_DIR / "sigkill-escalation-v1.json"
POST_STOP_PATH = EVIDENCE_DIR / "post-stop-snapshot-v1.json"


class ControlledTerminationError(RuntimeError):
    """Raised before mutation whenever the exact safety contract is not met."""


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _process_rows() -> list[dict[str, Any]]:
    output = subprocess.check_output(
        [
            "/bin/ps", "-ax", "-ww", "-o",
            "pid=,ppid=,pgid=,lstart=,etime=,%cpu=,rss=,state=,command=",
        ],
        text=True,
    )
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        fields = line.strip().split(None, 12)
        if len(fields) != 13:
            continue
        rows.append(
            {
                "pid": int(fields[0]),
                "ppid": int(fields[1]),
                "pgid": int(fields[2]),
                "launch_time": " ".join(fields[3:8]),
                "elapsed": fields[8],
                "cpu_percent": float(fields[9]),
                "rss_kib": int(fields[10]),
                "state": fields[11],
                "command": fields[12],
            }
        )
    return rows


def discover_exact_process(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = _process_rows() if rows is None else rows
    matches = [row for row in rows if row["pid"] == PID]
    if len(matches) != 1:
        raise ControlledTerminationError("exact target PID is absent or ambiguous")
    target = matches[0]
    checks = {
        "pid_exact": target["pid"] == PID,
        "ppid_exact": target["ppid"] == PPID,
        "pgid_exact": target["pgid"] == PGID,
        "launch_exact": target["launch_time"] == EXPECTED_LAUNCH,
        "command_exact": target["command"] == EXPECTED_COMMAND,
    }
    members = sorted(
        (row for row in rows if row["pgid"] == PGID), key=lambda row: row["pid"]
    )
    member_pids = {row["pid"] for row in members}
    checks["group_contains_target_and_parent"] = {PID, PPID}.issubset(member_pids)
    checks["group_has_no_unrelated_members"] = all(
        row["pid"] in {PID, PPID}
        and (
            row["pid"] == PID
            or ("rtk" in row["command"] and EXPECTED_COMMAND in row["command"])
        )
        for row in members
    )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise ControlledTerminationError(
            "process identity audit failed: " + ", ".join(failures)
        )
    return {"target": target, "group_members": members, "checks": checks}


def ledger_snapshot() -> dict[str, Any]:
    paths = sorted(LEDGER_DIR.glob("*.json"))
    records = [json.loads(path.read_text()) for path in paths]
    deltas = [(record.get("payload") or {}).get("delta") or {} for record in records]
    snapshot = {
        "record_count": len(records),
        "first_sequence": records[0]["sequence"] if records else None,
        "last_sequence": records[-1]["sequence"] if records else None,
        "last_record_digest": records[-1]["record_digest"] if records else None,
        "record_sha256": {path.name: _sha(path) for path in paths},
        "kinds": [record.get("kind") for record in records],
        "operations": [
            (record.get("payload") or {}).get("operation") for record in records
        ],
        "candidate_energy_evaluations": sum(
            delta.get("energy_evaluations", 0) for delta in deltas
        ),
        "optimizer_iterations": sum(
            delta.get("optimizer_iterations", 0) for delta in deltas
        ),
        "fci_reporting_mentions": sum(
            "fci" in json.dumps(record).lower() for record in records
        ),
        "terminal_present": any(
            record.get("kind") == "attempt-terminal" for record in records
        ),
    }
    snapshot["ledger_digest"] = _digest(snapshot)
    return snapshot


def _absence_state() -> dict[str, bool]:
    return {
        "checkpoint_present": (EXECUTION_DIR / f"raw-ledgers/{ITEM_KEY}.outcome.json").exists(),
        "result_present": (EXECUTION_DIR / f"item-results/{ITEM_KEY}.json").exists(),
        "receipt_present": (EXECUTION_DIR / f"item-receipts/{ITEM_KEY}.json").exists(),
    }


def capture_pre_stop() -> dict[str, Any]:
    identity = discover_exact_process()
    ledger = ledger_snapshot()
    if (
        ledger["record_count"] != 10
        or ledger["candidate_energy_evaluations"] != 0
        or ledger["optimizer_iterations"] != 0
        or ledger["fci_reporting_mentions"] != 0
        or ledger["terminal_present"]
        or any(_absence_state().values())
    ):
        raise ControlledTerminationError("pre-stop scientific boundary drifted")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    sample = subprocess.run(
        ["/usr/bin/sample", str(PID), "1", "1"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ).stdout
    SAMPLE_PATH.write_text(sample)
    record = {
        "schema": "v5-final.s11-v1-item028-controlled-termination-pre-stop.v1",
        "reason": REASON,
        "captured_at_unix_ns": time.time_ns(),
        "process_identity": identity,
        "sample_sha256": _sha(SAMPLE_PATH),
        "sample_dense_markers": {
            "scipy_matfuncs_expm": "matfuncs_expm" in sample,
            "pade_uv_calc": "pade_UV_calc" in sample,
            "openblas_zgemm": "zgemm" in sample,
        },
        "ledger": ledger,
        "derived_artifact_absence": _absence_state(),
        "scientific_classification": "INFRASTRUCTURE_INCIDENT_BEFORE_OUTCOME",
        "performance_negative_result": False,
        "signal_sent_by_capture": False,
    }
    record["record_digest"] = _digest(record)
    write_json_exclusive(PRE_STOP_PATH, record)
    return record


def _assert_pre_stop_binding() -> dict[str, Any]:
    pre = json.loads(PRE_STOP_PATH.read_text())
    body = dict(pre)
    observed = body.pop("record_digest", None)
    if observed != _digest(body):
        raise ControlledTerminationError("pre-stop snapshot digest invalid")
    current = ledger_snapshot()
    if current != pre["ledger"]:
        raise ControlledTerminationError("active ledger changed after pre-stop capture")
    discover_exact_process()
    return pre


def _alive_target() -> bool:
    return any(row["pid"] == PID for row in _process_rows())


def terminate(*, term_wait_seconds: float = 30.0, kill_wait_seconds: float = 10.0) -> dict[str, Any]:
    pre = _assert_pre_stop_binding()
    signal_sent = "SIGTERM"
    os.killpg(PGID, signal.SIGTERM)
    deadline = time.monotonic() + term_wait_seconds
    while _alive_target() and time.monotonic() < deadline:
        time.sleep(0.25)
    escalated = False
    if _alive_target():
        identity = discover_exact_process()
        escalation = {
            "schema": "v5-final.s11-v1-item028-sigkill-escalation.v1",
            "reason": REASON,
            "sigterm_wait_seconds": term_wait_seconds,
            "identity_revalidated": identity,
            "ledger": ledger_snapshot(),
        }
        escalation["record_digest"] = _digest(escalation)
        write_json_exclusive(ESCALATION_PATH, escalation)
        os.killpg(PGID, signal.SIGKILL)
        signal_sent = "SIGTERM_THEN_SIGKILL"
        escalated = True
        deadline = time.monotonic() + kill_wait_seconds
        while _alive_target() and time.monotonic() < deadline:
            time.sleep(0.25)
    rows = _process_rows()
    remaining = [row for row in rows if row["pgid"] == PGID or row["ppid"] == PID]
    if _alive_target() or remaining:
        raise ControlledTerminationError("target process group did not terminate cleanly")
    post_ledger = ledger_snapshot()
    if post_ledger != pre["ledger"]:
        raise ControlledTerminationError("ledger changed during controlled termination")
    record = {
        "schema": "v5-final.s11-v1-item028-controlled-termination-post-stop.v1",
        "reason": REASON,
        "captured_at_unix_ns": time.time_ns(),
        "signal_method": signal_sent,
        "sigkill_escalated": escalated,
        "target_process_absent": True,
        "target_group_and_children_absent": True,
        "preserved_ledger": post_ledger,
        "derived_artifact_absence": _absence_state(),
        "scientific_terminal_created": False,
        "performance_negative_result": False,
    }
    record["record_digest"] = _digest(record)
    write_json_exclusive(POST_STOP_PATH, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-pre-stop", action="store_true")
    parser.add_argument("--terminate", action="store_true")
    args = parser.parse_args()
    if args.capture_pre_stop == args.terminate:
        raise ControlledTerminationError("select exactly one operation")
    result = capture_pre_stop() if args.capture_pre_stop else terminate()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
