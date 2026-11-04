"""Evaluate launch gates and decide SHIP / HOLD / NO-SHIP.

Verdict rule (deliberately simple so a reviewer can predict it):
    any hard gate fails  -> NO-SHIP
    else any soft fails  -> HOLD
    else                 -> SHIP

There is no weighted score. A single number would let a strong average hide a
failed safety rule; here a hard failure can never be averaged away.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .scoring import CaseResult, SliceStat, compute_metric, cost_per_1k, slice_accuracy
from .spec import Candidate, Gate, Spec

SHIP, HOLD, NO_SHIP = "SHIP", "HOLD", "NO-SHIP"
_EPS = 1e-9
_PERCENT_METRICS = {"accuracy", "recall", "valid_format_rate"}


def format_value(metric: str, value: float) -> str:
    if metric in _PERCENT_METRICS:
        return f"{value * 100:.1f}%"
    if metric == "cost_per_1k":
        return f"${value:.2f}"
    if metric == "p95_latency_s":
        return f"{value:.2f}s"
    return f"{value:g}"


def passes(op: str, value: float, threshold: float) -> bool:
    if op == ">=":
        return value >= threshold - _EPS
    if op == "<=":
        return value <= threshold + _EPS
    if op == ">":
        return value > threshold + _EPS
    if op == "<":
        return value < threshold - _EPS
    if op == "==":
        return abs(value - threshold) <= _EPS
    raise ValueError(f"unknown operator {op!r}")  # unreachable: the spec loader validates operators


@dataclass
class GateOutcome:
    gate: Gate
    value: float
    passed: bool

    @property
    def shown_value(self) -> str:
        return format_value(self.gate.metric, self.value)

    @property
    def shown_threshold(self) -> str:
        return f"{self.gate.op} {format_value(self.gate.metric, self.gate.value)}"


@dataclass
class Evaluation:
    candidate: Candidate
    results: list[CaseResult]
    outcomes: list[GateOutcome]
    verdict: str
    reasons: list[str]
    slices: list[SliceStat] = field(default_factory=list)

    @property
    def failed(self) -> list[GateOutcome]:
        return [o for o in self.outcomes if not o.passed]


def decide(outcomes: list[GateOutcome]) -> str:
    if any(not o.passed and o.gate.severity == "hard" for o in outcomes):
        return NO_SHIP
    if any(not o.passed for o in outcomes):
        return HOLD
    return SHIP


def explain(outcomes: list[GateOutcome]) -> list[str]:
    reasons = []
    for o in outcomes:
        if not o.passed:
            reasons.append(
                f"Failed {o.gate.severity} gate \"{o.gate.description}\": "
                f"{o.shown_value} (needs {o.shown_threshold})"
            )
    return reasons or ["All gates passed."]


def evaluate(spec: Spec, candidate: Candidate, results: list[CaseResult]) -> Evaluation:
    outcomes = []
    for gate in spec.gates:
        value = compute_metric(gate, results, candidate, spec)
        outcomes.append(GateOutcome(gate, value, passes(gate.op, value, gate.value)))
    return Evaluation(
        candidate=candidate,
        results=results,
        outcomes=outcomes,
        verdict=decide(outcomes),
        reasons=explain(outcomes),
        slices=slice_accuracy(results),
    )


def recommend(evaluations: list[Evaluation]) -> tuple[Evaluation | None, str]:
    """Pick the cheapest candidate that passes every gate, or say that none can ship.

    This is a policy, kept explicit and boring: among SHIP candidates choose the lowest
    cost per 1,000 calls (ties broken by candidate id). It is evidence for a decision,
    not the decision.
    """
    shippable = [e for e in evaluations if e.verdict == SHIP]
    if shippable:
        best = min(shippable, key=lambda e: (cost_per_1k(e.results, e.candidate), e.candidate.id))
        return best, f"Recommended: {best.candidate.label}. It passes every gate and is the cheapest candidate that does."
    on_hold = [e for e in evaluations if e.verdict == HOLD]
    if on_hold:
        names = ", ".join(e.candidate.label for e in on_hold)
        return None, f"No candidate is ready to ship. On hold, pending a decision on the failed soft gates: {names}."
    return None, "No candidate is ready to ship. Every candidate fails at least one hard gate."
