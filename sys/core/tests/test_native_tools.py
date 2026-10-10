# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Native tool calling where the API has it (roadmap 73, owner 9 Oct: «ricordati delle API tool calling»): the agent
keeps its text form; the OpenAI-compatible client sends the tools as the API's own list and reads tool_calls back."""
import json
from types import SimpleNamespace

import httpx

from aurora import mdl_router as R
from aurora.agt_loop import Agent, parse

SPECS = [{"type": "function", "function": {"name": "weather__forecast", "description": "[read] the forecast",
                                           "parameters": {"type": "object", "properties": {"place": {"type": "string"}}}}},
         {"type": "function", "function": {"name": "finish", "description": "end", "parameters": {"type": "object"}}}]


def turns(cfg):
    system = Agent._system(SimpleNamespace(cfg=cfg), SPECS)
    return [{"role": "system", "content": system},
            {"role": "user", "content": "GOAL: il meteo a Trento"},
            {"role": "assistant", "content": 'Guardo.\n<tool_call>\n{"name": "weather__forecast", "arguments": '
                                             '{"place": "Trento"}}\n</tool_call>'},
            {"role": "tool", "content": "sole, 18 °C"}]


def test_the_text_turns_become_the_apis_own(cfg):
    msgs, tools = R.native_turns(turns(cfg))
    assert tools == SPECS
    assert "<tools>" not in msgs[0]["content"] and "tool calls" in msgs[0]["content"]
    call = msgs[2]["tool_calls"][0]
    assert msgs[2]["content"] == "Guardo." and call["function"]["name"] == "weather__forecast"
    assert json.loads(call["function"]["arguments"]) == {"place": "Trento"}
    assert msgs[3] == {"role": "tool", "tool_call_id": call["id"], "content": "sole, 18 °C"}
    assert R.native_turns([{"role": "user", "content": "ciao"}]) is None              # a plain chat: as it is


def test_a_call_left_without_its_result_is_answered(cfg):
    t = turns(cfg)[:3] + [{"role": "user", "content": "Think less: call the next tool"}]
    msgs, _ = R.native_turns(t)
    assert msgs[3]["role"] == "tool" and msgs[3]["tool_call_id"] == msgs[2]["tool_calls"][0]["id"]
    assert msgs[4]["role"] == "user"


def client(cfg, monkeypatch, replies):
    cfg.values["AURORA_OPENAI_API_KEY"] = "k"
    sent = []

    def post(url, headers, timeout, json):
        sent.append(json)
        status, body = replies.pop(0)
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    R.OpenAICompatLLM._refused.clear()
    return R.OpenAICompatLLM("openai", "gpt-x", cfg), sent


def test_the_apis_tool_calls_come_back_as_the_agents_calls(cfg, monkeypatch):
    reply = {"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
        {"id": "a", "type": "function", "function": {"name": "finish", "arguments": '{"summary": "sole a Trento"}'}}]}}],
        "usage": {"completion_tokens": 9}}
    llm, sent = client(cfg, monkeypatch, [(200, reply)])
    c = llm.complete_turns(turns(cfg), 500)
    assert sent[0]["tools"] == SPECS and sent[0]["messages"][3]["role"] == "tool"
    _, calls, _ = parse(c.answer)
    assert [json.loads(x) for x in calls] == [{"name": "finish", "arguments": {"summary": "sole a Trento"}}]


def test_a_model_that_refuses_tools_gets_the_text_form(cfg, monkeypatch):
    ok = {"choices": [{"finish_reason": "stop", "message": {"content": "fatto"}}], "usage": {}}
    llm, sent = client(cfg, monkeypatch, [(400, {"error": {"message": "tools are not supported"}}), (200, ok), (200, ok)])
    assert llm.complete_turns(turns(cfg), 500).answer == "fatto"
    assert "tools" in sent[0] and "tools" not in sent[1] and "<tools>" in sent[1]["messages"][0]["content"]
    llm.complete_turns(turns(cfg), 500)
    assert "tools" not in sent[2]                                                    # remembered: not tried again


def test_what_the_api_attached_to_a_call_goes_back_with_it(cfg, monkeypatch):
    """Gemini 3 (measured 10 Oct): a call sent back without its thought_signature is a 400."""
    given = {"id": "g1", "type": "function", "extra_content": {"google": {"thought_signature": "sig"}},
             "function": {"name": "weather__forecast", "arguments": '{"place": "Trento"}'}}
    reply = {"choices": [{"finish_reason": "tool_calls", "message": {"content": "", "tool_calls": [given]}}], "usage": {}}
    llm, sent = client(cfg, monkeypatch, [(200, reply), (200, {"choices": [{"message": {"content": "ok"}}], "usage": {}})])
    t = turns(cfg)[:2]
    t.append({"role": "assistant", "content": llm.complete_turns(t, 500).answer})
    t.append({"role": "tool", "content": "sole"})
    llm.complete_turns(t, 500)
    assert sent[1]["messages"][2]["tool_calls"] == [given] and sent[1]["messages"][3]["tool_call_id"] == "g1"
