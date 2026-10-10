# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How each model wants to be spoken to (owner, 9 Oct: «un modulo apposito così che quando si seleziona un modello e
questo viene chiamato passa dal modulo per l'applicazione del formato giusto … con cache che si aggiorna ogni tot»).

A Profile says, for one model: how its prompt is built, how its reasoning is switched on and off, the stop tokens,
the format it writes tool calls in, and whether its API takes tools natively.

- a local model (llama.cpp): read from its GGUF (mdl_gguf) — the architecture and the chat template it carries.
  Qwen keeps the hand-built ChatML prompt measured since M20-M24 («chatml»); any other family goes through
  llama-server's chat endpoint with its own template («native», llama-server started with --jinja), its reasoning
  switched by what the template understands (enable_thinking, reasoning_effort, a system line);
- a cloud model: from the provider and the model's name, and — where the provider lists its models' abilities
  (OpenRouter) — from that list, kept AURORA_FORMATS_CACHE_H hours in <STATUS>/model_formats.json: no call at
  every turn.
The agent's parser (agt_calls.parse) reads every format anyway: the profile is what Aurora tells and sends first.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from . import sys_config

_lock = threading.Lock()
CHATML_STOPS = ["<|im_end|>", "<|im_start|>", "<|endoftext|>"]


@dataclass(frozen=True)
class Profile:
    family: str                       # qwen, mistral, llama, nemotron, gpt-oss, gemma, deepseek, claude, openai…
    template: str                     # chatml (built by Aurora) | native (the model's own, llama-server --jinja) | api
    tools: str                        # the call format it writes: hermes, claude, llama, mistral, harmony, json, native
    native_tools: bool = False        # its API takes a tools list and returns tool_calls
    think_on: dict = field(default_factory=dict)      # chat_template_kwargs that switch the reasoning on…
    think_off: dict = field(default_factory=dict)     # …and off
    system_on: str = ""               # or a line in the system prompt (Nemotron: «detailed thinking on», /think)
    system_off: str = ""
    stops: tuple = ()

    def kwargs(self, think: bool) -> dict:
        return dict(self.think_on if think else self.think_off)

    def system(self, text: str, think: bool) -> str:
        line = self.system_on if think else self.system_off
        return f"{line}\n{text}" if line else text


def _tools_of(template: str) -> str:
    if "<tool_call>" in template:
        return "hermes"
    if "[TOOL_CALLS]" in template:
        return "mistral"
    if "<|python_tag|>" in template or "ipython" in template:
        return "llama"
    if "<|channel|>" in template:
        return "harmony"
    return "json"


def from_gguf(meta: dict) -> Profile:
    """The profile of a local model, from what its GGUF says (mdl_gguf.meta)."""
    arch, tmpl = str(meta.get("architecture", "")).lower(), str(meta.get("chat_template", ""))
    name = str(meta.get("name", "")).lower()
    if arch.startswith("qwen") and "<|im_start|>" in tmpl and "<think>" in tmpl:
        return Profile("qwen", "chatml", "hermes", stops=tuple(CHATML_STOPS))     # the measured path, unchanged
    family = next((f for f in ("nemotron", "mistral", "gpt-oss", "gemma", "deepseek", "llama", "granite", "phi", "qwen")
                   if f.replace("-", "") in (arch + name).replace("-", "")), arch or "unknown")
    on, off, son, soff = {}, {}, "", ""
    if "enable_thinking" in tmpl:
        on, off = {"enable_thinking": True}, {"enable_thinking": False}
    elif "reasoning_effort" in tmpl:
        on, off = {"reasoning_effort": "medium"}, {"reasoning_effort": "low"}
    elif "detailed thinking" in tmpl:
        son, soff = "detailed thinking on", "detailed thinking off"
    elif "/no_think" in tmpl:
        son, soff = "/think", "/no_think"
    return Profile(family, "native", _tools_of(tmpl), False, on, off, son, soff)


@lru_cache(maxsize=8)
def _local_cached(path: str, mtime: float) -> Profile:
    from . import mdl_gguf
    return from_gguf(mdl_gguf.meta(Path(path)))


def local(cfg: sys_config.Config | None = None) -> Profile:
    """The profile of the local reasoner (AURORA_LLM_MODEL); Qwen's when the file cannot be read (the measured one)."""
    cfg = cfg or sys_config.get()
    p = cfg.path("AURORA_LLM_MODEL")
    try:
        return _local_cached(str(p), p.stat().st_mtime)
    except (OSError, ValueError):
        return Profile("qwen", "chatml", "hermes", stops=tuple(CHATML_STOPS))


# ---- cloud models ----------------------------------------------------------------------------------------------
NATIVE_TOOLS = {"anthropic", "openai", "google", "mistral", "xai"}     # their chat APIs take tools


def _cache_file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "model_formats.json"


def _abilities(cfg: sys_config.Config, provider: str) -> dict:
    """{model: [supported parameters]} from the provider's own list, kept AURORA_FORMATS_CACHE_H hours. Only
    OpenRouter says it for every model (no key needed); the others: {}."""
    if provider != "openrouter":
        return {}
    f = _cache_file(cfg)
    with _lock:
        try:
            cache = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        hit = cache.get(provider)
        if hit and time.time() - hit.get("at", 0) < float(cfg["AURORA_FORMATS_CACHE_H"]) * 3600:
            return hit["models"]
        import httpx
        try:
            r = httpx.get("https://openrouter.ai/api/v1/models", timeout=20)
            r.raise_for_status()
            models = {m["id"]: m.get("supported_parameters") or [] for m in r.json().get("data", [])}
        except (httpx.HTTPError, ValueError, KeyError):
            return (hit or {}).get("models", {})              # the old list rather than none
        cache[provider] = {"at": time.time(), "models": models}
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache), encoding="utf-8")
        tmp.replace(f)
        return models


def cloud(cfg: sys_config.Config, provider: str, model: str) -> Profile:
    """The profile of a cloud model: Claude writes <invoke>, Mistral [TOOL_CALLS], the others JSON calls."""
    m = model.lower()
    if provider in ("anthropic", "claude_code") or m.startswith(("claude", "anthropic/")):
        return Profile("claude", "api", "claude", provider == "anthropic")
    family = next((f for f in ("mistral", "llama", "gemini", "gpt", "grok", "qwen", "deepseek") if f in m), provider)
    tools = {"mistral": "mistral", "llama": "llama", "qwen": "hermes"}.get(family, "json")
    native = provider in NATIVE_TOOLS
    if provider == "openrouter":
        native = "tools" in _abilities(cfg, provider).get(model, [])
    return Profile(family, "api", tools, native)


def profile(cfg: sys_config.Config, provider: str = "local", model: str = "") -> Profile:
    return local(cfg) if provider == "local" else cloud(cfg, provider, model)


def describe(p: Profile) -> dict:
    return asdict(p)


def needs_jinja(cfg: sys_config.Config | None = None) -> bool:
    """llama-server must apply the model's own template (--jinja): every family but the measured ChatML one."""
    return local(cfg).template == "native"

