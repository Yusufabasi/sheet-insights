from pathlib import Path

import pytest

SAMPLE_CSV = Path(__file__).resolve().parent.parent / "data" / "sample_readings.csv"


@pytest.fixture
def sample_csv() -> Path:
    return SAMPLE_CSV


def row(day: str, site: str, gen: str, cons: str, pay: str) -> dict[str, str]:
    return {
        "date": day,
        "site": site,
        "generated_kwh": gen,
        "consumed_kwh": cons,
        "payments_usd": pay,
    }
