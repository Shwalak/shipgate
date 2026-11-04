"""Command-line interface: `shipgate validate` and `shipgate run`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .export import to_dict
from .providers import ProviderError, get_provider
from .runner import RunResult, run
from .spec import SpecError, load_spec


def _format_summary(result: RunResult) -> str:
    lines = []
    mode = "SIMULATED (offline demo, not real model results)" if result.simulated else f"LIVE ({result.provider_name})"
    lines.append(f"{result.spec.feature_name}: {result.n_cases} cases, {len(result.evaluations)} candidates. Mode: {mode}")
    lines.append("")
    width = max(len(e.candidate.id) for e in result.evaluations)
    for ev in result.evaluations:
        lines.append(f"  {ev.candidate.id.ljust(width)}  {ev.verdict}")
        for reason in ev.reasons:
            lines.append(f"  {' ' * width}    - {reason}")
    return "\n".join(lines)


def _confirm_live(n_calls: int, assume_yes: bool, stdin=sys.stdin, out=sys.stderr) -> bool:
    print(f"--live will make {n_calls} billable API calls.", file=out)
    if assume_yes:
        return True
    if not stdin.isatty():
        print("Not an interactive terminal: pass --yes to confirm.", file=out)
        return False
    return input("Continue? [y/N] ").strip().lower() in ("y", "yes")


def cmd_validate(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    hard = sum(g.severity == "hard" for g in spec.gates)
    print(
        f"OK: '{spec.feature_name}' has {len(spec.cases)} cases, {len(spec.candidates)} candidates "
        f"and {len(spec.gates)} gates ({hard} hard, {len(spec.gates) - hard} soft)."
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    if args.live and not _confirm_live(len(spec.cases) * len(spec.candidates), args.yes):
        print("Aborted. Nothing was sent.", file=sys.stderr)
        return 1
    provider = get_provider(live=args.live)

    def progress(candidate_id: str, done: int, total: int) -> None:
        if args.live and (done == total or done % 10 == 0):
            print(f"  {candidate_id}: {done}/{total}", file=sys.stderr)

    result = run(spec, provider, progress=progress)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(to_dict(result), indent=2) + "\n", encoding="utf-8")
    print(_format_summary(result))
    print(f"\nWrote {out_dir / 'results.json'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shipgate", description="Launch-readiness evals for AI features.")
    parser.add_argument("--version", action="version", version=f"shipgate {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="check a spec without running anything")
    v.add_argument("spec")
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("run", help="run all candidates and evaluate the gates")
    r.add_argument("spec")
    r.add_argument("--out", default="out", help="output directory (default: out)")
    r.add_argument("--live", action="store_true", help="call a real model (needs ANTHROPIC_API_KEY; costs money)")
    r.add_argument("--yes", action="store_true", help="skip the --live confirmation prompt")
    r.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (SpecError, ProviderError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
