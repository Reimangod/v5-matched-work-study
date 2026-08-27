from __future__ import annotations

import platform

from v5_final.s8_parent_native_production_gate_v2 import (
    _reproducible_local_preflight_digest,
    build_ci_preflight,
    build_local_preflight,
)


def test_reproducible_preflight_digest_excludes_only_free_byte_sample():
    first = {
        "schema": "example",
        "capacity": {"available_bytes": 100, "execution_threshold_bytes": 80},
        "checks": {"capacity_passed": True},
    }
    second = {
        **first,
        "capacity": {**first["capacity"], "available_bytes": 90},
    }
    changed_threshold = {
        **first,
        "capacity": {**first["capacity"], "execution_threshold_bytes": 81},
    }
    assert _reproducible_local_preflight_digest(first) == (
        _reproducible_local_preflight_digest(second)
    )
    assert _reproducible_local_preflight_digest(first) != (
        _reproducible_local_preflight_digest(changed_threshold)
    )


def test_s8_v2_preflight_is_zero_outcome_and_does_not_authorize_execution():
    report = (
        build_local_preflight(require_clean_worktree=False)
        if platform.machine().lower() == "arm64"
        else build_ci_preflight()
    )
    assert all(report["checks"].values())
    if "reproducible_evidence_digest" in report:
        assert len(report["reproducible_evidence_digest"]) == 64
    assert report["candidate_molecular_energy_evaluations"] == 0
    assert report["authorization"]["H2_H4_execution"].startswith("NOT_AUTHORIZED")
