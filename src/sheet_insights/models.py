from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Reading:
    """One validated daily reading for one site."""

    row: int
    day: date
    site: str
    generated_kwh: float
    consumed_kwh: float
    payments_usd: float


@dataclass(frozen=True)
class Rejection:
    """A row that failed validation, kept with every reason so nothing vanishes silently."""

    row: int
    reasons: tuple[str, ...]
    raw: dict[str, str]


@dataclass(frozen=True)
class ValidationResult:
    valid: list[Reading]
    rejected: list[Rejection]

    @property
    def received(self) -> int:
        return len(self.valid) + len(self.rejected)
