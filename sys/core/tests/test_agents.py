# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import json
from types import SimpleNamespace

from aurora import agt_change
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
    short = [t.endswith("[shortened: an older result]") for t in tools]
    assert any(short) and short == sorted(short, reverse=True)          # only the oldest, as few as needed
    assert all(len(t) == 3000 for t in tools[-4:])                      # the latest four stay whole
    assert room >= 1000


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
