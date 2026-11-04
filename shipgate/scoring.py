"""Parse model output, score it against expectations, and compute gate metrics.

Scoring is deterministic by design (exact match on named fields). Output that is
not a JSON object counts as wrong everywhere and is tracked separately through
`valid_format_rate`, so a formatting failure is never silently forgiven.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

from .spec import Candidate, Case, Gate, Spec

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def parse_output(text: str) -> dict | None:
    """Return the JSON object in `text`, or None if it is not one.

    Strict on purpose: prose around the JSON is a failure. A single markdown
    code fence is tolerated because models add it habitually.
    """
    stripped = text.strip()
    match = _FENCE.match(stripped)
    if match:
        stripped = match.group(1)
    try:
        value = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


@dataclass
class CaseResult:
    case_id: str
    tags: list[str]
    expected: dict[str, str]
    output_text: str
    parsed: dict | None
    field_ok: dict[str, bool]
    input_tokens: int
    output_tokens: int
    latency_s: float
    simulated: bool = False

    @property
    def valid(self) -> bool:
        return self.parsed is not None

    @property
    def all_ok(self) -> bool:
        return all(self.field_ok.values())


def score_case(case: Case, fields: list[str], output_text: str, input_tokens: int, output_tokens: int,
               latency_s: float, simulated: bool = False) -> CaseResult:
    parsed = parse_output(output_text)
    field_ok = {
        f: parsed is not None and str(parsed.get(f, "")).strip().lower() == case.expected[f].strip().lower()
        for f in fields
    }
    return CaseResult(case.id, case.tags, case.expected, output_text, parsed, field_ok,
                      input_tokens, output_tokens, latency_s, simulated)


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. Simple and explainable; no interpolation."""
    if not values:
        raise ValueError("percentile of empty list")
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def _predicted(result: CaseResult, field_name: str) -> str | None:
    if result.parsed is None:
        return None
    value = result.parsed.get(field_name)
    return None if value is None else str(value).strip().lower()


def compute_metric(gate: Gate, results: list[CaseResult], candidate: Candidate, spec: Spec) -> float:
    """Compute the value a gate compares against its threshold."""
    if not results:
        raise ValueError("no results to score")
    n = len(results)
    m = gate.metric
    if m == "accuracy":
        if gate.field:
            return sum(r.field_ok[gate.field] for r in results) / n
        return sum(r.all_ok for r in results) / n
    if m == "valid_format_rate":
        return sum(r.valid for r in results) / n
    if m == "recall":
        target = (gate.label or "").strip().lower()
        relevant = [r for r in results if r.expected[gate.field or ""].strip().lower() == target]
        if not relevant:
            raise ValueError(f"gate '{gate.id}': no cases expect {gate.field}={gate.label}; recall is undefined")
        return sum(r.field_ok[gate.field or ""] for r in relevant) / len(relevant)
    if m == "forbidden_outcomes":
        count = 0
        for r in results:
            for fb in spec.forbidden:
                if r.expected[fb.field].strip().lower() == fb.expected.strip().lower() and \
                        _predicted(r, fb.field) == fb.predicted.strip().lower():
                    count += 1
        return float(count)
    if m == "cost_per_1k":
        per_call = [
            (r.input_tokens * candidate.price_in_per_mtok + r.output_tokens * candidate.price_out_per_mtok) / 1_000_000
            for r in results
        ]
        return sum(per_call) / n * 1000
    if m == "p95_latency_s":
        return percentile([r.latency_s for r in results], 95)
    raise ValueError(f"unknown metric {m!r}")  # unreachable: the spec loader validates metrics


@dataclass
class SliceStat:
    tag: str
    n: int
    accuracy: float


def slice_accuracy(results: list[CaseResult]) -> list[SliceStat]:
    """Accuracy per tag, so a weak segment cannot hide inside a good average."""
    by_tag: dict[str, list[CaseResult]] = {}
    for r in results:
        for tag in r.tags:
            by_tag.setdefault(tag, []).append(r)
    return [SliceStat(t, len(rs), sum(x.all_ok for x in rs) / len(rs)) for t, rs in sorted(by_tag.items())]
