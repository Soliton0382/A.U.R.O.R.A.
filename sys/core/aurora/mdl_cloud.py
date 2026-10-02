# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Cloud reasoners with the same interface as the local one (mdl_llm.LLM).

  anthropic     Anthropic Messages API over HTTPS (AURORA_ANTHROPIC_API_KEY): thinking, streaming,
                images, token counting.
  claude_code   the Claude Code CLI in print mode (`claude -p`), with the owner's subscription:
                no tools, no project settings, run from an empty folder; streaming; cost reported.

Only the reasoning roles go to the cloud (AURORA_CLOUD_ROLES); the small service calls (route,
translation, gate, verification, vision) stay on the local model. Every call logs its tokens and,
when known, its cost, so that the saving of the compression (txt_compress) is measured, not assumed.
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
from typing import Iterator

import httpx

from . import sys_config, sys_ethics, sys_log
from .mdl_llm import Completion

API = "https://api.anthropic.com/v1"


def _flatten(messages: list[dict]) -> tuple[str, str]:
    """(system, transcript) of a multi-turn conversation, for a provider that takes one prompt."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    lines = []
    for m in messages:
        if m["role"] == "user":
            lines.append(f"USER:\n{m['content']}")
        elif m["role"] == "assistant":
            lines.append(f"ASSISTANT:\n{m['content']}")
        elif m["role"] == "tool":
            lines.append(f"TOOL RESULT:\n<tool_response>\n{m['content']}\n</tool_response>")
    lines.append("Continue as ASSISTANT: write only your next turn.")
    return system, "\n\n".join(lines)


class ClaudeCodeLLM:
    name = "claude_code"
    context_tokens = 200_000

    def __init__(self, cfg: sys_config.Config | None = None, model: str | None = None):
        self.cfg = cfg or sys_config.get()
        self.bin = str(self.cfg["AURORA_CLAUDE_CODE_BIN"])
        self.model = model or self.cfg["AURORA_CLAUDE_CODE_MODEL"]
        self.cwd = self.cfg.path("AURORA_STATUS_DIR") / "claude_code"      # empty: no project instructions
        self.cwd.mkdir(parents=True, exist_ok=True)
        self.log = sys_log.get_logger("llm_client")

    def _cmd(self, system: str, stream: bool, max_tokens: int) -> list[str]:
        # The CLI has no output limit (A16): the budget is stated in the prompt; Italian measured at ~3.1
        # tokens per word (273 tokens / 88 words), so 0.35 words per token.
        system = sys_config.personal(system, self.cfg) + f"\n\nLENGTH: answer in at most about {max(20, int(max_tokens * 0.35))} words."
        cmd = [self.bin, "-p", "--model", self.model, "--no-session-persistence", "--tools", "",
               "--setting-sources", "", "--system-prompt", system]
        return cmd + (["--output-format", "stream-json", "--include-partial-messages", "--verbose"] if stream
                      else ["--output-format", "json"])

    def _account(self, d: dict, seconds: float) -> None:
        u = d.get("usage", {})
        self.log.info("claude_code %s: in %s (+cache %s/%s) out %s, cost %.4f USD, %.1f s", self.model,
                      u.get("input_tokens"), u.get("cache_read_input_tokens"), u.get("cache_creation_input_tokens"),
                      u.get("output_tokens"), d.get("total_cost_usd") or 0, seconds)
        sys_log.trace("llm_client", "cloud.call", {"provider": self.name, "model": self.model, "usage": u,
                                                   "cost_usd": d.get("total_cost_usd"), "seconds": round(seconds, 2)})
        from . import mdl_budget
        mdl_budget.record(self.cfg, self.name, u)

    def complete(self, system: str, user: str, max_tokens: int, think: bool = False) -> Completion:
        t0 = time.time()
        r = subprocess.run(self._cmd(system, False, max_tokens), input=user, capture_output=True, text=True,
                           timeout=self.cfg["AURORA_LLM_TIMEOUT_S"], cwd=self.cwd)
        try:
            d = json.loads(r.stdout)
        except ValueError:
            raise RuntimeError(f"claude -p failed: {(r.stderr or r.stdout)[-400:]}")
        if d.get("is_error"):
            raise RuntimeError(f"claude -p: {d.get('result') or d.get('api_error_status')}")
        self._account(d, time.time() - t0)
        return Completion(str(d.get("result", "")).strip(), "", int(d.get("usage", {}).get("output_tokens", 0)),
                          time.time() - t0, d.get("stop_reason") == "max_tokens")

    def stream(self, system: str, user: str, max_tokens: int, think: bool = False) -> Iterator[tuple[str, str]]:
        t0 = time.time()
        p = subprocess.Popen(self._cmd(system, True, max_tokens), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, cwd=self.cwd)
        p.stdin.write(user)
        p.stdin.close()
        self.last_speed, first = None, None
        for line in p.stdout:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "stream_event" and e["event"].get("type") == "content_block_delta":
                delta = e["event"]["delta"]
                first = first or time.time()
                if delta.get("type") == "text_delta":
                    yield "answer", delta["text"]
                elif delta.get("type") == "thinking_delta":
                    yield "thought", delta.get("thinking", "")
            elif e.get("type") == "result":
                self._account(e, time.time() - t0)
                n = int(e.get("usage", {}).get("output_tokens", 0))
                if n and first:
                    self.last_speed = {"tokens": n, "per_second": round(n / max(0.001, time.time() - first), 1)}
        p.wait(timeout=30)

    def complete_turns(self, messages: list[dict], max_tokens: int, think: bool = False) -> Completion:
        system, transcript = _flatten(messages)
        return self.complete(system, transcript, max_tokens, think)

    def count_tokens(self, text: str) -> int:
        return len(text) // 4                              # the CLI has no tokenizer: an estimate

    def see(self, jpeg: bytes, instruction: str, max_tokens: int = 700) -> str:
        raise NotImplementedError("vision stays on the local model")


class AnthropicLLM:
    name = "anthropic"
    context_tokens = 200_000

    def __init__(self, cfg: sys_config.Config | None = None, model: str | None = None):
        self.cfg = cfg or sys_config.get()
        self.model = model or self.cfg["AURORA_ANTHROPIC_MODEL"]
        self.key = self.cfg["AURORA_ANTHROPIC_API_KEY"]
        self.log = sys_log.get_logger("llm_client")

    def _headers(self) -> dict:
        if not self.key:
            raise RuntimeError("AURORA_ANTHROPIC_API_KEY is empty")
        return {"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"}

    def _body(self, system: str, messages: list[dict], max_tokens: int, think: bool, stream: bool) -> dict:
        budget = min(self.cfg["AURORA_PIPELINE_THINK_TOKENS"], max(1024, max_tokens - 1024)) if think else 0
        body = {"model": self.model, "system": sys_config.personal(system, self.cfg), "messages": messages, "stream": stream,
                "max_tokens": max_tokens + budget if think else max_tokens}
        if think:
            body["thinking"] = {"type": "enabled", "budget_tokens": budget}
        return body

    def _account(self, usage: dict, seconds: float) -> None:
        self.log.info("anthropic %s: in %s out %s, %.1f s", self.model, usage.get("input_tokens"),
                      usage.get("output_tokens"), seconds)
        from . import mdl_budget
        mdl_budget.record(self.cfg, self.name, usage)
        sys_log.trace("llm_client", "cloud.call", {"provider": self.name, "model": self.model, "usage": usage,
                                                   "seconds": round(seconds, 2)})

    @staticmethod
    def _turns(messages: list[dict]) -> tuple[str, list[dict]]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        out = []
        for m in messages:
            if m["role"] == "system":
                continue
            role = "assistant" if m["role"] == "assistant" else "user"
            text = m["content"] if m["role"] != "tool" else f"<tool_response>\n{m['content']}\n</tool_response>"
            if out and out[-1]["role"] == role:
                out[-1]["content"] += "\n\n" + text
            else:
                out.append({"role": role, "content": text})
        return system, out

    def _complete(self, system: str, messages: list[dict], max_tokens: int, think: bool) -> Completion:
        t0 = time.time()
        r = httpx.post(f"{API}/messages", headers=self._headers(), timeout=self.cfg["AURORA_LLM_TIMEOUT_S"],
                       json=self._body(system, messages, max_tokens, think, False))
        if r.status_code >= 400:
            raise RuntimeError(f"Anthropic {r.status_code}: {r.text[:300]}")
        d = r.json()
        answer = "".join(b.get("text", "") for b in d["content"] if b["type"] == "text")
        thought = "".join(b.get("thinking", "") for b in d["content"] if b["type"] == "thinking")
        self._account(d.get("usage", {}), time.time() - t0)
        return Completion(answer.strip(), thought.strip(), int(d.get("usage", {}).get("output_tokens", 0)),
                          time.time() - t0, d.get("stop_reason") == "max_tokens")

    def complete(self, system: str, user: str, max_tokens: int, think: bool = False) -> Completion:
        return self._complete(system, [{"role": "user", "content": user}], max_tokens, think)

    def complete_turns(self, messages: list[dict], max_tokens: int, think: bool = False) -> Completion:
        system, msgs = self._turns(messages)
        return self._complete(system, msgs, max_tokens, think)

    def stream(self, system: str, user: str, max_tokens: int, think: bool = False) -> Iterator[tuple[str, str]]:
        t0 = time.time()
        body = self._body(system, [{"role": "user", "content": user}], max_tokens, think, True)
        with httpx.stream("POST", f"{API}/messages", headers=self._headers(), json=body,
                          timeout=self.cfg["AURORA_LLM_TIMEOUT_S"]) as r:
            if r.status_code >= 400:
                raise RuntimeError(f"Anthropic {r.status_code}: {r.read()[:300]!r}")
            usage, first = {}, None
            self.last_speed = None
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                e = json.loads(line[6:])
                if e.get("type") == "content_block_delta":
                    first = first or time.time()
                    d = e["delta"]
                    if d.get("type") == "text_delta":
                        yield "answer", d["text"]
                    elif d.get("type") == "thinking_delta":
                        yield "thought", d.get("thinking", "")
                elif e.get("type") == "message_delta":
                    usage = e.get("usage", usage)
        self._account(usage, time.time() - t0)
        n = int(usage.get("output_tokens", 0))
        if n and first:
            self.last_speed = {"tokens": n, "per_second": round(n / max(0.001, time.time() - first), 1)}

    def count_tokens(self, text: str) -> int:
        r = httpx.post(f"{API}/messages/count_tokens", headers=self._headers(), timeout=30,
                       json={"model": self.model, "messages": [{"role": "user", "content": text}]})
        return r.json().get("input_tokens", len(text) // 4) if r.status_code < 400 else len(text) // 4

    def see(self, jpeg: bytes, instruction: str, max_tokens: int = 700) -> str:
        msg = [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()}},
            {"type": "text", "text": instruction}]}]
        return self._complete("", msg, max_tokens, False).answer


def make_reasoner(cfg: sys_config.Config, local):
    """The reasoner for the reasoning roles: the local model, or a cloud provider.

    Code of conduct, rule 9 (level B): private data never leaves the machine towards cloud models.
    The reasoning roles carry memory, logs and conversation, so without the owner's exemption the
    cloud provider is refused and the local model reasons.
    """
    provider = cfg["AURORA_REASONER_PROVIDER"]
    if provider != "local" and not sys_ethics.exempt(cfg):
        sys_log.get_logger("llm_client").warning(
            "reasoner %s refused: code of conduct rule 9 (no private data to cloud models) without the owner's exemption",
            provider)
        return local
    if provider == "claude_code":
        return ClaudeCodeLLM(cfg)
    if provider == "anthropic":
        return AnthropicLLM(cfg)
    return local
