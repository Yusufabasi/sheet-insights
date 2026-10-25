# Runbook

Draft. Items marked TODO need a live deployment to confirm.

## What runs
`sheet-insights run` once a day. It writes a report to `STATE_DIR/reports/` with status
`pending` (or `needs_review`) and exits `0` (pending) or `2` (needs review). It sends nothing.
A person then runs `sheet-insights approve <id> --by <name>`.

## Schedule
Example cron, 06:00 server time, logging to a file:

```
0 6 * * * cd /opt/sheet-insights && .venv/bin/sheet-insights run >> logs/run.log 2>&1
```

Monitoring: run `sheet-insights check` an hour later (e.g. from the same cron or an uptime
monitor). It exits `3` and prints `FAIL` if no report was created today (UTC), which catches a
run that crashed, never started, or ran on a dead host. Alert on any non-zero exit from
either command.

## Report states
| State | Meaning | Action |
|-------|---------|--------|
| `pending` | Summary passed the number audit | Review, then approve |
| `needs_review` | Summary failed the audit after all attempts (see `notes`) | Check the data and model, re-run; it cannot be approved |
| `approved` | Approved, publish not finished | Fix the sink/SMTP error, then `sheet-insights retry <id>`; steps already done (sheet row, email) are not repeated |
| `published` | Written to the output sheet and emailed | None |

## Common failures
- **`no valid readings`**: every row failed validation; open the sheet and check column names
  and formats.
- **Weather unavailable**: the report is still produced, with a note. No action needed.
- **Audit keeps failing**: look at `unsupported_numbers` in the report JSON; usually the model
  is rounding or adding a figure. Re-run, or check `SUMMARY_MODEL`.
- **Google 403/404**: the service account is not shared on the sheet, or the ID is wrong.

## Access and secrets
- Input service account: Viewer on the input sheet only, `spreadsheets.readonly` scope.
- Output service account: Editor on the output sheet only.
- Secrets come from environment variables or the host's secret manager, never from the repo.
  `.env` and `credentials/` are git-ignored.
- Rotate the service-account keys and the API key if a machine is lost or someone leaves.

## Rollback
Pipeline code is stateless apart from `STATE_DIR`. To roll back, redeploy the previous tag;
stored reports remain readable. A published row in the output sheet can be deleted by hand;
the input sheet is never modified.

## Backup and restore
`STATE_DIR` holds the audit trail (who approved what, when). Back it up daily.
TODO: document and test a restore.
