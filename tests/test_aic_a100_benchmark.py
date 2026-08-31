from __future__ import annotations

import numpy as np

from aic_a100_pilot.benchmark import (
    CURRENT_ORDER,
    SYNTHETIC_QUBITS,
    _synthetic_fixture,
)
from aic_a100_pilot.common import digest, load_json
from aic_a100_pilot.p0_baseline import PROTOCOL


def test_benchmark_domain_is_exactly_p0_frozen():
    protocol = load_json(PROTOCOL)
    assert list(CURRENT_ORDER) == protocol["case_order"]
    assert list(SYNTHETIC_QUBITS) == protocol["benchmark_policy"][
        "synthetic_scaling_qubits"
    ]
    assert protocol["benchmark_policy"]["measured_repetitions"] == 5
    assert protocol["benchmark_policy"]["warmup_repetitions_min"] == 1


def test_synthetic_fixture_is_deterministic_and_normalized():
    first = _synthetic_fixture(16)
    second = _synthetic_fixture(16)
    assert first[3] == second[3]
    assert first[1].qasm() == second[1].qasm()
    assert np.array_equal(first[0], second[0])
    assert np.linalg.norm(first[0]) == 1.0
    assert first[2].shape == (1 << 16, 1 << 16)
    assert digest({"fixture_digest": first[3]}) == digest(
        {"fixture_digest": second[3]}
    )
