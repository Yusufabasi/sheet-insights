import pytest

from sheet_insights.approval import APPROVED, PUBLISHED, ApprovalError
from sheet_insights.cli import main
from sheet_insights.pipeline import approve_and_publish, publish_approved
from test_pipeline import _Notifier, _run, _Sink


class _FlakyNotifier(_Notifier):
    def __init__(self):
        super().__init__()
        self.fail = True

    def send(self, subject, body):
        if self.fail:
            raise OSError("smtp down")
        super().send(subject, body)


def test_retry_does_not_repeat_a_completed_sink_write(sample_csv, tmp_path):
    store, report = _run(sample_csv, tmp_path)
    sink, notifier = _Sink(), _FlakyNotifier()

    with pytest.raises(OSError):
        approve_and_publish(report.id, "Jane", store, sink, notifier)
    assert store.get(report.id).status == APPROVED

    notifier.fail = False
    published = publish_approved(report.id, store, sink, notifier)

    assert published.status == PUBLISHED
    assert sink.written == [report.id]  # written once, not twice
    assert len(notifier.sent) == 1


def test_retry_refuses_a_report_that_was_never_approved(sample_csv, tmp_path):
    store, report = _run(sample_csv, tmp_path)

    with pytest.raises(ApprovalError):
        publish_approved(report.id, store, _Sink(), _Notifier())


def test_check_fails_when_no_report_today_and_passes_after_a_run(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))

    assert main(["check"]) == 3
    assert "FAIL" in capsys.readouterr().err

    csv = tmp_path / "readings.csv"
    csv.write_text("date,site,generated_kwh,consumed_kwh,payments_usd\n2026-01-01,A,1,1,1\n")
    monkeypatch.setenv("CSV_PATH", str(csv))
    assert main(["run", "--offline"]) == 0
    assert main(["check"]) == 0
