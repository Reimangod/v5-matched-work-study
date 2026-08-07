"""Exact, append-only authorization for one documentation-only README change."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import subprocess
from typing import Any, Mapping

from v5_matched_work.atomic_artifacts import canonical_json_bytes, write_json_exclusive

from .s0_successor import BASELINE_COMMIT, BASELINE_TAG, ROOT


OUTPUT = ROOT / "artifacts/v5-final/s0/documentation-amendment-v1.json"
S0_ARTIFACT = ROOT / "artifacts/v5-final/s0/successor-isolation-v1.json"
PUBLIC_AMENDMENT = ROOT / "artifacts/v5-final/s0/public-visibility-amendment-v2.json"
README_PATH = "README.md"


class DocumentationAmendmentError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git_bytes(*arguments: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments])


def _exact_diff(old: bytes, new: bytes) -> bytes:
    old_lines = old.decode("utf-8").splitlines(keepends=True)
    new_lines = new.decode("utf-8").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{README_PATH}",
            tofile=f"b/{README_PATH}",
            lineterm="\n",
        )
    ).encode("utf-8")


def build() -> dict[str, Any]:
    old = _git_bytes("show", f"{BASELINE_TAG}:{README_PATH}")
    new = (ROOT / README_PATH).read_bytes()
    if old == new:
        raise DocumentationAmendmentError("documentation amendment requires an exact README change")
    s0 = json.loads(S0_ARTIFACT.read_text())
    public = json.loads(PUBLIC_AMENDMENT.read_text())
    diff = _exact_diff(old, new)
    result: dict[str, Any] = {
        "schema": "v5-final.s0-documentation-amendment.v1",
        "stage": "S0-DOCUMENTATION-AMENDMENT",
        "status": "EXACT_DOCUMENTATION_CHANGE_AUTHORIZED",
        "immutable_s0": {
            "path": str(S0_ARTIFACT.relative_to(ROOT)),
            "artifact_sha256": _sha(S0_ARTIFACT.read_bytes()),
            "manifest_digest": s0["manifest_digest"],
            "baseline_tag": BASELINE_TAG,
            "baseline_commit": BASELINE_COMMIT,
        },
        "documentation_change": {
            "path": README_PATH,
            "old_sha256": _sha(old),
            "new_sha256": _sha(new),
            "exact_unified_diff_sha256": _sha(diff),
            "old_byte_count": len(old),
            "new_byte_count": len(new),
            "reason": (
                "Make the public repository's current pre-calibration No-Go, reproducible tag, "
                "MB3.1 hardening, and unapproved MB4.1 proposals discoverable without changing "
                "scientific evidence or authorization."
            ),
        },
        "repository_visibility": {
            "fact": "PUBLIC",
            "repository": "Reimangod/v5-matched-work-study",
            "evidence_path": str(PUBLIC_AMENDMENT.relative_to(ROOT)),
            "evidence_sha256": _sha(PUBLIC_AMENDMENT.read_bytes()),
            "evidence_amendment_digest": public["amendment_digest"],
        },
        "scope_guards": {
            "documentation_only": True,
            "scientific_artifact_changed": False,
            "performance_claim_changed": False,
            "queue_changed": False,
            "protocol_changed": False,
            "execution_authorized": False,
            "arbitrary_future_readme_change_authorized": False,
        },
        "authorization": {
            "README_exact_transition": "AUTHORIZED",
            "molecular_candidate_energy": "NOT_AUTHORIZED",
            "H2_H4_calibration": "NOT_AUTHORIZED",
            "development_queue_execution": "NOT_AUTHORIZED",
            "performance_claim": "NOT_AUTHORIZED",
        },
        "claim_boundary": "Exact README bytes only; no scientific or execution authorization.",
    }
    result["amendment_digest"] = _digest(result)
    return result


def validate_transition(
    artifact: Mapping[str, Any],
    *,
    old: bytes,
    new: bytes,
) -> bool:
    value = dict(artifact)
    observed = value.pop("amendment_digest", None)
    change = artifact.get("documentation_change", {})
    guards = artifact.get("scope_guards", {})
    authorizations = artifact.get("authorization", {})
    return all(
        (
            artifact.get("schema") == "v5-final.s0-documentation-amendment.v1",
            observed == _digest(value),
            change.get("path") == README_PATH,
            change.get("old_sha256") == _sha(old),
            change.get("new_sha256") == _sha(new),
            change.get("exact_unified_diff_sha256") == _sha(_exact_diff(old, new)),
            guards
            == {
                "documentation_only": True,
                "scientific_artifact_changed": False,
                "performance_claim_changed": False,
                "queue_changed": False,
                "protocol_changed": False,
                "execution_authorized": False,
                "arbitrary_future_readme_change_authorized": False,
            },
            authorizations.get("README_exact_transition") == "AUTHORIZED",
            all(
                authorizations.get(key) == "NOT_AUTHORIZED"
                for key in (
                    "molecular_candidate_energy",
                    "H2_H4_calibration",
                    "development_queue_execution",
                    "performance_claim",
                )
            ),
        )
    )


def committed_transition_allows(
    *,
    path: str,
    expected_old_sha256: str,
    observed_new_sha256: str,
) -> bool:
    if path != README_PATH or not OUTPUT.is_file():
        return False
    artifact = json.loads(OUTPUT.read_text())
    old = _git_bytes("show", f"{BASELINE_TAG}:{README_PATH}")
    new = (ROOT / README_PATH).read_bytes()
    if _sha(old) != expected_old_sha256 or _sha(new) != observed_new_sha256:
        return False
    if artifact != build():
        return False
    return validate_transition(artifact, old=old, new=new)


def audit() -> dict[str, bool]:
    committed = json.loads(OUTPUT.read_text())
    old = _git_bytes("show", f"{BASELINE_TAG}:{README_PATH}")
    new = (ROOT / README_PATH).read_bytes()
    checks = {
        "deterministic_rebuild": committed == build(),
        "exact_transition": validate_transition(committed, old=old, new=new),
        "immutable_s0_unchanged": _sha(S0_ARTIFACT.read_bytes())
        == committed["immutable_s0"]["artifact_sha256"],
        "public_evidence_unchanged": _sha(PUBLIC_AMENDMENT.read_bytes())
        == committed["repository_visibility"]["evidence_sha256"],
        "execution_closed": all(
            value == "NOT_AUTHORIZED"
            for key, value in committed["authorization"].items()
            if key != "README_exact_transition"
        ),
    }
    if not all(checks.values()):
        raise DocumentationAmendmentError("S0 documentation amendment audit failed")
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
