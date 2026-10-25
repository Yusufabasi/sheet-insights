"""AI summary, constrained to the computed payload and checked by the number audit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from sheet_insights.audit import allowed_numbers, audit_summary

SYSTEM_PROMPT = """You write a short operations summary (at most 120 words, plain English) \
for a solar mini-grid operator, from a JSON payload of already-computed figures.

Rules:
- Use ONLY numbers that appear in the JSON, copied exactly as written. Never calculate, \
estimate, round, convert or add figures.
- If weather figures are present, you may mention them as a possible reason for a swing in \
generation. Say "possible", never "certain".
- If data_quality.rows_rejected is above zero, say that some rows were excluded from the figures.
- If incomplete_days is not empty, say those dates were left out of the day-to-day comparison \
because a site's reading was missing.
- "Latest day" and "lowest day" figures are for complete days only; say "latest complete day".
- Do not give advice or make promises. No headings, no bullet lists."""


class Summarizer(Protocol):
    def summarize(self, payload: dict[str, Any], feedback: str | None = None) -> str: ...


class AnthropicSummarizer:
    def __init__(self, model: str, api_key: str | None = None) -> None:
        self._model = model
        self._api_key = api_key

    def summarize(self, payload: dict[str, Any], feedback: str | None = None) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        content = json.dumps(payload, ensure_ascii=False)
        if feedback:
            content += f"\n\nYour previous attempt was rejected: {feedback}"
        message = client.messages.create(
            model=self._model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        return "".join(block.text for block in message.content if block.type == "text").strip()


class TemplateSummarizer:
    """Deterministic, offline summary. Used for demos and tests; every figure is copied."""

    def summarize(self, payload: dict[str, Any], feedback: str | None = None) -> str:
        period, totals = payload["period"], payload["totals"]
        latest = payload["latest_complete_day"]
        quality = payload["data_quality"]
        parts = [
            f"From {period['start']} to {period['end']} ({period['days']} days) the sites "
            f"generated {totals['generated_kwh']:,.1f} kWh and consumed "
            f"{totals['consumed_kwh']:,.1f} kWh, with payments of "
            f"{totals['payments_usd']:,.2f} USD.",
            f"On {latest['date']}, the latest complete day, generation was "
            f"{latest['generated_kwh']:,.1f} kWh.",
        ]
        change = payload["trends"].get("generation_vs_previous_complete_day_pct")
        if change is not None:
            direction = "up" if change >= 0 else "down"
            parts.append(f"That is {direction} {abs(change)}% on the previous complete day.")
        if payload["incomplete_days"]:
            parts.append(
                "Left out of the day-to-day comparison because a site's reading was missing: "
                + ", ".join(payload["incomplete_days"])
                + "."
            )
        if quality["rows_rejected"]:
            parts.append(
                f"{quality['rows_rejected']} of {quality['rows_received']} rows were excluded "
                "because they failed validation."
            )
        return " ".join(parts)


@dataclass(frozen=True)
class SummaryOutcome:
    text: str | None  # None when every attempt failed the audit
    attempts: int
    unsupported: tuple[str, ...]


def summarize_audited(
    summarizer: Summarizer, payload: dict[str, Any], max_attempts: int = 3
) -> SummaryOutcome:
    """Ask for a summary; accept it only if every figure in it is in the payload."""
    allowed = allowed_numbers(payload)
    feedback: str | None = None
    unsupported: tuple[str, ...] = ()
    for attempt in range(1, max_attempts + 1):
        text = summarizer.summarize(payload, feedback)
        result = audit_summary(text, allowed)
        if result.ok:
            return SummaryOutcome(text=text, attempts=attempt, unsupported=())
        unsupported = result.unsupported
        feedback = (
            "these figures are not in the data: " + ", ".join(unsupported) + ". "
            "Use only figures from the JSON."
        )
    return SummaryOutcome(text=None, attempts=max_attempts, unsupported=unsupported)
