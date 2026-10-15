# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The same question asked again and again, thinned to its best answer (owner, 15 Oct: «teniamo il meglio»); one
reflection forgotten by the admin only."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

F = Path(__file__).resolve().parents[1] / "script" / "mem_prune.py"
spec = importlib.util.spec_from_file_location("mem_prune", F)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def ans(text, at):
    return SimpleNamespace(text=text, created_at=at, extra={})


def test_the_best_answer_stays_not_the_latest():
    g = {"question": "spiegami in due frasi cos'è l'entropia.", "runs": ["run:a", "run:b", "run:c"]}
    answers = {"run:a": ans("L'entropia misura il disordine di un sistema [1].", "2026-10-05"),
               "run:b": ans("I found no verified knowledge in my vault that answers this question.", "2026-10-09"),
               "run:c": ans("Use the same citations. Let's craft:", "2026-10-10")}
    assert M.best(g, answers, 1) == ["run:a"]


def test_it_does_not_exist_is_a_good_answer_and_a_group_of_refusals_goes_whole():
    g = {"question": "riassumi il romanzo «le nebbie di tarvelion»", "runs": ["run:a", "run:b"]}
    answers = {"run:a": ans("Non ho trovato una risposta né nel vault né sul web, e non voglio inventarla.", "2026-10-12"),
               "run:b": ans("Non trovo nessuna traccia di quello che chiedi: probabilmente non esiste.", "2026-10-13")}
    assert M.best(g, answers, 1) == ["run:b"]
    answers["run:b"] = ans("Nel mio vault non ho trovato conoscenza verificata che risponda.", "2026-10-13")
    assert M.best(g, answers, 1) == []


def test_a_reflection_is_forgotten_by_the_admin_only():
    src = (F.parents[1] / "aurora" / "api" / "activity.py").read_text(encoding="utf-8")   # api modules import core first
    assert '@router.delete("/v1/aurora/memory/reflection", dependencies=[Depends(admin_only)])' in src
