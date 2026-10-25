"""Number audit: reject any AI text containing a figure that was not in the computed payload."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class AuditResult:
    ok: bool
    unsupported: tuple[str, ...]


def allowed_numbers(payload: Any) -> set[float]:
    """Every numeric leaf in the payload, plus the parts of any ISO date strings in it.

    Signs are dropped: "down 12.5%" is supported by a metric of -12.5.
    """
    found: set[float] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            found.add(abs(float(node)))
        elif isinstance(node, str):
            for year, month, day in _ISO_DATE.findall(node):
                found.update({float(year), float(month), float(day)})
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(key)
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(payload)
    return found


def _decimals(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def audit_summary(text: str, allowed: set[float]) -> AuditResult:
    """A figure is supported if some allowed number rounds to it at the precision shown."""
    without_dates = _ISO_DATE.sub(" ", text)
    unsupported: list[str] = []
    for match in _NUMBER.findall(without_dates):
        cleaned = match.replace(",", "")
        value = float(cleaned)
        places = _decimals(cleaned)
        if not any(math.isclose(round(a, places), value, abs_tol=1e-9) for a in allowed):
            unsupported.append(match)
    return AuditResult(ok=not unsupported, unsupported=tuple(unsupported))
