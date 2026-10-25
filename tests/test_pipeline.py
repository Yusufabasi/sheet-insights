from datetime import UTC, datetime

import httpx
import pytest

from sheet_insights.approval import (
    APPROVED,
    NEEDS_REVIEW,
    PENDING,
    PUBLISHED,
    ApprovalError,
    ApprovalStore,
)
from sheet_insights.pipeline import approve_and_publish, run_pipeline
from sheet_insights.sheets import CsvSource
from sheet_insights.summarize import TemplateSummarizer

NOW = datetime(2026, 10, 20, 6, 0, tzinfo=UTC)


class _Sink:
    def __init__(self):
        self.written = []

    def write(self, report):
        self.written.append(report.id)


class _Notifier:
    def __init__(self):
        self.sent = []

    def send(self, subject, body):
        self.sent.append((subject, body))


class _BadSummarizer:
    def summarize(self, payload, feedback=None):
        return "Generation was 99,999 kWh."


def _run(sample_csv, tmp_path, **kwargs):
    store = ApprovalStore(tmp_path)
    report = run_pipeline(
        CsvSource(sample_csv),
        kwargs.pop("summarizer", TemplateSummarizer()),
        store,
        now=NOW,
        **kwargs,
    )
    return store, report


def test_run_leaves_a_pending_report_and_sends_nothing(sample_csv, tmp_path):
    store, report = _run(sample_csv, tmp_path)

    assert report.status == PENDING
    assert report.payload["data_quality"] == {
        "rows_received": 19,
        "rows_valid": 15,
        "rows_rejected": 4,
    }
    assert [r["row"] for r in report.rejections] == [14, 15, 19, 20]
    assert store.get(report.id).status == PENDING


def test_approve_publishes_to_sink_and_notifier(sample_csv, tmp_path):
    store, report = _run(sample_csv, tmp_path)
    sink, notifier = _Sink(), _Notifier()

    published = approve_and_publish(report.id, "Jane", store, sink, notifier)

    assert published.status == PUBLISHED
    assert published.approved_by == "Jane"
    assert sink.written == [report.id]
    assert len(notifier.sent) == 1
    assert "row 14" in notifier.sent[0][1]


def test_cannot_approve_twice(sample_csv, tmp_path):
    store, report = _run(sample_csv, tmp_path)
    approve_and_publish(report.id, "Jane", store, _Sink(), _Notifier())

    with pytest.raises(ApprovalError):
        store.approve(report.id, "Jane")


def test_approver_name_is_required(sample_csv, tmp_path):
    store, report = _run(sample_csv, tmp_path)

    with pytest.raises(ApprovalError):
        store.approve(report.id, "  ")
    assert store.get(report.id).status == PENDING


def test_failed_audit_cannot_be_approved_or_published(sample_csv, tmp_path):
    store, report = _run(sample_csv, tmp_path, summarizer=_BadSummarizer())
    sink, notifier = _Sink(), _Notifier()

    assert report.status == NEEDS_REVIEW
    assert report.summary is None
    with pytest.raises(ApprovalError):
        approve_and_publish(report.id, "Jane", store, sink, notifier)
    assert sink.written == [] and notifier.sent == []


def test_weather_outage_does_not_stop_the_report(sample_csv, tmp_path):
    def broken(start, today):
        raise httpx.ConnectError("offline")

    _, report = _run(sample_csv, tmp_path, weather=broken)

    assert report.status == PENDING
    assert "weather" not in report.payload
    assert any("weather unavailable" in note for note in report.notes)


def test_weather_is_attached_when_available(sample_csv, tmp_path):
    def fake(start, today):
        return {
            "2026-10-19": {"solar_radiation_mj_m2": 18.4},
            "2026-10-16": {"precipitation_mm": 22.0},
        }

    _, report = _run(sample_csv, tmp_path, weather=fake)

    assert report.payload["weather"]["latest_day"] == {"solar_radiation_mj_m2": 18.4}
    assert report.payload["weather"]["lowest_generation_day"] == {"precipitation_mm": 22.0}


def test_report_id_cannot_escape_the_state_dir(tmp_path):
    with pytest.raises(ApprovalError):
        ApprovalStore(tmp_path).get("../../etc/passwd")


def test_status_constants_are_distinct():
    assert len({PENDING, NEEDS_REVIEW, APPROVED, PUBLISHED}) == 4
