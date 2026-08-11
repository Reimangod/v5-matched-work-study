from __future__ import annotations

import json

import pytest


pytest.importorskip("numpy")

from v5_final import parent_native_execution_services as services
from v5_final.parent_native_development_execution_v1 import (
    development_runtime_scope,
)
from v5_final.parent_native_development_runtime_factory_v1 import (
    DEVELOPMENT_CASES,
    ENVIRONMENT_PATH,
    METHOD_IDS,
    WORK_ENVELOPES,
    _digest,
    _verify_plan,
)
from v5_final.parent_native_runtime_factory import QueueBoundRuntimeError
from v5_final.s11_development_successor_v1 import (
    FREEZE_OUTPUT,
    METHOD_RENAME,
    S5_PROTOCOL,
    _parent_digest,
    audit_static,
)


def _synthetic_preparation_plan() -> dict:
    items = []
    for case_id in DEVELOPMENT_CASES:
        for envelope in WORK_ENVELOPES:
            for method in METHOD_IDS:
                body = {
                    "case_id": case_id,
                    "work_envelope": envelope,
                    "method_id": method,
                    "terminal_status": "NOT_STARTED",
                }
                items.append(
                    {
                        **body,
                        "queue_item_id": (
                            "s11-development-preparation-item-v1:" + _digest(body)
                        ),
                    }
                )
    plan = {
        "schema": "v5-final.s11-development-preparation-plan.v1",
        "stage": "TEST",
        "status": "OUTCOME_FREE_INTERNAL_PREPARATION_ONLY",
        "items": items,
        "frozen_item_count": 90,
        "candidate_energy_evaluations": 0,
    }
    plan["plan_digest"] = _digest(plan)
    return plan


def test_s11_plan_validator_requires_exact_nonempty_5x3x6_grid() -> None:
    plan = _synthetic_preparation_plan()
    _verify_plan(plan)
    broken = dict(plan)
    broken["items"] = list(plan["items"][:-1])
    broken["frozen_item_count"] = 89
    broken["plan_digest"] = _digest(
        {key: value for key, value in broken.items() if key != "plan_digest"}
    )
    with pytest.raises(QueueBoundRuntimeError, match="exact zero-outcome 90-item"):
        _verify_plan(broken)


def test_development_environment_preserves_original_single_thread_identity() -> None:
    environment = json.loads(ENVIRONMENT_PATH.read_text())
    protocol = json.loads(S5_PROTOCOL.read_text())
    expected = {
        "MKL_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }
    assert environment["required_threads"] == expected
    assert protocol["policy"]["environment"]["required_threads"] == expected


def test_only_historical_no_rebuild_label_is_renamed() -> None:
    assert METHOD_RENAME == {
        "v5-sequential-without-rebuilding": (
            "v5-fixed-source-whitelist-no-replenishment"
        )
    }


def test_parent_candidate_identity_uses_parent_canonical_domain() -> None:
    from v5_final.parent_native_executors import _digest as executor_digest

    payload = {
        "source_state_preparation_id": "state-v1:" + "a" * 64,
        "position": 3,
        "pool_index": 17,
        "constraint": "theta_i->0",
        "physical_generator_deletion": True,
    }
    assert _parent_digest(payload) == executor_digest(payload)


def test_development_execution_overrides_are_narrow_and_restored() -> None:
    original_factory = services.build_queue_bound_runtime_v2
    original_services = services.ParentNativeExecutionServices
    original_v5 = services._dynamic_v5_preparation
    original_magnitude = services._dynamic_magnitude_preparation
    with development_runtime_scope():
        assert services.build_queue_bound_runtime_v2 is not original_factory
        assert services.ParentNativeExecutionServices is not original_services
        assert services._dynamic_v5_preparation is not original_v5
        assert services._dynamic_magnitude_preparation is not original_magnitude
    assert services.build_queue_bound_runtime_v2 is original_factory
    assert services.ParentNativeExecutionServices is original_services
    assert services._dynamic_v5_preparation is original_v5
    assert services._dynamic_magnitude_preparation is original_magnitude


def test_frozen_s11_artifacts_are_static_auditable_if_present() -> None:
    if FREEZE_OUTPUT.exists():
        assert all(audit_static().values())
