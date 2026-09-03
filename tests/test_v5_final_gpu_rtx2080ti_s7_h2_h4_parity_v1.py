from __future__ import annotations

from v5_final.gpu_rtx2080ti_s7_h2_h4_parity_v1 import (
    ENERGY_ABSOLUTE_TOLERANCE_HARTREE,
    GRADIENT_INFINITY_TOLERANCE,
    STATE_L2_TOLERANCE,
    _digest_without,
)


def test_s7_tolerances_are_frozen_strictly() -> None:
    assert STATE_L2_TOLERANCE == 1e-10
    assert ENERGY_ABSOLUTE_TOLERANCE_HARTREE == 1e-11
    assert GRADIENT_INFINITY_TOLERANCE == 1e-9


def test_s7_digest_excludes_only_named_field() -> None:
    record = {"schema": "test", "value": 1}
    digest = _digest_without(record, "digest")
    assert digest == _digest_without({**record, "digest": "ignored"}, "digest")
