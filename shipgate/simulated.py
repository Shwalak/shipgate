"""Scripted stand-ins for models, used by the offline demo.

READ THIS BEFORE QUOTING ANY NUMBER FROM A SIMULATED RUN
--------------------------------------------------------
These are hand-written keyword rule sets that imitate models of different skill
on the bundled ticket-triage example. They are NOT language models and say nothing
about how any real model performs. Their only purpose is to let anyone run the
whole pipeline (spec -> run -> gates -> report) with no API key and to give the
gate logic something realistic to chew on: a cheap-and-fast candidate that is
sloppy, a rubric-prompted candidate with one blind spot, a fixed version, and an
expensive one. Every result produced here is flagged `simulated` in the report.

To evaluate real models, run with `--live`.
"""

from __future__ import annotations

import json
import re

from .providers import SimProfile, _unit_hash

URGENCY_WORDS = ("urgent", "asap", "immediately", "!!!")

BILLING = ("charge", "invoice", "refund", "payment", "billing", "receipt", "vat", "tax", "credit card",
           "renewal", "seats to our plan", "quarterly", "annual")
ACCOUNT = ("password", "log in", "login", "logged into", "sign in", "locked out", "reset", "2fa", "sso",
           "access", "session expired", "workspace", "separate accounts", "share one seat")
BUG = ("error", "crash", "blank", "fail", "stopped", "wrong", "duplicat", "bug", "typo", "doesn't", "drops",
       "spin", "unreadable", "blurry", "rounds", "off from", "one way", "go to spam", "show up twice",
       "returns no results", "gone", "earlier than", "can't open", "can't log")
HOW_TO = ("how do i", "how can i", "where do i", "is there a way", "documentation", "show me how", "where can i find")
FEATURE = ("would be great", "feature idea", "can you add", "would be nice", "would be really helpful",
           "do you have plans", "let us attach")

COSMETIC = ("typo", "blurry", "icon", "footer", "looks", "colour", "unreadable")

# Blind spot of the v1 rubric: it does not know that data exposure is an emergency.
IMPACT_V1 = ("nobody", "everyone", "every user", "every customer", "whole organisation", "all of our",
             "can't open", "can't sign in", "can't log", "locked out", "another identical", "half of the records",
             "payroll runs", "logged into our", "crashes on launch", "is about to dispute", "every employee row",
             "losing sales")
# v2 adds the privacy and exposure patterns the v1 prompt missed.
PRIVACY_V2 = ("public repo", "former employee", "other customers'", "entire client list", "revoked")
# The strongest candidate also handles the remaining edge phrasings.
EDGE_STRONG = ("your system emailed", "confidential")


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def _score(text: str, words: tuple[str, ...]) -> int:
    return sum(w in text for w in words)


def _emit(category: str, urgency: str) -> str:
    return json.dumps({"category": category, "urgency": urgency})


# ------------------------------------------------------------------ baseline (short prompt, small model)


def respond_baseline(ticket: str) -> str:
    t = ticket.lower()
    if _has(t, BILLING):
        category = "billing"
    elif _has(t, ACCOUNT):
        category = "account_access"
    elif _has(t, BUG):
        category = "bug"
    else:
        category = "how_to" if "?" in t else "feature_request"
    if _has(t, URGENCY_WORDS):
        urgency = "urgent"
    elif _has(t, COSMETIC):
        urgency = "low"
    else:
        urgency = "normal"
    # Without a format instruction this prompt drifts into prose now and then.
    if _unit_hash("format", ticket) < 0.12:
        return f"This looks like a {category.replace('_', ' ')} issue and the priority seems {urgency}."
    return _emit(category, urgency)


# ------------------------------------------------------------------ rubric prompts


def _category(t: str, strong: bool = False) -> str:
    if strong:
        # A stronger model weighs the domain before the sentence shape: "Where do I update my
        # card?" is billing; "Can you add two seats to our plan?" is billing, not a feature ask;
        # a stranger inside an account or a leaked key is an access problem.
        if _has(t, ("logged into our", "api key")):
            return "account_access"
        if _score(t, BILLING) >= 2:
            return "billing"
    if _has(t, HOW_TO):
        # "How do I split them...?" about accounts is still an account question.
        if "separate accounts" in t:
            return "account_access"
        if "invoices" in t:
            return "billing"
        return "how_to"
    if _has(t, FEATURE):
        return "feature_request"
    scores = {"billing": _score(t, BILLING), "account_access": _score(t, ACCOUNT), "bug": _score(t, BUG)}
    best = max(scores.values())
    if best == 0:
        return "bug"
    # Ties favour the more specific domain over the generic "bug".
    for name in ("billing", "account_access", "bug"):
        if scores[name] == best:
            return name
    return "bug"  # pragma: no cover


def _respond_rubric(ticket: str, impact: tuple[str, ...], strong: bool = False) -> str:
    t = ticket.lower()
    category = _category(t, strong)
    # "Looks like a rounding bug" is the user's diagnosis, not a cosmetic complaint.
    cosmetic = _has(t, COSMETIC) and not (strong and " bug" in t)
    if category in ("how_to", "feature_request"):
        urgency = "low"
    elif _has(t, impact):
        urgency = "urgent"
    elif cosmetic or "not urgent" in t:
        urgency = "low"
    elif category == "billing" and "where do i find my invoices" in t:
        urgency = "low"
    else:
        urgency = "normal"
    return _emit(category, urgency)


def respond_rubric_v1(ticket: str) -> str:
    return _respond_rubric(ticket, IMPACT_V1)


def respond_rubric_v2(ticket: str) -> str:
    return _respond_rubric(ticket, IMPACT_V1 + PRIVACY_V2)


def respond_strong(ticket: str) -> str:
    return _respond_rubric(ticket, IMPACT_V1 + PRIVACY_V2 + EDGE_STRONG, strong=True)


PROFILES: dict[str, SimProfile] = {
    "baseline": SimProfile(respond_baseline, base_latency_s=0.30, per_token_latency_s=0.012, slow_tail_share=0.03),
    "rubric_v1": SimProfile(respond_rubric_v1, base_latency_s=0.45, per_token_latency_s=0.012, slow_tail_share=0.03),
    "rubric_v2": SimProfile(respond_rubric_v2, base_latency_s=0.45, per_token_latency_s=0.012, slow_tail_share=0.03),
    "strong": SimProfile(respond_strong, base_latency_s=1.25, per_token_latency_s=0.030, slow_tail_share=0.10),
}
