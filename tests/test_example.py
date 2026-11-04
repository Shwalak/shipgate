"""The bundled example is the demo people will run first, so it must keep working."""

from pathlib import Path

from shipgate.gate import HOLD, NO_SHIP, SHIP
from shipgate.providers import SimulatedProvider
from shipgate.runner import run
from shipgate.spec import load_spec

SPEC_PATH = Path(__file__).parent.parent / "examples" / "ticket-triage" / "spec.yaml"


def test_example_spec_is_valid_and_has_expected_shape():
    spec = load_spec(SPEC_PATH)
    assert len(spec.cases) == 48
    assert [c.id for c in spec.candidates] == ["baseline", "rubric_v1", "rubric_v2", "strong"]
    assert {g.severity for g in spec.gates} == {"hard", "soft"}


def test_simulated_demo_tells_the_intended_story():
    result = run(load_spec(SPEC_PATH), SimulatedProvider())
    verdicts = {e.candidate.id: e.verdict for e in result.evaluations}
    assert verdicts == {"baseline": NO_SHIP, "rubric_v1": NO_SHIP, "rubric_v2": SHIP, "strong": HOLD}


def test_hard_gate_blocks_a_candidate_that_looks_fine_on_average():
    result = run(load_spec(SPEC_PATH), SimulatedProvider())
    v1 = next(e for e in result.evaluations if e.candidate.id == "rubric_v1")
    accuracy = next(o for o in v1.outcomes if o.gate.id == "overall_accuracy").value
    assert accuracy > 0.8                      # looks decent on average...
    assert v1.verdict == NO_SHIP               # ...but a hard gate still blocks it
    assert {o.gate.id for o in v1.failed if o.gate.severity == "hard"} == {"never_bury", "urgent_recall"}


def test_every_simulated_result_is_flagged_as_simulated():
    result = run(load_spec(SPEC_PATH), SimulatedProvider())
    assert result.simulated is True
    assert all(r.simulated for e in result.evaluations for r in e.results)


def test_simulated_run_is_reproducible():
    spec = load_spec(SPEC_PATH)
    a = run(spec, SimulatedProvider(), now=lambda: __import__("datetime").datetime(2026, 1, 1))
    b = run(spec, SimulatedProvider(), now=lambda: __import__("datetime").datetime(2026, 1, 1))
    assert [[r.output_text for r in e.results] for e in a.evaluations] == \
           [[r.output_text for r in e.results] for e in b.evaluations]
