# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Talking with a project's conductor (prj_talk, N39 step 2): on the Claude CLI one session per project, started with
--session-id and resumed with --resume, no tools and nothing unmasked, the same placeholder in every turn and the
answer unmasked; the cost said; a «local» project never reaches the CLI; the local model gets the stored turns again;
a new conversation sets the old one aside; a failure is kept as the answer, said as such. No real CLI is run."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from aurora import mdl_router, prj_policy
from aurora import prj_talk as T


class _Local:
    name = "local"

    def __init__(self):
        self.seen = []

    def complete_turns(self, messages, max_tokens, think=False):
        self.seen.append(messages)
        return SimpleNamespace(answer=f"risposta {len(self.seen)}", tokens=7)


class _CLI:
    name, model, bin = "claude_code", "sonnet", "/fake/claude"

    def _env(self, max_tokens):
        return {}

    def _account(self, d, seconds):
        pass


@pytest.fixture
def project(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "motore"
    (p / "docs").mkdir(parents=True)
    (p / "docs" / "DA_FARE.md").write_text("- [ ] misurare la coppia\n", encoding="utf-8")
    return "motore"


def _pipe(cfg, cli=True):
    local = _Local()
    agent = mdl_router.Fallback(mdl_router.MaskedLLM(_CLI(), "agent", cfg), local, "agent", cfg, "claude_code") \
        if cli else local
    return SimpleNamespace(llm=local, _for=lambda role: agent)


@pytest.fixture
def cli_runs(monkeypatch):
    calls = []

    def run(cmd, input, **kw):
        calls.append((cmd, input, kw))
        sid = cmd[cmd.index("--resume") + 1] if "--resume" in cmd else cmd[cmd.index("--session-id") + 1]
        out = {"type": "result", "is_error": False, "result": "Scrivo a [EMAIL_1] come chiesto.", "session_id": sid,
               "total_cost_usd": 0.0123, "usage": {"input_tokens": 10, "output_tokens": 5}}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(out), "")
    monkeypatch.setattr(T.subprocess, "run", run)
    return calls


def test_one_cli_session_resumed_masked_and_without_tools(cfg, project, cli_runs):
    p = _pipe(cfg)
    a = T.say(cfg, project, "scrivi a mario.rossi@example.com", p)
    b = T.say(cfg, project, "e di nuovo a mario.rossi@example.com", p)
    (c1, in1, kw1), (c2, in2, _) = cli_runs
    assert "--session-id" in c1 and "--resume" not in c1 and "--resume" in c2
    sid = c1[c1.index("--session-id") + 1]
    assert c2[c2.index("--resume") + 1] == sid == T.session(cfg, project)["session"]
    for c in (c1, c2):
        assert c[c.index("--tools") + 1] == "" and "--strict-mcp-config" in c and "--no-session-persistence" not in c
    assert "example.com" not in in1 + in2 and "[EMAIL_1]" in in1 and "[EMAIL_1]" in in2      # the same placeholder
    assert kw1["cwd"].name == project and not any(kw1["cwd"].iterdir())                       # an empty folder
    assert a["text"] == "Scrivo a mario.rossi@example.com come chiesto." and a["backend"] == "cli"
    assert a["cost_usd"] == 0.0123 and a["new_session"] and not b["new_session"]
    assert [e["role"] for e in T.turns(cfg, project)] == ["owner", "conductor", "owner", "conductor"]


def test_a_local_project_never_reaches_the_cli(cfg, project, cli_runs):
    prj_policy.save(cfg, project, {"models": "local", "publish": False})
    p = _pipe(cfg)
    T.say(cfg, project, "prima", p)
    out = T.say(cfg, project, "seconda", p)
    assert not cli_runs and out["backend"] == "local" and out["cost_usd"] is None
    sent = p.llm.seen[-1]
    assert sent[0]["role"] == "system" and "motore" in sent[0]["content"]
    assert [m["content"] for m in sent[1:]] == ["prima", "risposta 1", "seconda"]                # the turns again


def test_a_new_conversation_and_a_failure(cfg, project, monkeypatch):
    p = _pipe(cfg)

    def boom(cmd, input, **kw):
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"is_error": True, "result": "session limit"}), "")
    monkeypatch.setattr(T.subprocess, "run", boom)
    out = T.say(cfg, project, "ciao", p)
    assert out["error"] and "session limit" in out["text"]
    T.new(cfg, project)
    assert T.turns(cfg, project) == [] and T.session(cfg, project) == {}
    assert list(T._dir(cfg, project).glob("talk-*.jsonl"))
    with pytest.raises(ValueError):
        T.turns(cfg, "../fuori")
