"""All arithmetic lives here. The AI never calculates; it only describes this output.

Day-level figures (latest day, lowest day, trends) use only *complete* days, where every site
has a valid reading. A day missing a site's reading (because the row was rejected) would look
like a collapse in generation, so it is excluded from those figures and listed instead.
Period totals and per-site figures use every valid reading.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sheet_insights.models import Reading


def _pct_change(new: float, old: float) -> float | None:
    if old == 0:
        return None
    return round((new - old) / old * 100, 1)


def _daily_totals(readings: list[Reading], attr: str) -> dict[date, float]:
    totals: dict[date, float] = defaultdict(float)
    for reading in readings:
        totals[reading.day] += getattr(reading, attr)
    return dict(totals)


def _window_avg(by_day: dict[date, float], end: date, days: int) -> float | None:
    """Average over the days in (end-days, end] that exist in by_day, or None if none do."""
    values = [by_day[d] for i in range(days) if (d := end - timedelta(days=i)) in by_day]
    return math.fsum(values) / len(values) if values else None


def compute_metrics(readings: list[Reading]) -> dict[str, Any]:
    """Return a JSON-able payload of computed numbers. Raises ValueError on empty input."""
    if not readings:
        raise ValueError("no valid readings to compute metrics from")

    all_days = sorted({reading.day for reading in readings})
    sites_seen = {reading.site for reading in readings}
    sites_by_day: dict[date, set[str]] = defaultdict(set)
    for reading in readings:
        sites_by_day[reading.day].add(reading.site)
    complete = [d for d in all_days if sites_by_day[d] == sites_seen]
    incomplete = [d for d in all_days if d not in set(complete)]
    day_level = complete or all_days  # fall back so a report is still possible

    complete_readings = [r for r in readings if r.day in set(day_level)]
    generated_all = _daily_totals(readings, "generated_kwh")
    consumed_all = _daily_totals(readings, "consumed_kwh")
    payments_all = _daily_totals(readings, "payments_usd")
    generated = _daily_totals(complete_readings, "generated_kwh")
    consumed = _daily_totals(complete_readings, "consumed_kwh")
    payments = _daily_totals(complete_readings, "payments_usd")

    sites: dict[str, dict[str, float]] = {}
    for site in sorted(sites_seen):
        own = [reading for reading in readings if reading.site == site]
        own_days = len({reading.day for reading in own})
        site_generated = math.fsum(reading.generated_kwh for reading in own)
        site_payments = math.fsum(reading.payments_usd for reading in own)
        sites[site] = {
            "days_reported": own_days,
            "generated_kwh": round(site_generated, 1),
            "consumed_kwh": round(math.fsum(reading.consumed_kwh for reading in own), 1),
            "payments_usd": round(site_payments, 2),
            "avg_daily_generated_kwh": round(site_generated / own_days, 1),
            "avg_daily_payments_usd": round(site_payments / own_days, 2),
        }

    latest = day_level[-1]
    previous = day_level[-2] if len(day_level) > 1 else None
    trends: dict[str, float | None] = {
        "generation_vs_previous_complete_day_pct": (
            _pct_change(generated[latest], generated[previous]) if previous else None
        ),
        "payments_vs_previous_complete_day_pct": (
            _pct_change(payments[latest], payments[previous]) if previous else None
        ),
    }
    if len(day_level) >= 14:
        recent = _window_avg(generated, latest, 7)
        prior = _window_avg(generated, latest - timedelta(days=7), 7)
        if recent is not None and prior is not None:
            trends["avg_generation_last_7_vs_prior_7_days_pct"] = _pct_change(recent, prior)

    lowest = min(day_level, key=generated.__getitem__)

    return {
        "period": {
            "start": all_days[0].isoformat(),
            "end": all_days[-1].isoformat(),
            "days": len(all_days),
            "site_count": len(sites_seen),
        },
        "incomplete_days": [d.isoformat() for d in incomplete],
        "totals": {
            "generated_kwh": round(math.fsum(generated_all.values()), 1),
            "consumed_kwh": round(math.fsum(consumed_all.values()), 1),
            "payments_usd": round(math.fsum(payments_all.values()), 2),
        },
        "latest_complete_day": {
            "date": latest.isoformat(),
            "generated_kwh": round(generated[latest], 1),
            "consumed_kwh": round(consumed[latest], 1),
            "payments_usd": round(payments[latest], 2),
        },
        "lowest_generation_complete_day": {
            "date": lowest.isoformat(),
            "generated_kwh": round(generated[lowest], 1),
        },
        "trends": trends,
        "sites": sites,
    }
