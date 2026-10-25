from conftest import row
from sheet_insights.sheets import CsvSource
from sheet_insights.validate import validate


def test_sample_csv_flags_exactly_the_bad_rows(sample_csv):
    rows = CsvSource(sample_csv).read_rows()
    result = validate(rows)

    assert result.received == len(rows) == 19
    assert len(result.valid) == 15
    assert [r.row for r in result.rejected] == [14, 15, 19, 20]


def test_every_rejection_has_a_reason(sample_csv):
    result = validate(CsvSource(sample_csv).read_rows())
    reasons = {r.row: " ".join(r.reasons) for r in result.rejected}

    assert "negative" in reasons[14]
    assert "not a number" in reasons[15]
    assert "duplicate of row 18" in reasons[19]
    assert "date: missing" in reasons[20]


def test_multiple_problems_are_all_reported():
    result = validate([row("not-a-date", "", "x", "-1", "")])

    assert len(result.rejected[0].reasons) == 5


def test_rejects_non_finite_and_implausible_values():
    result = validate(
        [row("2026-01-01", "A", "nan", "inf", "1"), row("2026-01-02", "A", "1e9", "1", "1")]
    )

    assert len(result.valid) == 0
    assert any("not finite" in reason for reason in result.rejected[0].reasons)
    assert any("implausibly large" in reason for reason in result.rejected[1].reasons)


def test_row_numbers_follow_the_sheet_offset():
    result = validate([row("2026-01-01", "A", "1", "1", "1")], first_row_number=5)

    assert result.valid[0].row == 5


def test_zero_is_valid():
    result = validate([row("2026-01-01", "A", "0", "0", "0")])

    assert len(result.valid) == 1
