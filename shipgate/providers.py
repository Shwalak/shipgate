"""Model providers.

A provider takes a Candidate (prompt + model) and one case input and returns a
Completion: the raw text, token counts and latency. Two providers ship:

* SimulatedProvider: deterministic, offline, no key. Used for the demo and tests.
  Everything it returns is flagged `simulated=True` and the report says so.
* AnthropicProvider: calls the Anthropic Messages API using only the standard
  library, so ShipGate has a single runtime dependency (PyYAML).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol

from .spec import Candidate


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    simulated: bool = False


class Provider(Protocol):
    name: str
    simulated: bool

    def complete(self, candidate: Candidate, user_input: str) -> Completion: ...


def estimate_tokens(text: str) -> int:
    """Rough token estimate (about 4 characters per token). Only used by the simulator."""
    return max(1, math.ceil(len(text) / 4))


def _unit_hash(*parts: str) -> float:
    """Deterministic pseudo-random float in [0, 1) derived from the inputs."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


# --------------------------------------------------------------------------- simulated


@dataclass
class SimProfile:
    """A scripted stand-in for a model.

    `respond` maps the case input to raw output text. The other fields shape the
    simulated latency so p95 is meaningful: base + per-output-token time, a
    deterministic jitter, and a slow tail for a small share of calls.
    """

    respond: Callable[[str], str]
    base_latency_s: float
    per_token_latency_s: float
    jitter: float = 0.25          # up to +25% on every call
    slow_tail_share: float = 0.0  # share of calls that are much slower
    slow_tail_factor: float = 2.5


class SimulatedProvider:
    """Offline provider driven by named profiles. Output is deterministic."""

    name = "simulated"
    simulated = True

    def __init__(self, profiles: dict[str, SimProfile] | None = None) -> None:
        if profiles is None:
            from .simulated import PROFILES  # bundled ticket-triage profiles

            profiles = PROFILES
        self.profiles = profiles

    def complete(self, candidate: Candidate, user_input: str) -> Completion:
        key = candidate.mock_profile
        if key is None or key not in self.profiles:
            known = ", ".join(sorted(self.profiles)) or "(none)"
            raise ValueError(
                f"candidate '{candidate.id}' needs a valid mock_profile for simulated runs "
                f"(got {key!r}; available: {known}). Use --live to call a real model instead."
            )
        profile = self.profiles[key]
        text = profile.respond(user_input)
        out_tokens = estimate_tokens(text)
        in_tokens = estimate_tokens(candidate.prompt) + estimate_tokens(user_input)
        latency = profile.base_latency_s + profile.per_token_latency_s * out_tokens
        latency *= 1 + profile.jitter * _unit_hash("jitter", candidate.id, user_input)
        if _unit_hash("tail", candidate.id, user_input) < profile.slow_tail_share:
            latency *= profile.slow_tail_factor
        return Completion(text, in_tokens, out_tokens, round(latency, 4), simulated=True)


# --------------------------------------------------------------------------- live

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class ProviderError(RuntimeError):
    pass


def _http_post(url: str, headers: dict[str, str], body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise ProviderError(f"HTTP {exc.code} from API: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"network error: {exc.reason}") from exc


class AnthropicProvider:
    """Calls the Anthropic Messages API. Reads the key from ANTHROPIC_API_KEY."""

    name = "anthropic"
    simulated = False

    def __init__(
        self,
        api_key: str | None = None,
        max_tokens: int = 300,
        retries: int = 2,
        timeout: float = 60.0,
        post: Callable[[str, dict[str, str], dict, float], dict] = _http_post,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set. Export it, or run without --live for the simulated demo.")
        self.max_tokens = max_tokens
        self.retries = retries
        self.timeout = timeout
        self._post = post
        self._sleep = sleep

    def build_request(self, candidate: Candidate, user_input: str) -> dict:
        body: dict = {
            "model": candidate.model,
            "max_tokens": self.max_tokens,
            "system": candidate.prompt,
            "messages": [{"role": "user", "content": user_input}],
        }
        if candidate.temperature is not None:
            body["temperature"] = candidate.temperature
        return body

    def complete(self, candidate: Candidate, user_input: str) -> Completion:
        headers = {
            "x-api-key": self.api_key or "",
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        body = self.build_request(candidate, user_input)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            start = time.perf_counter()
            try:
                data = self._post(API_URL, headers, body, self.timeout)
            except ProviderError as exc:
                last_error = exc
                retryable = any(code in str(exc) for code in ("HTTP 429", "HTTP 5", "network error"))
                if not retryable or attempt == self.retries:
                    raise
                self._sleep(2**attempt)
                continue
            latency = time.perf_counter() - start
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            usage = data.get("usage", {})
            return Completion(
                text=text,
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                latency_s=round(latency, 4),
                simulated=False,
            )
        raise ProviderError(f"request failed: {last_error}")  # pragma: no cover


def get_provider(live: bool) -> Provider:
    return AnthropicProvider() if live else SimulatedProvider()
