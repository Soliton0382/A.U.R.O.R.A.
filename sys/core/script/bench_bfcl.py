# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""BFCL — the Berkeley Function Calling Leaderboard (gorilla-llm, Apache-2.0): does the answer call the right function
with the right arguments (owner, 2026-10-19: «e il set uso strumenti?… parti con il set BFCL»). Read by
bench_public_data.

Three of its categories: simple (one function offered, one call), multiple (several offered, the right one chosen),
irrelevance (none fits: the right answer is no call). Asked the way BFCL asks a model without native function calling
(its «prompt» mode): the functions as JSON in the text and the answer as a list of Python calls, [f(a=1, b="x")]. Scored
by its AST checker written again here: the call parsed (never run), the function's name, every required argument present,
no argument the function has not got, each value one of the allowed (strings compared as BFCL does — case, spaces and
, . / - _ * ^ ignored —, an integer accepted for a float, lists and dicts element by element); an optional argument may be
left out when the allowed values hold "". Irrelevance is right when an answer came and nothing in it decodes as a call:
an empty answer (the thinking ran out of tokens or time) is wrong — stricter than BFCL's own checker, which counts it as
right (C358: 25 of the bare model's 50 were empty and all scored right). Rows fetched from the
dataset's files at a pinned revision, so that two runs ask the same questions.
"""
from __future__ import annotations

import ast
import json
import re

import httpx

REPO = "https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard/resolve"
REVISION = "61fc0608cfd831fcfbbaa676ebdfef0ed963eeda"
CATEGORIES = ("simple", "multiple", "irrelevance")
# BFCL's own system prompt for models prompted (no native function calling), sent with the question
SYSTEM = ("You are an expert in composing functions. You are given a question and a set of possible functions. Based on "
          "the question, you will need to make one or more function/tool calls to achieve the purpose. If none of the "
          "functions can be used, point it out. If the given question lacks the parameters required by the function, "
          "also point it out. You should only return the function calls in your response.\n\nIf you decide to invoke any "
          "of the function(s), you MUST put it in the format of [func_name1(params_name1=params_value1, "
          "params_name2=params_value2...), func_name2(params)]\n\nYou SHOULD NOT include any other text in the response."
          "\n\nHere is a list of functions in JSON format that you can invoke.\n")


def fetch(name: str) -> list[dict]:
    r = httpx.get(f"{REPO}/{REVISION}/{name}", timeout=120, follow_redirects=True)
    r.raise_for_status()
    return [json.loads(x) for x in r.text.splitlines() if x.strip()]


def rows(category: str) -> list[dict]:
    """The category's questions with their allowed answers (none for irrelevance)."""
    qs = fetch(f"BFCL_v3_{category}.json")
    if category == "irrelevance":
        return qs
    gold = {a["id"]: a["ground_truth"] for a in fetch(f"possible_answer/BFCL_v3_{category}.json")}
    return [{**q, "ground_truth": gold[q["id"]]} for q in qs if q["id"] in gold]


def items(rs: list[dict], category: str) -> list[dict]:
    out = []
    for r in rs:
        user = " ".join(m["content"] for turn in r["question"] for m in turn if m.get("role") == "user")
        prompt = f"{SYSTEM}{json.dumps(r['function'], ensure_ascii=False)}\n\n{user}"
        out.append({"id": r["id"], "kind": "bfcl", "category": category, "prompt": prompt,
                    "functions": r["function"], "gold": r.get("ground_truth", []),
                    "answer": json.dumps(r.get("ground_truth", []), ensure_ascii=False)[:200] or "no call"})
    return out


# ---- the AST checker -----------------------------------------------------------------------------------------------

def _name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_name(node.value)}.{node.attr}"
    raise ValueError("not a function's name")


def decode(text: str) -> list[dict] | None:
    """The answer's calls [{"name", "args"}] — the last bracketed list, or the bare calls — or None when nothing decodes."""
    t = re.sub(r"```(?:python|json|py)?", "", str(text or "")).strip()
    t = re.sub(r"(?s)<think>.*?</think>", "", t).strip()
    candidates = re.findall(r"\[[^\[\]]*\([^\[\]]*\)[^\[\]]*\]|\[.*\]", t, re.S)[::-1] + [f"[{t}]"]
    for c in candidates:
        try:
            tree = ast.parse(c.strip(), mode="eval").body
        except (SyntaxError, ValueError):
            continue
        calls = tree.elts if isinstance(tree, (ast.List, ast.Tuple)) else [tree]
        out = []
        try:
            for call in calls:
                if not isinstance(call, ast.Call) or call.args:
                    raise ValueError("not a call by keywords")
                out.append({"name": _name(call.func), "args": {k.arg: ast.literal_eval(k.value) for k in call.keywords}})
        except (ValueError, SyntaxError):
            continue
        if out:
            return out
    return None


def _std(s: str) -> str:
    return re.sub(r"[ ,./\-_*^]", "", str(s)).lower().replace("'", '"')


def same(value, allowed) -> bool:
    """One value against one allowed value, BFCL's way."""
    if isinstance(allowed, str):
        return isinstance(value, str) and _std(value) == _std(allowed)
    if isinstance(allowed, bool) or isinstance(value, bool):
        return value is allowed
    if isinstance(allowed, (int, float)):
        return isinstance(value, (int, float)) and float(value) == float(allowed)
    if isinstance(allowed, list):
        return isinstance(value, (list, tuple)) and len(value) == len(allowed) and all(
            same(v, a) for v, a in zip(value, allowed))
    if isinstance(allowed, dict):
        if not isinstance(value, dict):
            return False
        for k, opts in allowed.items():
            opts = opts if isinstance(opts, list) else [opts]
            if k not in value:
                if "" not in opts:
                    return False
            elif not any(same(value[k], o) for o in opts if o != ""):
                return False
        return set(value) <= set(allowed)
    return value == allowed


def check(call: dict, gold: dict, functions: list[dict]) -> str:
    """"" when the call is one the gold accepts, else why not."""
    (want, params), = gold.items()
    # the set names a few functions by their last part only (simple_363: «find_closest» for restaurant_search.find_closest)
    if call["name"] != want and call["name"].rsplit(".", 1)[-1] != want:
        return f"function {call['name']} instead of {want}"
    spec = next((f for f in functions if f["name"] == call["name"]), {})
    props = (spec.get("parameters") or {}).get("properties") or {}
    for k in call["args"]:
        if k not in props:
            return f"argument {k} the function has not got"
    for k, opts in params.items():
        if k not in call["args"]:
            if "" not in opts:
                return f"argument {k} missing"
            continue
        if not any(same(call["args"][k], o) for o in opts if o != ""):
            return f"argument {k}={call['args'][k]!r} not among {opts[:3]}"
    return ""


def score(item: dict, answer: str, judge=None) -> dict:
    if not (answer or "").strip():
        return {"right": False, "got": "no answer"}               # cut, not a choice (C358)
    calls = decode(answer)
    if item["category"] == "irrelevance":
        return {"right": not calls, "got": "no call" if not calls else f"called {calls[0]['name']}"}
    if not calls:
        return {"right": False, "got": "no call decoded"}
    if len(calls) != len(item["gold"]):
        return {"right": False, "got": f"{len(calls)} calls instead of {len(item['gold'])}"}
    why = check(calls[0], item["gold"][0], item["functions"])
    return {"right": not why, "got": why or f"{calls[0]['name']} ✓"}
