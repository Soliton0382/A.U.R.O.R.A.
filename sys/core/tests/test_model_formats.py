# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Each model spoken to in its own format (owner, 9 Oct: «un modulo apposito … con cache»): mdl_gguf reads a GGUF's
header, mdl_formats makes the profile, mdl_llm follows it — Qwen's measured ChatML path unchanged."""
import json
import struct
import time

import httpx

from aurora import mdl_formats as F
from aurora import mdl_gguf


def gguf(path, kv: dict) -> None:
    """A GGUF header with these keys (strings, uint32) and a long array, as the vocabulary is."""
    def s(x: str) -> bytes:
        b = x.encode()
        return struct.pack("<Q", len(b)) + b
    body = b""
    for k, v in kv.items():
        body += s(k) + (struct.pack("<I", 8) + s(v) if isinstance(v, str) else struct.pack("<II", 4, v))
    body += s("tokenizer.ggml.tokens") + struct.pack("<IIQ", 9, 8, 1000) + b"".join(s("t") for _ in range(1000))
    path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, len(kv) + 1) + body)


QWEN = "{{'<|im_start|>' + m.role}}{% if enable_thinking %}<think>{% endif %}<tool_call>"
MISTRAL = "[INST]{{ m.content }}[/INST][TOOL_CALLS]"
NEMOTRON = "<|start_header_id|>system: detailed thinking {{ x }}<|python_tag|>"
GPTOSS = "<|start|>system<|message|>Reasoning: {{ reasoning_effort }}<|channel|>"


def test_the_header_is_read_and_the_vocabulary_skipped(tmp_path):
    f = tmp_path / "m.gguf"
    gguf(f, {"general.architecture": "qwen35moe", "general.name": "Qwen3.6-35B-A3B", "qwen35moe.expert_count": 256,
             "qwen35moe.expert_used_count": 8, "qwen35moe.context_length": 262144, "tokenizer.chat_template": QWEN})
    m = mdl_gguf.meta(f)
    assert (m["architecture"], m["experts"], m["experts_used"], m["context"]) == ("qwen35moe", 256, 8, 262144)
    assert m["chat_template"] == QWEN
    (tmp_path / "x.gguf").write_bytes(b"NOPE")
    try:
        mdl_gguf.meta(tmp_path / "x.gguf")
        raise AssertionError("not a GGUF accepted")
    except mdl_gguf.NotGGUF:
        pass


def test_each_family_gets_its_profile():
    q = F.from_gguf({"architecture": "qwen35moe", "chat_template": QWEN})
    assert (q.family, q.template, q.tools) == ("qwen", "chatml", "hermes")          # the measured path
    m = F.from_gguf({"architecture": "llama", "name": "Mistral-Small-3.2", "chat_template": MISTRAL})
    assert (m.family, m.template, m.tools) == ("mistral", "native", "mistral")
    n = F.from_gguf({"architecture": "nemotron_h", "name": "Nemotron-Nano", "chat_template": NEMOTRON})
    assert (n.family, n.tools, n.system("x", True), n.system("x", False)) == \
        ("nemotron", "llama", "detailed thinking on\nx", "detailed thinking off\nx")
    g = F.from_gguf({"architecture": "gpt-oss", "chat_template": GPTOSS})
    assert g.tools == "harmony" and g.kwargs(True) == {"reasoning_effort": "medium"}


