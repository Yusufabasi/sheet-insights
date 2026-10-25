from sheet_insights.audit import allowed_numbers, audit_summary
from sheet_insights.summarize import summarize_audited

PAYLOAD = {
    "period": {"start": "2026-10-12", "end": "2026-10-19", "days": 8},
    "totals": {"generated_kwh": 1234.56, "payments_usd": 9000.0},
    "trends": {"generation_vs_previous_day_pct": -12.5},
}


def test_accepts_figures_from_the_payload():
    text = "Generation was 1,234.6 kWh over 8 days, down 12.5% on the day, payments 9,000 USD."

    assert audit_summary(text, allowed_numbers(PAYLOAD)).ok


def test_rejects_an_invented_figure():
    result = audit_summary("Generation was 1,300 kWh.", allowed_numbers(PAYLOAD))

    assert not result.ok
    assert result.unsupported == ("1,300",)


def test_rounding_is_checked_at_the_precision_shown():
    allowed = allowed_numbers(PAYLOAD)

    assert audit_summary("1,234.56 kWh", allowed).ok
    assert audit_summary("1,235 kWh", allowed).ok
    assert not audit_summary("1,234.7 kWh", allowed).ok


def test_iso_dates_and_their_parts_are_allowed():
    allowed = allowed_numbers(PAYLOAD)

    assert audit_summary("From 2026-10-12 to 2026-10-19.", allowed).ok
    assert audit_summary("On the 19 the output dipped.", allowed).ok


def test_sign_is_ignored_both_ways():
    assert audit_summary("down 12.5%", allowed_numbers(PAYLOAD)).ok


class _Scripted:
    def __init__(self, replies):
        self._replies = iter(replies)
        self.feedback = []

    def summarize(self, payload, feedback=None):
        self.feedback.append(feedback)
        return next(self._replies)


def test_retries_with_feedback_then_accepts():
    summarizer = _Scripted(["Output was 777 kWh.", "Output was 1,234.56 kWh."])

    outcome = summarize_audited(summarizer, PAYLOAD, max_attempts=3)

    assert outcome.text == "Output was 1,234.56 kWh."
    assert outcome.attempts == 2
    assert "777" in summarizer.feedback[1]


def test_gives_up_after_max_attempts():
    outcome = summarize_audited(_Scripted(["777 kWh"] * 3), PAYLOAD, max_attempts=3)

    assert outcome.text is None
    assert outcome.attempts == 3
    assert outcome.unsupported == ("777",)
