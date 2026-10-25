from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """Minimal .env loader. Real environment variables win over the file."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    input_source: str
    csv_path: Path
    input_spreadsheet_id: str
    input_worksheet: str
    input_credentials_path: Path
    output_spreadsheet_id: str
    output_credentials_path: Path
    latitude: float
    longitude: float
    summary_model: str
    summary_max_attempts: int
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    email_to: tuple[str, ...]
    state_dir: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env
        return cls(
            input_source=e.get("INPUT_SOURCE", "csv"),
            csv_path=Path(e.get("CSV_PATH", "data/sample_readings.csv")),
            input_spreadsheet_id=e.get("INPUT_SPREADSHEET_ID", ""),
            input_worksheet=e.get("INPUT_WORKSHEET", "Readings"),
            input_credentials_path=Path(
                e.get("INPUT_CREDENTIALS_PATH", "credentials/input-readonly.json")
            ),
            output_spreadsheet_id=e.get("OUTPUT_SPREADSHEET_ID", ""),
            output_credentials_path=Path(
                e.get("OUTPUT_CREDENTIALS_PATH", "credentials/output-writer.json")
            ),
            latitude=float(e.get("SITE_LATITUDE", "-1.6585")),
            longitude=float(e.get("SITE_LONGITUDE", "29.2205")),
            summary_model=e.get("SUMMARY_MODEL", "claude-haiku-5-5"),
            summary_max_attempts=int(e.get("SUMMARY_MAX_ATTEMPTS", "3")),
            smtp_host=e.get("SMTP_HOST", ""),
            smtp_port=int(e.get("SMTP_PORT", "587")),
            smtp_user=e.get("SMTP_USER", ""),
            smtp_password=e.get("SMTP_PASSWORD", ""),
            email_from=e.get("EMAIL_FROM", ""),
            email_to=tuple(a.strip() for a in e.get("EMAIL_TO", "").split(",") if a.strip()),
            state_dir=Path(e.get("STATE_DIR", "state")),
        )
