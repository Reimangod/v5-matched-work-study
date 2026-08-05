from v5_matched_work.s3_build_v3 import build


def test_historical_normalization_is_not_claimed_as_actual_kernel_events() -> None:
    normalized, chain, protocol = build()
    assert not normalized["actual_kernel_events"]
    assert protocol["production_work_caps"] is None
    assert not protocol["actual_kernel_event_calibration_available"]
    assert protocol["s5_authorization_permitted"] is False
    assert chain["status"] == "IMPLEMENTED_NOT_YET_BOUND_TO_PRODUCTION_KERNELS"
