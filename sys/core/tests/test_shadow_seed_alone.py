# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C251: the shadow seed is published with the code, so its answers must not know the owner (owner, 10 Oct: «la mia
aurora è la mia aurora… per creare ombre useremo degli script così restano generiche»)."""
from types import SimpleNamespace

import pytest

from aurora import kno_shadow as K

PUB = [{"source": "arxiv:2401.1", "n": 1, "sid": "a", "title": "T", "domain": "physics"}]


class Emb:
    def encode_queries(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


def test_a_seed_question_reads_no_conversation_the_owners_do(monkeypatch):
    from aurora import sys_log
    from aurora.kno_answer import Pipeline
    monkeypatch.setattr(sys_log, "trace", lambda *a, **k: None)

    class Stop(Exception):
        pass

    def route(q, recent, quote):
        raise Stop(recent)

    seen = []
    p = object.__new__(Pipeline)
    p.cfg = {"AURORA_MEMORY_RECENT_TURNS": 8}
    p.reader = SimpleNamespace(recent=lambda n: ["the owner's turn"])
    p._route = route
    with pytest.raises(Stop) as e:
        p.run("Cos'è un solitone?", emit=lambda ev, d: seen.append(ev), alone=True)
    assert e.value.args[0] == [] and "run.alone" in seen
    with pytest.raises(Stop) as e:
        p.run("e dove abito?")                                       # the owner's Aurora: her chat, as before
    assert e.value.args[0] == ["the owner's turn"]


def test_only_the_scripts_questions_asked_alone_leave_never_the_nights_thoughts(cfg):
    K.add(cfg, Emb(), "Cos'è la decoerenza?", "La decoerenza è… [1]", PUB, origin="seed")
    K.add(cfg, Emb(), "Cos'è un solitone?", "Un'onda… [1]", PUB, origin="seed")
    K.add(cfg, Emb(), "Cos'è l'entropia?", "Come dicevi ieri… [1]", PUB, origin="train")  # a thought of the night
    assert [r["question"] for r in K.export_seed(cfg)] == ["Cos'è la decoerenza?", "Cos'è un solitone?"]
    assert [r["question"] for r in K.export_seed(cfg, only={"Cos'è un solitone?"})] == ["Cos'è un solitone?"]


def test_the_script_holds_back_what_is_personal(cfg, monkeypatch):
    import importlib.util

    from aurora import sys_config
    monkeypatch.setattr(sys_config, "get", lambda: cfg)
    from pathlib import Path
    f = Path(__file__).resolve().parents[1] / "script" / "shadow_seed.py"
    spec = importlib.util.spec_from_file_location("shadow_seed_script", f)
    S = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(S)
    import re
    deny = [re.compile("Pinco Pallino", re.I)]
    assert not S.private("Oscillations proceed via a two-component Higgs field [3].", deny)   # a «via», not a street
    assert S.private("Ne parlava Pinco Pallino [1].", deny)
    assert S.private("Scrivi a mario.rossi@example.com [1].", deny)


def test_the_whole_row_is_read_but_only_its_texts_are_masked(cfg, monkeypatch):
    """C259: a suggested follow-up named the owner (only question and answer were read); reading the row as JSON
    instead held back 262 of 319 for the sources' ids. The texts — question, answer, follow-ups, titles — are masked."""
    import importlib.util
    from pathlib import Path

    from aurora import sys_config
    monkeypatch.setattr(sys_config, "get", lambda: cfg)
    f = Path(__file__).resolve().parents[1] / "script" / "shadow_seed.py"
    spec = importlib.util.spec_from_file_location("shadow_seed_script2", f)
    S = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(S)
    row = {"question": "Cos'è un solitone?", "answer": "Un'onda [1].", "sources": [
        {"sid": "9f8e7d6c5b4a39281706f5e4d3c2b1a0", "title": "Solitons", "source": "arxiv:2401.1"}],
        "follow": [{"question": "Chi ha scritto di Pinco Pallino?", "focus": [{"source": "legacy:paper_x"}]}]}
    text = S.words(row)
    assert "Pinco Pallino" in text and "9f8e7d6c" not in text and "legacy:paper_x" not in text
