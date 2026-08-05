"""Independent S4 rebuilding-ablation and comparator audit."""

from __future__ import annotations
import argparse,hashlib,json
from typing import Any
from jsonschema import Draft202012Validator
from .atomic_artifacts import canonical_json_bytes,write_json_exclusive
from .comparators import CatalogSnapshot,PRIMARY_METHODS,catalog_sequence
from .s0_common import PARENT,ROOT,sha256


def audit()->dict[str,Any]:
    path=ROOT/"artifacts/s4/comparator-protocol-v1.json";value=json.loads(path.read_text());schema=json.loads((ROOT/"schemas/s4-comparator-protocol-v1.schema.json").read_text());errors=list(Draft202012Validator(schema).iter_errors(value))
    source=CatalogSnapshot("source",("a","b")); builder=lambda child:CatalogSnapshot(child,(f"{child}-new",))
    without=catalog_sequence(source,("child-1","child-2"),rebuild=False,builder=builder);full=catalog_sequence(source,("child-1","child-2"),rebuild=True,builder=builder)
    checks={
        "schema_valid":not errors,"digest":value["protocol_digest"]==hashlib.sha256(canonical_json_bytes({k:v for k,v in value.items() if k!="protocol_digest"})).hexdigest(),
        "parent_hashes":all(sha256(PARENT/i["path"])==i["sha256"] for i in value["immutable_parent_inputs"]),
        "all_primary_methods":tuple(i["method_id"] for i in value["comparators"])==PRIMARY_METHODS,
        "without_rebuilding_reuses_original":all(item==source for item in without),
        "full_v5_rebuilds":full[1].parent_state_id=="child-1" and full[2].parent_state_id=="child-2",
        "only_ablation_is_catalog":value["ablation_identity"].startswith("Methods 5 and 6 differ only"),
        "structural_magnitude":next(i for i in value["comparators"] if i["method_id"]=="structural-magnitude-pruning")["coefficient_only_zeroing_forbidden"] is True,
        "full_recount":all(i["physical_recount"] is True for i in value["comparators"]),
        "fci_firewall":value["common_contract"]["fci_or_exact_reference_online"] is False,
        "s5_authorized":value["decision"]=="GO_S5",
    };failed=[k for k,v in checks.items() if not v]
    result={"schema":"v5-matched-work.s4-comparator-audit.v1","stage":"S4","passed":not failed,"checks":checks,"failed_checks":failed,"schema_errors":[e.message for e in errors],"protocol_sha256":sha256(path),"claim_boundary":"Comparator and rebuilding-mechanism audit only; toy evidence is not molecular performance evidence."};result["audit_digest"]=hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if failed:raise RuntimeError("S4 audit failed: "+", ".join(failed))
    return result


def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--verify-only",action="store_true");args=parser.parse_args();output=ROOT/"artifacts/s4/comparator-audit-v1.json";result=audit()
    if args.verify_only:
        if output.read_bytes()!=canonical_json_bytes(result):raise RuntimeError("S4 audit drift")
    else:write_json_exclusive(output,result)
    print(json.dumps({"passed":result["passed"],"checks":len(result["checks"])},sort_keys=True))
if __name__=="__main__":main()
