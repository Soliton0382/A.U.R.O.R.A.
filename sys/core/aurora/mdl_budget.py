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
        now = time.time()                               # the last minute's calls, for a per-minute limit
        d.setdefault("recent", {})[provider] = [t for t in d.get("recent", {}).get(provider, []) if now - t < 60] + [now]
    return _update(cfg, add)["tokens"][provider]


# Per-provider limits (owner, 2026-10-06: "a tick beside each choice to stay in the free usage"): a provider with
# "free" on is not called past its requests a minute, requests a day or tokens a day — its steps go to the local model
# until the minute or the day turns. The presets are the free tiers as the providers published them (2025-2026),
# NOT measured here and changed by the providers often: the owner can correct them on the Models page.
FREE_PRESETS = {"google": {"per_minute": 10, "per_day": 250, "tokens_per_day": 250000},
                "xai": {"per_minute": 0, "per_day": 0, "tokens_per_day": 0},
                "openai": {"per_minute": 0, "per_day": 0, "tokens_per_day": 0},
                "anthropic": {"per_minute": 0, "per_day": 0, "tokens_per_day": 0},
                "mistral": {"per_minute": 1, "per_day": 0, "tokens_per_day": 0},
                "openrouter": {"per_minute": 20, "per_day": 50, "tokens_per_day": 0}}


def _limits_file(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d / "limits.json"


def limits(cfg: sys_config.Config) -> dict:
    try:
        saved = json.loads(_limits_file(cfg).read_text())
    except (OSError, ValueError):
        saved = {}
    return {p: {"free": bool((saved.get(p) or {}).get("free")), **FREE_PRESETS[p],
                **{k: int(v) for k, v in (saved.get(p) or {}).items() if k in FREE_PRESETS[p]}} for p in FREE_PRESETS}


def set_limits(cfg: sys_config.Config, changes: dict) -> dict:
    cur = limits(cfg)
    for p, c in changes.items():
        if p not in FREE_PRESETS or not isinstance(c, dict):
            raise ValueError(f"provider: one of {sorted(FREE_PRESETS)}")
        if "free" in c:
            cur[p]["free"] = bool(c["free"])
        for k in FREE_PRESETS[p]:
            if k in c:
                v = int(c[k])
                if not 0 <= v <= 10_000_000:
                    raise ValueError(f"{p}.{k}: 0-10,000,000 (0 = no limit)")
                cur[p][k] = v
    _limits_file(cfg).write_text(json.dumps(cur, indent=1))
    return cur


def free_reason(cfg: sys_config.Config, provider: str, d: dict | None = None) -> str:
    """Why a provider kept in its free tier may not be called now ("" when it may)."""
    lim = limits(cfg).get(provider)
    if not lim or not lim["free"]:
        return ""
    d = today(cfg) if d is None else d
    now = time.time()
    if lim["per_minute"] and len([t for t in d.get("recent", {}).get(provider, []) if now - t < 60]) >= lim["per_minute"]:
        return f"{lim['per_minute']} requests a minute"
    if lim["per_day"] and d.get("calls", {}).get(provider, 0) >= lim["per_day"]:
        return f"{lim['per_day']} requests a day"
    if lim["tokens_per_day"] and d.get("tokens", {}).get(provider, 0) >= lim["tokens_per_day"]:
        return f"{lim['tokens_per_day']} tokens a day"
    return ""


def today(cfg: sys_config.Config) -> dict:
    try:
        return json.loads(_file(cfg).read_text() or "{}")
    except (OSError, ValueError):
        return {}


def over(cfg: sys_config.Config, provider: str) -> bool:
    """True when a provider paid by the token has spent today's ceiling (said once a day in the log and the trace)."""
    d = today(cfg)
    why = free_reason(cfg, provider, d)
    if why:                                             # the free tier the owner chose to stay in: the local model
        sys_log.trace("llm_client", "cloud.free_limit", {"provider": provider, "limit": why})
        return True
    cap = int(cfg["AURORA_CLOUD_DAILY_TOKENS"] or 0)
    if provider not in PAID or cap <= 0:
        return False
    spent = d.get("tokens", {}).get(provider, 0)
    if spent < cap:
        if provider in d.get("stopped", []):              # the owner raised the ceiling: no longer stopped
            _update(cfg, lambda x: x["stopped"].remove(provider) if provider in x.get("stopped", []) else None)
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
