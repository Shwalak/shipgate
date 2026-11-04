from pathlib import Path
import textwrap

import pytest

from shipgate.spec import SpecError, load_spec


def write(tmp_path: Path, body: str, name: str = "spec.yaml") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


VALID = """
feature:
  name: Demo
fields: [label]
candidates:
  - id: a
    prompt: "Classify."
    model: some-model
    price_per_mtok: {input: 1.0, output: 2.0}
cases:
  - id: c1
    input: hello
    expected: {label: x}
gates:
  - id: g1
    metric: accuracy
    op: ">="
    value: 0.5
"""


def test_valid_spec_loads(tmp_path):
    spec = load_spec(write(tmp_path, VALID))
    assert spec.feature_name == "Demo"
    assert spec.candidates[0].price_out_per_mtok == 2.0
    assert spec.gates[0].severity == "hard"  # default is the strict one


def test_missing_file_is_a_spec_error(tmp_path):
    with pytest.raises(SpecError, match="file not found"):
        load_spec(tmp_path / "nope.yaml")


def test_unknown_metric_names_the_field(tmp_path):
    bad = VALID.replace("metric: accuracy", "metric: vibes")
    with pytest.raises(SpecError, match=r"gates\[0\]\.metric: unknown metric 'vibes'"):
        load_spec(write(tmp_path, bad))


def test_case_missing_scored_field(tmp_path):
    bad = VALID.replace("expected: {label: x}", "expected: {other: x}")
    with pytest.raises(SpecError, match="missing scored field 'label'"):
        load_spec(write(tmp_path, bad))


def test_recall_needs_field_and_label(tmp_path):
    bad = VALID.replace("metric: accuracy", "metric: recall")
    with pytest.raises(SpecError, match="needs both 'field' and 'label'"):
        load_spec(write(tmp_path, bad))


def test_forbidden_gate_requires_forbidden_list(tmp_path):
    bad = VALID.replace("metric: accuracy", "metric: forbidden_outcomes")
    with pytest.raises(SpecError, match="no 'forbidden' list"):
        load_spec(write(tmp_path, bad))


def test_duplicate_case_ids_rejected(tmp_path):
    bad = VALID.replace(
        "cases:\n  - id: c1\n    input: hello\n    expected: {label: x}",
        "cases:\n  - id: c1\n    input: hello\n    expected: {label: x}\n  - id: c1\n    input: again\n    expected: {label: y}",
    )
    with pytest.raises(SpecError, match="duplicate case id 'c1'"):
        load_spec(write(tmp_path, bad))


def test_cases_can_live_in_a_separate_file(tmp_path):
    (tmp_path / "cases.yaml").write_text("- id: c1\n  input: hi\n  expected: {label: x}\n", encoding="utf-8")
    body = VALID.split("cases:")[0] + "cases: cases.yaml\ngates:" + VALID.split("gates:")[1]
    spec = load_spec(write(tmp_path, body))
    assert [c.id for c in spec.cases] == ["c1"]
