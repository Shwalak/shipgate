"""Render a RunResult as one self-contained HTML file.

No JavaScript, no external fonts, scripts or images: the file can be emailed,
attached to a pull request or opened offline, and nothing in it can phone home.
Every piece of text that comes from a spec or a model is HTML-escaped.
"""

from __future__ import annotations

from html import escape

from .gate import HOLD, NO_SHIP, SHIP, Evaluation, recommend
from .runner import RunResult
from .scoring import cost_per_1k, percentile

CSS = """
:root{--bg:#f6f6f3;--surface:#fff;--text:#1b1b1a;--muted:#5d5d59;--border:#dedcd6;
--ship:#17703f;--ship-bg:#e1f3e8;--hold:#8a5a00;--hold-bg:#fdf0cc;--stop:#b0261c;--stop-bg:#fce6e3;
--sim-bg:#fff4d6;--sim-border:#e0b84a;--accent:#2b4a8a}
@media (prefers-color-scheme: dark){:root{--bg:#141413;--surface:#1d1d1b;--text:#ecebe6;--muted:#a3a29b;
--border:#34332f;--ship:#6fd69b;--ship-bg:#13301f;--hold:#f0c25a;--hold-bg:#382b09;--stop:#ff9189;--stop-bg:#3c1612;
--sim-bg:#352b0c;--sim-border:#8a6d1f;--accent:#8fb0ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:1.7rem;line-height:1.25;margin:0 0 4px}
h2{font-size:1.15rem;margin:40px 0 12px}
p{margin:0 0 12px}
.muted{color:var(--muted)}
.meta{color:var(--muted);font-size:.9rem}
.banner{background:var(--sim-bg);border:1px solid var(--sim-border);border-radius:8px;padding:12px 16px;margin:20px 0}
.banner strong{display:block}
.rec{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:8px;padding:14px 16px;margin:20px 0;font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px}
.card h3{font-size:1rem;margin:10px 0 2px}
.model{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.8rem;color:var(--muted)}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-weight:700;font-size:.85rem;letter-spacing:.03em}
.pill.SHIP{background:var(--ship-bg);color:var(--ship)}
.pill.HOLD{background:var(--hold-bg);color:var(--hold)}
.pill.NO-SHIP{background:var(--stop-bg);color:var(--stop)}
dl.kv{display:grid;grid-template-columns:1fr auto;gap:2px 12px;margin:12px 0;font-size:.9rem}
dl.kv dt{color:var(--muted)} dl.kv dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}
ul.reasons{margin:8px 0 0;padding-left:18px;font-size:.88rem;color:var(--muted)}
.scroll{overflow-x:auto;background:var(--surface);border:1px solid var(--border);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{padding:9px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--border)}
tr:last-child td{border-bottom:0}
th{font-weight:600;color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.ok{color:var(--ship)} .bad{color:var(--stop);font-weight:600}
.tag{display:inline-block;font-size:.72rem;padding:1px 7px;border-radius:4px;border:1px solid var(--border);color:var(--muted);margin-left:6px}
.tag.hard{color:var(--stop);border-color:var(--stop)}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.82rem}
details{background:var(--surface);border:1px solid var(--border);border-radius:10px;margin-bottom:10px}
summary{cursor:pointer;padding:12px 16px;font-weight:600}
details .scroll{border:0;border-top:1px solid var(--border);border-radius:0 0 10px 10px}
.note{font-size:.88rem;color:var(--muted)}
footer{margin-top:48px;font-size:.85rem;color:var(--muted)}
@media (max-width:600px){h1{font-size:1.4rem}}
"""


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _accuracy(ev: Evaluation) -> float:
    return sum(r.all_ok for r in ev.results) / len(ev.results)


def _cards(result: RunResult) -> str:
    out = []
    for ev in result.evaluations:
        c = ev.candidate
        p95 = percentile([r.latency_s for r in ev.results], 95)
        reasons = "".join(f"<li>{escape(r)}</li>" for r in ev.reasons)
        out.append(
            f'<section class="card"><span class="pill {ev.verdict}">{ev.verdict}</span>'
            f"<h3>{escape(c.label)}</h3><div class=\"model\">{escape(c.model)}</div>"
            f'<dl class="kv"><dt>Accuracy (all fields)</dt><dd>{_pct(_accuracy(ev))}</dd>'
            f"<dt>Cost per 1,000 calls</dt><dd>${cost_per_1k(ev.results, c):.2f}</dd>"
            f"<dt>p95 latency</dt><dd>{p95:.2f}s</dd></dl>"
            f'<ul class="reasons">{reasons}</ul></section>'
        )
    return f'<div class="cards">{"".join(out)}</div>'


