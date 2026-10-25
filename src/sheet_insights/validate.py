from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date

from sheet_insights.models import Reading, Rejection, ValidationResult

REQUIRED_COLUMNS = ("date", "site", "generated_kwh", "consumed_kwh", "payments_usd")
NUMERIC_COLUMNS = ("generated_kwh", "consumed_kwh", "payments_usd")

# A single site producing more than this in one day is a data-entry error, not a record.
MAX_PLAUSIBLE_KWH = 50_000.0


def _parse_number(value: object) -> float | str:
    """Return the float, or a short reason string if the value is unusable."""
    text = str(value).strip()
    if text == "":
        return "missing"
    try:
        number = float(text)
    except ValueError:
        return f"not a number ({text!r})"
    if not math.isfinite(number):
        return f"not finite ({text!r})"
    if number < 0:
        return f"negative ({text})"
    return number


def validate(rows: Sequence[Mapping[str, object]], first_row_number: int = 2) -> ValidationResult:
    """Split rows into valid readings and rejections. Every input row lands in exactly one."""
    valid: list[Reading] = []
    rejected: list[Rejection] = []
    seen: dict[tuple[date, str], int] = {}

    for offset, raw in enumerate(rows):
        row_number = first_row_number + offset
        reasons: list[str] = []
        raw_text = {key: str(value) for key, value in raw.items()}

        day: date | None = None
        date_text = str(raw.get("date", "")).strip()
        if date_text == "":
            reasons.append("date: missing")
        else:
            try:
                day = date.fromisoformat(date_text)
            except ValueError:
                reasons.append(f"date: not ISO YYYY-MM-DD ({date_text!r})")

        site = str(raw.get("site", "")).strip()
        if site == "":
            reasons.append("site: missing")

        numbers: dict[str, float] = {}
        for column in NUMERIC_COLUMNS:
            parsed = _parse_number(raw.get(column, ""))
            if isinstance(parsed, str):
                reasons.append(f"{column}: {parsed}")
            else:
                numbers[column] = parsed

        for column in ("generated_kwh", "consumed_kwh"):
            if numbers.get(column, 0.0) > MAX_PLAUSIBLE_KWH:
                reasons.append(f"{column}: implausibly large ({numbers[column]:g})")

        if day is not None and site and not reasons:
            key = (day, site)
            if key in seen:
                reasons.append(f"duplicate of row {seen[key]} ({day.isoformat()}, {site})")
            else:
                seen[key] = row_number

        if reasons:
            rejected.append(Rejection(row=row_number, reasons=tuple(reasons), raw=raw_text))
        else:
            assert day is not None
            valid.append(
                Reading(
                    row=row_number,
                    day=day,
                    site=site,
                    generated_kwh=numbers["generated_kwh"],
                    consumed_kwh=numbers["consumed_kwh"],
                    payments_usd=numbers["payments_usd"],
                )
            )

    assert len(valid) + len(rejected) == len(rows)
    return ValidationResult(valid=valid, rejected=rejected)
