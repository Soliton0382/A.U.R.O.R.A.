# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import json
from types import SimpleNamespace

from aurora import agt_change
from aurora.agt_loop import unwritten
from aurora.mdl_fit import SHORTENED
from aurora.agt_loop import Agent
from aurora.sys_approvals import Approvals, needs_owner


def test_gate_follows_effect_and_settings(cfg):
    assert not needs_owner("read", cfg) and not needs_owner("write_local", cfg)
    # without the owner's exemption (ethics code, level B) the .env cannot switch confirmations off;
    # with it, the .env decides (test_ethics.test_level_b_holds_without_the_owners_exemption)
    cfg.values["AURORA_CONFIRM_EXTERNAL_ACTIONS"] = False
    cfg.values["AURORA_FORGE_MODE"] = "auto"
    assert needs_owner("external", cfg) and needs_owner("code_change", cfg)


def test_approvals_store(cfg):
    a = Approvals(cfg)
    r = a.request("tool_call", "external", "telegram.send_message", "tell the owner", {"text": "ciao"},
                  {"plugin": "telegram", "tool": "send_message", "arguments": {"text": "ciao"}})
    assert [x["id"] for x in a.list("pending")] == [r["id"]]
    a.update(r["id"], status="rejected")
    assert a.get(r["id"])["status"] == "rejected" and a.list("pending") == []


class FakeLLM:
    def __init__(self, turns):
        self.turns, self.seen = list(turns), []

    def complete_turns(self, messages, max_tokens, think=False):
        self.seen.append(messages[-1])
        return SimpleNamespace(answer=self.turns.pop(0), thought="", truncated=False)


def fake_pipeline(llm):
    return SimpleNamespace(llm=llm, _for=lambda role: llm)


class FakeHost:
    def __init__(self):
        self.calls = []

    def plugins(self):
        tools = [{"name": "read_log", "description": "read", "input_schema": {}, "effect": "read"},
                 {"name": "read_file", "description": "read a file", "input_schema": {}, "effect": "read"},
                 {"name": "project_edit_file", "description": "edit a file", "input_schema": {}, "effect": "write_local"},
                 {"name": "send_message", "description": "send", "input_schema": {}, "effect": "external"}]
        return [SimpleNamespace(name="demo", available=True, tools=tools)]

    def get(self, plugin):
        return SimpleNamespace(manifest={"publishes": {"send_message": "text"}})

    def call(self, plugin, tool, args, run_id=None):
        self.calls.append((plugin, tool, args))
        return {"ok": True, "text": "log line 1", "seconds": 0}


def call(name, **args):
    return "<tool_call>\n" + json.dumps({"name": name, "arguments": args}) + "\n</tool_call>"


def test_agent_reads_asks_for_external_and_finishes(cfg):
    cfg.values["AURORA_CONFIRM_EXTERNAL_ACTIONS"] = True
    llm = FakeLLM([call("demo__read_log", component="api"),
                   "Invio un messaggio. " + call("demo__send_message", text="ciao"),
                   call("finish", summary="Letto il log; messaggio in attesa di approvazione.")])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    events = []
    ans = agent.run("prova", lambda e, p: events.append((e, p)), "run1")
    assert agent.host.calls == [("demo", "read_log", {"component": "api"})]          # the external one did not run
    pending = agent.approvals.list("pending")
    assert [x["title"] for x in pending] == ["demo.send_message"]
    sent = pending[0]["action"]["arguments"]["text"]                  # AI Act art. 50: marked, in its language
    assert sent.startswith("ciao") and sent.endswith((cfg["AURORA_AI_DISCLOSURE_IT"], cfg["AURORA_AI_DISCLOSURE_EN"]))
    assert ans.text.startswith("⏳ Proposto, non ancora fatto") and "\n\nLetto il log" in ans.text and ans.mode == "agent"
    names = [e for e, _ in events]
    assert names[0] == "agent.start" and "approval.request" in names and names[-1] == "agent.finish"
    assert llm.seen[1]["role"] == "tool" and "log line 1" in llm.seen[1]["content"]


