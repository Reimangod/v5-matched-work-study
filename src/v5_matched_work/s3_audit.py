"""Independent S3 event-reconstruction and cap audit."""

from __future__ import annotations

import argparse, hashlib, json
from typing import Any
from jsonschema import Draft202012Validator
from .atomic_artifacts import canonical_json_bytes, write_json_exclusive
from .s0_common import PARENT, ROOT, sha256
from .work_ledger import WorkEvent, WorkLedger, WorkLedgerError, WorkVector, reconstruct


def audit() -> dict[str, Any]:
    path = ROOT / "artifacts/s3/work-ledger-protocol-v1.json"; value = json.loads(path.read_text())
    schema = json.loads((ROOT / "schemas/s3-work-ledger-protocol-v1.schema.json").read_text())
    errors = list(Draft202012Validator(schema).iter_errors(value))
    cap = WorkVector(**value["work_caps"]["LOW"]); ledger = WorkLedger(cap)
    common = {"method_id":"toy","case_id":"toy","candidate_id":"c","path_id":"p","cache":"miss"}
    ledger.record(**common, operation="exact", outcome="rejected", delta=WorkVector(N_E=3,N_exact=1,N_rounds=1))
    ledger.record(**common, operation="rollback", outcome="rollback", delta=WorkVector(N_recount=1))
    blocked = False
    try: ledger.record(**common, operation="over-cap", outcome="failed", delta=WorkVector(N_exact=2))
    except WorkLedgerError: blocked = True
    canonical = [WorkEvent(**{**event.__dict__}) for event in reversed(ledger.events)]
    checks = {
        "schema_valid": not errors,
        "digest": value["protocol_digest"] == hashlib.sha256(canonical_json_bytes({k:v for k,v in value.items() if k != "protocol_digest"})).hexdigest(),
        "input_hashes": all(sha256(PARENT / item["path"]) == item["sha256"] for item in value["cap_basis"]["inputs"]),
        "raw_reconstruction": reconstruct(ledger.events) == ledger.total,
        "process_order_invariant": reconstruct(canonical) == ledger.total,
        "rejected_and_rollback_counted": ledger.total.N_exact == 1 and ledger.total.N_recount == 1,
        "pre_operation_cap_enforced": blocked and ledger.total.N_exact == 1,
        "caps_componentwise_monotonic": all(value["work_caps"]["LOW"][f] <= value["work_caps"]["MEDIUM"][f] <= value["work_caps"]["HIGH"][f] for f in value["work_vector_fields"]),
        "measurement_cost_null": value["paper_measurement_cost"] is None,
        "s4_authorized": value["decision"] == "GO_S4",
    }
    failed=[k for k,v in checks.items() if not v]
    result={"schema":"v5-matched-work.s3-work-ledger-audit.v1","stage":"S3","passed":not failed,"checks":checks,"failed_checks":failed,"schema_errors":[e.message for e in errors],"protocol_sha256":sha256(path),"claim_boundary":"Work-ledger audit only; no molecular performance outcome."}
    result["audit_digest"]=hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if failed: raise RuntimeError("S3 audit failed: "+", ".join(failed))
    return result


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--verify-only",action="store_true"); args=parser.parse_args(); output=ROOT/"artifacts/s3/work-ledger-audit-v1.json"; result=audit()
    if args.verify_only:
        if output.read_bytes()!=canonical_json_bytes(result): raise RuntimeError("S3 audit drift")
    else: write_json_exclusive(output,result)
    print(json.dumps({"passed":result["passed"],"checks":len(result["checks"])},sort_keys=True))


if __name__ == "__main__": main()
