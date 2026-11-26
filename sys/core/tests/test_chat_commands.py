# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N158: «/» commands — listed for the composer, /calcola and /fem sent to the agent with the compute tool, /lean left
to the Lean mathematician, a message that only looks like one untouched; the router knows the compute service."""
from aurora import chat_commands as C


def test_the_listing_shows_built_in_commands_always_and_plugin_ones_only_when_available():
    it = C.listing("it", available=set())
    cmds = [c["cmd"] for c in it]
    assert {"/calcola", "/fem", "/lean", "/arxiv", "/immagine", "/pagina", "/telefono"} <= set(cmds)
    assert "/email" not in cmds and "/meteo" not in cmds
    assert "/email" in [c["cmd"] for c in C.listing("it", available={"email"})]
    assert all(c["text"] and c["example"].startswith(c["cmd"]) for c in C.listing("en"))
    assert len({c["cmd"] for c in C.COMMANDS}) == len(C.COMMANDS)


def test_forced_commands_aliases_and_what_is_not_one():
    c, rest = C.forced("/calcola 17**23")
    assert c["cmd"] == "/calcola" and rest == "17**23"
    assert C.forced("  /FEM: piastra calda")[0]["cmd"] == "/fem"
    assert C.forced("/calc 2+2")[0]["cmd"] == "/calcola" and C.forced("/posta oggi", {"email"})[0]["cmd"] == "/email"
    assert C.forced("/lean 1+1=2") is None                 # the Lean mathematician's own
    assert C.forced("calcola 2+2") is None and C.forced("/calcolatrice x") is None and C.forced("a/b") is None
    assert C.forced("/email oggi", available=set()) is None        # its plugin not available: normal routing
    assert C.forced("/arxiv yig")[0]["kind"] == "arxiv"


def test_the_goal_names_the_tool():
    assert "the compute tool" in C.goal(C.forced("/calcola x")[0], "x")
    g = C.goal(C.forced("/fem x")[0], "piastra")
    assert "fem=true" in g and "exact solution" in g and g.endswith("piastra")


ROUTE = (__import__("pathlib").Path(__file__).resolve().parents[1] / "aurora" / "api" / "core_route.py").read_text(
    encoding="utf-8")


def test_a_computation_takes_the_short_path_before_the_tools_agent():
    """27 Nov, measured: through the 184-tool agent a computation failed whenever the cloud was out."""
    body = ROUTE[ROUTE.index("def answer_or_acquire"):]
    assert body.index("kno_compute.wants(") < body.index("wants_tools(question, recent, emit)")
    assert '"- compute:' not in ROUTE                          # not a service of the agent any more
    assert '"/calcola", "/fem"' in body and "_compute(question, rest" in body


def test_a_forced_command_goes_to_the_agent_before_lean_and_the_tools_router():
    body = ROUTE[ROUTE.index("def answer_or_acquire"):]
    assert body.index("chat_commands.forced(question") < body.index("kno_prove_chat.answer(") < body.index("wants_tools(")
    seg = body[body.index("chat_commands.forced(question"):body.index("kno_prove_chat.answer(")]
    assert "_agent_job(chat_commands.goal(c, rest)" in seg and "asked=True" in seg and 'not kw.get("attached")' in seg
    assert seg.index('"/calcola", "/fem"') < seg.index("_agent_job(")
    assert "ArxivAgent(p, cfg).run(rest" in seg and "available_plugins()" in seg
