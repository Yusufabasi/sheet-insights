from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from sheet_insights.approval import ApprovalError, ApprovalStore
from sheet_insights.config import Settings, load_dotenv
from sheet_insights.notify import ConsoleNotifier, Notifier, SmtpNotifier
from sheet_insights.pipeline import approve_and_publish, publish_approved, run_pipeline
from sheet_insights.sheets import (
    CsvSource,
    GoogleSheetSink,
    GoogleSheetSource,
    LocalSink,
    ReportSink,
    RowSource,
)
from sheet_insights.summarize import AnthropicSummarizer, Summarizer, TemplateSummarizer
from sheet_insights.weather import fetch_weather


def _source(settings: Settings) -> RowSource:
    if settings.input_source == "google":
        return GoogleSheetSource(
            settings.input_spreadsheet_id,
            settings.input_worksheet,
            settings.input_credentials_path,
        )
    return CsvSource(settings.csv_path)


def _sink(settings: Settings) -> ReportSink:
    if settings.input_source == "google" and settings.output_spreadsheet_id:
        return GoogleSheetSink(settings.output_spreadsheet_id, settings.output_credentials_path)
    return LocalSink(Path("out"))


def _notifier(settings: Settings) -> Notifier:
    if settings.smtp_host and settings.email_from and settings.email_to:
        return SmtpNotifier(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.email_from,
            settings.email_to,
        )
    return ConsoleNotifier()


def _cmd_run(args: argparse.Namespace, settings: Settings, store: ApprovalStore) -> int:
    summarizer: Summarizer
    weather = None
    if args.offline:
        summarizer = TemplateSummarizer()
    else:
        summarizer = AnthropicSummarizer(
            settings.summary_model, os.environ.get("ANTHROPIC_API_KEY")
        )
        weather = partial(fetch_weather, settings.latitude, settings.longitude)
    report = run_pipeline(
        _source(settings),
        summarizer,
        store,
        weather=weather,
        max_attempts=settings.summary_max_attempts,
    )
    print(f"{report.id}: {report.status}")
    print(f"rows rejected: {len(report.rejections)}")
    for note in report.notes:
        print(f"note: {note}")
    if report.summary:
        print(f"\n{report.summary}\n\nApprove with: sheet-insights approve {report.id} --by <name>")
    return 0 if report.summary else 2


def _cmd_pending(_: argparse.Namespace, __: Settings, store: ApprovalStore) -> int:
    for report in store.list():
        print(f"{report.id}  {report.status}")
    return 0


def _cmd_approve(args: argparse.Namespace, settings: Settings, store: ApprovalStore) -> int:
    report = approve_and_publish(
        args.report_id, args.by, store, _sink(settings), _notifier(settings)
    )
    print(f"{report.id}: {report.status} (approved by {report.approved_by})")
    return 0


def _cmd_retry(args: argparse.Namespace, settings: Settings, store: ApprovalStore) -> int:
    report = publish_approved(args.report_id, store, _sink(settings), _notifier(settings))
    print(f"{report.id}: {report.status}")
    return 0


def _cmd_check(_: argparse.Namespace, __: Settings, store: ApprovalStore) -> int:
    """Healthcheck for a scheduler or monitor: non-zero if no report was created today (UTC)."""
    today = datetime.now(UTC).date().isoformat()
    if any(r.created_at.startswith(today) for r in store.list()):
        print(f"ok: a report exists for {today}")
        return 0
    print(f"FAIL: no report created on {today}", file=sys.stderr)
    return 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sheet-insights")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="build a report and leave it pending approval")
    run.add_argument("--offline", action="store_true", help="no AI or weather calls (demo)")
    commands.add_parser("pending", help="list reports and their status")
    approve = commands.add_parser("approve", help="approve a pending report and publish it")
    approve.add_argument("report_id")
    approve.add_argument("--by", required=True, help="name of the person approving")
    retry = commands.add_parser("retry", help="finish publishing an approved report")
    retry.add_argument("report_id")
    commands.add_parser("check", help="exit non-zero if no report was created today")
    args = parser.parse_args(argv)

    load_dotenv(Path(".env"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    store = ApprovalStore(settings.state_dir)
    handlers = {
        "run": _cmd_run,
        "pending": _cmd_pending,
        "approve": _cmd_approve,
        "retry": _cmd_retry,
        "check": _cmd_check,
    }
    try:
        return handlers[args.command](args, settings, store)
    except ApprovalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
