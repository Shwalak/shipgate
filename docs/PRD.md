# PRD: ShipGate

**Author:** Saksham · **Status:** v0.1 (MVP built) · **Type:** Developer-adjacent tool for product teams

> Honesty note: this PRD records assumptions and hypotheses. I have not run user
> interviews for this project, so nothing here is presented as validated research.
> Section 9 lists what I would test first.

## 1. Problem

Teams shipping AI features usually decide "is it good enough?" by trying a few
examples and trusting a feeling. That goes wrong in predictable ways:

- A prompt tweak fixes one case and silently breaks others (no regression view).
- A model swap changes behaviour and nobody notices until a customer does.
- "Good enough" is never written down, so launch reviews become opinion fights.
- Cost and latency are discovered after launch, not before.

The PM owns the launch decision but usually has no lightweight way to get evidence.
Existing eval tooling tends to be built for ML engineers: code-first, framework-heavy,
and silent about the one thing a PM must produce, which is a defensible
ship / don't-ship call.

## 2. Target user

**Primary:** a product manager (or technical PM) responsible for an LLM-powered
feature who can write a spec and a handful of example cases, and is comfortable
editing a YAML file.

**Secondary:** the engineer who implements the feature and wants a clear
definition of done; the reviewer (design, legal, leadership) who needs a one-page
justification for the launch decision.

**Not for:** ML researchers benchmarking models in general; teams needing
large-scale, continuous production monitoring.

## 3. Jobs to be done

1. "When I change a prompt or model, show me what got better and what got worse."
2. "Let me write down what 'good enough to launch' means before I see the results."
3. "Give me one page I can put in front of stakeholders that says SHIP, HOLD or
   NO-SHIP and why."
4. "Show me the cost and latency tradeoff, not just accuracy."

## 4. Goals and non-goals

**Goals (MVP)**
- Define a feature, test cases and launch gates in one human-readable file.
- Compare several candidates (prompt and model pairs) on the same cases.
- Produce a self-contained report with a verdict and the reasons behind it.
- Run end to end with no API key, so anyone can try it in one command.

**Non-goals (MVP)**
- A web UI or hosted service.
- Production traffic monitoring or online A/B testing.
- Auto-generating test cases with an LLM.
- Supporting every model provider.

## 5. Key concepts

| Concept | Meaning |
|---|---|
| Spec | One YAML file: the feature, the cases, the candidates and the gates. |
| Candidate | A prompt plus model (and price) pair under evaluation. |
| Case | An input with the expected output fields, optional tags for slicing. |
| Gate | A pass/fail criterion on a metric, marked `hard` or `soft`. |
| Verdict | `SHIP` (all gates pass), `HOLD` (only soft gates fail), `NO-SHIP` (any hard gate fails). |

## 6. Requirements

| ID | Requirement | Priority |
|---|---|---|
| R1 | Load and validate a YAML spec; fail with a message that names the broken field. | Must |
| R2 | Run every candidate against every case and record output, tokens, latency. | Must |
| R3 | Score structured outputs by exact field match; track malformed output separately. | Must |
| R4 | Support metrics: accuracy, recall for a label, forbidden-outcome count, valid-format rate, cost per 1,000 calls, p95 latency. | Must |
| R5 | Evaluate gates and return SHIP / HOLD / NO-SHIP with per-gate reasons. | Must |
| R6 | Generate a self-contained HTML report and a JSON results file. | Must |
| R7 | Run with no API key using a clearly labelled simulated provider. | Must |
| R8 | Optional live provider (Anthropic Messages API). | Should |
| R9 | Optional LLM-as-judge scorer for open-ended outputs. | Should (not built in v0.1; see section 10) |
| R10 | Per-tag slice breakdown so a weak segment cannot hide inside a good average. | Should |

## 7. Success metrics (targets to validate, not results)

- **Time to first report:** a new user gets a report from the bundled example in
  under 5 minutes. *(Target; measure by timing a cold install.)*
- **Spec authoring:** a PM can adapt the example spec to a different feature in
  under an hour. *(Target; needs observation of real users.)*
- **Decision clarity:** reviewers can state the verdict and its main reason after
  reading only the report. *(Target; test with 3 to 5 reviewers.)*
- **Guardrail (must hold in every release):** no result from the simulated provider is ever shown without a visible "simulated" label. *(Enforced by tests on the simulated flag and the report banner.)*

## 8. Key product decisions and tradeoffs

| Decision | Chose | Gave up | Why |
|---|---|---|---|
| Interface | YAML spec + CLI | A web UI | Specs can live in version control next to the feature and be reviewed like code. Ships faster; a UI is a clear next step. |
| Output | Static HTML file | A hosted dashboard | Shareable by email or PR attachment, no infrastructure, no accounts. |
| Scoring | Deterministic checks first | LLM judge as default | Judges are biased, cost money and are hard to audit. They are opt-in. |
| Verdict | Three states with hard/soft gates | A single score | A weighted score hides which criterion failed. A hard fail on a safety rule must not be averaged away. |
| Demo mode | Simulated provider | Requiring a key | Anyone can run it; the cost is that demo numbers say nothing about real models, so they are labelled. |
| Test set | Small, hand-written, auditable | Large generated set | A reviewer can read every case. The cost is statistical weakness, flagged in the report. |

## 9. Risks and open questions

- **Small samples:** with ~40 cases, a single miss moves accuracy by 2.5 points.
  The report should say so and never imply false precision.
- **Gate gaming:** people can pick thresholds after seeing results. Mitigation:
  gates live in the spec and the spec is committed before the run.
- **Goodhart risk:** passing the gate is not the same as a good product. The
  verdict is evidence for a decision, not the decision.
- **Open:** do PMs actually want to write YAML, or is a form better? First thing to test.
- **Open:** is `HOLD` useful, or do teams collapse it into ship / don't ship?

## 10. What I would do next (with a team of three engineers for a sprint)

0. LLM-as-judge scorer for open-ended outputs (R9), once there is a way to validate the judge itself.
1. Guided spec builder (form to YAML) and a spec linter that warns on tiny samples.
2. More providers behind the existing provider interface.
3. Run history: compare today's run with last week's to catch regressions.
4. CI mode: fail a pull request when a hard gate regresses.
5. Confidence intervals on every metric in the report.

## 11. Launch gate for ShipGate itself

- Test suite passes in CI.
- The bundled example runs from a clean checkout with one command.
- Every number in the repo that comes from the simulated provider is labelled as simulated.
- README documents limitations as clearly as features.
