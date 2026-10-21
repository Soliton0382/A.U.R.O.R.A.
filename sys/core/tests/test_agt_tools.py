# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugins on request (16 Oct: GitHub's 45 tools were 17,750 of the catalog's ~39,700 tokens; the agent's prompt for a
goal not about GitHub went from 42,215 to 24,664 tokens)."""
import json
from types import SimpleNamespace

from aurora import agt_tools

GH = {"on_demand": {"words": ["github", "pull request", "repo"]}}


def plugin(name, manifest, n=2):
    tools = [{"name": f"t{i}", "effect": "read", "description": "d", "input_schema": {"type": "object"}} for i in range(n)]
    return SimpleNamespace(name=name, manifest={"description": {"en": f"{name} things"}, **manifest}, tools=tools)


def test_a_plugin_on_request_only_when_the_goal_names_it():
    assert agt_tools.wanted({}, "anything")                                   # every other plugin, always
    assert agt_tools.wanted(GH, "Apri una pull request sul mio GitHub")
    assert agt_tools.wanted(GH, "il mio repo")
    assert not agt_tools.wanted(GH, "Quante routine ho attive?")
    assert not agt_tools.wanted(GH, "il reporter ha scritto")                  # whole words: «repo» is not «reporter»


def test_more_tools_gives_the_specs_and_makes_them_callable():
    gh = plugin("github", GH)
    index = {}
    text = agt_tools.more([gh], "github", index, "__")
    assert set(index) == {"github__t0", "github__t1"} and index["github__t0"] == ("github", "t0", "read")
    specs = [json.loads(x) for x in text.split("<tools>\n")[1].split("\n</tools>")[0].split("\n")]
    assert specs[0]["function"]["name"] == "github__t0"
    assert agt_tools.more([gh], "dropbox", {}, "__").startswith("ERROR")
    assert "github: github things (2 tools)" in agt_tools.section([gh]) and agt_tools.section([]) == ""


def test_a_long_result_says_where_it_stops():
    # C381: every tool result was cut at 6,000 characters without a word (a patent page ended at its «Definitions»)
    from aurora import agt_tools
    short = "x" * 100
    assert agt_tools.clip(short) == short
    out = agt_tools.clip("y" * (agt_tools.RESULT_CHARS + 500))
    assert out.startswith("y" * agt_tools.RESULT_CHARS) and "500 more characters" in out and "offset" in out


def test_a_long_page_is_read_in_parts():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("web_plugin_server", Path(__file__).resolve().parents[2] / "plugins" / "web" / "server.py")
    web = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(web)
    text = "a" * 30 + "b" * 30
    first = web._part(text, 30, 0)
    assert first.startswith("a" * 30) and "30 more characters" in first and "offset=30" in first
    assert web._part(text, 30, 30) == "b" * 30
