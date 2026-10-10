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


def test_a_local_model_with_its_own_template_gets_the_tools_as_a_list(cfg, monkeypatch):
    """M169: Mistral Small 3.2 on llama-server --jinja — the tools as a list, its calls read back by the server."""
    from aurora import mdl_formats as F, mdl_llm
    monkeypatch.setattr(F, "local", lambda c=None, model="": F.from_gguf({"architecture": "llama", "name": "mistral",
                                                                 "chat_template": "{{ tools }}"}))
    reply = {"choices": [{"finish_reason": "tool_calls", "message": {"content": "", "tool_calls": [
        {"id": "x", "type": "function", "function": {"name": "finish", "arguments": '{"summary": "sole"}'}}]}}],
        "usage": {"completion_tokens": 5}}
    sent = []

    def post(url, json, timeout):
        sent.append(json)
        if "tools" in json and len(sent) >= 2:              # the second model refuses them
            return httpx.Response(500, json={"error": "this template does not support tools"}, request=httpx.Request("POST", url))
        return httpx.Response(200, json=reply, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    mdl_llm.LLM._no_tools = False
    c = mdl_llm.LLM(cfg).complete_turns(turns(cfg), 300)
    assert sent[0]["tools"] == SPECS and sent[0]["messages"][3]["tool_call_id"]
    assert [json.loads(x)["name"] for x in parse(c.answer)[1]] == ["finish"]
    mdl_llm.LLM(cfg).complete_turns(turns(cfg)[:2], 300)                 # a template that refuses them: the text
    assert "tools" not in sent[-1] and mdl_llm.LLM._no_tools
    mdl_llm.LLM._no_tools = False


def test_mistrals_newer_call_form_is_read():
    raw = '[TOOL_CALLS]tool_call[ARGS]\n{"name": "weather__forecast", "arguments": {"place": "Trento"}}\n</tool_call[TOOL_CALLS]'
    assert parse(raw)[1:] == (['{"name": "weather__forecast", "arguments": {"place": "Trento"}}'], "")
    two = 'Guardo. [TOOL_CALLS]weather__forecast[ARGS]{"place": "Trento"}[TOOL_CALLS]finish[ARGS]{"summary": "ok"}'
    calls, said = parse(two)[1:]
    assert [json.loads(x)["name"] for x in calls] == ["weather__forecast", "finish"] and said == "Guardo."


def test_an_output_the_server_cannot_read_is_asked_again_not_sent_to_the_text_form(cfg, monkeypatch):
    """M170: gpt-oss now and then — «does not match the expected … format» — was taken for a template without
    tools, and every later turn lost them (1 of 8 runs right; asked again: 8 of 8)."""
    from aurora import mdl_formats as F, mdl_llm
    monkeypatch.setattr(F, "local", lambda c=None, model="": F.from_gguf({"architecture": "gpt-oss", "chat_template": "{{ tools }}"}))
    ok = {"choices": [{"finish_reason": "stop", "message": {"content": "fatto"}}], "usage": {}}
    bad = {"error": {"code": 500, "message": "The model produced output that does not match the expected peg-native format"}}
    replies = [(500, bad), (200, ok)]
    sent = []

    def post(url, json, timeout):
        sent.append(json)
        status, body = replies.pop(0)
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    mdl_llm.LLM._no_tools = False
    assert mdl_llm.LLM(cfg).complete_turns(turns(cfg), 300).answer == "fatto"
    assert len(sent) == 2 and "tools" in sent[1] and not mdl_llm.LLM._no_tools


def test_the_agent_is_told_which_plugins_wait_for_settings(cfg):
    from aurora.plg_host import Plugin
    host = SimpleNamespace(plugins=lambda: [
        Plugin("weather", None, {"description": {"en": "Forecasts", "it": "Previsioni"}}, missing=["AURORA_WEATHER_LAT"]),
        Plugin("web", None, {"description": "Search"})])
    a = SimpleNamespace(host=host, allow=None)
    text = Agent._waiting(a)
    assert "weather: Forecasts (needs AURORA_WEATHER_LAT)" in text and "web" not in text
    assert Agent._waiting(SimpleNamespace(host=host, allow={"web"})) == ""
