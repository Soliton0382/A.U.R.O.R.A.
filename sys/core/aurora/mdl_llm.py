# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Client of the reasoner (llama.cpp server).

Prompts are built in ChatML, as in the measurements (M20-M24):
- with thinking, the prompt opens the reasoning block (`<think>\\n`): without
  it Qwen3.6 skips reasoning altogether (M22, first attempt);
- without thinking, an empty block is given, so the model answers directly.

`complete` returns the answer and the reasoning separately; `stream` yields
("thought", text) and ("answer", text) pieces as they arrive, splitting on the
closing tag even when it is cut across two pieces.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Iterator

import httpx

from . import sys_config, sys_log

END_THINK = "</think>"
STOPS = ["<|im_end|>", "<|im_start|>", "<|endoftext|>"]


@dataclass
class Completion:
    answer: str
    thought: str
    tokens: int
    seconds: float
    truncated: bool          # budget exhausted before the answer ended


def chatml(system: str, user: str, think: bool) -> str:
    tail = "<think>\n" if think else "<think>\n\n</think>\n"
    return (f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n{tail}")


def chatml_turns(messages: list[dict], think: bool) -> str:
    """A multi-turn ChatML prompt (system, user, assistant, tool messages), ending with Aurora's turn.
    Tool results go back as a user turn wrapped in <tool_response>, as Qwen's own template does."""
    parts = []
    for m in messages:
        role, content = m["role"], m["content"]
        if role == "tool":
            role, content = "user", f"<tool_response>\n{content}\n</tool_response>"
        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>\n")
    tail = "<think>\n" if think else "<think>\n\n</think>\n"
    return "".join(parts) + f"<|im_start|>assistant\n{tail}"


class LLM:
    def __init__(self, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.url = f"http://{self.cfg['AURORA_LLM_HOST']}:{self.cfg['AURORA_LLM_PORT']}"
        self.timeout = self.cfg["AURORA_LLM_TIMEOUT_S"]
        self.log = sys_log.get_logger("llm_client")

    def health(self) -> bool:
        try:
            return httpx.get(self.url + "/health", timeout=3).json().get("status") == "ok"
        except (httpx.HTTPError, ValueError):
            return False

    def _body(self, system: str, user: str, max_tokens: int, think: bool, stream: bool) -> dict:
        return {"prompt": chatml(sys_config.personal(system, self.cfg), user, think), "n_predict": max_tokens, "stream": stream,
                "temperature": 0.6 if think else 0.0, "top_p": 0.95, "top_k": 20,
                "stop": STOPS, "cache_prompt": True}

    def see(self, jpeg: bytes, instruction: str, max_tokens: int = 700) -> str:
        """Look at an image (JPEG bytes) and answer the instruction, without thinking.

        Goes through llama-server's chat endpoint, which applies the model's own template to the
        image; needs the vision projector (AURORA_LLM_MMPROJ) loaded."""
        t0 = time.time()
        uri = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        r = httpx.post(self.url + "/v1/chat/completions", timeout=self.timeout, json={
            "messages": [{"role": "user", "content": [{"type": "text", "text": instruction},
                                                        {"type": "image_url", "image_url": {"url": uri}}]}],
            "max_tokens": max_tokens, "temperature": 0.0, "chat_template_kwargs": {"enable_thinking": False}})
        r.raise_for_status()
        text = r.json()["choices"][0]["message"].get("content") or ""
        self.log.info("see: %d bytes image, %d chars in %.1f s", len(jpeg), len(text), time.time() - t0)
        return text.strip()

    def see_many(self, frames: list[tuple[str, bytes]], instruction: str, max_tokens: int = 1600) -> str:
        """Look at several images in order, each with its label (a video's frames with their time), in one call."""
        t0 = time.time()
        parts: list[dict] = [{"type": "text", "text": instruction}]
        for label, jpeg in frames:
            parts += [{"type": "text", "text": f"Frame at {label}:"},
                      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}}]
        r = httpx.post(self.url + "/v1/chat/completions", timeout=self.timeout, json={
            "messages": [{"role": "user", "content": parts}], "max_tokens": max_tokens, "temperature": 0.0,
            "chat_template_kwargs": {"enable_thinking": False}})
        r.raise_for_status()
        text = r.json()["choices"][0]["message"].get("content") or ""
        self.log.info("see_many: %d images, %d chars in %.1f s", len(frames), len(text), time.time() - t0)
        return text.strip()

    def complete(self, system: str, user: str, max_tokens: int, think: bool = False) -> Completion:
        t0 = time.time()
        r = httpx.post(self.url + "/completion", json=self._body(system, user, max_tokens, think, False),
                       timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        text = data.get("content", "")
        if think:
            thought, found, answer = text.partition(END_THINK)
            if not found:                          # the budget ended inside the reasoning
                thought, answer = text, ""
        else:
            thought, answer = "", text
        done = Completion(answer.strip(), thought.strip(), int(data.get("tokens_predicted", 0)),
                          time.time() - t0, bool(data.get("stopped_limit")) or (think and not found))
        self.log.debug("complete: think=%s %d tokens in %.1f s%s", think, done.tokens, done.seconds,
                       " (truncated)" if done.truncated else "")
        return done

    def count_tokens(self, text: str) -> int:
        """Tokens of a text for this model (llama-server /tokenize)."""
        r = httpx.post(self.url + "/tokenize", json={"content": text}, timeout=60)
        r.raise_for_status()
        return len(r.json()["tokens"])

    def complete_turns(self, messages: list[dict], max_tokens: int, think: bool = False) -> Completion:
        """Like complete(), for a conversation of several turns (agents)."""
        t0 = time.time()
        messages = [{**m, "content": sys_config.personal(m["content"], self.cfg)} if m["role"] == "system" else m for m in messages]
        body = {"prompt": chatml_turns(messages, think), "n_predict": max_tokens, "stream": False,
                "temperature": 0.6 if think else 0.0, "top_p": 0.95, "top_k": 20, "stop": STOPS, "cache_prompt": True}
        r = httpx.post(self.url + "/completion", json=body, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        text = data.get("content", "")
        found = True
        if think:
            thought, found, answer = text.partition(END_THINK)
            if not found:
                thought, answer = text, ""
        else:
            thought, answer = "", text
        return Completion(answer.strip(), thought.strip(), int(data.get("tokens_predicted", 0)), time.time() - t0,
                          bool(data.get("stopped_limit")) or (think and not found))

    def stream(self, system: str, user: str, max_tokens: int, think: bool = False) -> Iterator[tuple[str, str]]:
        phase = "thought" if think else "answer"
        pending = ""
        self.last_speed = None
        with httpx.stream("POST", self.url + "/completion", json=self._body(system, user, max_tokens, think, True),
                          timeout=self.timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                chunk = json.loads(line[6:])
                piece = chunk.get("content", "")
                if chunk.get("stop") and chunk.get("timings"):      # measured by llama-server, not estimated
                    tm = chunk["timings"]
                    self.last_speed = {"tokens": tm.get("predicted_n"), "per_second": round(tm.get("predicted_per_second", 0), 1)}
                if phase == "answer":
                    if piece:
                        yield "answer", piece
                    continue
                pending += piece
                if END_THINK in pending:
                    before, _, after = pending.partition(END_THINK)
                    if before:
                        yield "thought", before
                    phase, pending = "answer", ""
                    if after.lstrip():
                        yield "answer", after.lstrip()
                    continue
                keep = len(END_THINK) - 1              # the tag may be cut across two pieces
                if len(pending) > keep:
                    yield "thought", pending[:-keep]
                    pending = pending[-keep:]
        if phase == "thought" and pending:
            yield "thought", pending
