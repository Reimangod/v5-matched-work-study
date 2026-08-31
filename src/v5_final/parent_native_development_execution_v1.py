"""Narrow compatibility wrapper for S11 development item execution.

The frozen parent-native execution service is left byte-for-byte unchanged.
Within one isolated item process this wrapper substitutes only the queue-bound
runtime factory, then applies the already-audited zero-dimensional optimizer
boundary.  All six method semantics, accounting, acceptance, and persistence
continue to use the same S9 service implementation.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import threading
from typing import Any, Iterator, Mapping

from . import parent_native_execution_services as services
from .parent_native_development_runtime_factory_v1 import (
    build_queue_bound_development_runtime_v1,
)
from .parent_native_zero_dimensional_v2 import zero_dimensional_boundary_scope
from .parent_native_work_accounting import ComponentwiseCapRejected


class DevelopmentExecutionBindingError(services.ParentNativeExecutionError):
    pass


_LOCK = threading.RLock()
_FROZEN_FACTORY = services.build_queue_bound_runtime_v2
_FROZEN_SERVICES = services.ParentNativeExecutionServices
_FROZEN_DYNAMIC_V5 = services._dynamic_v5_preparation
_FROZEN_DYNAMIC_MAGNITUDE = services._dynamic_magnitude_preparation


@contextmanager
def development_runtime_scope() -> Iterator[None]:
    with _LOCK:
        if (
            services.build_queue_bound_runtime_v2 is not _FROZEN_FACTORY
            or services.ParentNativeExecutionServices is not _FROZEN_SERVICES
            or services._dynamic_v5_preparation is not _FROZEN_DYNAMIC_V5
            or services._dynamic_magnitude_preparation
            is not _FROZEN_DYNAMIC_MAGNITUDE
        ):
            raise DevelopmentExecutionBindingError(
                "unexpected development execution override already active"
            )
        tracker: dict[str, Any] = {
            "maximum_rounds": None,
            "dynamic_calls": 0,
            "round_limit_reached": False,
            "method_id": None,
        }

        def enforce_round_limit(dynamic: Any):
            def guarded(*args: Any, **kwargs: Any) -> Any:
                maximum = tracker["maximum_rounds"]
                if not isinstance(maximum, int) or maximum < 1:
                    raise DevelopmentExecutionBindingError(
                        "frozen development maximum_rounds is invalid"
                    )
                if tracker["dynamic_calls"] >= maximum - 1:
                    tracker["round_limit_reached"] = True
                    raise ComponentwiseCapRejected(
                        "frozen development maximum_rounds reached"
                    )
                tracker["dynamic_calls"] += 1
                return dynamic(*args, **kwargs)

            return guarded

        class DevelopmentExecutionServices(_FROZEN_SERVICES):
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(**kwargs)
                maximum = self.item.get("maximum_rounds")
                if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
                    raise DevelopmentExecutionBindingError(
                        "development item lacks a positive frozen maximum_rounds"
                    )
                tracker["maximum_rounds"] = maximum
                tracker["method_id"] = self.item["method_id"]

            def execute_prepared(self, executor: Any) -> dict[str, Any]:
                result = super().execute_prepared(executor)
                if tracker["round_limit_reached"]:
                    reason = str(result.get("stopping_reason", ""))
                    if not reason.startswith("WORK_CAP_REACHED_AFTER_COMMITTED_"):
                        raise DevelopmentExecutionBindingError(
                            "round-limit sentinel did not reach the expected safe boundary"
                        )
                    result["stopping_reason"] = (
                        "FROZEN_MAXIMUM_ROUNDS_REACHED_AFTER_COMMITTED_CHILD"
                    )
                    result["frozen_maximum_rounds"] = tracker["maximum_rounds"]
                    result["round_limit_was_not_component_cap"] = True
                return result

        services.build_queue_bound_runtime_v2 = (
            build_queue_bound_development_runtime_v1
        )
        services.ParentNativeExecutionServices = DevelopmentExecutionServices
        services._dynamic_v5_preparation = enforce_round_limit(
            _FROZEN_DYNAMIC_V5
        )
        services._dynamic_magnitude_preparation = enforce_round_limit(
            _FROZEN_DYNAMIC_MAGNITUDE
        )
        try:
            yield
        finally:
            if (
                services.build_queue_bound_runtime_v2
                is not build_queue_bound_development_runtime_v1
                or services.ParentNativeExecutionServices
                is not DevelopmentExecutionServices
            ):
                services.build_queue_bound_runtime_v2 = _FROZEN_FACTORY
                services.ParentNativeExecutionServices = _FROZEN_SERVICES
                services._dynamic_v5_preparation = _FROZEN_DYNAMIC_V5
                services._dynamic_magnitude_preparation = (
                    _FROZEN_DYNAMIC_MAGNITUDE
                )
                raise DevelopmentExecutionBindingError(
                    "development execution override changed during item"
                )
            services.build_queue_bound_runtime_v2 = _FROZEN_FACTORY
            services.ParentNativeExecutionServices = _FROZEN_SERVICES
            services._dynamic_v5_preparation = _FROZEN_DYNAMIC_V5
            services._dynamic_magnitude_preparation = _FROZEN_DYNAMIC_MAGNITUDE


def execute_development_item_v1(
    *,
    plan: Mapping[str, Any],
    item: Mapping[str, Any],
    raw_ledger_root: Path,
    result_output: Path,
) -> dict[str, Any]:
    if plan.get("schema") != "v5-final.s11-development-plan.v4":
        raise DevelopmentExecutionBindingError(
            "development execution requires the exact S11 v4 successor plan"
        )
    if len(plan.get("items", ())) != 90:
        raise DevelopmentExecutionBindingError(
            "development execution requires the complete 90-item plan"
        )
    with development_runtime_scope(), zero_dimensional_boundary_scope():
        return services.execute_frozen_item(
            plan=plan,
            item=item,
            raw_ledger_root=raw_ledger_root,
            result_output=result_output,
        )
