from __future__ import annotations

import numpy as np

from aic_a100_pilot.aer_gpu_backend import phase_aligned_max_error
from aic_a100_pilot.parity import _from_float_hex


def test_phase_aligned_error_ignores_only_global_phase():
    reference = np.asarray([1.0, 1.0j], dtype=np.complex128) / np.sqrt(2)
    observed = reference * np.exp(0.75j)
    assert phase_aligned_max_error(reference, observed) < 1e-15


def test_float_hex_round_trip_matches_frozen_binary64():
    assert _from_float_hex("3ff0000000000000") == 1.0
    assert _from_float_hex("bfe0000000000000") == -0.5
