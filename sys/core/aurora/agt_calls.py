# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The agent's tool calls read from a model's reply, in every format models write them (C111, C232, C245): Aurora's
own <tool_call>{…}</tool_call>, Claude's <invoke>, Llama's <function=…> and <|python_tag|>, Mistral's [TOOL_CALLS] in
both its forms, a bare or fenced JSON call — and a reply cut where the model began to invent a tool's result."""
from __future__ import annotations

import json
import re

# closed as it should, or with the wrong tag (</tool_response>), or left open at the end of the text: a long call
# (a whole HTML page for create_artifact) was written with the wrong closing tag and taken for the report (C111)
CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*(?:</tool_call>|</tool_response>|\Z)", re.S)
SUMMARY = re.compile(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)', re.S)
# a model used to Claude's own format writes its calls as <invoke name="plugin__tool"><parameter name="k">v</parameter>
# (C232, 9 Oct: Claude Code haiku, the 20:00 Facebook routine — 0 calls made, and the run reported the results it
# had written itself after each call: «Metodo non disponibile»)
INVOKE = re.compile(r'<invoke name="([^"]+)">(.*?)</invoke>', re.S)
PARAM = re.compile(r'<parameter name="([^"]+)">(.*?)</parameter>', re.S)
# what only Aurora may write: a tool's result. A model that writes one invented it; the text stops there
INVENTED = re.compile(r"<tool_response>|<function_results>|Tool call results|TOOL RESULT:", re.I)


def _param(v: str):
    try:
        return json.loads(v)
    except ValueError:
        return v.strip()


# the other formats models write their calls in (owner, 9 Oct: «compatibile con ogni formato utilizzato dai vari
# provider e modelli»): Llama 3.1's <function=name>{…}</function> and <|python_tag|>{…}, Mistral's [TOOL_CALLS] […],
# and a reply that is nothing but the call's JSON (bare or in a ```json block)
FUNCTION = re.compile(r"<function=([\w.\-]+)>\s*(\{.*?\})\s*</function>", re.S)
PYTAG = re.compile(r"<\|python_tag\|>\s*(\{.*\})", re.S)
MISTRAL = re.compile(r"\[TOOL_CALLS\]\s*(\[.*\])", re.S)
# Mistral's newer form, one call each: [TOOL_CALLS]name[ARGS]{…} (M169: Mistral Small 3.2 wrote
# «[TOOL_CALLS]tool_call[ARGS]{"name": …, "arguments": …}</tool_call[TOOL_CALLS]», its form around the prompt's)
MISTRAL_ARGS = re.compile(r"\[TOOL_CALLS\]\s*([\w.\-]+)\s*\[ARGS\]\s*", re.S)


def _mistral_args(text: str) -> tuple[list[str], str]:
    """The calls in Mistral's [TOOL_CALLS]name[ARGS]{…} form, and the text without them."""
    calls, cut, dec = [], [], json.JSONDecoder()
    for m in MISTRAL_ARGS.finditer(text):
        try:
            obj, end = dec.raw_decode(text, m.end())
        except ValueError:
            continue
        found = _call(obj) if isinstance(obj, dict) and "name" in obj else _call({"name": m.group(1), "arguments": obj})
        if found:
            calls.append(found)
            cut.append((m.start(), end))
    for a, b in reversed(cut):
        text = text[:a] + text[b:]
    return calls, re.sub(r"</?tool_call>?|\[TOOL_CALLS\]", "", text) if calls else text
FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
BARE = re.compile(r"^\s*(?:```(?:json)?\s*)?(\{.*\}|\[.*\])\s*(?:```)?\s*$", re.S)


def _call(obj) -> str | None:
    """One call in the loop's own JSON, from any provider's shape: name + arguments / parameters / input, the
    arguments as an object or as a JSON string (OpenAI's), or nested under «function»."""
    if not isinstance(obj, dict):
        return None
    obj = obj.get("function", obj) if isinstance(obj.get("function"), dict) else obj
    name = obj.get("name")
    args = next((obj[k] for k in ("arguments", "parameters", "input", "args") if k in obj), {})
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except ValueError:
            return None
    if not isinstance(name, str) or not name or not isinstance(args, dict):
        return None
    return json.dumps({"name": name, "arguments": args}, ensure_ascii=False)


def _calls_in(raw: str) -> list[str]:
    try:
        obj = json.loads(raw)
    except ValueError:
        return []
    items = obj.get("tool_calls", [obj]) if isinstance(obj, dict) else obj if isinstance(obj, list) else []
    out = [_call(x) for x in items]
    return [x for x in out if x] if all(out) else []


def parse(text: str) -> tuple[str, list[str], str]:
    """(the reply as kept, its tool calls as the loop's JSON, what it said around them). The reply is cut where the
    model began to write a tool's result itself; every known call format becomes the loop's own."""
    m = INVENTED.search(text)
    if m:
        text = text[:m.start()].rstrip()
    calls = [c for raw in CALL.findall(text) for c in (_calls_in(raw) or [raw])]
    calls += [json.dumps({"name": n, "arguments": {k: _param(v) for k, v in PARAM.findall(body)}}, ensure_ascii=False)
              for n, body in INVOKE.findall(text)]
    calls += [c for n, body in FUNCTION.findall(text) for c in _calls_in(json.dumps({"name": n, "arguments": _param(body)}))]
    for rx in (PYTAG, MISTRAL):
        calls += [c for raw in rx.findall(text) for c in _calls_in(raw)]
    found, rest = _mistral_args(text)
    said = rest
    calls += found
    for rx in (CALL, INVOKE, FUNCTION, PYTAG, MISTRAL):
        said = rx.sub("", said)
    said = re.sub(r"</?(function_calls|antml:function_calls)>", "", said).strip()
    if not calls:                                       # a reply that is only a call's JSON
        b = BARE.match(text)
        if b and re.search(r'"(arguments|parameters|input|tool_calls)"', b.group(1)) and (found := _calls_in(b.group(1))):
            calls, said = found, ""
    if not calls:                                       # a ```json block among words: a call only to one of Aurora's tools
        for raw in FENCED.findall(text):
            found = [c for c in _calls_in(raw) if (n := json.loads(c)["name"]) == "finish" or "__" in n]
            if found and re.search(r'"(arguments|parameters|input)"', raw):
                calls += found
                said = said.replace(raw, "")
        said = re.sub(r"```(?:json)?\s*```", "", said).strip() if calls else said
    return text, calls, said


def unwrap(report: str) -> str:
    """A report the model wrapped in a finish call it never closed: its summary's text, not the raw call."""
    if "<tool_call>" not in report:
        return report
    m = SUMMARY.search(report)
    if m:
        try:
            return json.loads('"' + m.group(1).rstrip("\\") + '"').strip()
        except ValueError:
            return m.group(1).replace("\\n", "\n").strip()
    return report.split("<tool_call>")[0].strip()
