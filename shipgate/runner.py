"""Run every candidate against every case and evaluate the gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .gate import Evaluation, evaluate
from .providers import Provider
from .scoring import CaseResult, score_case
from .spec import Spec


@dataclass
class RunResult:
    spec: Spec
    evaluations: list[Evaluation]
    provider_name: str
    simulated: bool
    generated_at: str

    @property
    def n_cases(self) -> int:
        return len(self.spec.cases)


def run(spec: Spec, provider: Provider, progress: Callable[[str, int, int], None] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> RunResult:
    """Sequential on purpose: deterministic, easy to reason about, and gentle on rate limits.

    `progress(candidate_id, done, total)` is called after each case if provided.
    """
    evaluations = []
    for candidate in spec.candidates:
        results: list[CaseResult] = []
        for i, case in enumerate(spec.cases, start=1):
            completion = provider.complete(candidate, case.input)
            results.append(
                score_case(case, spec.fields, completion.text, completion.input_tokens,
                           completion.output_tokens, completion.latency_s, completion.simulated)
            )
            if progress:
                progress(candidate.id, i, len(spec.cases))
        evaluations.append(evaluate(spec, candidate, results))
    return RunResult(
        spec=spec,
        evaluations=evaluations,
        provider_name=provider.name,
        simulated=provider.simulated,
        generated_at=now().replace(microsecond=0).isoformat(),
    )
