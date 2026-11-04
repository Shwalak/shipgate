import re
from pathlib import Path

from shipgate.gate import NO_SHIP, SHIP, recommend
from shipgate.providers import Completion, SimulatedProvider
from shipgate.report import render_report
from shipgate.runner import run
from shipgate.spec import Candidate, Case, Gate, Spec, load_spec

SPEC_PATH = Path(__file__).parent.parent / "examples" / "ticket-triage" / "spec.yaml"


def example_result():
    return run(load_spec(SPEC_PATH), SimulatedProvider())


def test_report_shows_verdicts_banner_and_recommendation():
    html = render_report(example_result())
    assert "Simulated run: not real model results" in html
    for verdict in ("SHIP", "HOLD", "NO-SHIP"):
        assert f'class="pill {verdict}"' in html
    assert "Recommended: Rubric prompt v2 (adds safety rule), small model." in html


def test_report_is_static_and_self_contained():
    html = render_report(example_result())
    assert "<script" not in html.lower()
    assert not re.search(r"(src|href)=[\"']https?://", html)
    assert "@import" not in html and "url(" not in html


def test_report_escapes_untrusted_text():
    evil = "<script>alert(1)</script>"
    cand = Candidate("c", evil, "p", "m", 1, 1, mock_profile="x")
    spec = Spec(evil, evil, ["label"], [cand], [Case("c1", evil, {"label": "a"}, [evil])],
                [Gate("g", evil, "accuracy", ">=", 0.5, "hard")], [])

    class P:
        name, simulated = "p", False

        def complete(self, candidate, user_input):
            return Completion(evil, 1, 1, 0.1)

    html = render_report(run(spec, P()))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_live_report_has_no_simulated_banner():
    cand = Candidate("c", "C", "p", "m", 1, 1)
    spec = Spec("F", "", ["label"], [cand], [Case("c1", "in", {"label": "a"})], [Gate("g", "G", "accuracy", ">=", 0.5, "hard")], [])

    class P:
        name, simulated = "anthropic", False

        def complete(self, candidate, user_input):
            return Completion('{"label": "a"}', 1, 1, 0.1)

    html = render_report(run(spec, P()))
    assert "Simulated run" not in html and "Live (anthropic)" in html


def test_recommend_picks_cheapest_shippable_else_explains():
    result = example_result()
    best, msg = recommend(result.evaluations)
    assert best is not None and best.candidate.id == "rubric_v2" and "cheapest" in msg
    only_failing = [e for e in result.evaluations if e.verdict == NO_SHIP]
    none, msg = recommend(only_failing)
    assert none is None and "fails at least one hard gate" in msg
    on_hold = [e for e in result.evaluations if e.candidate.id == "strong"]
    none, msg = recommend(on_hold)
    assert none is None and "pending a decision" in msg
