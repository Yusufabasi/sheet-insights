from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Protocol

from sheet_insights.approval import Report


class Notifier(Protocol):
    def send(self, subject: str, body: str) -> None: ...


def render_report(report: Report) -> tuple[str, str]:
    period = report.payload["period"]
    subject = f"Daily operations summary, {period['end']}"
    lines = [report.summary or "", ""]
    if report.rejections:
        lines.append(f"{len(report.rejections)} row(s) were excluded from the figures:")
        lines += [f"  row {r['row']}: {'; '.join(r['reasons'])}" for r in report.rejections]
        lines.append("")
    lines.append(f"Approved by {report.approved_by} at {report.approved_at}.")
    return subject, "\n".join(lines)


class ConsoleNotifier:
    def send(self, subject: str, body: str) -> None:
        print(f"--- EMAIL (not sent, SMTP not configured) ---\nSubject: {subject}\n\n{body}")


class SmtpNotifier:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        sender: str,
        recipients: tuple[str, ...],
    ) -> None:
        self._host, self._port = host, port
        self._user, self._password = user, password
        self._sender, self._recipients = sender, recipients

    def send(self, subject: str, body: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._sender
        message["To"] = ", ".join(self._recipients)
        message.set_content(body)
        with smtplib.SMTP(self._host, self._port, timeout=30) as smtp:
            smtp.starttls()
            if self._user:
                smtp.login(self._user, self._password)
            smtp.send_message(message)
