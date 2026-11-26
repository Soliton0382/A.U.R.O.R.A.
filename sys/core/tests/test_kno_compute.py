# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N158: the chat's agent computes instead of remembering — offered with a known person, never in the anonymous
chat; the program runs in the read-only cage (no network, nothing of the user), its folder gone after."""
import shutil

import pytest

from aurora import kno_compute, sys_context

needs_cage = pytest.mark.skipif(not shutil.which("bwrap"), reason="no bubblewrap")


def test_offered_to_a_known_person_never_in_the_anonymous_chat(cfg, monkeypatch):
    monkeypatch.setattr(sys_context, "anonymous_now", lambda: False)
    assert [t["name"] for t in kno_compute.offered(cfg, "quanto fa")] == ["compute"]
    monkeypatch.setattr(sys_context, "anonymous_now", lambda: True)
    assert kno_compute.offered(cfg, "quanto fa") == []
    assert kno_compute.agent_call(type("A", (), {"cfg": cfg})(), {"code": "print(1)"}).startswith("ERROR")


def test_the_tool_tells_the_model_not_to_answer_numbers_from_memory():
    d = kno_compute.TOOL["description"]
    assert "never give a numeric or symbolic result from memory" in d and "No network" in d


def test_empty_or_long_programs_are_refused(cfg):
    with pytest.raises(ValueError):
        kno_compute.run(cfg, "   ")
    with pytest.raises(ValueError):
        kno_compute.run(cfg, "x" * (kno_compute.CODE_CHARS + 1))


@needs_cage
def test_it_computes_in_the_cage_without_network_and_leaves_nothing(cfg, monkeypatch, tmp_path):
    monkeypatch.setattr(kno_compute.tempfile, "tempdir", str(tmp_path))
    r = kno_compute.run(cfg, "import math\nprint(round(math.sqrt(2), 6))")
    assert r["exit"] == 0 and r["output"] == "1.414214"
    net = kno_compute.run(cfg, "import socket\nsocket.create_connection(('1.1.1.1', 53), 2)")
    assert net["exit"] != 0 and "unreachable" in net["output"].lower()
    assert not list(tmp_path.glob("aurora-compute-*"))      # the program's folder is gone


def test_not_offered_where_there_is_no_cage(cfg, monkeypatch):
    monkeypatch.setattr(sys_context, "anonymous_now", lambda: False)
    monkeypatch.setattr(kno_compute.shutil, "which", lambda name: None)
    assert kno_compute.offered(cfg, "quanto fa") == []


class _Model:
    """A model that writes a program, then answers from its output; the second program only after a failure."""
    def __init__(self, programs):
        self.programs, self.seen = list(programs), []

    def complete(self, system, user, n, think=False):
        self.seen.append((system[:20], user))
        text = (f"```python\n{self.programs.pop(0)}\n```" if system.startswith("You write ONE") else "Fa 42 (calcolato).")
        return type("C", (), {"answer": text})()


@needs_cage
def test_the_short_path_computes_retries_once_and_answers_from_the_output(cfg, monkeypatch):
    m = _Model(["print(1/0)", "print(6*7)"])
    monkeypatch.setattr(kno_compute, "_model", lambda c: m)
    res = kno_compute.solve(cfg, "quanto fa 6 per 7?")
    assert res["ok"] and res["output"] == "42" and res["code"] == "print(6*7)"
    assert "ZeroDivisionError" in m.seen[1][1]                 # the second attempt saw the first one's error
    assert "OUTPUT:\n42" in m.seen[2][1]
    text = kno_compute.chat_text(res)
    assert text.startswith("Fa 42") and "```python fold" in text and "# 42" in text


def test_the_computation_question_is_one_decision():
    class D:
        def decide(self, system, user, words):
            assert words == ["COMPUTE", "NO"] and "MESSAGE: risolvi" in user
            return {"COMPUTE": 0.9, "NO": 0.1}
    assert kno_compute.wants(D(), "risolvi x^2-5x+6=0")
