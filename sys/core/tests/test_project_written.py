# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C384: the run's «file scritti» counted only the write tool's files; the files written by the commands run in the
project (run_in_project) count too, each file once, and the folders a command fills by itself are left out."""
import json
import os
from types import SimpleNamespace

from aurora import prj_run
from aurora.agt_loop import Agent


def test_snapshot_sees_new_and_changed_files_not_the_tool_folders(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "keep.txt").write_text("k")
    before = prj_run.snapshot(tmp_path)
    (tmp_path / "a.py").write_text("x = 22\n")
    os.utime(tmp_path / "a.py", ns=(before["a.py"][0] + 10**9, before["a.py"][0] + 10**9))
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "result.csv").write_text("1,2\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "a.pyc").write_bytes(b"\0")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "index").write_bytes(b"\0")
    assert prj_run.changed(before, prj_run.snapshot(tmp_path)) == ["a.py", "out/result.csv"]


def call(name, **args):
    return "<tool_call>\n" + json.dumps({"name": name, "arguments": args}) + "\n</tool_call>"


class LLM:
    def __init__(self, turns):
        self.turns = list(turns)

    def complete_turns(self, messages, max_tokens, think=False):
        return SimpleNamespace(answer=self.turns.pop(0), thought="", truncated=False)


def test_the_record_counts_the_files_the_commands_wrote(cfg, monkeypatch):
    monkeypatch.setattr(prj_run, "run", lambda cfg, name, command: {
        "exit": 0, "seconds": 0.1, "output": "ok", "changed": ["out/a.csv", "out/b.csv", "src/gen.py"]})
    llm = LLM([call("run_in_project", project="demo", command="python src/gen.py"),
               call("finish", summary="Generati i dati.")])
    agent = Agent(SimpleNamespace(llm=llm, _for=lambda role: llm), cfg)
    agent.host = SimpleNamespace(plugins=lambda: [], get=lambda p: None)
    agent.notify = lambda *a, **k: None
    ans = agent.run("lavora a demo", lambda e, p: None, "r1")
    assert "3 file scritti nei progetti" in ans.text
    agent.touched.add(("demo", "src/gen.py"))                 # the write tool's file, written again by a command: once
    agent.ledger.append(("projects__project_write_file", True))
    assert "3 file scritti nei progetti" in agent._record()


def test_run_in_project_takes_the_name_as_the_project_tools_call_it(cfg, monkeypatch):
    # C392: the local model wrote «name» (as projects__project_* want it); the run refused a valid project name
    seen = []
    monkeypatch.setattr(prj_run, "run", lambda cfg, name, command: seen.append(name) or {
        "exit": 0, "seconds": 0.1, "output": "ok", "changed": []})
    raw = "<tool_call>\n" + json.dumps({"name": "run_in_project", "arguments": {
        "name": "elica-chirale", "command": "python -m pytest -q tests"}}) + "\n</tool_call>"
    llm = LLM([raw,
               call("finish", summary="Test passati.")])
    agent = Agent(SimpleNamespace(llm=llm, _for=lambda role: llm), cfg)
    agent.host = SimpleNamespace(plugins=lambda: [], get=lambda p: None)
    agent.notify = lambda *a, **k: None
    agent.run("lavora a elica-chirale", lambda e, p: None, "r1")
    assert seen == ["elica-chirale"]


def test_a_run_without_its_report_says_what_the_record_shows(cfg, monkeypatch):
    # C393: the local phase ran its commands and wrote files, its report came out empty, the judge read «nothing done»
    monkeypatch.setattr(prj_run, "run", lambda cfg, name, command: {
        "exit": 0, "seconds": 9.0, "output": "ok", "changed": ["docs/22_dot.md"]})
    llm = LLM([call("run_in_project", project="demo", command="python src/esperimento.py dot p=2"),
               call("finish", summary=""), ""])
    agent = Agent(SimpleNamespace(llm=llm, _for=lambda role: llm), cfg)
    agent.host = SimpleNamespace(plugins=lambda: [], get=lambda p: None)
    agent.notify = lambda *a, **k: None
    ans = agent.run("lavora a demo", lambda e, p: None, "r1")
    assert "Nessun resoconto prodotto" not in ans.text
    assert "`python src/esperimento.py dot p=2` → exit 0 in 9.0 s" in ans.text and "demo/docs/22_dot.md" in ans.text