def test_a_native_model_goes_through_the_chat_endpoint(cfg, monkeypatch):
    from aurora import mdl_llm
    monkeypatch.setattr(F, "local", lambda c=None, model="": F.from_gguf({"architecture": "llama", "name": "mistral",
                                                                 "chat_template": "{% if enable_thinking %}{% endif %}"}))
    sent = []

    def post(url, json, timeout):
        sent.append((url, json))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ciao", "reasoning_content": "penso"},
                                                      "finish_reason": "stop"}], "usage": {"completion_tokens": 3}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    out = mdl_llm.LLM(cfg).complete_turns([{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
                                           {"role": "tool", "content": "r"}], 50, think=True)
    url, body = sent[0]
    assert url.endswith("/v1/chat/completions") and body["chat_template_kwargs"] == {"enable_thinking": True}
    assert body["messages"][2] == {"role": "user", "content": "TOOL RESULT:\nr"}
    assert (out.answer, out.thought, out.tokens) == ("ciao", "penso", 3)


def test_qwen_keeps_the_measured_chatml_prompt(cfg, monkeypatch):
    from aurora import mdl_llm
    monkeypatch.setattr(F, "local", lambda c=None, model="": F.from_gguf({"architecture": "qwen35moe", "chat_template": QWEN}))
    sent = []

    def post(url, json, timeout):
        sent.append((url, json))
        return httpx.Response(200, json={"content": "pensa</think>ok", "tokens_predicted": 2},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    out = mdl_llm.LLM(cfg).complete("s", "u", 50, think=True)
    assert sent[0][0].endswith("/completion") and sent[0][1]["prompt"].endswith("<|im_start|>assistant\n<think>\n")
    assert (out.answer, out.thought) == ("ok", "pensa")


def test_cloud_profiles_and_the_providers_list_is_kept(cfg, monkeypatch):
    assert F.cloud(cfg, "claude_code", "haiku").tools == "claude"
    assert F.cloud(cfg, "mistral", "mistral-large").tools == "mistral" and F.cloud(cfg, "openai", "gpt-5").native_tools
    calls = []

    def get(url, timeout):
        calls.append(url)
        return httpx.Response(200, json={"data": [{"id": "meta/llama-4", "supported_parameters": ["tools"]},
                                                  {"id": "x/tiny", "supported_parameters": []}]},
                              request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    cfg.values["AURORA_FORMATS_CACHE_H"] = 24
    assert F.cloud(cfg, "openrouter", "meta/llama-4").native_tools
    assert not F.cloud(cfg, "openrouter", "x/tiny").native_tools
    assert len(calls) == 1                                                  # kept: not asked at every turn
    cache = json.loads(F._cache_file(cfg).read_text())
    cache["openrouter"]["at"] = time.time() - 25 * 3600                     # older than AURORA_FORMATS_CACHE_H
    F._cache_file(cfg).write_text(json.dumps(cache))
    F.cloud(cfg, "openrouter", "x/tiny")
    assert len(calls) == 2


def test_the_fit_says_whole_experts_in_ram_or_no():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
    import sys_model_check as M
    moe = {"size_gb": 20.6, "experts": 256}
    assert M.fit(moe, 32.0, 64)["verdict"] == "whole"                     # the reference machine: 2 × 16 GB
    assert M.fit(moe, 16.0, 64)["verdict"] == "experts_in_ram"
    assert M.fit({"size_gb": 20.6, "experts": 0}, 16.0, 64)["verdict"] == "no"   # dense: all of it on the GPU
    assert M.fit(moe, 0.0, 16)["verdict"] == "no"


def test_after_a_switch_the_client_speaks_the_new_models_format(cfg, tmp_path):
    """C257: the API's pipelines keep their client; after a switch from the Models page it went on with the format of
    the model of the API's start (Qwen's ChatML for Nemotron, Qwen3-Next…). The format now follows the .env."""
    from aurora import mdl_llm, sys_config
    for name, arch, tpl in (("qwen.gguf", "qwen35moe", QWEN), ("mistral.gguf", "llama", MISTRAL)):
        gguf(cfg.root / name, {"general.architecture": arch, "general.name": name, "tokenizer.chat_template": tpl})
    sys_config.write_env(cfg.env_file, {"AURORA_LLM_MODEL": "qwen.gguf"})
    cfg.values["AURORA_LLM_MODEL"] = "qwen.gguf"
    llm = mdl_llm.LLM(cfg)                                            # built once, as the API's pipeline is
    first = llm.fmt.family
    import os
    import time
    sys_config.write_env(cfg.env_file, {"AURORA_LLM_MODEL": "mistral.gguf"})      # the Models page switched
    os.utime(cfg.env_file, (time.time() + 5, time.time() + 5))
    assert (first, llm.fmt.family) == ("qwen", "mistral")
