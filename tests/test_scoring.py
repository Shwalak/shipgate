import pytest

from shipgate.scoring import CaseResult, compute_metric, parse_output, percentile, score_case, slice_accuracy
from shipgate.spec import Candidate, Case, Forbidden, Gate, Spec

FIELDS = ["category", "urgency"]


def spec_with(forbidden=()):
    return Spec("T", "", FIELDS, [], [], [], list(forbidden))


CAND = Candidate("a", "A", "p", "m", price_in_per_mtok=1.0, price_out_per_mtok=5.0)


def gate(metric, **kw):
    return Gate(id="g", description="g", metric=metric, op=">=", value=0, severity="hard", **kw)


def result(case_id, expected, output, tags=(), tokens=(100, 20), latency=1.0):
    case = Case(case_id, "x", expected, list(tags))
    return score_case(case, FIELDS, output, tokens[0], tokens[1], latency)


GOOD = '{"category": "billing", "urgency": "normal"}'


def test_parse_accepts_plain_and_fenced_json():
    assert parse_output(GOOD) == {"category": "billing", "urgency": "normal"}
    assert parse_output("```json\n" + GOOD + "\n```") == {"category": "billing", "urgency": "normal"}


@pytest.mark.parametrize("bad", ["Sure! " + GOOD, "billing", "[1, 2]", "", "{broken"])
def test_parse_rejects_prose_arrays_and_garbage(bad):
    assert parse_output(bad) is None


def test_scoring_is_case_insensitive_on_labels():
    r = result("c", {"category": "billing", "urgency": "normal"}, '{"category": "Billing", "urgency": " NORMAL "}')
    assert r.all_ok


def test_invalid_output_fails_every_field():
    r = result("c", {"category": "billing", "urgency": "normal"}, "I think billing")
    assert not r.valid and not any(r.field_ok.values())


def test_accuracy_all_fields_vs_single_field():
    exp = {"category": "billing", "urgency": "normal"}
    rs = [
        result("1", exp, GOOD),
        result("2", exp, '{"category": "billing", "urgency": "urgent"}'),
    ]
    assert compute_metric(gate("accuracy"), rs, CAND, spec_with()) == 0.5
    assert compute_metric(gate("accuracy", field="category"), rs, CAND, spec_with()) == 1.0


def test_recall_counts_only_relevant_cases():
    urgent = {"category": "bug", "urgency": "urgent"}
    normal = {"category": "bug", "urgency": "normal"}
    rs = [
        result("1", urgent, '{"category": "bug", "urgency": "urgent"}'),
        result("2", urgent, '{"category": "bug", "urgency": "low"}'),
        result("3", normal, '{"category": "bug", "urgency": "urgent"}'),  # false alarm: not recall's concern
    ]
    g = gate("recall", field="urgency", label="urgent")
    assert compute_metric(g, rs, CAND, spec_with()) == 0.5


def test_recall_without_relevant_cases_is_an_error():
    rs = [result("1", {"category": "bug", "urgency": "normal"}, GOOD)]
    with pytest.raises(ValueError, match="recall is undefined"):
        compute_metric(gate("recall", field="urgency", label="urgent"), rs, CAND, spec_with())


def test_forbidden_outcomes_counts_only_the_listed_pair():
    fb = [Forbidden("urgency", "urgent", "low")]
    urgent = {"category": "bug", "urgency": "urgent"}
    rs = [
        result("1", urgent, '{"category": "bug", "urgency": "low"}'),      # forbidden
        result("2", urgent, '{"category": "bug", "urgency": "normal"}'),   # wrong, but not the forbidden pair
        result("3", urgent, "garbage"),                                    # invalid: counted elsewhere
    ]
    assert compute_metric(gate("forbidden_outcomes"), rs, CAND, spec_with(fb)) == 1.0


def test_cost_per_1k_uses_token_prices():
    # 100 in * $1/M + 20 out * $5/M = $0.0002 per call -> $0.20 per 1,000
    rs = [result("1", {"category": "a", "urgency": "b"}, GOOD, tokens=(100, 20))]
    assert compute_metric(gate("cost_per_1k"), rs, CAND, spec_with()) == pytest.approx(0.2)


def test_valid_format_rate():
    exp = {"category": "billing", "urgency": "normal"}
    rs = [result("1", exp, GOOD), result("2", exp, "nope"), result("3", exp, GOOD), result("4", exp, GOOD)]
    assert compute_metric(gate("valid_format_rate"), rs, CAND, spec_with()) == 0.75


def test_percentile_nearest_rank():
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) == 5
    assert percentile([3.0], 95) == 3.0


def test_p95_latency_metric():
    exp = {"category": "billing", "urgency": "normal"}
    rs = [result(str(i), exp, GOOD, latency=float(i)) for i in range(1, 21)]
    assert compute_metric(gate("p95_latency_s"), rs, CAND, spec_with()) == 19.0


def test_slice_accuracy_by_tag():
    exp = {"category": "billing", "urgency": "normal"}
    rs = [
        result("1", exp, GOOD, tags=["a", "b"]),
        result("2", exp, "bad", tags=["a"]),
    ]
    stats = {s.tag: (s.n, s.accuracy) for s in slice_accuracy(rs)}
    assert stats == {"a": (2, 0.5), "b": (1, 1.0)}
