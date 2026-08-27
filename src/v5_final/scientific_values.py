"""Tagged scientific values that never encode missingness as a number."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any


class ScientificValueError(ValueError):
    pass


class ScientificValueState(str, Enum):
    NOT_PRESENT = "NOT_PRESENT"
    NOT_EVALUATED = "NOT_EVALUATED"
    AVAILABLE = "AVAILABLE"
    INVALID = "INVALID"
    LEGACY_SENTINEL_NOT_EVALUATED = "LEGACY_SENTINEL_NOT_EVALUATED"


@dataclass(frozen=True)
class TaggedScientificValue:
    """A scientific scalar with explicit epistemic state.

    Decimal text is used instead of a binary float so canonical artifacts retain
    the exact value supplied by the executor.
    """

    quantity: str
    unit: str
    state: ScientificValueState
    value: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.quantity or not self.unit:
            raise ScientificValueError("quantity and unit are required")
        if self.state is ScientificValueState.AVAILABLE:
            if self.value is None:
                raise ScientificValueError("AVAILABLE requires an explicit value")
            try:
                parsed = Decimal(self.value)
            except (InvalidOperation, TypeError) as error:
                raise ScientificValueError("AVAILABLE value must be decimal text") from error
            if not parsed.is_finite():
                raise ScientificValueError("AVAILABLE value must be finite")
            if self.reason is not None:
                raise ScientificValueError("AVAILABLE cannot carry a missingness reason")
        else:
            if self.value is not None:
                raise ScientificValueError(
                    f"{self.state.value} must not carry a numeric value"
                )
            if not self.reason:
                raise ScientificValueError(f"{self.state.value} requires a reason")

    @classmethod
    def available(cls, *, quantity: str, unit: str, value: str) -> "TaggedScientificValue":
        return cls(quantity=quantity, unit=unit, state=ScientificValueState.AVAILABLE, value=value)

    @classmethod
    def not_evaluated(
        cls, *, quantity: str, unit: str, reason: str
    ) -> "TaggedScientificValue":
        return cls(
            quantity=quantity,
            unit=unit,
            state=ScientificValueState.NOT_EVALUATED,
            reason=reason,
        )

    @classmethod
    def from_legacy_energy(cls, legacy_value: int | float | None) -> "TaggedScientificValue":
        """Decode only the documented V1--V4 placeholder convention.

        Numeric zero was used as a non-evaluation placeholder in historical
        candidate records. It is therefore tagged as a legacy sentinel, never
        promoted to an AVAILABLE scientific zero.
        """

        if legacy_value == 0 and not isinstance(legacy_value, bool):
            return cls(
                quantity="candidate_energy",
                unit="hartree",
                state=ScientificValueState.LEGACY_SENTINEL_NOT_EVALUATED,
                reason="historical_zero_placeholder_not_a_measurement",
            )
        if legacy_value is None:
            return cls(
                quantity="candidate_energy",
                unit="hartree",
                state=ScientificValueState.NOT_PRESENT,
                reason="legacy_field_absent",
            )
        raise ScientificValueError(
            "legacy import accepts only the documented zero sentinel or an absent field"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "quantity": self.quantity,
            "unit": self.unit,
            "state": self.state.value,
            "value": self.value,
            "reason": self.reason,
        }


def scientific_value_from_dict(value: dict[str, Any]) -> TaggedScientificValue:
    return TaggedScientificValue(
        quantity=str(value["quantity"]),
        unit=str(value["unit"]),
        state=ScientificValueState(value["state"]),
        value=value.get("value"),
        reason=value.get("reason"),
    )
