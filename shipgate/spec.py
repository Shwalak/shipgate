"""Load and validate a ShipGate spec (YAML) into plain dataclasses.

Design note: validation is hand-written instead of using a schema library so
that error messages can name the exact field a PM needs to fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

METRICS = {
    "accuracy",            # share of cases where all scored fields match (or one field)
    "recall",              # of cases whose expected `field` == `label`, share predicted correctly
    "valid_format_rate",   # share of outputs that parsed as the expected JSON object
    "forbidden_outcomes",  # count of cases hitting a pair listed under `forbidden`
    "cost_per_1k",         # USD per 1,000 calls, from token counts and candidate prices
    "p95_latency_s",       # 95th percentile latency in seconds
}
OPS = {">=", "<=", ">", "<", "=="}
SEVERITIES = {"hard", "soft"}


class SpecError(ValueError):
    """Raised when a spec is invalid. The message names the field to fix."""


@dataclass
class Case:
    id: str
    input: str
    expected: dict[str, str]
    tags: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    id: str
    label: str
    prompt: str
    model: str
    price_in_per_mtok: float
    price_out_per_mtok: float
    mock_profile: str | None = None


@dataclass
class Gate:
    id: str
    description: str
    metric: str
    op: str
    value: float
    severity: str
    field: str | None = None
    label: str | None = None


@dataclass
class Forbidden:
    field: str
    expected: str
    predicted: str


@dataclass
class Spec:
    feature_name: str
    feature_description: str
    fields: list[str]
    candidates: list[Candidate]
    cases: list[Case]
    gates: list[Gate]
    forbidden: list[Forbidden]
    source_path: Path | None = None


def _require(obj: Any, key: str, where: str, kind: type | tuple = object) -> Any:
    if not isinstance(obj, dict) or key not in obj:
        raise SpecError(f"{where}: missing required field '{key}'")
    value = obj[key]
    if kind is not object and not isinstance(value, kind):
        names = kind.__name__ if isinstance(kind, type) else "/".join(k.__name__ for k in kind)
        raise SpecError(f"{where}.{key}: expected {names}, got {type(value).__name__}")
    return value


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SpecError(f"file not found: {path}") from None
    except yaml.YAMLError as exc:
        raise SpecError(f"{path}: invalid YAML ({exc})") from None


def _parse_candidates(raw: Any, base: Path) -> list[Candidate]:
    if not isinstance(raw, list) or not raw:
        raise SpecError("candidates: provide at least one candidate")
    out: list[Candidate] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        where = f"candidates[{i}]"
        cid = str(_require(item, "id", where))
        if cid in seen:
            raise SpecError(f"{where}.id: duplicate candidate id '{cid}'")
        seen.add(cid)
        if "prompt_file" in item:
            prompt_path = (base / item["prompt_file"]).resolve()
            try:
                prompt = prompt_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                raise SpecError(f"{where}.prompt_file: file not found: {item['prompt_file']}") from None
        else:
            prompt = _require(item, "prompt", where, str)
        price = _require(item, "price_per_mtok", where, dict)
        out.append(
            Candidate(
                id=cid,
                label=str(item.get("label", cid)),
                prompt=prompt,
                model=str(_require(item, "model", where)),
                price_in_per_mtok=float(_require(price, "input", f"{where}.price_per_mtok")),
                price_out_per_mtok=float(_require(price, "output", f"{where}.price_per_mtok")),
                mock_profile=item.get("mock_profile"),
            )
        )
    return out


def _parse_cases(raw: Any, base: Path, fields: list[str]) -> list[Case]:
    if isinstance(raw, str):  # path to a separate cases file
        raw = _load_yaml(base / raw)
    if not isinstance(raw, list) or not raw:
        raise SpecError("cases: provide at least one case (inline list or a file path)")
    out: list[Case] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        where = f"cases[{i}]"
        cid = str(_require(item, "id", where))
        if cid in seen:
            raise SpecError(f"{where}.id: duplicate case id '{cid}'")
        seen.add(cid)
        expected = _require(item, "expected", where, dict)
        for f in fields:
            if f not in expected:
                raise SpecError(f"{where}.expected: missing scored field '{f}' (case '{cid}')")
        tags = item.get("tags", [])
        if not isinstance(tags, list):
            raise SpecError(f"{where}.tags: expected a list")
        out.append(
            Case(
                id=cid,
                input=str(_require(item, "input", where)),
                expected={k: str(v) for k, v in expected.items()},
                tags=[str(t) for t in tags],
            )
        )
    return out


def _parse_gates(raw: Any, fields: list[str]) -> list[Gate]:
    if not isinstance(raw, list) or not raw:
        raise SpecError("gates: define at least one launch gate")
    out: list[Gate] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        where = f"gates[{i}]"
        gid = str(_require(item, "id", where))
        if gid in seen:
            raise SpecError(f"{where}.id: duplicate gate id '{gid}'")
        seen.add(gid)
        metric = str(_require(item, "metric", where))
        if metric not in METRICS:
            raise SpecError(f"{where}.metric: unknown metric '{metric}'. Choose one of: {', '.join(sorted(METRICS))}")
        op = str(_require(item, "op", where))
        if op not in OPS:
            raise SpecError(f"{where}.op: unknown operator '{op}'. Choose one of: {', '.join(sorted(OPS))}")
        severity = str(item.get("severity", "hard"))
        if severity not in SEVERITIES:
            raise SpecError(f"{where}.severity: must be 'hard' or 'soft'")
        value = _require(item, "value", where, (int, float))
        gfield = item.get("field")
        glabel = item.get("label")
        if gfield is not None and gfield not in fields:
            raise SpecError(f"{where}.field: '{gfield}' is not one of the scored fields {fields}")
        if metric == "recall" and (gfield is None or glabel is None):
            raise SpecError(f"{where}: metric 'recall' needs both 'field' and 'label'")
        out.append(
            Gate(
                id=gid,
                description=str(item.get("description", gid)),
                metric=metric,
                op=op,
                value=float(value),
                severity=severity,
                field=gfield,
                label=None if glabel is None else str(glabel),
            )
        )
    return out


def _parse_forbidden(raw: Any, fields: list[str], gates: list[Gate]) -> list[Forbidden]:
    raw = raw or []
    if not isinstance(raw, list):
        raise SpecError("forbidden: expected a list")
    out: list[Forbidden] = []
    for i, item in enumerate(raw):
        where = f"forbidden[{i}]"
        f = str(_require(item, "field", where))
        if f not in fields:
            raise SpecError(f"{where}.field: '{f}' is not one of the scored fields {fields}")
        out.append(Forbidden(f, str(_require(item, "expected", where)), str(_require(item, "predicted", where))))
    if any(g.metric == "forbidden_outcomes" for g in gates) and not out:
        raise SpecError("gates use 'forbidden_outcomes' but the spec has no 'forbidden' list")
    return out


def load_spec(path: str | Path) -> Spec:
    """Load, validate and return a Spec. Raises SpecError with an actionable message."""
    path = Path(path)
    raw = _load_yaml(path)
    base = path.parent
    feature = _require(raw, "feature", "spec", dict)
    fields = _require(raw, "fields", "spec", list)
    if not fields or not all(isinstance(f, str) for f in fields):
        raise SpecError("fields: provide a non-empty list of output field names to score")
    candidates = _parse_candidates(raw.get("candidates"), base)
    cases = _parse_cases(raw.get("cases"), base, fields)
    gates = _parse_gates(raw.get("gates"), fields)
    forbidden = _parse_forbidden(raw.get("forbidden"), fields, gates)
    return Spec(
        feature_name=str(_require(feature, "name", "feature")),
        feature_description=str(feature.get("description", "")),
        fields=list(fields),
        candidates=candidates,
        cases=cases,
        gates=gates,
        forbidden=forbidden,
        source_path=path,
    )
