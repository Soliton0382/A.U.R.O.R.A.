# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How much each step costs, and a daily ceiling on what the cloud may spend.

Cloud: every call's tokens (input + output, cache writes included, the provider's own count) are added to the day's
file <AURORA_STATUS_DIR>/models/usage/<YYYYMMDD>.json, shared by every process under a lock. A provider paid by the
token (Anthropic API, OpenAI, Google, xAI, Mistral, OpenRouter) that reaches AURORA_CLOUD_DAILY_TOKENS today is not
called again until tomorrow: its steps go back to the local model (mdl_router.Fallback), the day's file records it
and the health says it. 0 = no ceiling. Claude Code is the owner's subscription, not billed by the token: no ceiling.
The default (200,000) is ~20 calls at the measured p90 of 9,968 tokens per call (M61).

Local: every call of the local model is traced with its role ("local.call": output tokens, input characters,
seconds), so that what a step would cost on the cloud is measured before it is moved there.
"""
from __future__ import annotations

import fcntl
import json
import time
from pathlib import Path

from . import sys_config, sys_log

PAID = {"anthropic", "openai", "google", "xai", "mistral", "openrouter"}


def tokens_of(usage: dict) -> int:
    u = usage or {}
    return int((u.get("input_tokens") or u.get("prompt_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
               + (u.get("output_tokens") or u.get("completion_tokens") or 0))


def _file(cfg: sys_config.Config, day: str | None = None) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "models" / "usage"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{day or time.strftime('%Y%m%d')}.json"


def _update(cfg: sys_config.Config, change) -> dict:
    f = _file(cfg)
    with open(f, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        try:
            data = json.loads(fh.read() or "{}")
        except ValueError:
            data = {}
        change(data)
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(data))
    return data


def record(cfg: sys_config.Config, provider: str, usage: dict) -> int:
    """Add a call's tokens to today's total of `provider`; returns the new total."""
    n = tokens_of(usage)

    def add(d):
        d.setdefault("tokens", {})[provider] = d.get("tokens", {}).get(provider, 0) + n
        d.setdefault("calls", {})[provider] = d.get("calls", {}).get(provider, 0) + 1
    return _update(cfg, add)["tokens"][provider]


def today(cfg: sys_config.Config) -> dict:
    try:
        return json.loads(_file(cfg).read_text() or "{}")
    except (OSError, ValueError):
        return {}


def over(cfg: sys_config.Config, provider: str) -> bool:
    """True when a provider paid by the token has spent today's ceiling (said once a day in the log and the trace)."""
    cap = int(cfg["AURORA_CLOUD_DAILY_TOKENS"] or 0)
    if provider not in PAID or cap <= 0:
        return False
    d = today(cfg)
    spent = d.get("tokens", {}).get(provider, 0)
    if spent < cap:
        return False
    if provider not in d.get("stopped", []):
        _update(cfg, lambda x: x.setdefault("stopped", []).append(provider) if provider not in x.get("stopped", []) else None)
        sys_log.get_logger("llm_client").warning("%s: daily ceiling reached (%d of %d tokens): local model until tomorrow",
                                                 provider, spent, cap)
        sys_log.trace("llm_client", "cloud.budget", {"provider": provider, "spent": spent, "cap": cap})
    return True


class Metered:
    """The local model as it is, with each call traced under the step's name (what the step would cost elsewhere)."""

    def __init__(self, inner, role: str):
        self._inner, self._role = inner, role

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def _trace(self, t0: float, chars_in: int, tokens_out: int) -> None:
        sys_log.trace("llm_client", "local.call", {"role": self._role, "chars_in": chars_in, "tokens_out": tokens_out,
                                                   "seconds": round(time.time() - t0, 2)})

    def complete(self, system: str, user: str, max_tokens: int, think: bool = False):
        t0 = time.time()
        c = self._inner.complete(system, user, max_tokens, think)
        self._trace(t0, len(system) + len(user), c.tokens)
        return c

    def complete_turns(self, messages: list[dict], max_tokens: int, think: bool = False):
        t0 = time.time()
        c = self._inner.complete_turns(messages, max_tokens, think)
        self._trace(t0, sum(len(str(m.get("content", ""))) for m in messages), c.tokens)
        return c

    def stream(self, system: str, user: str, max_tokens: int, think: bool = False):
        t0, chars = time.time(), 0
        for kind, piece in self._inner.stream(system, user, max_tokens, think):
            chars += len(piece)
            yield kind, piece
        self._trace(t0, len(system) + len(user), chars // 4)     # streamed: output tokens estimated from characters