def test_change_detection_services_and_rollback(cfg, tmp_path):
    root = cfg.root
    live = root / "sys" / "core" / "aurora"
    live.mkdir(parents=True)
    (live / "a.py").write_text("x = 1\n")
    box = cfg.path("AURORA_SANDBOX_DIR") / "fix-000001"
    (box / "sys" / "core" / "aurora").mkdir(parents=True)
    (box / "sys" / "core" / "aurora" / "a.py").write_text("x = 2\n")
    (box / "sys" / "core" / "aurora" / "b.py").write_text("y = 1\n")
    files = agt_change.changed_files(box, root)
    assert files == ["sys/core/aurora/a.py", "sys/core/aurora/b.py"]
    assert agt_change.services_for(files) == ["aurora-api", "aurora-harvester", "aurora-rem"]
    assert agt_change.services_for(["sys/core/webui/js/main.js", "sys/core/script/svc_models.py"]) == ["aurora-models"]
    backup = box / ".backup" / "sys" / "core" / "aurora"                # what apply() saves before copying
    backup.mkdir(parents=True)
    (backup / "a.py").write_text("x = 1\n")
    (box / ".backup" / "NEW_FILES.json").write_text('["sys/core/aurora/b.py"]')
    (live / "a.py").write_text("x = 2\n")
    (live / "b.py").write_text("y = 1\n")
    agt_change.rollback("fix-000001", cfg)
    assert (live / "a.py").read_text() == "x = 1\n" and not (live / "b.py").exists()


def test_empty_turns_are_nudged_and_a_report_is_always_written(cfg):
    # empty, tool call, empty, empty (the nudges are used up: the loop ends), then the report it asks for
    llm = FakeLLM(["", call("demo__read_log", component="api"), "", "", "Resoconto: letto il log, nulla da correggere."])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    events = []
    ans = agent.run("prova", lambda e, p: events.append(e), "run2")
    assert events.count("agent.nudge") == 2                     # two empty turns get a nudge, not the end
    assert agent.host.calls == [("demo", "read_log", {"component": "api"})]
    assert ans.text.startswith("Resoconto: letto il log, nulla da correggere.")   # the report is asked for
    assert "Azioni eseguite" in ans.text


