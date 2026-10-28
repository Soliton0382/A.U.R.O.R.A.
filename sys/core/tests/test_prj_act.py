# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The conductor acts (prj_act, N39 step 3): its tools stay inside the project (no «..», no .git written), an edit
needs a unique anchor, what goes back to the cloud is masked and long prose compressed by SSCC, what comes from it is
unmasked before it is written; the CLI is started with its own tools off and Aurora's relay as its only MCP server;
a whole turn with a stand-in CLI ends as the conversation's next turn, the steps kept, «working» cleared. The relay
speaks MCP. No real CLI is run."""
import json
import sys
import time

import pytest

from aurora import prj_act as A
from aurora import prj_talk as T
from aurora import sys_seal
from aurora.sec_mask import Pseudonymizer


@pytest.fixture
def run(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "motore"
    (p / "docs").mkdir(parents=True)
    (p / "docs" / "DA_FARE.md").write_text("- [ ] misurare la coppia\n", encoding="utf-8")
    (p / "calc.py").write_text("K = 2\nK2 = 2\n", encoding="utf-8")
    (p / ".git").mkdir()
    r = A.Run(cfg, "motore", Pseudonymizer(cfg), "misura la coppia")
    with A._lock:
        A._RUNS[r.token] = r
    yield r
    A._RUNS.pop(r.token, None)


def test_the_tools_stay_in_the_project_and_obey_the_anchor(run):
    assert "calc.py" in A.call(run, "list_files", {})["text"]
    for bad in ({"path": "../../etc/passwd"}, {"path": "/etc/passwd"}):
        assert A.call(run, "read_file", bad)["error"]
    assert A.call(run, "write_file", {"path": ".git/config", "content": "x"})["error"]
    assert "REFUSED" in A.call(run, "edit_file", {"path": "calc.py", "old": "= 2", "new": "= 3"})["text"]   # twice
    assert not A.call(run, "edit_file", {"path": "calc.py", "old": "K = 2", "new": "K = 3"})["error"]
    assert "1\tK = 3" in A.call(run, "read_file", {"path": "calc.py"})["text"]
    assert "misurare la coppia" in A.call(run, "project_notes", {})["text"]
    steps = A.working(run.cfg, "motore") or json.loads(sys_seal.read_any(run.cfg, A._state(run.cfg, "motore"), run.cfg.user))
    assert any(s["text"].startswith("✗ read_file") for s in steps["steps"])


def test_masked_out_unmasked_in(run):
    p = A.prj_run.project_dir(run.cfg, "motore") / "contatti.txt"
    p.write_text("scrivere a mario.rossi@example.com\n", encoding="utf-8")
    out = A.call(run, "read_file", {"path": "contatti.txt"})["text"]
    assert "example.com" not in out and "[EMAIL_1]" in out
    A.call(run, "write_file", {"path": "copia.txt", "content": "per [EMAIL_1]"})          # the cloud's placeholder
    assert (p.parent / "copia.txt").read_text(encoding="utf-8") == "per mario.rossi@example.com"


def test_sscc_on_long_prose_only_when_on(run):
    text = " ".join(f"Frase numero {i} sulla coppia del motore e altro." for i in range(400))
    run.cfg.values["AURORA_CLOUD_COMPRESSION"] = True
    assert len(A._prose(run, text)) < len(text)
    run.cfg.values["AURORA_CLOUD_COMPRESSION"] = False
    assert A._prose(run, text) == text and A._prose(run, "corto") == "corto"


def test_the_cli_has_only_aurora_s_tools(run):
    cc = type("CC", (), {"bin": "claude", "model": "opus"})()
    cmd = A._command(run, cc, "/s.txt", "/m.json", "sid", False)
    assert cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--mcp-config") + 1] == "/m.json" and cmd[cmd.index("--session-id") + 1] == "sid"
    allowed = cmd[cmd.index("--allowedTools") + 1].split(",")
    assert allowed and all(a.startswith("mcp__aurora__") for a in allowed) and "--max-budget-usd" in cmd
    assert A.lookup(run.token) is run and A.lookup("nope") is None and A.lookup("") is None


FAKE_CLI = r'''#!/bin/sh
cat > /dev/null
echo '{"type":"assistant","message":{"content":[{"type":"text","text":"Leggo le note di [EMAIL_1]"}]}}'
echo '{"type":"result","is_error":false,"result":"**Fatto** scritto a [EMAIL_1]","session_id":"s-1","total_cost_usd":0.5,"usage":{"input_tokens":3,"output_tokens":4}}'
'''


def test_a_whole_turn_with_a_stand_in_cli(cfg, run, tmp_path):
    fake = tmp_path / "claude"
    fake.write_text(FAKE_CLI)
    fake.chmod(0o755)
    cc = type("CC", (), {"bin": str(fake), "model": "opus", "name": "claude_code", "_env": lambda self, n: {"PATH": "/usr/bin:/bin"},
                         "_account": lambda self, d, s: None})()
    run.mask.mask("mario.rossi@example.com")                                                 # the session's map
    A._RUNS.pop(run.token)
    out = A.start(cfg, "motore", cc, "scrivi a mario.rossi@example.com", "sistema", {"mask": run.mask.to_val}, "it")
    assert out == {"working": True}
    for _ in range(100):
        if not A.working(cfg, "motore"):
            break
        time.sleep(0.05)
    last = T.turns(cfg, "motore")[-1]
    assert last["role"] == "conductor" and last["acted"] and last["text"] == "**Fatto** scritto a mario.rossi@example.com"
    assert last["cost_usd"] == 0.5 and T.session(cfg, "motore")["session"] == "s-1"
    steps = json.loads(sys_seal.read_any(cfg, A._state(cfg, "motore"), cfg.user))["steps"]   # sealed (N64)
    assert steps[-1]["text"] == "✻ Leggo le note di mario.rossi@example.com" and not A._RUNS


def test_the_relay_speaks_mcp(monkeypatch):
    sys.path.insert(0, str(A.Path(A.__file__).resolve().parent.parent / "script"))
    import mcp_relay as R
    monkeypatch.setattr(R, "api", lambda path, body=None: {"tools": A.TOOLS} if path == "/tools" else {"text": "ok", "error": False})
    init = R.answer({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
    assert init["result"]["serverInfo"]["name"] == "aurora" and R.answer({"method": "notifications/initialized"}) is None
    assert [t["name"] for t in R.answer({"id": 2, "method": "tools/list"})["result"]["tools"]] == [t["name"] for t in A.TOOLS]
    r = R.answer({"id": 3, "method": "tools/call", "params": {"name": "run", "arguments": {"command": "pytest"}}})
    assert r["result"] == {"content": [{"type": "text", "text": "ok"}], "isError": False}


RESUME_FAILS = r'''#!/bin/sh
cat > /dev/null
case " $* " in
  *" --resume "*) echo '{"type":"result","is_error":true,"subtype":"error_during_execution","result":""}' ;;
  *) echo '{"type":"result","is_error":false,"result":"fatto","session_id":"new-1","total_cost_usd":0.01,"usage":{}}' ;;
esac
'''


def test_a_session_of_another_login_starts_again(cfg, run, tmp_path):
    """U6, 28 Oct: after the services moved to their own account the old session (the owner's login) could not be
    resumed («error_during_execution»): a new session, said as such."""
    fake = tmp_path / "claude"
    fake.write_text(RESUME_FAILS)
    fake.chmod(0o755)
    cc = type("CC", (), {"bin": str(fake), "model": "opus", "name": "claude_code", "_env": lambda self, n: {"PATH": "/usr/bin:/bin"},
                         "_account": lambda self, d, s: None})()
    A._RUNS.pop(run.token)
    A.start(cfg, "motore", cc, "ancora", "sistema", {"session": "old-session"}, "it")
    for _ in range(100):
        if not A.working(cfg, "motore"):
            break
        time.sleep(0.05)
    last = T.turns(cfg, "motore")[-1]
    assert last["text"] == "fatto" and last["new_session"] and T.session(cfg, "motore")["session"] == "new-1"
