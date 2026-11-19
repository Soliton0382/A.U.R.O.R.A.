# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧑‍⚖️ The severe referee (prj_referee, N142): it reads the goal, the changed files, the documents and the frozen
predictions — never the agent's report nor the talk; its tools are read only (no write tool, a read-only cage);
Aurora writes reviews/REV_NNN.md and the conductor's reply starts with its verdict; a «local» project gets none,
said; a review past its spending ceiling stops, said. A stand-in CLI; the real one is never run."""
import shutil
import subprocess
import time
from types import SimpleNamespace

import pytest

from aurora import prj_act as A
from aurora import prj_conduct as C
from aurora import prj_policy, prj_prereg, prj_run
from aurora import prj_referee as R
from aurora import prj_talk as T
from aurora.sec_mask import Pseudonymizer

REPORT = "RAPPORTO-DELL-AGENTE: tutto verificato, nessun problema"
TALK = "PAROLE-DEL-PROPRIETARIO nella conversazione"


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "molla"
    (p / "docs").mkdir(parents=True)
    (p / "molla.py").write_text("k = 120.0  # N/m\n", encoding="utf-8")
    since = time.time() - 1
    (p / "docs" / "03_rigidezza.md").write_text("# 03 — Rigidezza\n\nLa costante misurata è k = 120 N/m.\n",
                                                encoding="utf-8")
    prj_prereg.freeze(cfg, "molla", "Rigidezza", [{"id": "P1", "text": "k fra 115 e 125 N/m"}], ["molla.py"])
    C.add(cfg, "molla", "reply", REPORT)                       # what the conductor's history holds
    T._add(cfg, "molla", "owner", TALK)                       # and the talk
    return p, since


def test_the_input_holds_the_work_not_what_was_said_of_it(cfg, proj):
    _, since = proj
    text = R.inputs(cfg, "molla", "Misura la rigidezza della molla", since)
    assert "Misura la rigidezza" in text and "docs/03_rigidezza.md" in text and "k = 120 N/m" in text
    assert "molla.py" in text and '"id": "001"' in text and "k fra 115 e 125 N/m" in text
    assert REPORT not in text and TALK not in text and "prereg/LEDGER" not in text.split("## Frozen")[0]


def test_the_referee_cannot_write(cfg, proj):
    names = {t["name"] for t in R.TOOLS}
    assert names == {"list_files", "read_file", "search_vault", "run", "proof_check",   # proof_check: N143, read only
                     "long_run", "novelty_check"}   # N145 status/list only, N146 no report file (their tests)
    run = A.Run(cfg, "molla", Pseudonymizer(cfg), "g")
    run.tools, run.readonly, run.notes = R.TOOLS, True, False
    out = A.call(run, "write_file", {"path": "docs/x.md", "content": "x"})
    assert out["error"] and "not one of this run's tools" in out["text"]
    assert not (proj[0] / "docs" / "x.md").exists()
    cmd = A._command(run, SimpleNamespace(bin="claude", model="opus"), "/s", "/m", "sid", False, model="sonnet",
                     max_usd=2, persist=False)
    allowed = cmd[cmd.index("--allowedTools") + 1].split(",")
    assert "mcp__aurora__write_file" not in allowed and "mcp__aurora__freeze_predictions" not in allowed
    assert cmd[cmd.index("--model") + 1] == "sonnet" and "--no-session-persistence" in cmd and "--session-id" not in cmd
    assert cmd[cmd.index("--max-budget-usd") + 1] == "2"


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bubblewrap not installed")
def test_the_read_only_cage_cannot_write(cfg, proj):
    if subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"], capture_output=True).returncode:
        pytest.skip("bwrap cannot make a namespace here")
    r = prj_run.run(cfg, "molla", "echo x > scritto.txt", readonly=True)
    assert r["exit"] != 0 and not (proj[0] / "scritto.txt").exists() and r["changed"] == []
    r = prj_run.run(cfg, "molla", "echo 7 > /tmp/s && cat /tmp/s && cat molla.py", readonly=True)
    assert r["exit"] == 0 and "7" in r["output"] and "k = 120.0" in r["output"]


def test_the_referee_model_is_never_the_conductor_s(cfg):
    assert R.model_for(cfg, "opus") == "sonnet"
    assert R.model_for(cfg, "sonnet") == "opus"
    cfg.values["AURORA_REFEREE_MODEL"] = "haiku"
    assert R.model_for(cfg, "opus") == "haiku"


def test_a_local_project_gets_no_cloud_referee(cfg, proj):
    prj_policy.save(cfg, "molla", {"models": "local", "publish": False})
    out = R.phase(cfg, "molla", "g", proj[1], pipeline=None, lang="it")
    assert out["status"] == "skipped" and "revisione severa non eseguita: progetto locale" in out["summary"].lower()
    cfg.values["AURORA_REFEREE_ENABLED"] = False
    assert R.phase(cfg, "molla", "g", proj[1], pipeline=None) is None


def test_no_cli_no_referee_said(cfg, proj, monkeypatch):
    monkeypatch.setattr(T, "backend", lambda cfg, project, pipeline: ("cloud", object()))
    out = R.phase(cfg, "molla", "g", proj[1], pipeline=None, lang="it")
    assert out["status"] == "skipped" and "CLI di Claude" in out["summary"]


def _cli(tmp_path, result: str):
    seen = tmp_path / "stdin.txt"
    fake = tmp_path / "claude"
    fake.write_text(f"#!/bin/sh\necho \"$@\" > {tmp_path}/args.txt\ncat > {seen}\nprintf '%s\\n' '{result}'\n")
    fake.chmod(0o755)
    cc = type("CC", (), {"bin": str(fake), "model": "opus", "name": "claude_code",
                         "_env": lambda self, n: {"PATH": "/usr/bin:/bin"}, "_account": lambda self, d, s: None})()
    return cc, seen


DONE = ('{"type":"result","is_error":false,"total_cost_usd":0.31,"result":"VERDICT: MAJOR REVISION — FATAL 0, '
        'MAJOR 1, MINOR 0, OK 1\\nRevisore IA.\\n| 1 | k = 120 N/m | docs/03 | MAJOR | not measured |"}')


def test_a_review_is_written_by_aurora_and_leads_the_reply(cfg, proj, tmp_path):
    cc, seen = _cli(tmp_path, DONE)
    ref = R.review(cfg, "molla", "Misura la rigidezza", proj[1], cc, "it")
    assert ref["status"] == "done" and ref["verdict"].startswith("VERDICT: MAJOR REVISION") and ref["cost_usd"] == 0.31
    f = proj[0] / ref["file"]
    assert ref["file"] == "reviews/REV_001.md" and "an AI reviewer" in f.read_text() and "| MAJOR |" in f.read_text()
    sent = seen.read_text()
    assert "k = 120 N/m" in sent and REPORT not in sent and TALK not in sent             # what reached the CLI
    args = (tmp_path / "args.txt").read_text()
    assert "--model sonnet" in args and "--no-session-persistence" in args
    listed = R.reviews(cfg, "molla")
    assert listed[0]["verdict"] == ref["verdict"] and listed[0]["status"] == "done" and listed[0]["seconds"] >= 0
    assert ref["summary"].startswith("🧑‍⚖️ **Revisione severa** (revisore IA, sonnet): VERDICT: MAJOR REVISION")
    llm = SimpleNamespace(seen=[])
    llm.complete = lambda s, u, n, think=False: llm.seen.append(u) or SimpleNamespace(answer="1. Fatto.")
    r = C.review(cfg, "molla", "Misura la rigidezza", REPORT, llm, "it", commands=1, since=proj[1], referee=ref)
    assert r["text"].startswith(ref["summary"]) and r["review"] == "reviews/REV_001.md"
    assert "severe referee's review" in llm.seen[0] and "001 open" in llm.seen[0]
    assert not A._RUNS


def test_over_budget_the_review_stops_and_says_so(cfg, proj, tmp_path):
    cc, _ = _cli(tmp_path, '{"type":"result","is_error":true,"subtype":"error_max_budget_usd","total_cost_usd":2.4}')
    ref = R.review(cfg, "molla", "Misura la rigidezza", proj[1], cc, "it")
    assert ref["status"] == "stopped" and "tetto di spesa" in ref["summary"] and "AURORA_REFEREE_MAX_USD" in ref["summary"]
    assert ref["text"] == "" and (proj[0] / ref["file"]).is_file()
    assert R.reviews(cfg, "molla")[0]["status"] == "stopped"
