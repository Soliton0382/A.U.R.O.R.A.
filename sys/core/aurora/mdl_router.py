# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Which model does each step: the owner chooses, per role, a provider and a model (the 🧠 Models page).

 providers  local (llama.cpp), claude_code (the owner's subscription, CLI), anthropic, and the OpenAI-compatible APIs:
            openai, google (Gemini), xai (Grok), mistral, openrouter. Keys are secrets in the .env; model names are read
            from each provider's own list (/models), never typed from memory.
 roles      the steps of Aurora (ROLES): routing, translation, gate, extraction, synthesis, verification, self, agent,
            autonomic cycle, forge writer, forge judge, vision. Stored in <AURORA_STATUS_DIR>/models/roles.json; without
            it, the old AURORA_REASONER_PROVIDER / AURORA_CLOUD_ROLES decide.
 masking    every cloud call goes through sec_mask.Pseudonymizer (AURORA_CLOUD_MASK, on by default): what leaves is
            masked, the answer comes back unmasked; pictures cannot be masked and are counted apart.
 ethics     rule 9 (level B): without the owner's exemption no role goes to the cloud; a cloud error falls back to the
            local model, so a step never dies because a provider is down.
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Iterator

import httpx

from . import sys_config, sys_ethics, sys_log
from .mdl_llm import Completion
from .sec_mask import Pseudonymizer

PROVIDERS = {
    "local": {"label": "Locale (llama.cpp)", "kind": "local"},
    "claude_code": {"label": "Claude Code (abbonamento)", "kind": "claude_code"},
    "anthropic": {"label": "Anthropic API", "kind": "anthropic", "key": "AURORA_ANTHROPIC_API_KEY",
                  "base": "https://api.anthropic.com/v1"},
    "openai": {"label": "OpenAI", "kind": "openai", "key": "AURORA_OPENAI_API_KEY", "base": "https://api.openai.com/v1"},
    "google": {"label": "Google Gemini", "kind": "openai", "key": "AURORA_GOOGLE_API_KEY",
               "base": "https://generativelanguage.googleapis.com/v1beta/openai"},
    "xai": {"label": "xAI Grok", "kind": "openai", "key": "AURORA_XAI_API_KEY", "base": "https://api.x.ai/v1"},
    "mistral": {"label": "Mistral", "kind": "openai", "key": "AURORA_MISTRAL_API_KEY", "base": "https://api.mistral.ai/v1"},
    "openrouter": {"label": "OpenRouter", "kind": "openai", "key": "AURORA_OPENROUTER_API_KEY",
                   "base": "https://openrouter.ai/api/v1"},
}
ROLES = {   # role: (Italian label, English label, what it sees)
    "route": ("Smistamento delle domande", "Routing the questions", "your message, the last turns"),
    "translate": ("Traduzione", "Translation", "your question"),
    "gate": ("Cancello (le fonti rispondono?)", "Gate (do the sources answer?)", "question and passages of the vault"),
    "extract": ("Estrazione dalle fonti", "Extraction from the sources", "question and passages of the vault"),
    "synthesis": ("Sintesi della risposta", "Writing the answer", "extractions, recent conversation"),
    "verify": ("Verifica delle frasi", "Verifying the sentences", "sentences and passages"),
    "self": ("Risposte su di sé", "Answers about herself", "her state, memories, conversation"),
    "agent": ("Agente (strumenti)", "Agent (tools)", "the goal, tool results (logs, files, mail...)"),
    "rem": ("Ciclo autonomo (sogni, pensieri)", "Autonomic cycle (dreams, thoughts)", "memories, logs"),
    "forge_write": ("Forgia: scrittura plugin", "Forge: writing plugins", "samples of the data the plugin reads"),
    "forge_judge": ("Forgia: giudice", "Forge: judge", "samples and the plugin's output"),
    "vision": ("Visione (immagini)", "Vision (pictures)", "your photos and video frames — NOT maskable"),
}


def _dir(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def assignments(cfg: sys_config.Config) -> dict[str, dict]:
    """{role: {"provider", "model"}} — the owner's choice, else the old two settings."""
    try:
        saved = json.loads((_dir(cfg) / "roles.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = None
    if saved is None:
        old, cloud = cfg["AURORA_REASONER_PROVIDER"], {r.strip() for r in str(cfg["AURORA_CLOUD_ROLES"]).split(",")}
        saved = {r: {"provider": old if old != "local" and r in cloud else "local", "model": ""} for r in ROLES}
    return {r: {"provider": (saved.get(r) or {}).get("provider", "local"), "model": (saved.get(r) or {}).get("model", "")}
            for r in ROLES}


def set_assignments(cfg: sys_config.Config, changes: dict[str, dict]) -> dict[str, dict]:
    cur = assignments(cfg)
    for role, a in changes.items():
        if role not in ROLES or a.get("provider") not in PROVIDERS:
            raise ValueError(f"unknown role or provider: {role} {a.get('provider')}")
        cur[role] = {"provider": a["provider"], "model": str(a.get("model", ""))[:200]}
    f = _dir(cfg) / "roles.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    os.replace(tmp, f)
    return cur


# ---- OpenAI-compatible providers ---------------------------------------------------------------------------

class OpenAICompatLLM:
    """Chat completions of OpenAI, Google Gemini, xAI, Mistral, OpenRouter (same protocol)."""
    context_tokens = 128_000

    def __init__(self, provider: str, model: str, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.name, self.model = provider, model
        spec = PROVIDERS[provider]
        self.base, self.key = spec["base"], str(self.cfg.values.get(spec["key"]) or "")
        self.log = sys_log.get_logger("llm_client")
        self.last_speed = None

    def _headers(self) -> dict:
        if not self.key:
            raise RuntimeError(f"{PROVIDERS[self.name]['key']} is empty")
        return {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

    def _account(self, usage: dict, seconds: float) -> None:
        self.log.info("%s %s: in %s out %s, %.1f s", self.name, self.model, usage.get("prompt_tokens"),
                      usage.get("completion_tokens"), seconds)
        sys_log.trace("llm_client", "cloud.call", {"provider": self.name, "model": self.model, "usage": usage,
                                                   "cost_usd": usage.get("cost"), "seconds": round(seconds, 2)})

    def _chat(self, messages: list[dict], max_tokens: int) -> Completion:
        t0 = time.time()
        r = httpx.post(f"{self.base}/chat/completions", headers=self._headers(), timeout=self.cfg["AURORA_LLM_TIMEOUT_S"],
                       json={"model": self.model, "messages": messages, "max_tokens": max_tokens})
        r.raise_for_status()
        d = r.json()
        text = (d["choices"][0]["message"].get("content") or "").strip()
        self._account(d.get("usage") or {}, time.time() - t0)
        u = d.get("usage") or {}
        return Completion(text, "", int(u.get("completion_tokens") or 0), time.time() - t0,
                          d["choices"][0].get("finish_reason") == "length")

    def complete(self, system: str, user: str, max_tokens: int, think: bool = False) -> Completion:
        return self._chat([{"role": "system", "content": sys_config.personal(system, self.cfg)},
                           {"role": "user", "content": user}], max_tokens)

    def complete_turns(self, messages: list[dict], max_tokens: int, think: bool = False) -> Completion:
        msgs = [{"role": "user" if m["role"] == "tool" else m["role"],
                 "content": (f"TOOL RESULT:\n{m['content']}" if m["role"] == "tool" else
                             sys_config.personal(m["content"], self.cfg) if m["role"] == "system" else m["content"])}
                for m in messages]
        return self._chat(msgs, max_tokens)

    def stream(self, system: str, user: str, max_tokens: int, think: bool = False) -> Iterator[tuple[str, str]]:
        c = self.complete(system, user, max_tokens, think)             # one piece: simple and measured
        self.last_speed = {"tokens": c.tokens, "per_second": round(c.tokens / max(0.001, c.seconds), 1)}
        yield "answer", c.answer

    def see(self, jpeg: bytes, instruction: str, max_tokens: int = 700) -> str:
        uri = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        return self._chat([{"role": "user", "content": [{"type": "text", "text": instruction},
                                                          {"type": "image_url", "image_url": {"url": uri}}]}], max_tokens).answer

    def count_tokens(self, text: str) -> int:
        return len(text) // 3                                          # an estimate: these APIs have no counter


def list_models(provider: str, cfg: sys_config.Config | None = None) -> list[str]:
    """The provider's own list of models (GET /models)."""
    cfg = cfg or sys_config.get()
    spec = PROVIDERS[provider]
    if spec["kind"] == "local":
        return [Path(str(cfg["AURORA_LLM_MODEL"])).name]
    if spec["kind"] == "claude_code":
        return ["opus", "sonnet", "haiku"]                             # the CLI's own aliases
    key = str(cfg.values.get(spec["key"]) or "")
    if not key:
        raise RuntimeError(f"{spec['key']} is empty: add the key in the plugin's settings")
    headers = ({"x-api-key": key, "anthropic-version": "2023-06-01"} if spec["kind"] == "anthropic"
               else {"Authorization": f"Bearer {key}"})
    r = httpx.get(f"{spec['base']}/models", headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json().get("data") or r.json().get("models") or []
    return sorted({(m.get("id") or m.get("name") or "").removeprefix("models/") for m in data} - {""})


# ---- masking around every cloud call ------------------------------------------------------------------------

class MaskedLLM:
    """A cloud model seen through the Pseudonymizer: what leaves is masked, what comes back unmasked."""

    def __init__(self, inner, role: str, cfg: sys_config.Config):
        self.inner, self.role, self.cfg = inner, role, cfg
        self.name, self.model = inner.name, getattr(inner, "model", "")
        self.context_tokens = getattr(inner, "context_tokens", 32_000)
        self.last_speed = None

    def _p(self) -> Pseudonymizer:
        return Pseudonymizer(self.cfg)

    def _note(self, p: Pseudonymizer, images: int = 0) -> None:
        sys_log.trace("llm_client", "cloud.mask", {"role": self.role, "provider": self.name, "model": self.model,
                                                   "masked": dict(p.counts), "images": images})

    def complete(self, system: str, user: str, max_tokens: int, think: bool = False) -> Completion:
        p = self._p()
        c = self.inner.complete(p.mask(system), p.mask(user), max_tokens, think)
        self._note(p)
        return Completion(p.unmask(c.answer), p.unmask(c.thought), c.tokens, c.seconds, c.truncated)

    def complete_turns(self, messages: list[dict], max_tokens: int, think: bool = False) -> Completion:
        p = self._p()
        c = self.inner.complete_turns([{**m, "content": p.mask(m["content"])} for m in messages], max_tokens, think)
        self._note(p)
        return Completion(p.unmask(c.answer), p.unmask(c.thought), c.tokens, c.seconds, c.truncated)

    def stream(self, system: str, user: str, max_tokens: int, think: bool = False) -> Iterator[tuple[str, str]]:
        p = self._p()
        yield from p.unmask_stream(self.inner.stream(p.mask(system), p.mask(user), max_tokens, think))
        self.last_speed = getattr(self.inner, "last_speed", None)
        self._note(p)

    def see(self, jpeg: bytes, instruction: str, max_tokens: int = 700) -> str:
        p = self._p()
        out = self.inner.see(jpeg, p.mask(instruction), max_tokens)    # the picture itself cannot be masked
        self._note(p, images=1)
        return p.unmask(out)

    def count_tokens(self, text: str) -> int:
        return self.inner.count_tokens(text)


class Fallback:
    """A cloud model that falls back to the local one on any error (logged), so a step never dies."""

    def __init__(self, primary, local, role: str):
        self.primary, self.local, self.role = primary, local, role
        self.name, self.model = primary.name, getattr(primary, "model", "")
        self.context_tokens = getattr(primary, "context_tokens", 32_000)
        self.last_speed = None

    def _try(self, method: str, *a, **k):
        try:
            return getattr(self.primary, method)(*a, **k)
        except Exception as e:                           # noqa: BLE001 - a provider down must not stop Aurora
            sys_log.get_logger("llm_client").warning("%s on %s failed (%s): the local model does it", self.role,
                                                     self.name, str(e)[:200])
            sys_log.trace("llm_client", "cloud.fallback", {"role": self.role, "provider": self.name, "error": str(e)[:300]})
            return getattr(self.local, method)(*a, **k)

    def complete(self, *a, **k):
        return self._try("complete", *a, **k)

    def complete_turns(self, *a, **k):
        return self._try("complete_turns", *a, **k)

    def see(self, *a, **k):
        return self._try("see", *a, **k)

    def count_tokens(self, text: str) -> int:
        return self._try("count_tokens", text)

    def stream(self, *a, **k):
        try:
            pieces = list(self.primary.stream(*a, **k))                # a stream cannot change model half-way
            self.last_speed = getattr(self.primary, "last_speed", None)
            yield from pieces
        except Exception as e:                           # noqa: BLE001
            sys_log.get_logger("llm_client").warning("%s stream on %s failed (%s): local", self.role, self.name, str(e)[:200])
            yield from self.local.stream(*a, **k)
            self.last_speed = getattr(self.local, "last_speed", None)


def model_for(role: str, local, cfg: sys_config.Config | None = None):
    """The model that does `role` now: the owner's assignment, masked and with a local fallback when it is cloud."""
    cfg = cfg or sys_config.get()
    a = assignments(cfg).get(role, {"provider": "local", "model": ""})
    provider = a["provider"]
    if provider == "local":
        return local
    if not sys_ethics.exempt(cfg):                       # rule 9: no private data to cloud models without the exemption
        return local
    from . import mdl_cloud
    kind = PROVIDERS[provider]["kind"]
    if kind == "claude_code":
        inner = mdl_cloud.ClaudeCodeLLM(cfg, a["model"] or None)
    elif kind == "anthropic":
        inner = mdl_cloud.AnthropicLLM(cfg, a["model"] or None)
    else:
        if not a["model"]:
            return local
        inner = OpenAICompatLLM(provider, a["model"], cfg)
    model = MaskedLLM(inner, role, cfg) if cfg["AURORA_CLOUD_MASK"] else inner
    return Fallback(model, local, role)


# ---- statistics (the 🧠 Models page) ---------------------------------------------------------------------------

def stats(cfg: sys_config.Config | None = None, days: float = 7) -> dict:
    """Cloud calls, tokens, cost, masked items, pictures sent, fallbacks and SSCC compression of the last `days`,
    read from the trace files (written by the code at every call: measured, not estimated)."""
    import datetime as dt
    import gzip
    from collections import Counter, defaultdict
    cfg = cfg or sys_config.get()
    since = (dt.datetime.now().astimezone() - dt.timedelta(days=days)).isoformat()
    tdir = cfg.path("AURORA_LOG_DIR") / "trace"
    calls: dict = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0, "cached": 0, "cost_usd": 0.0, "seconds": 0.0})
    masked, by_role, images, fallbacks = Counter(), Counter(), 0, Counter()
    sscc = {"calls": 0, "chars_in": 0, "chars_out": 0}
    for f in sorted(tdir.glob("llm_client*")) + sorted(tdir.glob("api*")):
        opener = gzip.open if f.suffix == ".gz" else open
        try:
            with opener(f, "rt", errors="replace") as h:
                for line in h:
                    if '"cloud.' not in line or line[8:40] < since[:32]:
                        continue
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e["ts"] < since:
                        continue
                    p, ev = e.get("payload") or {}, e.get("event")
                    if ev == "cloud.call":
                        u = p.get("usage") or {}
                        c = calls[f"{p.get('provider')} · {p.get('model')}"]
                        c["calls"] += 1
                        c["in"] += int(u.get("input_tokens") or u.get("prompt_tokens") or 0)
                        c["out"] += int(u.get("output_tokens") or u.get("completion_tokens") or 0)
                        c["cached"] += int(u.get("cache_read_input_tokens") or 0)
                        c["cost_usd"] += float(p.get("cost_usd") or 0)
                        c["seconds"] += float(p.get("seconds") or 0)
                    elif ev == "cloud.mask":
                        masked.update(p.get("masked") or {})
                        by_role[p.get("role", "?")] += 1
                        images += int(p.get("images") or 0)
                    elif ev == "cloud.fallback":
                        fallbacks[p.get("role", "?")] += 1
                    elif ev == "cloud.compress":
                        sscc["calls"] += 1
                        sscc["chars_in"] += int(p.get("chars_in") or 0)
                        sscc["chars_out"] += int(p.get("chars_out") or 0)
        except OSError:
            continue
    sscc["saved_pct"] = round(100 * (1 - sscc["chars_out"] / sscc["chars_in"]), 1) if sscc["chars_in"] else None
    ref = None
    try:                                                  # the measured reference (M41, at the current 60%)
        bench = cfg.path("AURORA_STATUS_DIR") / "bench"
        f = bench / "sscc_long_60.json" if (bench / "sscc_long_60.json").exists() else bench / "sscc_long.json"
        b = json.loads(f.read_text())
        ref = {"tokens_full": b["tokens"][0], "tokens_sscc": b["tokens"][1], "score": b.get("mean"), "file": f.name}
    except (OSError, ValueError, KeyError, IndexError):
        pass
    return {"days": days, "calls": {k: {**v, "cost_usd": round(v["cost_usd"], 4), "seconds": round(v["seconds"], 1)}
                                    for k, v in calls.items()},
            "masked": dict(masked), "masked_calls_by_role": dict(by_role), "pictures_sent": images,
            "fallbacks": dict(fallbacks), "sscc": sscc, "sscc_reference": ref}
