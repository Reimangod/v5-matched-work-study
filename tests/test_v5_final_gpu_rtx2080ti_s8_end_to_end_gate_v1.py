from v5_final.gpu_rtx2080ti_s8_end_to_end_gate_v1 import (
    MINIMUM_FREE_STORAGE_BYTES,
    MINIMUM_MEDIAN_SPEEDUP,
    REPETITIONS,
)


def test_s8_policy_is_fixed_before_formal_benchmark() -> None:
    assert REPETITIONS == 3
    assert MINIMUM_MEDIAN_SPEEDUP == 1.0
    assert MINIMUM_FREE_STORAGE_BYTES == 40 * 1024**3
