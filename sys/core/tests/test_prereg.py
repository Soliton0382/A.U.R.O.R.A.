# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔒 Frozen predictions (prj_prereg, N142): a freeze writes the predictions and hashes them with their code; a close
re-hashes — intact, or «changed after freeze» with its «passed» not counted; nothing under prereg/ is written by a
tool (the conductor's, the agent's plugin); the ledger kept by Aurora outside the project catches a hand edit; the
draft carries the rule unless the mode is off; a phase that ran commands and froze nothing is said in the reply;
strict mode refuses a command before a freeze. An invented project in tmp_path; no CLI, no cage needed."""
import hashlib
import json
import time
from types import SimpleNamespace

import pytest

from aurora import prj_act as A
from aurora import prj_conduct as C
from aurora import prj_policy
from aurora import prj_prereg as P
from aurora.sec_mask import Pseudonymizer


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "pendolo"
    (p / "docs").mkdir(parents=True)
    (p / "sim.py").write_text("G = 9.81\nL = 1.0\n", encoding="utf-8")
    (p / "risultati.txt").write_text("T = 2.006 s\n", encoding="utf-8")
    return p


PRED = [{"id": "P1", "text": "il periodo per L = 1 m sta fra 2.00 e 2.01 s"},
        {"id": "P2", "text": "raddoppiando L il periodo cresce di un fattore 1.41 ± 0.01"}]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_freeze_writes_and_hashes(cfg, proj):
    e = P.freeze(cfg, "pendolo", "Periodo del pendolo", PRED, ["sim.py"])
    f = proj / e["file"]
    assert e["id"] == "001" and e["file"] == "prereg/001_periodo-del-pendolo.md" and f.is_file()
    assert e["sha256"] == sha(f) and e["code"] == {"sim.py": sha(proj / "sim.py")} and e["status"] == "open"
    assert "**P1**" in f.read_text() and "Frozen (UTC):" in f.read_text()
    line = json.loads((proj / "prereg" / "LEDGER.jsonl").read_text().splitlines()[0])
    assert line["event"] == "freeze" and line["sha256"] == e["sha256"] and P.ledger_intact(cfg, "pendolo")
    assert P.freeze(cfg, "pendolo", "Secondo", PRED[:1], [])["id"] == "002"


def test_bad_freezes_are_refused(cfg, proj):
    dup = [{"id": "P1", "text": "a"}, {"id": "P1", "text": "b"}]
    assert "duplicate" in P.tool(cfg, "pendolo", "freeze_predictions", {"title": "x", "predictions": dup, "code_files": []})
    for files in (["manca.py"], ["../fuori.py"], ["/etc/passwd"]):
        out = P.tool(cfg, "pendolo", "freeze_predictions", {"title": "x", "predictions": PRED, "code_files": files})
        assert out.startswith("REFUSED"), files
    assert not P.entries(cfg, "pendolo")


def test_close_intact_counts_the_outcomes(cfg, proj):
    e = P.freeze(cfg, "pendolo", "Periodo", PRED, ["sim.py"])
    out = P.tool(cfg, "pendolo", "close_predictions", {"id": e["id"], "evidence": "risultati.txt", "outcomes": [
        {"id": "P1", "outcome": "passed", "value": "2.006 s"}, {"id": "P2", "outcome": "failed", "value": "1.38"}]})
    assert "integrity intact" in out and "P2 (1.38)" in out and "WARNING" not in out
    got = P.entries(cfg, "pendolo")[0]
    assert got["status"] == "closed" and got["integrity"] == "intact"
    assert got["counted"] == {"passed": 1, "failed": 1, "void": 0} and got["evidence"] == "risultati.txt"
    assert "closed already" in P.tool(cfg, "pendolo", "close_predictions", {"id": e["id"], "evidence": "risultati.txt",
                                                                           "outcomes": []})


def test_an_outcome_per_prediction(cfg, proj):
    e = P.freeze(cfg, "pendolo", "Periodo", PRED, ["sim.py"])
    out = P.tool(cfg, "pendolo", "close_predictions", {"id": e["id"], "evidence": "risultati.txt",
                                                        "outcomes": [{"id": "P1", "outcome": "passed"}]})
    assert out.startswith("REFUSED") and "missing: P2" in out and P.entries(cfg, "pendolo")[0]["status"] == "open"


def test_code_changed_after_freeze_is_flagged_and_not_counted(cfg, proj):
    e = P.freeze(cfg, "pendolo", "Periodo", PRED, ["sim.py"])
    (proj / "sim.py").write_text("G = 9.81\nL = 1.0  # retuned\n", encoding="utf-8")   # a shell write in the cage
    out = P.tool(cfg, "pendolo", "close_predictions", {"id": e["id"], "evidence": "risultati.txt", "outcomes": [
        {"id": "P1", "outcome": "passed"}, {"id": "P2", "outcome": "passed"}]})
    assert "changed after freeze: sim.py" in out and "do not count" in out
    got = P.entries(cfg, "pendolo")[0]
    assert got["integrity"] == "changed after freeze" and got["changed"] == ["sim.py"]
    assert got["counted"]["passed"] == 0 and got["counted"]["not_counted"] == 2
    assert "0 (2 not counted)" in P.table(cfg, "pendolo")
    assert "2 passed NOT counted" in P.balance(cfg, "pendolo")


def test_nothing_under_prereg_is_written_by_a_tool(cfg, proj):
    P.freeze(cfg, "pendolo", "Periodo", PRED, ["sim.py"])
    run = A.Run(cfg, "pendolo", Pseudonymizer(cfg), "periodo")
    for args in ({"path": "prereg/001_periodo.md", "content": "x"}, {"path": "./docs/../prereg/nuovo.md", "content": "x"},
                 {"path": "reviews/REV_001.md", "content": "ACCEPT"}):
        assert A.call(run, "write_file", args)["text"].startswith("REFUSED")
    assert A.call(run, "edit_file", {"path": "prereg/LEDGER.jsonl", "old": "open", "new": "closed"})["text"].startswith("REFUSED")
    assert not (proj / "prereg" / "nuovo.md").exists() and not (proj / "reviews").exists()
    agent = SimpleNamespace(cfg=cfg, local_only=False)
    refused = prj_policy.guard(agent, "projects", "project_write_file", {"name": "pendolo", "path": "prereg/x.md"}, None)
    assert refused.startswith("REFUSED")
    assert prj_policy.guard(agent, "projects", "project_write_file", {"name": "pendolo", "path": "docs/x.md"}, None) == ""


def test_a_hand_edit_of_the_ledger_is_said(cfg, proj):
    P.freeze(cfg, "pendolo", "Periodo", PRED, ["sim.py"])
    (proj / "prereg" / "LEDGER.jsonl").write_text("", encoding="utf-8")         # wiped from a shell
    assert not P.ledger_intact(cfg, "pendolo") and P.entries(cfg, "pendolo")       # Aurora's copy still has it
    assert "changed by hand" in P.table(cfg, "pendolo")


def test_the_ledger_table(cfg, proj):
    assert P.tool(cfg, "pendolo", "predictions_ledger", {}) == "(no frozen predictions)"
    P.freeze(cfg, "pendolo", "Periodo", PRED, ["sim.py"])
    t = P.tool(cfg, "pendolo", "predictions_ledger", {})
    assert t.splitlines()[0].startswith("| id | title | status") and "| 001 | Periodo | open |" in t


def test_the_draft_carries_the_rule_unless_off(cfg, proj):
    assert P.mode(cfg) == "warn"
    assert "freeze_predictions" in C.draft_system(cfg, "pendolo", "masked cloud allowed")
    assert "report every failed prediction" in C.draft_system(cfg, "pendolo", "x")
    cfg.values["AURORA_PREREG_MODE"] = "off"
    assert "freeze_predictions" not in C.draft_system(cfg, "pendolo", "x") and P.rule(cfg) == ""
    assert P.offered(cfg, "goal with freeze_predictions") == []


class _LLM:
    def __init__(self):
        self.seen = []

    def complete(self, system, user, max_tokens, think=False):
        self.seen.append((system, user))
        return SimpleNamespace(answer="1. Fatto.")


def test_the_reply_says_commands_ran_without_freezing(cfg, proj):
    since, llm = time.time() - 5, _LLM()
    r = C.review(cfg, "pendolo", "misura il periodo", "Tutto verificato.", llm, "it", commands=3, since=since)
    assert "nessuna previsione congelata" in r["text"] and "**Non regge**" in r["text"]
    assert "frozen predictions (prereg/, read by Aurora): none in this phase" in llm.seen[0][1]
    P.freeze(cfg, "pendolo", "Periodo", PRED, ["sim.py"])
    r = C.review(cfg, "pendolo", "misura il periodo", "Tutto verificato.", _LLM(), "it", commands=3, since=since)
    assert "nessuna previsione congelata" not in r["text"]
    assert "nessuna previsione" not in C.review(cfg, "pendolo", "g", "r", _LLM(), "it", commands=0, since=since)["text"]


def test_strict_refuses_a_command_before_a_freeze(cfg, proj):
    cfg.values["AURORA_PREREG_MODE"] = "strict"
    run = A.Run(cfg, "pendolo", Pseudonymizer(cfg), "periodo")
    assert "strict" in A.call(run, "run", {"command": "python sim.py"})["text"]
    A.call(run, "freeze_predictions", {"title": "Periodo", "predictions": PRED, "code_files": ["sim.py"]})
    assert run.frozen == {"pendolo"} and P.strict_refusal(cfg, "pendolo", run.frozen) == ""


def test_the_cloud_s_placeholders_are_unmasked_in_the_frozen_file(cfg, proj):
    run = A.Run(cfg, "pendolo", Pseudonymizer(cfg), "periodo")
    run.mask.mask("misura di laura.bianchi@example.com")                     # the session's map: [EMAIL_1]
    ph = next(iter(run.mask.to_val))
    A.call(run, "freeze_predictions", {"title": "Periodo", "code_files": ["sim.py"],
                                       "predictions": [{"id": "P1", "text": f"confermato da {ph}"}]})
    text = (proj / P.entries(cfg, "pendolo")[0]["file"]).read_text()
    assert "laura.bianchi@example.com" in text and ph not in text


def test_the_agent_gets_the_tools_only_in_a_phase(cfg, proj):
    assert P.offered(cfg, "che tempo fa domani?") == []
    tools = P.offered(cfg, "goal\n" + P.rule(cfg))
    assert [t["name"] for t in tools] == ["freeze_predictions", "close_predictions", "predictions_ledger"]
    assert all(t["input_schema"]["required"][0] == "project" for t in tools)
    agent = SimpleNamespace(cfg=cfg, projects=set())
    out = P.agent_call(agent, "freeze_predictions", {"project": "pendolo", "title": "Periodo", "predictions": PRED,
                                                     "code_files": ["sim.py"]})
    assert out.startswith("FROZEN 001") and agent.prereg_frozen == {"pendolo"} and agent.projects == {"pendolo"}
