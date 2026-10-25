import pytest

from conftest import row
from sheet_insights.metrics import compute_metrics
from sheet_insights.validate import validate


def _metrics():
    rows = [
        row("2026-01-01", "A", "100", "80", "10"),
        row("2026-01-01", "B", "50", "40", "5"),
        row("2026-01-02", "A", "120", "90", "12"),
        row("2026-01-02", "B", "60", "45", "6"),
    ]
    return compute_metrics(validate(rows).valid)


def test_totals():
    totals = _metrics()["totals"]

    assert totals["generated_kwh"] == 330.0
    assert totals["consumed_kwh"] == 255.0
    assert totals["payments_usd"] == 33.0


def test_per_site_figures():
    site_a = _metrics()["sites"]["A"]

    assert site_a["generated_kwh"] == 220.0
    assert site_a["avg_daily_generated_kwh"] == 110.0


def test_day_over_day_trend_and_lowest_day():
    metrics = _metrics()

    assert metrics["period"]["site_count"] == 2
    assert metrics["trends"]["generation_vs_previous_complete_day_pct"] == 20.0
    assert metrics["lowest_generation_complete_day"] == {
        "date": "2026-01-01",
        "generated_kwh": 150.0,
    }


def test_incomplete_day_is_excluded_from_day_level_figures_but_not_totals():
    rows = [
        row("2026-01-01", "A", "100", "1", "1"),
        row("2026-01-01", "B", "100", "1", "1"),
        row("2026-01-02", "A", "100", "1", "1"),  # B missing: looks like a collapse
        row("2026-01-03", "A", "110", "1", "1"),
        row("2026-01-03", "B", "110", "1", "1"),
    ]

    metrics = compute_metrics(validate(rows).valid)

    assert metrics["incomplete_days"] == ["2026-01-02"]
    assert metrics["totals"]["generated_kwh"] == 520.0
    assert metrics["latest_complete_day"]["date"] == "2026-01-03"
    assert metrics["lowest_generation_complete_day"]["date"] == "2026-01-01"
    assert metrics["trends"]["generation_vs_previous_complete_day_pct"] == 10.0


def test_weekly_trend_needs_two_full_weeks():
    assert "avg_generation_last_7_vs_prior_7_days_pct" not in _metrics()["trends"]

    rows = [row(f"2026-01-{d:02d}", "A", str(100 + 10 * (d > 7)), "1", "1") for d in range(1, 15)]
    trends = compute_metrics(validate(rows).valid)["trends"]

    assert trends["avg_generation_last_7_vs_prior_7_days_pct"] == 10.0


def test_single_day_has_no_trend():
    metrics = compute_metrics(validate([row("2026-01-01", "A", "1", "1", "1")]).valid)

    assert metrics["trends"]["generation_vs_previous_complete_day_pct"] is None


def test_empty_input_raises():
    with pytest.raises(ValueError):
        compute_metrics([])