def _gate_matrix(result: RunResult) -> str:
    head = "".join(f"<th>{escape(e.candidate.id)}</th>" for e in result.evaluations)
    rows = []
    for i, gate in enumerate(result.spec.gates):
        cells = []
        for ev in result.evaluations:
            o = ev.outcomes[i]
            cls, word = ("ok", "Pass") if o.passed else ("bad", "Fail")
            cells.append(f'<td class="{cls}"><strong>{word}</strong> <span class="mono">{escape(o.shown_value)}</span></td>')
        sev = f'<span class="tag {gate.severity}">{gate.severity}</span>'
        first = escape(f"{gate.description}")
        needs = escape(f"needs {gate.op} {result.evaluations[0].outcomes[i].shown_threshold.split(' ', 1)[1]}")
        rows.append(f"<tr><td>{first}{sev}<div class=\"note\">{needs}</div></td>{''.join(cells)}</tr>")
    return (
        '<div class="scroll"><table><thead><tr><th>Launch gate</th>'
        f"{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _segments(result: RunResult) -> str:
    tags = sorted({s.tag for ev in result.evaluations for s in ev.slices})
    if not tags:
        return '<p class="note">No tags were set on the cases, so there is no segment breakdown.</p>'
    head = "".join(f'<th class="num">{escape(e.candidate.id)}</th>' for e in result.evaluations)
    rows = []
    overall = "".join(f'<td class="num">{_pct(_accuracy(e))}</td>' for e in result.evaluations)
    rows.append(f"<tr><td><strong>All cases</strong> <span class=\"note\">(n={result.n_cases})</span></td>{overall}</tr>")
    for tag in tags:
        cells = []
        n = 0
        for ev in result.evaluations:
            stat = next((s for s in ev.slices if s.tag == tag), None)
            if stat is None:
                cells.append('<td class="num">-</td>')
                continue
            n = stat.n
            cls = "bad" if stat.accuracy < 0.8 else ""
            cells.append(f'<td class="num {cls}">{_pct(stat.accuracy)}</td>')
        rows.append(f"<tr><td>{escape(tag)} <span class=\"note\">(n={n})</span></td>{''.join(cells)}</tr>")
    return (
        '<div class="scroll"><table><thead><tr><th>Segment (accuracy, all fields)</th>'
        f"{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _failures(result: RunResult) -> str:
    blocks = []
    for ev in result.evaluations:
        bad = [r for r in ev.results if not r.all_ok]
        title = f"{escape(ev.candidate.label)}: {len(bad)} of {len(ev.results)} cases wrong"
        if not bad:
            blocks.append(f"<details><summary>{title}</summary><p class=\"note\" style=\"padding:0 16px 12px\">No failing cases.</p></details>")
            continue
        case_input = {c.id: c.input for c in result.spec.cases}
        rows = []
        for r in bad:
            got = escape(r.output_text) if r.valid else f"<em>invalid format:</em> {escape(r.output_text)}"
            exp = escape(", ".join(f"{k}={v}" for k, v in r.expected.items()))
            rows.append(
                f'<tr><td class="mono">{escape(r.case_id)}</td><td>{escape(case_input[r.case_id])}</td>'
                f'<td class="mono">{exp}</td><td class="mono">{got}</td></tr>'
            )
        blocks.append(
            f"<details><summary>{title}</summary><div class=\"scroll\"><table><thead><tr><th>Case</th><th>Ticket</th>"
            f"<th>Expected</th><th>Got</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></details>"
        )
    return "".join(blocks)


def render_report(result: RunResult) -> str:
    spec = result.spec
    _, recommendation = recommend(result.evaluations)
    n = result.n_cases
    banner = ""
    if result.simulated:
        banner = (
            '<div class="banner" role="note"><strong>Simulated run: not real model results</strong>'
            "These outputs come from scripted stand-ins (see <code>shipgate/simulated.py</code>), not from language "
            "models. They demonstrate the pipeline and the gate logic. Run with <code>--live</code> to evaluate real "
            "models.</div>"
        )
    mode = "Simulated (offline demo)" if result.simulated else f"Live ({escape(result.provider_name)})"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ShipGate report: {escape(spec.feature_name)}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>Launch report: {escape(spec.feature_name)}</h1>
<p class="meta">{n} cases &middot; {len(result.evaluations)} candidates &middot; {mode} &middot; generated {escape(result.generated_at)}</p>
<p class="muted">{escape(spec.feature_description)}</p>
{banner}
<div class="rec">{escape(recommendation)}</div>

<h2>Verdict by candidate</h2>
{_cards(result)}

<h2>Launch gates</h2>
<p class="note">Hard gates block a launch. Soft gates put it on hold until someone accepts the tradeoff. The gates were defined in the spec before this run.</p>
{_gate_matrix(result)}

<h2>Where each candidate is weak</h2>
<p class="note">Segments can overlap. A good average can hide a weak segment, so check this before trusting a headline number.</p>
{_segments(result)}

<h2>Cases each candidate got wrong</h2>
{_failures(result)}

<h2>How to read this</h2>
<p class="note"><strong>Sample size.</strong> With {n} cases, one case moves accuracy by {100 / n:.1f} points. Treat gaps smaller than a few cases as noise, and treat this as a screen, not proof. Add cases for any segment you care about.</p>
<p class="note"><strong>Verdicts.</strong> SHIP: every gate passes. HOLD: only soft gates fail. NO-SHIP: at least one hard gate fails. There is deliberately no combined score, so a failed safety rule cannot be averaged away.</p>
<footer>Generated by ShipGate. The verdict is evidence for a launch decision, not the decision.</footer>
</main>
</body>
</html>
"""
