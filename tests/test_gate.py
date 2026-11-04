from datetime import datetime, timezone

from shipgate.gate import HOLD, NO_SHIP, SHIP, GateOutcome, decide, evaluate, format_value, passes
from shipgate.providers import Completion
from shipgate.runner import run
from shipgate.scoring import score_case
from shipgate.spec import Candidate, Case, Gate, Spec


def outcome(severity, ok):
    g = Gate("g", "desc", "accuracy", ">=", 0.9, severity)
    return GateOutcome(g, 0.95 if ok else 0.5, ok)


def test_verdict_rules():
    assert decide([outcome("hard", True), outcome("soft", True)]) == SHIP
    assert decide([outcome("hard", True), outcome("soft", False)]) == HOLD
    assert decide([outcome("hard", False), outcome("soft", True)]) == NO_SHIP
    # a hard failure can never be rescued by passing everything else
    assert decide([outcome("hard", False), outcome("soft", False)]) == NO_SHIP


def test_passes_operators_and_float_edge():
    assert passes(">=", 34 / 40, 0.85)
    assert passes("<=", 0.0, 0.0)
    assert not passes(">", 0.5, 0.5)
    assert not passes("<", 0.5, 0.5)
    assert passes("==", 1.0, 1.0)


def test_format_value():
    assert format_value("accuracy", 0.875) == "87.5%"
    assert format_value("cost_per_1k", 0.2) == "$0.20"
    assert format_value("p95_latency_s", 1.234) == "1.23s"
    assert format_value("forbidden_outcomes", 2.0) == "2"


FIELDS = ["label"]
CAND_GOOD = Candidate("good", "Good", "p", "m", 1.0, 1.0, mock_profile="good")
CAND_BAD = Candidate("bad", "Bad", "p", "m", 1.0, 1.0, mock_profile="bad")
CASES = [Case(f"c{i}", f"in{i}", {"label": "x"}) for i in range(4)]
GATES = [Gate("acc", "Accuracy at least 75%", "accuracy", ">=", 0.75, "hard")]
SPEC = Spec("T", "", FIELDS, [CAND_GOOD, CAND_BAD], CASES, GATES, [])


class ScriptedProvider:
    name, simulated = "scripted", True

    def complete(self, candidate, user_input):
        text = '{"label": "x"}' if candidate.id == "good" else '{"label": "y"}'
        return Completion(text, 10, 5, 0.5, simulated=True)


def test_runner_end_to_end_with_scripted_provider():
    fixed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    result = run(SPEC, ScriptedProvider(), now=lambda: fixed)
    verdicts = {e.candidate.id: e.verdict for e in result.evaluations}
    assert verdicts == {"good": SHIP, "bad": NO_SHIP}
    assert result.simulated is True and result.n_cases == 4
    assert result.generated_at == "2026-01-02T03:04:05+00:00"
    bad = result.evaluations[1]
    assert bad.reasons == ['Failed hard gate "Accuracy at least 75%": 0.0% (needs >= 75.0%)']


def test_runner_reports_progress():
    calls = []
    run(SPEC, ScriptedProvider(), progress=lambda cid, done, total: calls.append((cid, done, total)))
    assert calls[0] == ("good", 1, 4) and calls[-1] == ("bad", 4, 4) and len(calls) == 8


def test_evaluate_lists_all_passed_when_clean():
    results = [score_case(c, FIELDS, '{"label": "x"}', 1, 1, 0.1) for c in CASES]
    ev = evaluate(SPEC, CAND_GOOD, results)
    assert ev.reasons == ["All gates passed."] and ev.failed == []
