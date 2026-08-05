"""S2-v2 quantum reconstruction including the scheduled H4 source."""

from __future__ import annotations

import json

from .s0_common import PARENT
from .s2_probe import CASES, run_probe


CASES_V2 = {
    **CASES,
    "h4-1.5-known-development": (
        PARENT / "artifacts/s8/calibration-bundle/checkpoint-h4-1.5-first-chemical-accuracy.json"
    ),
}


def main() -> None:
    print(json.dumps(run_probe(CASES_V2, probe_version="s2-stationary-source-quantum-probe-v2"),
                     allow_nan=False, sort_keys=True))


if __name__ == "__main__":
    main()
