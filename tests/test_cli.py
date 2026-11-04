import io
import json
from pathlib import Path

from shipgate.cli import _confirm_live, main

SPEC = str(Path(__file__).parent.parent / "examples" / "ticket-triage" / "spec.yaml")


def test_validate_ok(capsys):
    assert main(["validate", SPEC]) == 0
    out = capsys.readouterr().out
    assert "48 cases" in out and "4 candidates" in out and "7 gates (3 hard, 4 soft)" in out


def test_validate_reports_spec_errors_with_exit_code_2(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("feature: {name: x}\nfields: [a]\n", encoding="utf-8")
    assert main(["validate", str(bad)]) == 2
    assert "error:" in capsys.readouterr().err


def test_run_writes_results_and_labels_simulated(tmp_path, capsys):
    assert main(["run", SPEC, "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "SIMULATED" in out and "rubric_v2  SHIP" in out
    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert data["simulated"] is True and data["n_cases"] == 48
    assert {e["candidate"]["id"]: e["verdict"] for e in data["evaluations"]}["strong"] == "HOLD"


def test_live_refuses_without_confirmation_and_sends_nothing(monkeypatch, capsys):
    # Non-interactive stdin and no --yes: must abort before any provider is built.
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["run", SPEC, "--live"]) == 1
    assert "Aborted. Nothing was sent." in capsys.readouterr().err


def test_live_without_key_fails_clearly(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["run", SPEC, "--live", "--yes"]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_confirm_live_states_the_call_count():
    err = io.StringIO()
    assert _confirm_live(192, assume_yes=True, out=err) is True
    assert "192 billable API calls" in err.getvalue()
