from __future__ import annotations

from v5_final.s0_successor import (
    ALLOWED_BASELINE_MODIFICATIONS,
    BASELINE_COMMIT,
    BASELINE_TAG,
    HISTORICAL_TAGS,
    audit_manifest,
    build_manifest,
)


def test_successor_manifest_binds_all_historical_no_go_tags() -> None:
    manifest = build_manifest()
    observed = {item["tag"]: item["peeled_commit"] for item in manifest["historical_tags"]}
    assert observed[BASELINE_TAG] == BASELINE_COMMIT
    assert len(observed) == len(HISTORICAL_TAGS)


def test_successor_manifest_forbids_all_performance_work() -> None:
    authorization = build_manifest()["authorization"]
    assert authorization["performance_experiment"] == "NOT_AUTHORIZED"
    assert authorization["candidate_molecular_energy_evaluation"] == "NOT_AUTHORIZED"
    assert authorization["s5_freeze"] == "NOT_AUTHORIZED"


def test_successor_scope_separates_primary_and_secondary_methods() -> None:
    scope = build_manifest()["scientific_scope"]
    assert "V5-Core" in scope["primary_method"]
    assert "V5-Pro" in scope["secondary_method"]
    assert "secondary" in scope["secondary_method"]


def test_only_package_registration_may_change_from_baseline() -> None:
    assert ALLOWED_BASELINE_MODIFICATIONS == {
        "pyproject.toml": (
            "register src/v5_final as an installable package; this does not alter "
            "any historical evidence or scientific result"
        )
    }


def test_successor_dual_gate_audit_passes_while_dirty_is_not_release_checked() -> None:
    result = audit_manifest(require_clean=False)
    assert result["passed"] is True
    assert result["checks"]["academic_gate_explicit"] is True
    assert result["checks"]["safety_gate_explicit"] is True
