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


def window(cfg) -> int:
    """Tokens one local slot holds; 0 when the settings do not say."""
    try:
        return int(cfg["AURORA_LLM_CTX"]) // max(1, int(cfg["AURORA_LLM_PARALLEL"] or 1))
    except (KeyError, TypeError, ValueError):
        return 0


def used(messages: list[dict]) -> int:
    return sum(len(str(m.get("content") or "")) for m in messages) // 3      # a safe estimate: chars / 3


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
            m["content"] = str(m["content"])[:SHORT] + "\n[shortened: an older result]"
    while used(out) + want > ctx and len(out) > 2 + KEEP_LAST:
        del out[2]
        while len(out) > 2 + KEEP_LAST and out[2]["role"] == "tool":    # no result without the call that asked it
            del out[2]
    return out, max_tokens
