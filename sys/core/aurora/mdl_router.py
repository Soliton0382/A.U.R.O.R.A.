# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Which model does each step: the owner chooses, per role, a provider and a model (the 🧠 Models page).

 providers  local (llama.cpp), claude_code (the owner's subscription, CLI), anthropic, and the OpenAI-compatible APIs:
            openai, google (Gemini), xai (Grok), mistral, openrouter. Keys are secrets in the .env; model names are read
            from each provider's own list (/models), never typed from memory.
 roles      the steps of Aurora (ROLES): routing, translation, gate, extraction, synthesis, verification, self, agent,
            autonomic cycle, forge writer, forge judge, vision. Stored in <AURORA_STATUS_DIR>/models/roles.json; without
            it, the old AURORA_REASONER_PROVIDER / AURORA_CLOUD_ROLES decide.
 masking    every cloud call goes through sec_mask.Pseudonymizer, always (no setting turns it off): what leaves is
            masked, the answer comes back unmasked; pictures cannot be masked and are counted apart.
 ethics     rule 9 (level B): without the owner's exemption no role goes to the cloud; a cloud error falls back to the
            local model, so a step never dies because a provider is down.
"""
from __future__ import annotations

import base64
import json
import os
import re
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
    # any other OpenAI-compatible service: its address is a setting, its key may be empty (a server that asks none)
    "custom": {"label": "Altro servizio (compatibile OpenAI)", "kind": "openai", "key": "AURORA_CUSTOM_API_KEY",
               "base_key": "AURORA_CUSTOM_BASE_URL", "key_optional": True},
}


def base_url(provider: str, cfg: sys_config.Config) -> str:
    """A provider's address: fixed, or the owner's setting (custom)."""
    spec = PROVIDERS[provider]
    return str(spec.get("base") or cfg.values.get(spec.get("base_key", "")) or "").rstrip("/")


def configured(provider: str, cfg: sys_config.Config) -> bool:
    """Whether a provider can be asked: its key (and, for custom, its address) set."""
    spec = PROVIDERS[provider]
    if spec["kind"] in ("local", "claude_code"):
        return True
    if spec.get("base_key") and not base_url(provider, cfg):
        return False
    return bool(spec.get("key_optional") or cfg.values.get(spec.get("key", "")))
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
    "service": ("Chiamate di servizio (titoli, classificazione, ricerca di fonti, bozze)",
                "Service calls (titles, classification, finding sources, drafts)",
                "titles and pieces of documents, your question, the drafts"),
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
        key = PROVIDERS[a["provider"]].get("key")
        if not configured(a["provider"], cfg) and a["provider"] != cur[role]["provider"]:
            raise ValueError(f"{a['provider']} has no key or address yet ({key}): add it in the cloud plugin's card first")
        cur[role] = {"provider": a["provider"], "model": str(a.get("model", ""))[:200]}
    f = _dir(cfg) / "roles.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    os.replace(tmp, f)
    return cur


# ---- OpenAI-compatible providers ---------------------------------------------------------------------------

def _thought(d: dict, max_tokens: int) -> bool:
    """The thinking took at least half the budget (usage: total - prompt - visible, the Gemini way; or the
    reasoning_tokens OpenAI reports)."""
    u = d.get("usage") or {}
    spent = (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
    if spent is None and u.get("total_tokens") is not None:
        spent = int(u["total_tokens"]) - int(u.get("prompt_tokens") or 0) - int(u.get("completion_tokens") or 0)
    return bool(spent) and spent >= max_tokens / 2


# the agent's tools in its system prompt (agt_loop.Agent._system): one JSON spec per line, then the call format
TOOLS_LIST = re.compile(r"<tools>\n(.*?)\n</tools>", re.S)
TOOLS_BLOCK = re.compile(r"# Tools\n.*?</tool_call>", re.S)
NATIVE_NOTE = "# Tools\n\nCall the functions you are given through the API's tool calls, one or more per turn."
# a reply's tool_calls as the API gave them, by (name, arguments): sent back as they were — Gemini 3 refuses a call
# without the thought_signature it attached (measured 10 Oct: 400 «Function call is missing a thought_signature»)
_GIVEN: dict[tuple[str, str], dict] = {}
_GIVEN_MAX = 256


def _key(name: str, args) -> tuple[str, str]:
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except ValueError:
            return name, args
    return name, json.dumps(args, ensure_ascii=False, sort_keys=True)


def native_turns(messages: list[dict]) -> tuple[list[dict], list[dict]] | None:
    """(messages, tools) in the chat API's own tool form (roadmap 73: «ricordati delle API tool calling»), from the
    agent's text form: the specs leave the system prompt for the request's `tools`, an assistant turn's calls become
    its tool_calls, each tool result answers its call by id. None when the turns carry no tool list (a plain chat) or
    a spec is not JSON: the text form then goes as it is."""
    from .agt_loop import parse                         # here: agt_loop reaches this module through the pipeline
    system = next((m for m in messages if m["role"] == "system" and isinstance(m["content"], str)
                   and TOOLS_LIST.search(m["content"])), None)
    if system is None:
        return None
    try:
        tools = [json.loads(x) for x in TOOLS_LIST.search(system["content"]).group(1).splitlines() if x.strip()]
    except ValueError:
        return None
    out: list[dict] = []
    waiting: list[str] = []                             # ids of the last calls not answered yet

    def settle():                                       # every call needs its answer, or the API refuses the turn
        while waiting:
            out.append({"role": "tool", "tool_call_id": waiting.pop(0), "content": "(no result)"})
    for n, m in enumerate(messages):
        if m is system:
            out.append({"role": "system", "content": TOOLS_BLOCK.sub(NATIVE_NOTE, m["content"])})
        elif m["role"] == "assistant":
            settle()
            _, calls, said = parse(m["content"] or "")
            native = []
            for k, raw in enumerate(calls):
                try:
                    c = json.loads(raw)
                    name, args = str(c["name"]), c.get("arguments") or {}
                except (ValueError, KeyError, TypeError):
                    continue
                given = _GIVEN.get(_key(name, args))
                native.append(given or {"id": f"call_{n}_{k}", "type": "function", "function": {
                    "name": name, "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)}})
            if native:
                out.append({"role": "assistant", "content": said or None, "tool_calls": native})
                waiting = [c["id"] for c in native]
            else:
                out.append({"role": "assistant", "content": m["content"]})
        elif m["role"] == "tool" and waiting:
            out.append({"role": "tool", "tool_call_id": waiting.pop(0), "content": m["content"]})
        elif m["role"] == "tool":                       # a result with no call left to answer: said as text
            out.append({"role": "user", "content": f"TOOL RESULT:\n{m['content']}"})
        else:
            settle()
            out.append({"role": m["role"], "content": m["content"]})
    settle()
    return out, tools


def as_text(message: dict) -> str:
    """A reply's native tool_calls written in the agent's own <tool_call> form, after its words."""
    text = (message.get("content") or "").strip()
    for c in message.get("tool_calls") or []:
        fn = c.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = fn.get("arguments")
        _GIVEN[_key(fn.get("name", ""), args)] = c
        while len(_GIVEN) > _GIVEN_MAX:
            _GIVEN.pop(next(iter(_GIVEN)))
        text += "\n<tool_call>\n" + json.dumps({"name": fn.get("name", ""), "arguments": args}, ensure_ascii=False) \
                + "\n</tool_call>"
    return text.strip()


class OpenAICompatLLM:
    """Chat completions of OpenAI, Google Gemini, xAI, Mistral, OpenRouter (same protocol)."""
    context_tokens = 128_000

    def __init__(self, provider: str, model: str, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.name, self.model = provider, model
        spec = PROVIDERS[provider]
        self.base, self.key = base_url(provider, self.cfg), str(self.cfg.values.get(spec["key"]) or "")
        self.key_optional = bool(spec.get("key_optional"))
        self.log = sys_log.get_logger("llm_client")
        self.last_speed = None

    def _headers(self) -> dict:
        if not self.base:
            raise RuntimeError(f"{PROVIDERS[self.name].get('base_key')} is empty")
        if not self.key and not self.key_optional:
            raise RuntimeError(f"{PROVIDERS[self.name]['key']} is empty")
        return {**({"Authorization": f"Bearer {self.key}"} if self.key else {}), "Content-Type": "application/json"}

    def _account(self, usage: dict, seconds: float) -> None:
        self.log.info("%s %s: in %s out %s, %.1f s", self.name, self.model, usage.get("prompt_tokens"),
                      usage.get("completion_tokens"), seconds)
        sys_log.trace("llm_client", "cloud.call", {"provider": self.name, "model": self.model, "usage": usage,
                                                   "cost_usd": usage.get("cost"), "seconds": round(seconds, 2)})
        from . import mdl_budget
        mdl_budget.record(self.cfg, self.name, usage)

    # (provider, model) that refused a parameter: not sent to them again in this process
    _refused: set[tuple[str, str, str]] = set()
    THINK_ROOM = 4096                                  # C209: added once when the thinking took the whole budget

    def _post(self, body: dict) -> dict:
        """One chat call. A parameter the model refuses (reasoning_effort on a model that does not think, max_tokens
        where only max_completion_tokens is accepted) is dropped or renamed once, and remembered."""
        body = dict(body)
        if (self.name, self.model, "reasoning_effort") in self._refused:
            body.pop("reasoning_effort", None)
        if (self.name, self.model, "max_tokens") in self._refused and "max_tokens" in body:
            body["max_completion_tokens"] = body.pop("max_tokens")
        for _ in range(3):
            r = httpx.post(f"{self.base}/chat/completions", headers=self._headers(),
                           timeout=self.cfg["AURORA_LLM_TIMEOUT_S"], json=body)
            low = r.text.lower() if r.status_code in (400, 422) else ""
            if "reasoning_effort" in body and "reasoning" in low:
                self._refused.add((self.name, self.model, "reasoning_effort"))
                body.pop("reasoning_effort")
            elif "max_tokens" in body and "max_completion_tokens" in low:
                self._refused.add((self.name, self.model, "max_tokens"))
                body["max_completion_tokens"] = body.pop("max_tokens")
            else:
                break
        r.raise_for_status()
        return r.json()

    def _chat(self, messages: list[dict], max_tokens: int, think: bool = False, tools: list | None = None) -> Completion:
        t0 = time.time()
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens}
        if tools:
            body["tools"] = tools
        if not think:                                  # a short step: as little thinking as the model allows
            body["reasoning_effort"] = "low"
        d = self._post(body)
        text = as_text(d["choices"][0]["message"])
        if d["choices"][0].get("finish_reason") == "length" and (not text or _thought(d, max_tokens)):
            # C209: a model that cannot stop thinking (Gemini pro) counts its thinking in max_tokens: with the 16-32
            # tokens of a short step it answered nothing (measured 8 Oct 2026, gemini-pro-latest: 0 tokens of answer).
            # C230: or a few words of it — 6 visible of 200, 190 thought: the question cut to «La mia mail è [EMAIL»
            self.log.info("%s %s: the thinking took all %d tokens, asked again with %d more", self.name, self.model,
                          max_tokens, self.THINK_ROOM)
            self._account(d.get("usage") or {}, time.time() - t0)
            d = self._post({**body, "max_tokens": max_tokens + self.THINK_ROOM})
            text = as_text(d["choices"][0]["message"])
        self._account(d.get("usage") or {}, time.time() - t0)
        u = d.get("usage") or {}
        return Completion(text, "", int(u.get("completion_tokens") or 0), time.time() - t0,
                          d["choices"][0].get("finish_reason") == "length")

    def complete(self, system: str, user: str, max_tokens: int, think: bool = False) -> Completion:
        return self._chat([{"role": "system", "content": sys_config.personal(system, self.cfg)},
                           {"role": "user", "content": user}], max_tokens, think)

    def complete_turns(self, messages: list[dict], max_tokens: int, think: bool = False) -> Completion:
        from . import mdl_formats
        native = native_turns(messages) if (self.name, self.model, "tools") not in self._refused else None
        if native and mdl_formats.cloud(self.cfg, self.name, self.model).native_tools:
            msgs, tools = native
            msgs = [{**m, "content": sys_config.personal(m["content"], self.cfg)} if m["role"] == "system" else m
                    for m in msgs]
            try:
                return self._chat(msgs, max_tokens, think, tools)
            except httpx.HTTPStatusError as e:          # a model that refuses tools after all: the text form, from now on
                if e.response.status_code not in (400, 404, 422) or "tool" not in e.response.text.lower():
                    raise
                self._refused.add((self.name, self.model, "tools"))
                self.log.info("%s %s refused native tools (%s): the text form", self.name, self.model,
                              e.response.text[:160])
        msgs = [{"role": "user" if m["role"] == "tool" else m["role"],
                 "content": (f"TOOL RESULT:\n{m['content']}" if m["role"] == "tool" else
                             sys_config.personal(m["content"], self.cfg) if m["role"] == "system" else m["content"])}
                for m in messages]
        return self._chat(msgs, max_tokens, think)

    def stream(self, system: str, user: str, max_tokens: int, think: bool = False) -> Iterator[tuple[str, str]]:
        c = self.complete(system, user, max_tokens, think)             # one piece: simple and measured
        self.last_speed = {"tokens": c.tokens, "per_second": round(c.tokens / max(0.001, c.seconds), 1)}
        yield "answer", c.answer

    def see(self, jpeg: bytes, instruction: str, max_tokens: int = 700) -> str:
        uri = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        return self._chat([{"role": "user", "content": [{"type": "text", "text": instruction},
                                                          {"type": "image_url", "image_url": {"url": uri}}]}], max_tokens).answer

    def see_many(self, frames: list[tuple[str, bytes]], instruction: str, max_tokens: int = 1600) -> str:
        parts: list[dict] = [{"type": "text", "text": instruction}]
        for label, jpeg in frames:
            parts += [{"type": "text", "text": f"Frame at {label}:"},
                      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}}]
        return self._chat([{"role": "user", "content": parts}], max_tokens).answer

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
    if not configured(provider, cfg):
        raise RuntimeError(f"{spec.get('base_key') if spec.get('base_key') and not base_url(provider, cfg) else spec['key']}"
                           " is empty: add it in the plugin's settings")
    headers = ({"x-api-key": key, "anthropic-version": "2023-06-01"} if spec["kind"] == "anthropic"
               else {"Authorization": f"Bearer {key}"} if key else {})
    r = httpx.get(f"{base_url(provider, cfg)}/models", headers=headers, timeout=30)
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

    def _named(self, system: str) -> str:
        """The names put into the prompt BEFORE masking (C132): filled after it, by the provider's client, the owner's
        name left unmasked."""
        return sys_config.personal(system, self.cfg)

    def _note(self, p: Pseudonymizer, images: int = 0) -> None:
        sys_log.trace("llm_client", "cloud.mask", {"role": self.role, "provider": self.name, "model": self.model,
                                                   "masked": dict(p.counts), "images": images})

    @staticmethod
    def _keep(p: Pseudonymizer, system: str) -> str:
        """The masked system prompt, told to keep the placeholders as they are when there are any (C86)."""
        from .sec_mask import KEEP
        return system + KEEP if p.counts else system

    def complete(self, system: str, user: str, max_tokens: int, think: bool = False) -> Completion:
        p = self._p()
        ms, mu = p.mask(self._named(system)), p.mask(user)
        c = self.inner.complete(self._keep(p, ms), mu, max_tokens, think)
        self._note(p)
        return Completion(p.unmask(c.answer), p.unmask(c.thought), c.tokens, c.seconds, c.truncated)

    def complete_turns(self, messages: list[dict], max_tokens: int, think: bool = False) -> Completion:
        p = self._p()
        masked = [{**m, "content": p.mask(self._named(m["content"]) if m.get("role") == "system" else m["content"])}
                  for m in messages]
        if p.counts:                                     # keep the placeholders (C86): told in the system message
            i = next((n for n, m in enumerate(masked) if m.get("role") == "system" and isinstance(m["content"], str)), None)
            if i is None:
                masked.insert(0, {"role": "system", "content": self._keep(p, "").strip()})
            else:
                masked[i] = {**masked[i], "content": self._keep(p, masked[i]["content"])}
        c = self.inner.complete_turns(masked, max_tokens, think)
        self._note(p)
        return Completion(p.unmask(c.answer), p.unmask(c.thought), c.tokens, c.seconds, c.truncated)

    def stream(self, system: str, user: str, max_tokens: int, think: bool = False) -> Iterator[tuple[str, str]]:
        p = self._p()
        ms, mu = p.mask(self._named(system)), p.mask(user)
        yield from p.unmask_stream(self.inner.stream(self._keep(p, ms), mu, max_tokens, think))
        self.last_speed = getattr(self.inner, "last_speed", None)
        self._note(p)

    def see(self, jpeg: bytes, instruction: str, max_tokens: int = 700) -> str:
        p = self._p()
        out = self.inner.see(jpeg, p.mask(instruction), max_tokens)    # the picture itself cannot be masked
        self._note(p, images=1)
        return p.unmask(out)

    def see_many(self, frames: list[tuple[str, bytes]], instruction: str, max_tokens: int = 1600) -> str:
        p = self._p()
        out = self.inner.see_many(frames, p.mask(instruction), max_tokens)
        self._note(p, images=len(frames))
        return p.unmask(out)

    def count_tokens(self, text: str) -> int:
        return self.inner.count_tokens(text)


class Fallback:
    """A cloud model that falls back to the local one on any error (logged), so a step never dies."""

    def __init__(self, primary, local, role: str, cfg: sys_config.Config | None = None, provider: str = ""):
        self.primary, self.local, self.role, self.cfg, self.provider = primary, local, role, cfg, provider
        self.name, self.model = primary.name, getattr(primary, "model", "")
        self.context_tokens = getattr(primary, "context_tokens", 32_000)
        self.last_speed = None

    def _try(self, method: str, *a, **k):
        from . import mdl_budget
        if self.cfg is not None and mdl_budget.over(self.cfg, self.provider):    # today's ceiling: the local model
            return getattr(self.local, method)(*a, **k)
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

    def see_many(self, *a, **k):
        return self._try("see_many", *a, **k)

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


def is_local(model, local) -> bool:
    """Whether a step's model is the local one (model_for wraps it in a meter: identity is not the test)."""
    return model is local or getattr(model, "_inner", None) is local


def model_for(role: str, local, cfg: sys_config.Config | None = None):
    """The model that does `role` now: the owner's assignment, masked and with a local fallback when it is cloud."""
    cfg = cfg or sys_config.get()
    a = assignments(cfg).get(role, {"provider": "local", "model": ""})
    provider = a["provider"]
    from .mdl_budget import Metered
    metered = Metered(local, role)                       # every local call traced with its step (what it would cost)
    if provider == "local":
        return metered
    if not sys_ethics.exempt(cfg):                       # rule 9: no private data to cloud models without the exemption
        return metered
    inner = cloud_client(provider, a["model"], cfg)
    if inner is None:
        return metered
    model = MaskedLLM(inner, role, cfg)                 # always: no setting turns the masking off (owner, 2026-10-05)
    return Fallback(model, metered, role, cfg, provider)


def cloud_client(provider: str, model: str, cfg: sys_config.Config):
    """A cloud provider's client, not masked yet (model_for and CloudBase wrap it); None when an OpenAI-compatible
    provider has no model chosen."""
    from . import mdl_cloud
    kind = PROVIDERS[provider]["kind"]
    if kind == "claude_code":
        return mdl_cloud.ClaudeCodeLLM(cfg, model or None)
    if kind == "anthropic":
        return mdl_cloud.AnthropicLLM(cfg, model or None)
    if kind == "openai" and model:
        return OpenAICompatLLM(provider, model, cfg)
    return None


# ---- a machine without a local reasoner --------------------------------------------------------------------------

def cloud_only(cfg: sys_config.Config) -> bool:
    """No local reasoner on this machine (AURORA_LLM_BACKEND=cloud: the installer found no suitable GPU)."""
    return str(cfg["AURORA_LLM_BACKEND"]) == "cloud"


def private_model(llm, cfg: sys_config.Config | None = None):
    """The model for data that never reaches a cloud model (health, the firewall's configuration: owner, 2026-10-05):
    the local one, or None on a machine without a local reasoner, where the «local» model is the cloud's (C213). The
    caller says what it does without it; it never falls back to the cloud."""
    cfg = cfg or sys_config.get()
    if not (cloud_only(cfg) or isinstance(getattr(llm, "_inner", llm), CloudBase)):
        return llm                                    # a local model: private data stays here, in every mode
    from . import sys_cloud_consent                   # «Tutto cloud»: the owner's signed consent, from a shell
    return llm if sys_ethics.exempt(cfg) and sys_cloud_consent.signed(cfg) else None


def forge_cloud(cfg: sys_config.Config):
    """The model the forge asks when the local one failed and the owner allowed the cloud for that plugin: the forge's
    own assignment if it is a cloud one, else the cloud default, else Claude Code. Not masked here: the forge masks its
    samples itself (agt_forge.Masker)."""
    a = assignments(cfg).get("forge_write", {})
    for provider, model in ((a.get("provider", "local"), a.get("model", "")),
                            (str(cfg["AURORA_CLOUD_PROVIDER"]), str(cfg["AURORA_CLOUD_MODEL"] or ""))):
        if provider in PROVIDERS and PROVIDERS[provider]["kind"] != "local" and configured(provider, cfg):
            client = cloud_client(provider, model, cfg)
            if client is not None:
                return client
    from . import mdl_cloud
    return mdl_cloud.ClaudeCodeLLM(cfg)


def label(provider: str, cfg: sys_config.Config) -> str:
    """A provider's name on the Models page: "local" says what it is on a machine without a local reasoner."""
    if provider == "local" and cloud_only(cfg):
        return f"Predefinito: {cfg['AURORA_CLOUD_PROVIDER']} {cfg['AURORA_CLOUD_MODEL'] or ''}".rstrip() + " (nessun modello locale)"
    return PROVIDERS[provider]["label"]


def base(cfg: sys_config.Config | None = None):
    """The model of the steps assigned "local": llama.cpp (aurora-llm), or on a cloud-only machine the default cloud
    model (CloudBase)."""
    cfg = cfg or sys_config.get()
    if cloud_only(cfg):
        return CloudBase(cfg)
    from .mdl_llm import LLM
    return LLM(cfg)


class CloudBase:
    """What "local" means where there is no local reasoner: AURORA_CLOUD_PROVIDER / AURORA_CLOUD_MODEL, masked as every
    cloud call. Nothing is asked of the provider when it is made (a page that only reads works without it); a call
    without the owner's exemption (rule 9), without a key or past today's ceiling fails saying why: there is no local
    model to fall back to."""

    def __init__(self, cfg: sys_config.Config):
        self.cfg = cfg
        self.provider, self.model = str(cfg["AURORA_CLOUD_PROVIDER"]), str(cfg["AURORA_CLOUD_MODEL"] or "")
        self.name = self.provider
        self.context_tokens = 128_000 if PROVIDERS.get(self.provider, {}).get("kind") == "openai" else 200_000
        self.last_speed = None

    def problem(self) -> str:
        """Why a call cannot go now ("" when it can), without asking the provider."""
        spec = PROVIDERS.get(self.provider)
        if spec is None or spec["kind"] == "local":
            return f"AURORA_CLOUD_PROVIDER {self.provider!r} is not a cloud provider"
        if not sys_ethics.exempt(self.cfg):
            return ("no local reasoner and no exemption from level B (rule 9): "
                    "sudo .venv/bin/python sys/core/script/sys_ethics_sign.py setup --exempt")
        if spec.get("base_key") and not base_url(self.provider, self.cfg):
            return f"{spec['base_key']} is empty"
        if spec.get("key") and not spec.get("key_optional") and not self.cfg.values.get(spec["key"]):
            return f"{spec['key']} is empty"
        if spec["kind"] == "openai" and not self.model:
            return "AURORA_CLOUD_MODEL is empty"
        return ""

    def _m(self) -> MaskedLLM:
        from . import mdl_budget
        why = self.problem()
        if why:
            raise RuntimeError(why)
        if mdl_budget.over(self.cfg, self.provider):
            raise RuntimeError(f"{self.provider}: today's ceiling is reached (AURORA_CLOUD_DAILY_TOKENS) and this "
                               "machine has no local model")
        return MaskedLLM(cloud_client(self.provider, self.model, self.cfg), "base", self.cfg)

    def health(self) -> bool:
        return not self.problem()

    def complete(self, system: str, user: str, max_tokens: int, think: bool = False) -> Completion:
        return self._m().complete(system, user, max_tokens, think)

    def complete_turns(self, messages: list[dict], max_tokens: int, think: bool = False) -> Completion:
        return self._m().complete_turns(messages, max_tokens, think)

    def stream(self, system: str, user: str, max_tokens: int, think: bool = False) -> Iterator[tuple[str, str]]:
        m = self._m()
        yield from m.stream(system, user, max_tokens, think)
        self.last_speed = m.last_speed

    def see(self, jpeg: bytes, instruction: str, max_tokens: int = 700) -> str:
        return self._m().see(jpeg, instruction, max_tokens)

    def see_many(self, frames: list[tuple[str, bytes]], instruction: str, max_tokens: int = 1600) -> str:
        return self._m().see_many(frames, instruction, max_tokens)

    def count_tokens(self, text: str) -> int:
        return len(text) // 3                          # an estimate, no call: the conservative ratio of OpenAICompatLLM


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
