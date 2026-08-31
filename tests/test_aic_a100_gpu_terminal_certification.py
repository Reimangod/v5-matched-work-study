from __future__ import annotations

import numpy as np

from aic_a100_pilot.gpu_terminal_certification import _max_component_delta


def test_terminal_delta_requires_equal_shapes():
    assert np.isinf(_max_component_delta([1.0], [1.0, 2.0]))


def test_terminal_delta_is_componentwise_maximum():
    assert _max_component_delta([1.0, -2.0], [1.25, -2.1]) == 0.25


def test_empty_terminal_gradient_is_well_defined():
    assert _max_component_delta([], []) == 0.0
