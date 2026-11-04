"""Serialise a RunResult to plain JSON (the machine-readable twin of the HTML report)."""

from __future__ import annotations

from .gate import Evaluation
from .runner import RunResult


def evaluation_to_dict(ev: Evaluation) -> dict:
    return {
        "candidate": {"id": ev.candidate.id, "label": ev.candidate.label, "model": ev.candidate.model},
        "verdict": ev.verdict,
        "reasons": ev.reasons,
        "gates": [
            {
                "id": o.gate.id,
                "description": o.gate.description,
                "severity": o.gate.severity,
                "metric": o.gate.metric,
                "threshold": f"{o.gate.op} {o.gate.value:g}",
                "value": round(o.value, 6),
                "passed": o.passed,
            }
            for o in ev.outcomes
        ],
        "slices": [{"tag": s.tag, "n": s.n, "accuracy": round(s.accuracy, 4)} for s in ev.slices],
        "cases": [
            {
                "id": r.case_id,
                "expected": r.expected,
                "output": r.output_text,
                "valid": r.valid,
                "correct": r.all_ok,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "latency_s": r.latency_s,
            }
            for r in ev.results
        ],
    }


def to_dict(result: RunResult) -> dict:
    return {
        "feature": result.spec.feature_name,
        "generated_at": result.generated_at,
        "provider": result.provider_name,
        "simulated": result.simulated,
        "n_cases": result.n_cases,
        "evaluations": [evaluation_to_dict(e) for e in result.evaluations],
    }
