# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A terminal in a project's cage (roadmap 75): no network, only the project's folder, input works, closed when idle."""
import shutil
import time

import pytest

from aurora import prj_term as T



def until(sid, user, text, after=0, limit=15):
    out, end = "", time.time() + limit
    while text not in out and time.time() < end:
        items, _ = T.chunks(sid, user, after, 2)
        for n, d in items:
            out, after = out + d, n
    return out.replace("\r", ""), after


def test_the_cage_has_no_network_and_a_program_can_ask(cfg):
    if not shutil.which("bwrap"):
        pytest.skip("bubblewrap not here")
    proj = cfg.path("AURORA_PROJECTS_DIR") / "demo"
    proj.mkdir(parents=True)
    (proj / "ask.py").write_text("n = input('nome? ')\nprint('ciao', n)\n")
    sid = T.start(cfg, "demo", "u1")["id"]
    try:
        T.write(sid, "u1", "python -c \"import socket; socket.create_connection(('1.1.1.1', 80), 2)\" 2>&1 | tail -1; echo FATTO\n")
        out, after = until(sid, "u1", "FATTO\n")
        assert "unreachable" in out.lower() or "network" in out.lower()
        T.write(sid, "u1", "python ask.py\n")
        until(sid, "u1", "nome?", after)
        T.write(sid, "u1", "Aurora\n")
        out, _ = until(sid, "u1", "ciao Aurora", after)
        assert "ciao Aurora" in out
        with pytest.raises(KeyError):
            T.write(sid, "someone else", "ls\n")                       # another user's terminal: not theirs
    finally:
        T.stop(sid, "u1")
    assert sid not in T._sessions


def test_limits_and_idle_terminals_are_closed(cfg, monkeypatch):
    if not shutil.which("bwrap"):
        pytest.skip("bubblewrap not here")
    (cfg.path("AURORA_PROJECTS_DIR") / "demo").mkdir(parents=True)
    cfg.values["AURORA_PROJECT_TERM_MAX"] = 1
    sid = T.start(cfg, "demo", "u2")["id"]
    with pytest.raises(T.TermError):
        T.start(cfg, "demo", "u2")
    assert T.reap(time.time() + 16 * 60) == 1 and sid not in T._sessions
