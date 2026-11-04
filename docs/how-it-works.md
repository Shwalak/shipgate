# How ShipGate works (plain English)

This is the walkthrough I would give a hiring manager, an engineer or a teammate who asks
"so what does it actually do, and why is it built this way?"

## The one-sentence version

You write down what "good enough to launch" means for an AI feature, ShipGate tests several
versions of the feature against your examples, and it tells you which versions can ship and
why the others cannot.

## The flow, step by step

1. **`spec.py` reads your YAML file.** It checks everything up front and names the exact field
   when something is wrong (`gates[0].metric: unknown metric 'vibes'`). A PM should never have
   to read a stack trace.
2. **`runner.py` loops over every candidate and every case.** A candidate is a prompt plus a model.
   For each pair it asks the provider for an answer and records the text, the token counts and the time taken.
3. **`providers.py` supplies the answers.** Offline, `SimulatedProvider` returns scripted answers so
   anyone can run the demo. With `--live`, `AnthropicProvider` calls the real API.
4. **`scoring.py` judges each answer.** It parses the JSON (prose around the JSON counts as a failure,
   on purpose), compares each field to the expected value, and computes the six metrics the gates can use.
5. **`gate.py` applies your gates and decides.** Any failed hard gate gives `NO-SHIP`. Otherwise any failed
   soft gate gives `HOLD`. Otherwise `SHIP`.
6. **`report.py` and `export.py` write the outputs**: a one-page HTML report and a `results.json`.

## The ideas worth being able to explain

**Why gates are written before the run.** If thresholds are picked after seeing results, they get picked
to make a favourite candidate pass. Putting them in the spec, and committing the spec first, makes
"good enough" a decision instead of a rationalisation.

**Why hard and soft.** Some failures are about trust (burying an urgent ticket). Others are about economics
(too slow, too expensive). A hard gate says "do not launch, full stop". A soft gate says "a human has to
consciously accept this tradeoff". Those are different conversations.

**Why no single score.** A weighted average can show 87% while hiding that the one case you can never get
wrong, you got wrong. In the demo, prompt v1 has 83% accuracy and is still blocked by two hard gates.

**Why the segment table.** The same logic one level down. The demo winner (v2) scores 87.5% overall but
only 40% on security-tagged tickets. The headline would never show you that.

**Why deterministic scoring first.** Exact-match checks are cheap, repeatable and easy to audit. An
LLM judge is flexible but adds bias, cost and a second thing to validate. It is a next step, not a
shortcut to skip.

**Why a simulated provider.** So a reviewer can run the whole thing in one command without an API key.
The price is that demo numbers prove nothing about real models. That is why the report and README
label them, and why the module that produces them opens with a warning.

## Questions to be ready for

- *"Is this real model performance?"* No. The demo uses scripted stand-ins to exercise the pipeline.
  The live path exists and is unit-tested against a fake transport; run it with a key for real results.
- *"Why 48 cases?"* Small enough that every case can be read and argued about. The report states what one
  case is worth (2.1 points) so nobody reads false precision into it.
- *"What would you build next?"* Run history and CI mode first: the moment a team trusts the gates, they
  want a failing hard gate to block a pull request. Then a judge scorer for open-ended output.
- *"How would you know ShipGate itself is valuable?"* The PRD lists targets to validate: time to first report,
  time to adapt the example to a new feature, and whether reviewers can state the verdict and main reason from
  the report alone. I have not run those studies; I would start with 3 to 5 real PMs.
- *"What was hard?"* Deciding what the verdict should mean. A single score was easier to build and worse
  to use; the three-state verdict with hard and soft gates took more thought and is the actual product idea.

## Where to look in the code

| If you want to understand | Read |
|---|---|
| What a spec can express | `examples/ticket-triage/spec.yaml` |
| How a verdict is decided | `shipgate/gate.py` (the verdict rule is the five-line `decide()` function) |
| How metrics are computed | `shipgate/scoring.py` |
| How the demo stays honest | `shipgate/simulated.py` (docstring) and `tests/test_example.py` |
