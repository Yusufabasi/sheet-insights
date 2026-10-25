"""Inputs and outputs. The input side is read-only by construction (scope + Viewer share)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Protocol

from sheet_insights.approval import Report

READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
WRITE_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


class RowSource(Protocol):
    def read_rows(self) -> list[dict[str, str]]: ...


class ReportSink(Protocol):
    def write(self, report: Report) -> None: ...


class CsvSource:
    def __init__(self, path: Path) -> None:
        self._path = path

    def read_rows(self) -> list[dict[str, str]]:
        with self._path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))


class GoogleSheetSource:
    """Reads a worksheet with a read-only service account. Cell values stay as raw strings."""

    def __init__(self, spreadsheet_id: str, worksheet: str, credentials_path: Path) -> None:
        self._spreadsheet_id = spreadsheet_id
        self._worksheet = worksheet
        self._credentials_path = credentials_path

    def read_rows(self) -> list[dict[str, str]]:
        import gspread

        client = gspread.service_account(
            filename=str(self._credentials_path), scopes=[READONLY_SCOPE]
        )
        sheet = client.open_by_key(self._spreadsheet_id).worksheet(self._worksheet)
        return [
            {key: str(value) for key, value in record.items()}
            for record in sheet.get_all_records(numericise_ignore=["all"])
        ]


class LocalSink:
    """Writes the published report as JSON under out/. Used for the offline demo."""

    def __init__(self, out_dir: Path) -> None:
        self._out_dir = out_dir

    def write(self, report: Report) -> None:
        self._out_dir.mkdir(parents=True, exist_ok=True)
        target = self._out_dir / f"{report.id}.json"
        target.write_text(
            json.dumps(
                {
                    "id": report.id,
                    "period": report.payload["period"],
                    "summary": report.summary,
                    "approved_by": report.approved_by,
                    "approved_at": report.approved_at,
                    "rows_rejected": len(report.rejections),
                    "rejections": report.rejections,
                },
                indent=2,
                ensure_ascii=False,
            )
        )


class GoogleSheetSink:
    """Appends to a separate output spreadsheet; the input sheet is never written to."""

    def __init__(self, spreadsheet_id: str, credentials_path: Path) -> None:
        self._spreadsheet_id = spreadsheet_id
        self._credentials_path = credentials_path

    def write(self, report: Report) -> None:
        import gspread

        client = gspread.service_account(filename=str(self._credentials_path), scopes=[WRITE_SCOPE])
        book = client.open_by_key(self._spreadsheet_id)
        book.worksheet("Reports").append_row(
            [
                report.id,
                report.payload["period"]["end"],
                report.summary or "",
                report.approved_by or "",
                report.approved_at or "",
                len(report.rejections),
            ],
            value_input_option="RAW",
        )
        if report.rejections:
            rejected = book.worksheet("Rejected rows")
            rejected.append_rows(
                [
                    [report.id, r["row"], "; ".join(r["reasons"]), json.dumps(r["raw"])]
                    for r in report.rejections
                ],
                value_input_option="RAW",
            )
