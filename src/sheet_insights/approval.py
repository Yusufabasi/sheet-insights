"""Human approval gate. Nothing is published unless a named person approved the report."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PENDING = "pending"
NEEDS_REVIEW = "needs_review"  # summary failed the number audit; cannot be approved as-is
APPROVED = "approved"
PUBLISHED = "published"


class ApprovalError(Exception):
    pass


@dataclass
class Report:
    id: str
    created_at: str
    status: str
    summary: str | None
    summary_attempts: int
    unsupported_numbers: list[str]
    payload: dict[str, Any]
    rejections: list[dict[str, Any]]
    notes: list[str] = field(default_factory=list)
    approved_by: str | None = None
    approved_at: str | None = None
    published_at: str | None = None
    # Publish steps are recorded one by one so a retry never repeats a completed side effect.
    sink_written: bool = False
    email_sent: bool = False


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ApprovalStore:
    """One JSON file per report under <state_dir>/reports/."""

    def __init__(self, state_dir: Path) -> None:
        self._dir = state_dir / "reports"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, report_id: str) -> Path:
        if not report_id.replace("-", "").replace("T", "").replace("Z", "").isalnum():
            raise ApprovalError(f"invalid report id {report_id!r}")
        return self._dir / f"{report_id}.json"

    def save(self, report: Report) -> None:
        path = self._path(report.id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False))
        tmp.replace(path)

    def get(self, report_id: str) -> Report:
        path = self._path(report_id)
        if not path.is_file():
            raise ApprovalError(f"no such report: {report_id}")
        return Report(**json.loads(path.read_text()))

    def list(self, status: str | None = None) -> list[Report]:
        reports = [Report(**json.loads(p.read_text())) for p in sorted(self._dir.glob("*.json"))]
        return [r for r in reports if status is None or r.status == status]

    def approve(self, report_id: str, approver: str) -> Report:
        if not approver.strip():
            raise ApprovalError("an approver name is required")
        report = self.get(report_id)
        if report.status != PENDING:
            raise ApprovalError(
                f"report {report_id} is {report.status}, only pending can be approved"
            )
        if not report.summary:
            raise ApprovalError(f"report {report_id} has no summary to approve")
        report.status = APPROVED
        report.approved_by = approver.strip()
        report.approved_at = _now()
        self.save(report)
        return report

    def mark_published(self, report_id: str) -> Report:
        report = self.get(report_id)
        if report.status != APPROVED:
            raise ApprovalError(f"report {report_id} is {report.status}, not approved")
        report.status = PUBLISHED
        report.published_at = _now()
        self.save(report)
        return report
