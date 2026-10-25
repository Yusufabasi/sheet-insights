# Sheet Insights

A scheduled pipeline that reads a Google Sheet of daily energy and payment readings, validates
every row, computes the numbers in code, has an AI write a short summary, **audits that summary
against the computed numbers**, and waits for a named human to approve before anything is
written or emailed.

Built as a worked example of "connect a Google Sheet to an API and add a simple AI summary",
with the controls an operator would want around it: nothing silently dropped, nothing
unreviewed sent, nothing invented by the model.

## How it works

```
Sheet (read-only) -> validate -> metrics (code) -> + weather -> AI summary -> number audit
                         |                                                       |
                  rejected rows                                          pass: PENDING
                  kept with reasons                                      fail x3: NEEDS_REVIEW
                                                                                |
                                          named human: approve  <---------------+
                                                   |
                                    output sheet + email (only now)
```

| Step | Module | What it guarantees |
|------|--------|--------------------|
| Read | `sheets.py` | Input uses a read-only scope on a service account shared as Viewer; output goes to a *separate* sheet |
| Validate | `validate.py` | Every row ends up valid or rejected with all its reasons; counts always add up |
| Compute | `metrics.py` | All arithmetic is code. Days where a site's row was rejected are excluded from day-level figures and listed, so a missing row never looks like an outage |
| Weather | `weather.py` | Open-Meteo solar radiation and rain, to explain swings. An outage degrades the report, it does not stop it |
| Summarise | `summarize.py` | The model only sees the computed JSON and is told to copy figures exactly |
| Audit | `audit.py` | Any figure in the summary not present in the payload (at the precision shown) rejects it; retried with feedback, then marked `needs_review` |
| Approve | `approval.py` | Only a `pending` report with a summary can be approved, by a named person; every transition is stored |
| Publish | `pipeline.py` | Output sheet write and email happen only after approval |

## Try it (no accounts needed)

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/sheet-insights run --offline        # sample data, deterministic summary
.venv/bin/sheet-insights pending
.venv/bin/sheet-insights approve <report-id> --by "Your Name"
.venv/bin/pytest
```

`data/sample_readings.csv` contains deliberately bad rows (negative value, text in a number
column, a duplicate, a missing date) so you can see the rejections.

## Running for real

Copy `.env.example` to `.env`, set `INPUT_SOURCE=google`, the sheet IDs and credentials paths,
`ANTHROPIC_API_KEY`, and SMTP settings. Then `sheet-insights run` (schedule it, see
[the runbook](docs/RUNBOOK.md)) and approve from the CLI.

## Design decisions

- **The AI never does maths.** It receives computed figures and describes them. This is the
  difference between a summary you can send to finance and one you have to re-check.
- **Audit by number, not by trust.** A cheap, deterministic check catches the failure that
  matters (an invented or mis-copied figure) without a second model call.
- **Reject loudly.** Bad rows are never dropped; they are listed in the report and the email.
- **Human gate before any outward action.** Matches the rule that a person reviews AI output
  that touches money.
- **Ports and adapters.** `RowSource`, `ReportSink`, `Summarizer`, `Notifier` are small
  protocols, so the CSV demo, Google, and the AI provider swap without touching the pipeline.

## Status

Working and tested offline (32 tests). The Open-Meteo call has been checked against the live
API. **Not yet exercised against live services:** Google Sheets read/write, the Anthropic call,
and SMTP; they need credentials. `sheet-insights check` and `retry` cover failure alerting and
safe re-publishing. The same pipeline rebuilt in n8n, with a comparison, is in the companion
repo `sheet-insights-n8n` (see its `COMPARISON.md`).
