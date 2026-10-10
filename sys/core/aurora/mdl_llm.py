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

Another family (owner, 9 Oct: «se uno lo vuole cambiare con un modello suo»): its profile (mdl_formats, read from the
GGUF) says «native» — the prompt goes through llama-server's chat endpoint with the model's own template (--jinja),
the reasoning switched as the template understands it and given back apart (reasoning_content).
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Iterator

import httpx

from . import mdl_formats, sys_config, sys_log

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
        self.fmt = mdl_formats.local(self.cfg)

    # a template that refused the tools as a list (llama-server's error): the text form for this process
    _no_tools = False

    def _native(self, messages: list[dict], max_tokens: int, think: bool, stream: bool = False) -> dict:
        """The chat endpoint's body for a model with its own template (a tool's result as a user turn: not every
        template takes a «tool» role without a call id). An agent's turns go with the tools as the API's own list:
        llama-server writes them in the model's own format and reads its calls back (M169: Mistral Small 3.2 mixed
        its [TOOL_CALLS]…[ARGS] with the <tool_call> of the prompt, and no call was read)."""
        from .mdl_router import native_turns                # here: mdl_router imports this module
        native = None if self._no_tools or stream else native_turns(messages)
        if native:
            msgs = [{**m, "content": self.fmt.system(sys_config.personal(m["content"], self.cfg), think)}
                    if m["role"] == "system" else m for m in native[0]]
            return {"messages": msgs, "tools": native[1], "max_tokens": max_tokens, "stream": False,
                    "temperature": 0.6 if think else 0.0, "top_p": 0.95,
                    "chat_template_kwargs": self.fmt.kwargs(think), "cache_prompt": True}
        msgs = []
        for m in messages:
            role, content = m["role"], m["content"]
            if role == "system":
                content = self.fmt.system(sys_config.personal(content, self.cfg), think)
            elif role == "tool":
                role, content = "user", f"TOOL RESULT:\n{content}"
            msgs.append({"role": role, "content": content})
        if not msgs or msgs[0]["role"] != "system":
            line = self.fmt.system("", think).strip()
            if line:
                msgs.insert(0, {"role": "system", "content": line})
        return {"messages": msgs, "max_tokens": max_tokens, "stream": stream, "temperature": 0.6 if think else 0.0,
                "top_p": 0.95, "chat_template_kwargs": self.fmt.kwargs(think), "cache_prompt": True}

    def _chat(self, messages: list[dict], max_tokens: int, think: bool) -> Completion:
        from .mdl_router import as_text
        t0 = time.time()
        body = self._native(messages, max_tokens, think)
        r = httpx.post(self.url + "/v1/chat/completions", json=body, timeout=self.timeout)
        if r.status_code >= 400 and "tools" in body:       # the model's template takes no tools: the text form
            LLM._no_tools = True
            self.log.info("local model refused the tools as a list (%s): the text form", r.text[:160])
            r = httpx.post(self.url + "/v1/chat/completions", json=self._native(messages, max_tokens, think),
                           timeout=self.timeout)
        r.raise_for_status()
        d = r.json()
        msg = d["choices"][0]["message"]
        answer, thought = as_text(msg), msg.get("reasoning_content") or ""
        if END_THINK in answer:                    # a template that leaves the reasoning in the text
            thought, _, answer = answer.partition(END_THINK)
            thought = thought.replace("<think>", "")
        return Completion(answer.strip(), thought.strip(), int((d.get("usage") or {}).get("completion_tokens") or 0),
                          time.time() - t0, d["choices"][0].get("finish_reason") == "length")

    def health(self) -> bool:
        try:
            return httpx.get(self.url + "/health", timeout=3).json().get("status") == "ok"
        except (httpx.HTTPError, ValueError):
            return False

    def _body(self, system: str, user: str, max_tokens: int, think: bool, stream: bool) -> dict:
        return {"prompt": chatml(sys_config.personal(system, self.cfg), user, think), "n_predict": max_tokens, "stream": stream,
                "temperature": 0.6 if think else 0.0, "top_p": 0.95, "top_k": 20,
                "stop": STOPS, "cache_prompt": True}

    def _off(self) -> dict:
        """No reasoning, in the model's own words (Qwen's: enable_thinking, as measured)."""
        return {"enable_thinking": False} if self.fmt.template == "chatml" else self.fmt.kwargs(False)

    def see(self, jpeg: bytes, instruction: str, max_tokens: int = 700) -> str:
        """Look at an image (JPEG bytes) and answer the instruction, without thinking.

        Goes through llama-server's chat endpoint, which applies the model's own template to the
        image; needs the vision projector (AURORA_LLM_MMPROJ) loaded."""
        t0 = time.time()
        uri = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        r = httpx.post(self.url + "/v1/chat/completions", timeout=self.timeout, json={
            "messages": [{"role": "user", "content": [{"type": "text", "text": instruction},
                                                        {"type": "image_url", "image_url": {"url": uri}}]}],
            "max_tokens": max_tokens, "temperature": 0.0, "chat_template_kwargs": self._off()})
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
            "chat_template_kwargs": self._off()})
        r.raise_for_status()
        text = r.json()["choices"][0]["message"].get("content") or ""
        self.log.info("see_many: %d images, %d chars in %.1f s", len(frames), len(text), time.time() - t0)
        return text.strip()

    def complete(self, system: str, user: str, max_tokens: int, think: bool = False) -> Completion:
        if self.fmt.template == "native":
            return self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}], max_tokens, think)
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
        if self.fmt.template == "native":
            return self._chat(messages, max_tokens, think)
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

    def _stream_native(self, system: str, user: str, max_tokens: int, think: bool) -> Iterator[tuple[str, str]]:
        body = self._native([{"role": "system", "content": system}, {"role": "user", "content": user}], max_tokens,
                            think, stream=True)
        self.last_speed = None
        with httpx.stream("POST", self.url + "/v1/chat/completions", json=body, timeout=self.timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data: ") or line.strip() == "data: [DONE]":
                    continue
                delta = (json.loads(line[6:]).get("choices") or [{}])[0].get("delta") or {}
                if delta.get("reasoning_content"):
                    yield "thought", delta["reasoning_content"]
                if delta.get("content"):
                    yield "answer", delta["content"]

    def stream(self, system: str, user: str, max_tokens: int, think: bool = False) -> Iterator[tuple[str, str]]:
        if self.fmt.template == "native":
            yield from self._stream_native(system, user, max_tokens, think)
            return
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
