from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime

import httpx

from sheet_insights.approval import (
    APPROVED,
    NEEDS_REVIEW,
    PENDING,
    ApprovalError,
    ApprovalStore,
    Report,
)
from sheet_insights.metrics import compute_metrics
from sheet_insights.notify import Notifier, render_report
from sheet_insights.sheets import ReportSink, RowSource
from sheet_insights.summarize import Summarizer, summarize_audited
from sheet_insights.validate import validate

log = logging.getLogger(__name__)

WeatherFetcher = Callable[[date, date], dict[str, dict[str, float]]]


def run_pipeline(
    source: RowSource,
    summarizer: Summarizer,
    store: ApprovalStore,
    weather: WeatherFetcher | None = None,
    max_attempts: int = 3,
    now: datetime | None = None,
) -> Report:
    """Read -> validate -> compute -> (weather) -> audited summary -> save as pending."""
    now = now or datetime.now(UTC)
    result = validate(source.read_rows())
    payload = compute_metrics(result.valid)
    payload["data_quality"] = {
        "rows_received": result.received,
        "rows_valid": len(result.valid),
        "rows_rejected": len(result.rejected),
    }

    notes: list[str] = []
    if weather is not None:
        start = date.fromisoformat(payload["period"]["start"])
        try:
            by_day = weather(start, now.date())
        except (httpx.HTTPError, KeyError, ValueError) as error:
            log.warning("weather unavailable: %s", error)
            notes.append(f"weather unavailable: {error}")
        else:
            figures = {
                label: by_day[payload[key]["date"]]
                for label, key in (
                    ("latest_day", "latest_complete_day"),
                    ("lowest_generation_day", "lowest_generation_complete_day"),
                )
                if payload[key]["date"] in by_day
            }
            if figures:
                payload["weather"] = figures

    outcome = summarize_audited(summarizer, payload, max_attempts)
    if outcome.text is None:
        notes.append(
            "summary failed the number audit after "
            f"{outcome.attempts} attempts; unsupported figures: {', '.join(outcome.unsupported)}"
        )

    report = Report(
        id=now.strftime("run-%Y%m%dT%H%M%SZ"),
        created_at=now.isoformat(timespec="seconds"),
        status=PENDING if outcome.text else NEEDS_REVIEW,
        summary=outcome.text,
        summary_attempts=outcome.attempts,
        unsupported_numbers=list(outcome.unsupported),
        payload=payload,
        rejections=[
            {"row": r.row, "reasons": list(r.reasons), "raw": r.raw} for r in result.rejected
        ],
        notes=notes,
    )
    store.save(report)
    return report


def approve_and_publish(
    report_id: str,
    approver: str,
    store: ApprovalStore,
    sink: ReportSink,
    notifier: Notifier,
) -> Report:
    """Approve (raises unless pending with a summary), write the output sheet, send the email."""
    store.approve(report_id, approver)
    return publish_approved(report_id, store, sink, notifier)


def publish_approved(
    report_id: str, store: ApprovalStore, sink: ReportSink, notifier: Notifier
) -> Report:
    """Finish publishing an approved report. Safe to re-run after a sink or SMTP failure:
    a step that already succeeded is not repeated."""
    report = store.get(report_id)
    if report.status != APPROVED:
        raise ApprovalError(f"report {report_id} is {report.status}, not approved")
    if not report.sink_written:
        sink.write(report)
        report.sink_written = True
        store.save(report)
    if not report.email_sent:
        subject, body = render_report(report)
        notifier.send(subject, body)
        report.email_sent = True
        store.save(report)
    return store.mark_published(report_id)