def test_old_tool_results_are_shortened_when_the_context_is_full(cfg):
    cfg.values["AURORA_LLM_CTX"] = 6000
    agent = Agent(fake_pipeline(SimpleNamespace(count_tokens=lambda text: len(text) // 4)), cfg)
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "goal"}]
    for i in range(8):
        messages += [{"role": "assistant", "content": f"call {i}"}, {"role": "tool", "content": f"{i}" * 3000}]
    room = agent._fit(messages, 1000, lambda e, p: None)
    tools = [m["content"] for m in messages if m["role"] == "tool"]
    short = [t.endswith(SHORTENED) for t in tools]
    assert any(short) and short == sorted(short, reverse=True)          # only the oldest, as few as needed
    assert all(len(t) == 3000 for t in tools[-4:])                      # the latest four stay whole
    assert room >= 1000
    assert "call the same tool again" in SHORTENED                      # the model is told how to get it back


def test_the_sources_the_goal_names_are_shortened_last(cfg):
    # C396: the paper's material, read first, was cut to 400 characters while a vault search stayed whole
    cfg.values["AURORA_LLM_CTX"] = 6000
    agent = Agent(fake_pipeline(SimpleNamespace(count_tokens=lambda text: len(text) // 4)), cfg)
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "goal"}]
    for i in range(8):
        messages += [{"role": "assistant", "content": f"call {i}"}, {"role": "tool", "content": f"{i}" * 3000}]
    agent.pinned = {id(messages[3])}                                    # the first result: a source the goal names
    agent._fit(messages, 1000, lambda e, p: None)
    tools = [m["content"] for m in messages if m["role"] == "tool"]
    assert len(tools[0]) == 3000 and tools[1].endswith(SHORTENED)       # the next oldest went instead


def test_a_read_of_a_file_the_goal_names_is_pinned(cfg):
    llm = FakeLLM([call("demo__read_file", path="docs/fonte.md"), call("demo__read_file", path="altro.md"),
                   call("finish", summary="Fatto.")])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    agent.run("scrivi partendo da docs/fonte.md", lambda e, p: None, "run9")
    assert len(agent.pinned) == 1


def test_report_ends_with_the_record_and_false_claims_are_flagged(cfg):
    llm = FakeLLM([call("demo__read_log", component="api"),
                   call("finish", summary="Ho creato una sandbox e i test passano.")])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    ans = agent.run("prova", lambda e, p: None, "run3")
    assert ans.text.startswith("⚠️ Attenzione")                               # the claim is not in the log
    assert "Azioni eseguite (dal registro delle chiamate): 1 chiamate; 1 letture; 0 sandbox create" in ans.text


def test_each_claim_needs_its_action_in_the_log(cfg):
    llm = FakeLLM([call("self__sandbox_create", label="x"),
                   call("finish", summary="Ho creato una sandbox e ho sostituito l'accesso allo schema.")])
    agent = Agent(fake_pipeline(llm), cfg)

    class SelfHost(FakeHost):
        def plugins(self):
            return [SimpleNamespace(name="self", available=True, tools=[
                {"name": "sandbox_create", "description": "", "input_schema": {}, "effect": "write_local"}])]
    agent.host = SelfHost()
    ans = agent.run("prova", lambda e, p: None, "run4")
    first = ans.text.splitlines()[0]
    assert "modifiche al codice" in first and "sandbox create" not in first     # the sandbox was made, the edit not


def test_a_report_never_says_published_while_the_post_waits_for_the_owner():
    import logging
    from aurora.agt_loop import Agent
    a = Agent.__new__(Agent)
    a.ledger, a.log, a.pending = [("facebook__publish_post", True)], logging.getLogger("t"), ["facebook.publish_post"]
    out = a._honest("Ho pubblicato la foto su Facebook con una bella didascalia.")
    assert out.startswith("⚠️ Niente è stato ancora pubblicato") and "facebook.publish_post" in out.splitlines()[1]
    a.pending = []
    assert a._honest("Ecco la didascalia che ti propongo.") == "Ecco la didascalia che ti propongo."


def test_a_report_left_inside_an_unclosed_finish_call_is_unwrapped():
    from aurora.agt_loop import unwrap
    raw = '<tool_call>\n{"name": "finish", "arguments": {"summary": "Causa trovata:\\nil plugin non è installato."'
    assert unwrap(raw) == "Causa trovata:\nil plugin non è installato."
    assert unwrap("Resoconto normale.") == "Resoconto normale."
    assert unwrap("Testo prima <tool_call> {rotto") == "Testo prima"


def test_a_tool_call_closed_with_the_wrong_tag_or_left_open_is_still_a_call():
    """C111: a long create_artifact call closed with </tool_response> was taken for the report."""
    import json

    from aurora.agt_loop import CALL
    for text, names in (('<tool_call>{"name": "a", "arguments": {"x": "}"}}</tool_call>', ["a"]),
                        ('<tool_call>\n{"name": "b", "arguments": {}}\n</tool_response>', ["b"]),
                        ('ok <tool_call>{"name": "c", "arguments": {"h": "<p>{}</p>"}}', ["c"])):
        assert [json.loads(m)["name"] for m in CALL.findall(text)] == names


def test_a_project_s_report_is_not_flagged_as_false(cfg):
    """C134: files written and tests run in a project are actions in the log, not claims without evidence."""
    from types import SimpleNamespace
    from aurora.agt_loop import Agent
    a = Agent(SimpleNamespace(llm=None, _for=lambda r: None), cfg, host=SimpleNamespace())
    a.ledger = [("projects__project_write_file", True), ("run_in_project", True)]
    out = a._honest("Ho modificato core.py e i test passano: 32 superati.")
    assert not out.startswith("⚠️") and "1 file scritti nei progetti" in a._record()
    a.ledger = []
    assert a._honest("Ho modificato core.py e i test passano.").startswith("⚠️")



def test_a_denied_action_is_not_a_claim():
    """C155: «Non ho modificato codice, non ho creato sandbox e non ho proposto modifiche» flagged a weather report."""
    from aurora.agt_loop import Agent
    a = Agent.__new__(Agent)
    a.ledger, a.pending, a.effects = [], [], {}
    import logging
    a.log = logging.getLogger("t")
    text = "Meteo a Roma: 20 °C. Non ho modificato codice, non ho creato sandbox e non ho proposto modifiche: non servivano."
    assert a._honest(text) == text
    assert a._honest("I did not create a sandbox. Ho creato una sandbox e ho applicato il fix.").startswith("⚠️")


def test_a_heading_answered_by_nothing_is_not_a_claim():
    """C350: «**Cosa ho cambiato o proposto**\nNiente: ho solo letto» was flagged as code changes not in the log."""
    from aurora.agt_loop import Agent
    import logging
    a = Agent.__new__(Agent)
    a.ledger, a.pending, a.effects, a.log = [], [], {}, logging.getLogger("t")
    text = "Ho riletto i dati.\n\n**Cosa ho cambiato o proposto**\nNiente: ho solo letto, non ho creato sandbox."
    assert a._honest(text) == text
    assert a._honest("**Cosa ho cambiato**\nHo modificato core.py.").startswith("⚠️")
    assert a._honest("Ho cambiato la soglia del firewall.").startswith("⚠️")


def test_a_call_written_in_claudes_own_format_is_made_and_its_invented_result_is_dropped(cfg):
    """C232 (owner, 9 Oct: «routine raccomandate… ha dato degli errori»): Claude Code haiku wrote its calls as
    <invoke name=…> and, after each, a result it made up («Metodo non disponibile»); the run made 0 calls and reported
    that. The call is made; what the model wrote as its result is never read as one."""
    haiku = ('<invoke name="demo__read_log">\n<parameter name="limit">20</parameter>\n</invoke>\n'
             'iTool call results (not part of the conversation):\n{"error": "Metodo non disponibile: read_log"}\n\n'
             '<invoke name="finish">\n<parameter name="summary">Non ho potuto leggere.</parameter>\n</invoke>')
    llm = FakeLLM([haiku, '<invoke name="finish"><parameter name="summary">Letto: log line 1.</parameter></invoke>'])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    ans = agent.run("prova", lambda e, p: None, "run1")
    assert agent.host.calls == [("demo", "read_log", {"limit": 20})]                 # made, with its typed argument
    assert "Metodo non disponibile" not in ans.text and "Letto: log line 1." in ans.text
    assert llm.seen[1]["role"] == "tool" and "log line 1" in llm.seen[1]["content"]   # the real result went back


import pytest  # noqa: E402

FORMATS = {
    "hermes / qwen": '<tool_call>\n{"name": "demo__read_log", "arguments": {"limit": 5}}\n</tool_call>',
    "hermes with parameters": '<tool_call>{"name": "demo__read_log", "parameters": {"limit": 5}}</tool_call>',
    "claude": '<invoke name="demo__read_log"><parameter name="limit">5</parameter></invoke>',
    "claude in function_calls": ('<function_calls>\n<invoke name="demo__read_log">\n<parameter name="limit">5</parameter>'
                                 '\n</invoke>\n</function_calls>'),
    "claude invoke_tool (C275)": ('<invoke_tool>\n<parameter name="name">demo__read_log</parameter>\n'
                                  '<parameter name="arguments">{"limit": 5}</parameter>\n</invoke_tool>'),
    "llama 3.1 function": '<function=demo__read_log>{"limit": 5}</function>',
    "llama 3.1 python_tag": '<|python_tag|>{"name": "demo__read_log", "parameters": {"limit": 5}}',
    "mistral": '[TOOL_CALLS] [{"name": "demo__read_log", "arguments": {"limit": 5}}]',
    "openai as text": '{"tool_calls": [{"function": {"name": "demo__read_log", "arguments": "{\\"limit\\": 5}"}}]}',
    "bare json": '{"name": "demo__read_log", "arguments": {"limit": 5}}',
    "json block": 'Leggo il log.\n```json\n{"name": "demo__read_log", "arguments": {"limit": 5}}\n```',
}


@pytest.mark.parametrize("fmt", sorted(FORMATS))
def test_every_providers_call_format_is_read(fmt):
    """Owner, 9 Oct: «compatibile con ogni formato utilizzato dai vari provider e modelli» — each becomes the loop's
    own call, with its arguments typed."""
    from aurora.agt_loop import parse
    _, calls, _ = parse(FORMATS[fmt])
    assert [json.loads(c) for c in calls] == [{"name": "demo__read_log", "arguments": {"limit": 5}}], fmt


def test_a_report_with_json_in_it_is_not_a_call():
    from aurora.agt_loop import parse
    assert parse('{"name": "Mario", "eta": 40}')[1] == []
    assert parse("Fatto. Il file contiene {\"a\": 1}.")[1] == []
    assert parse('Esempio:\n```json\n{"name": "Mario", "arguments": {}}\n```')[1] == []     # not one of Aurora's tools


def test_a_call_cut_mid_way_is_asked_again_not_shown_as_the_answer(cfg):
    # C278: «accendi la luce» → '<tool_call>{"name": …, "entity_id": "light.gard' (the reply cut): it was the answer
    cut = '<tool_call>\n{"name": "demo__read_log", "arguments": {"component": "ap'
    llm = FakeLLM([cut, call("demo__read_log", component="api"), call("finish", summary="Fatto.")])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    events = []
    ans = agent.run("prova", lambda e, p: events.append((e, p)), "run1")
    assert agent.host.calls == [("demo", "read_log", {"component": "api"})] and "Fatto." in ans.text
    assert ("agent.nudge", {"reason": "cut call"}) in events and "tool_call" not in ans.text
    assert not [p for e, p in events if e == "agent.say"]


def test_broken_pieces_of_a_call_are_never_the_report(cfg):
    # C302: Home Assistant down, the local model's last words were the pieces of a call: they were the owner's report
    junk = '<invoke-name>\n<parameter name="name">homeassistant__states</parameter>\n</invoke>'
    llm = FakeLLM([junk, "_tool_call_placeholder", "_tool_call_placeholder", "Prese non lette: <parameter name=\"x\">"])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    events = []
    ans = agent.run("prova", lambda e, p: events.append((e, p)), "run1")
    assert "parameter" not in ans.text and "placeholder" not in ans.text and "Prese non lette:" in ans.text
    assert [p["reason"] for e, p in events if e == "agent.nudge"] == ["cut call", "cut call"]
    assert not [p for e, p in events if e == "agent.say"]


def test_a_finish_written_with_the_calls_before_their_results_is_not_the_report(cfg):
    # C304: one turn held the calls and a finish whose report had invented their results
    turn = call("demo__read_log", component="api") + "\n" + call("finish", summary="Tutto ok: i test passano.")
    llm = FakeLLM([turn, call("finish", summary="Il log dice: ok.")])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    events = []
    ans = agent.run("prova", lambda e, p: events.append((e, p)), "run1")
    assert agent.host.calls == [("demo", "read_log", {"component": "api"})]
    assert "Il log dice: ok." in ans.text and "Tutto ok" not in ans.text
    assert ("agent.nudge", {"reason": "finish before results"}) in events



def test_an_empty_finish_is_not_the_report_it_is_asked_again(cfg):
    # C391: two routines ended with only the call log as their report: the finish came with nothing in it
    llm = FakeLLM([call("demo__read_log", component="api"), call("finish", summary=""),
                   "Resoconto: il log dice ok."])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    events = []
    ans = agent.run("prova", lambda e, p: events.append((e, p)), "run1")
    assert "Resoconto: il log dice ok." in ans.text
    empty = [p for e, p in events if e == "agent.empty_finish"]
    assert empty and empty[0]["keys"] == ["summary"] and '"finish"' in empty[0]["raw"]


def test_a_finish_with_its_report_under_another_key_is_kept(cfg):
    llm = FakeLLM([call("finish", report="Fatto: tre punti.")])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    ans = agent.run("prova", lambda e, p: None, "run1")
    assert ans.text.startswith("Fatto: tre punti.")

def test_a_catalog_too_big_for_the_context_becomes_one_line_signatures(cfg):
    # C279: 176 tools ≈ the 32k context of the local model; the room for the answer fell to its 256-token floor
    llm = FakeLLM([call("finish", summary="ok")])
    llm.context_tokens = 400
    llm.count_tokens = lambda prompt: len(prompt) // 3
    agent = Agent(fake_pipeline(llm), cfg)
    host = FakeHost()
    big = {"type": "object", "required": ["domain"], "properties": {
        "domain": {"type": "string", "description": "x" * 300}, "mode": {"enum": ["on", "off"]}}}
    host.plugins = lambda: [SimpleNamespace(name="demo", available=True, tools=[
        {"name": f"t{i}", "description": "does a thing " * 5, "input_schema": big, "effect": "read"} for i in range(6)])]
    agent.host = host
    events = []
    agent.run("prova", lambda e, p: events.append((e, p)), "run1")
    short = [p for e, p in events if e == "agent.compact" and "tools" in p]
    assert short and short[0]["short_tokens"] < short[0]["prompt_tokens"]
    from aurora.agt_loop import signature
    line = signature({"function": {"name": "demo__t0", "description": "Turn on.", "parameters": big}})
    assert line == "demo__t0(domain*: string, mode: on|off) Turn on."


def test_the_local_context_is_the_servers_divided_among_its_slots(cfg):
    cfg.values["AURORA_LLM_CTX"], cfg.values["AURORA_LLM_PARALLEL"] = 65536, 2
    agent = Agent(fake_pipeline(SimpleNamespace()), cfg)
    assert agent._ctx() == 32768                                  # C279: it counted 65536
    agent.p = fake_pipeline(SimpleNamespace(context_tokens=200_000))
    assert agent._ctx() == 200_000


def test_a_home_command_the_owner_asked_for_is_done_one_a_run_decided_waits(cfg, monkeypatch):
    # C281, owner 2026-10-12: «se io le chiedo di farlo deve farlo automaticamente»
    class Home(FakeHost):
        def plugins(self):
            tools = [{"name": "call_service", "description": "", "input_schema": {}, "effect": "external"}]
            return [SimpleNamespace(name="homeassistant", available=True, tools=tools)]

        def get(self, plugin):
            return SimpleNamespace(manifest={"home_commands": ["call_service"]})

    def run(asked, level, exempt=False):
        cfg.values["AURORA_CONFIRM_EXTERNAL_ACTIONS"], cfg.values["AURORA_HA_COMMANDS"] = True, level
        monkeypatch.setattr("aurora.sys_ethics.exempt", lambda c=None: exempt)
        llm = FakeLLM([call("homeassistant__call_service", domain="light", service="turn_on", entity_id="light.a"),
                       call("finish", summary="ok")])
        agent = Agent(fake_pipeline(llm), cfg)
        agent.host, agent.asked = Home(), asked
        agent.run("accendi la luce", lambda e, p: None, "run1")
        return len(agent.host.calls), len(agent.approvals.list("pending"))

    assert run(True, 1) == (1, 0)                       # asked in the chat: done
    assert run(True, 0) == (0, 1)                       # 0: every command waits
    assert run(False, 1) == (0, 2)                      # a routine's own decision waits
    assert run(False, 2) == (0, 3)                      # 2 without the exemption from level B: still waits
    assert run(False, 2, exempt=True) == (1, 3)



def test_an_owner_only_command_never_runs_by_a_runs_own_decision(cfg, monkeypatch):
    # disarming an alarm: done when the owner asks, never by a routine — not even at level 2 with the exemption
    monkeypatch.setattr("aurora.sys_ethics.exempt", lambda c=None: True)
    cfg.values["AURORA_HA_COMMANDS"] = 2
    agent = Agent(fake_pipeline(FakeLLM([])), cfg)
    agent.host = SimpleNamespace(get=lambda p: SimpleNamespace(manifest={"home_commands": ["arm", "disarm"],
                                                                         "owner_only": ["disarm"]}))
    assert agent._home_free("alarm", "arm") and not agent._home_free("alarm", "disarm")
    agent.asked = True
    assert agent._home_free("alarm", "disarm")


def test_a_plugin_that_does_not_start_is_said_not_forged_again(cfg):
    # C311: the patent plugin down (C309) and the agent asked the forge for «a tool patent_document»
    agent = Agent(fake_pipeline(FakeLLM([])), cfg)
    down = SimpleNamespace(name="patent", enabled=True, available=False, missing=[], tools=[],
                           error="ModuleNotFoundError: No module named 'check'",
                           manifest={"description": {"en": "Patent filings for projects"}})
    waiting = SimpleNamespace(name="weather", enabled=True, available=False, missing=["AURORA_WEATHER_LAT"], tools=[],
                              error="", manifest={"description": {"en": "The weather"}})
    agent.host = SimpleNamespace(plugins=lambda **k: [down, waiting])
    text = agent._waiting()
    assert "Installed, not starting" in text and "- patent: Patent filings" in text and "No module named" in text
    assert "waiting for the owner's settings" in text and "AURORA_WEATHER_LAT" in text


def test_the_same_read_a_third_time_is_not_made_again(cfg):
    # C313: a routine read the same sockets 8 times
    same = call("demo__read_log", component="api")
    llm = FakeLLM([same, same, same, same, call("finish", summary="Fatto.")])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    ans = agent.run("prova", lambda e, p: None, "run1")
    assert len(agent.host.calls) == 2 and "Fatto." in ans.text


def test_the_system_prompt_holds_nothing_of_the_moment():
    """The tools' ~45k tokens are read back from the cloud's prompt cache run after run only if the prompt before them
    is the same: «NOW» moved into the goal's message (16 Oct: a week wrote 35.5M tokens to the cache, read 5.5M)."""
    import inspect
    spec = {"type": "function", "function": {"name": "x", "description": "d", "parameters": {"type": "object"}}}
    assert Agent._system(object(), [spec]) == Agent._system(object(), [spec])
    assert "NOW:" not in Agent._system(object(), [spec]) and 'f"NOW: {sns_clock.now_text' in inspect.getsource(Agent.run)


def test_an_announced_write_with_no_call_is_asked_again(cfg):
    # C397: «I will now write paper.md» with no tool call ended the phase as its report, the file never written
    llm = FakeLLM(["Ora scrivo il file.", call("finish", summary="Fatto.")])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    events = []
    agent.run("Write the document `docs/paper/paper.md` from the notes", lambda e, p: events.append((e, p)), "run10")
    nudges = [p for e, p in events if e == "agent.nudge"]
    assert nudges and nudges[0]["reason"] == "file not written" and nudges[0]["paths"] == ["docs/paper/paper.md"]
    assert unwritten("Write the file `a.md`", {("p", "a.md")}) == []                  # written: nothing owed


def test_an_edited_file_counts_as_written(cfg):
    # C399: nine edits of paper.md, then «not written», then the model wrote a copy of the paper under another name
    edit = "<tool_call>\n" + json.dumps({"name": "demo__project_edit_file", "arguments": {
        "name": "p", "path": "docs/paper/paper.md", "old": "a", "new": "b"}}) + "\n</tool_call>"
    llm = FakeLLM([edit,
                   "Fatto: modificato."])
    agent = Agent(fake_pipeline(llm), cfg)
    agent.host = FakeHost()
    events = []
    agent.run("Write the document `docs/paper/paper.md` with the fixes", lambda e, p: events.append((e, p)), "run11")
    assert ("p", "docs/paper/paper.md") in agent.touched
    assert not [p for e, p in events if e == "agent.nudge" and p.get("reason") == "file not written"]
