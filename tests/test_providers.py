import pytest

from shipgate.providers import (
    AnthropicProvider,
    ProviderError,
    SimProfile,
    SimulatedProvider,
    estimate_tokens,
)
from shipgate.spec import Candidate


def cand(**kw):
    base = dict(id="a", label="A", prompt="Be brief.", model="m", price_in_per_mtok=1, price_out_per_mtok=2, mock_profile="echo")
    base.update(kw)
    return Candidate(**base)


PROFILES = {"echo": SimProfile(respond=lambda t: '{"x": "%s"}' % t[:3], base_latency_s=0.5, per_token_latency_s=0.01)}


def test_simulated_is_deterministic_and_flagged():
    p = SimulatedProvider(PROFILES)
    a = p.complete(cand(), "hello world")
    b = p.complete(cand(), "hello world")
    assert a == b
    assert a.simulated is True
    assert a.text == '{"x": "hel"}'
    assert a.latency_s >= 0.5


def test_simulated_requires_known_profile():
    p = SimulatedProvider(PROFILES)
    with pytest.raises(ValueError, match="mock_profile"):
        p.complete(cand(mock_profile=None), "hi")


def test_estimate_tokens_never_zero():
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 40) == 10


def test_anthropic_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider()


def test_anthropic_request_shape_and_parsing():
    seen = {}

    def fake_post(url, headers, body, timeout):
        seen.update(url=url, headers=headers, body=body)
        return {"content": [{"type": "text", "text": '{"ok": true}'}], "usage": {"input_tokens": 12, "output_tokens": 5}}

    p = AnthropicProvider(api_key="k", post=fake_post)
    out = p.complete(cand(model="some-model"), "ticket text")
    assert seen["url"].endswith("/v1/messages")
    assert seen["headers"]["x-api-key"] == "k"
    assert seen["body"]["system"] == "Be brief."
    assert seen["body"]["messages"] == [{"role": "user", "content": "ticket text"}]
    assert "temperature" not in seen["body"]  # omitted unless the spec sets it
    assert (out.text, out.input_tokens, out.output_tokens, out.simulated) == ('{"ok": true}', 12, 5, False)


def test_anthropic_temperature_included_when_set():
    p = AnthropicProvider(api_key="k", post=lambda *a: {"content": [], "usage": {}})
    assert p.build_request(cand(temperature=0.0), "x")["temperature"] == 0.0


def test_anthropic_retries_then_succeeds():
    calls = {"n": 0}

    def flaky(url, headers, body, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ProviderError("HTTP 429 from API: rate limited")
        return {"content": [{"type": "text", "text": "hi"}], "usage": {}}

    sleeps = []
    p = AnthropicProvider(api_key="k", post=flaky, sleep=sleeps.append)
    assert p.complete(cand(), "x").text == "hi"
    assert calls["n"] == 3 and sleeps == [1, 2]


def test_anthropic_does_not_retry_client_errors():
    def bad(url, headers, body, timeout):
        raise ProviderError("HTTP 400 from API: bad request")

    p = AnthropicProvider(api_key="k", post=bad, sleep=lambda s: None)
    with pytest.raises(ProviderError, match="HTTP 400"):
        p.complete(cand(), "x")
