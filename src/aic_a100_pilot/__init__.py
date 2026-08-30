"""Fail-closed AIC A100 qualification pilot.

The package is intentionally isolated from the production V5 executors.  It
may import the immutable CPU reference implementation, but production code
must not import this package.
"""

from __future__ import annotations

PILOT_SCHEMA_VERSION = "aic-a100-pilot-v1"

__all__ = ["PILOT_SCHEMA_VERSION"]
