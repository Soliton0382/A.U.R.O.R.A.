# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""An agent's conversation shortened to fit the local model's window (C331, found by Aurora's own self-repair).

The agent trims its conversation to the cloud model's context (200k). When the cloud call fails, or today's budget is
spent, the same conversation goes to the local server, whose context is split among its slots (32768 each): a longer
one is a 400 «exceeds the available context size». Here the oldest tool results are shortened first, then the oldest
steps dropped; the system prompt, the goal and the last four turns always stay. Her fix from the sandbox
fallback-ctx-10c9d2, plus two more things: it also covers the budget path, and a dropped step takes its tool results with it.
"""
from __future__ import annotations

KEEP_LAST = 4                                            # the latest turns: what the model is answering now
SHORT = 400
# said so the model can get it back (C396: a source cut without a way back was filled with invention)
SHORTENED = "[shortened: an older result — call the same tool again if you still need it]"


def window(cfg) -> int:
    """Tokens one local slot holds; 0 when the settings do not say."""
    try:
        return int(cfg["AURORA_LLM_CTX"]) // max(1, int(cfg["AURORA_LLM_PARALLEL"] or 1))
    except (KeyError, TypeError, ValueError):
        return 0


def used(messages: list[dict]) -> int:
    # a safe estimate: chars / 2.5 — chars / 3 let 42,540 real tokens through as fitting (C380: code, JSON, Italian)
    return sum(len(str(m.get("content") or "")) for m in messages) * 2 // 5


def fit(messages: list[dict], max_tokens: int, ctx: int) -> tuple[list[dict], int]:
    """(messages, max_tokens) that fit `ctx`; the caller's list is not changed."""
    if ctx <= 0:
        return messages, max_tokens
    max_tokens = min(max_tokens, ctx // 4)               # an answer never takes the whole window
    want = max_tokens + 256
    out = [dict(m) for m in messages]
    for m in out[2:-KEEP_LAST]:
        if used(out) + want <= ctx:
            break
        if m["role"] == "tool" and len(str(m["content"])) > SHORT + 100:
            m["content"] = str(m["content"])[:SHORT] + "\n" + SHORTENED
    while used(out) + want > ctx and len(out) > 2 + KEEP_LAST:
        del out[2]
        while len(out) > 2 + KEEP_LAST and out[2]["role"] == "tool":    # no result without the call that asked it
            del out[2]
    for m in out[2:]:                      # C380: the last turns alone too long (long file reads): their results too
        if used(out) + want <= ctx:
            break
        if m["role"] == "tool" and len(str(m["content"])) > 5 * SHORT:
            m["content"] = str(m["content"])[:5 * SHORT] + "\n[shortened to fit the local model's window]"
    return out, max_tokens


class CloudOut(RuntimeError):
    """The cloud stopped mid-run and what is left of the run does not fit the local slot (C385): the phase stops with
    a clear word («cloud esaurito», try again later) instead of a context error from the local server."""


def fits(messages: list[dict], max_tokens: int, ctx: int) -> bool:
    """Whether fitted messages and their answer stay inside the local window (the same estimate as fit)."""
    return ctx <= 0 or used(messages) + max_tokens + 256 <= ctx


def context_error(e: Exception) -> bool:
    """A local server's refusal of a prompt longer than its slot (a 400 «exceeds the available context size»)."""
    r = getattr(e, "response", None)
    try:
        return r is not None and r.status_code == 400 and "context" in r.text.lower()
    except Exception:                                    # noqa: BLE001 - a body that cannot be read: not this error
        return False
