# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Cuts on the way of a question, said instead of silent (C614, C6xx-a…e). Invented texts only."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as N

from aurora import kno_self, kno_stages, mdl_llm
from aurora.kno_self import SelfTalk, clip
from aurora.kno_stages import EXTRACT_CUT, SYNTH_CUT, Stages

LONG_STORY = ("Da un mese vado in bicicletta al lavoro, venti minuti all'andata e venti al ritorno, e la sera mi fa male "
              "il polso sinistro, soprattutto quando apro un barattolo. Non sono caduto e non vedo gonfiore. Lavoro "
              "molto al computer con il mouse e dormo sul fianco sinistro. Vorrei sapere che cosa può essere, se devo "
              "smettere di pedalare e che cosa posso fare per stare meglio.")


def _turn(text, role, minutes=5):
    at = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    return N(sid=f"{role}{minutes}", created_at=at, text=text, extra={"role": role})


CFG = {"AURORA_TIMEZONE": "UTC", "AURORA_OWNER_NAME": "Owner", "AURORA_ASSISTANT_NAME": "Aurora",
       "AURORA_PIPELINE_SELF_THINKING": False, "AURORA_PIPELINE_THINK_TOKENS": 600, "AURORA_CHAT_STREAMING": False,
       "AURORA_PIPELINE_GATE": True, "AURORA_PIPELINE_GATE_KEEP": 0.0, "AURORA_PIPELINE_SPLIT_CHARS": 220,
       "AURORA_PIPELINE_THINKING": False, "AURORA_CLOUD_COMPRESSION": False, "AURORA_PIPELINE_VERIFY": False}


# ---- C6xx-a: the turns her self route reads -------------------------------------------------------------------
def test_a_cut_says_how_much_is_missing():
    assert clip("abc", 5) == "abc" and clip("abc", None) == "abc"
    out = clip("x" * 1000, 400)
    assert out.startswith("x" * 400) and "[…600 more characters not shown]" in out


def test_a_shortened_turn_says_so():
    talk = N(cfg=CFG)
    out = SelfTalk._turns(talk, [_turn("parola " * 200, "user")], 1, 500)
    assert "more characters not shown]" in out


def test_the_budget_keeps_the_newest_turns_whole_and_says_what_is_left_out():
    talk = N(cfg=CFG)
    turns = [_turn("vecchio " * 500, "user", 50), _turn("medio " * 300, "assistant", 40), _turn("nuovo " * 200, "user", 1)]
    out = SelfTalk._turns(talk, turns, 3, cut=None, budget=2500)
    assert ("nuovo " * 200).strip() in out                            # the newest whole (1,200 characters)
    assert "more characters not shown]" in out                          # the one before it shortened, said
    assert out.startswith("[1 older turns not shown]")                   # the oldest left out, counted


class _Recorder:
    def __init__(self):
        self.system = ""

    def stream(self, system, user, max_tokens, think=False):
        self.system = system
        yield "answer", "Ho letto tutto."


def test_her_self_route_reads_a_long_answer_whole(monkeypatch):
    """C6xx-a reproduced: the owner says a long answer of hers was wrong; before, 500 characters of it reached her."""
    answer = "Risposta lunga sul polso. " + " ".join(f"Frase {i} sul tema del polso e della bici." for i in range(80))
    report = "La tua risposta di prima parlava d'altro: " + "dettaglio " * 60
    recent = [_turn(LONG_STORY, "user", 12), _turn(answer, "assistant", 10), _turn(report, "user", 2)]
    rec = _Recorder()

    class Talk(SelfTalk):
        cfg = CFG

        def self_state(self):
            return {"time": "now"}

        def _memories(self, question, recent, ev):
            return [], []

        def _for(self, role):
            return rec

    monkeypatch.setattr(kno_self.sys_persona, "identity", lambda cfg: "Sei Aurora.")
    monkeypatch.setattr(kno_self, "people_block", lambda cfg, recent=None: "")
    events = []
    Talk()._self_answer("Perché?", recent, lambda e, p: events.append((e, p)))
    assert len(answer) > 3000 and answer in rec.system and report.strip() in rec.system
    assert ("self.turns", {"turns": 3, "chars": sum(len(t.text) for t in recent), "budget": kno_self.SELF_TURNS_CHARS}) in events


# ---- C6xx-b: a local answer cut at its room is known as cut ------------------------------------------------------
def test_the_local_server_s_limit_is_read_from_this_build_s_field():
    assert mdl_llm.at_limit({"stop_type": "limit"}) and mdl_llm.at_limit({"stopped_limit": True})
    assert not mdl_llm.at_limit({"stop_type": "eos"}) and not mdl_llm.at_limit({})


# ---- C614, C6xx-c/d/e: the stages --------------------------------------------------------------------------------
def _hit(n, domain, rerank=0.2, used="q"):
    return N(sid=f"s{n}", rerank=rerank, query_used=used,
             soliton=N(domain=domain, title=f"t{n}", source_id=f"src{n}", text=f"Testo inventato {n} su {domain}."))


class _Model:
    def __init__(self, gate="1", extract="- fatto [1]", cut_extract=False, synth="Il polso [1].", cut_synth=False):
        self.gate, self.extract, self.cut_extract, self.synth, self.cut_synth = gate, extract, cut_extract, synth, cut_synth
        self.calls, self.synth_user, self.gate_budget = [], "", None
        self.last_truncated = False

    def complete(self, system, user, max_tokens, think=False):
        if system == kno_stages.SYS_GATE:
            self.gate_budget = max_tokens
            return N(answer=self.gate, truncated=False)
        self.calls.append(user)
        return N(answer=self.extract, truncated=self.cut_extract)

    def stream(self, system, user, max_tokens, think=False):
        self.synth_user = user
        self.last_truncated = self.cut_synth
        yield "answer", self.synth


class _Pipe(Stages):
    def __init__(self, model):
        self.cfg, self.llm, self.model = CFG, model, model
        self.log = N(info=lambda *a: None)

    def _for(self, role):
        return self.model


def _run(model, question, hits):
    events = []
    out = _Pipe(model)._answer(question, hits, "", lambda e, p: events.append((e, p)))
    return out, events


def test_a_long_question_extracts_only_the_domains_the_gate_chose():
    """C614 reproduced: passage 1 (medicine) chosen by the gate; religion and society at 0.15-0.18 came first and
    their extractions found «something» — now not extracted at all."""
    hits = [_hit(1, "medicine", 0.7), _hit(2, "religion", 0.18), _hit(3, "society", 0.16), _hit(4, "medicine", 0.3)]
    m = _Model(gate="1, 4")
    out, events = _run(m, LONG_STORY, hits)
    assert len(m.calls) == 1 and "religion" not in m.calls[0] and "medicine" in m.calls[0]
    assert ("gate.domains", {"kept": ["medicine"], "skipped": ["religion", "society"]}) in events
    assert out[0].startswith("Il polso [1].")


def test_a_short_question_extracts_every_domain_as_before():
    hits = [_hit(1, "medicine", 0.7), _hit(2, "religion", 0.18)]
    m = _Model(gate="1")
    _run(m, "Perché fa male il polso?", hits)
    assert len(m.calls) == 2


def test_the_gate_has_room_for_every_number():
    hits = [_hit(i, "medicine") for i in range(1, 23)]
    m = _Model(gate=", ".join(str(i) for i in range(1, 23)))
    _run(m, LONG_STORY, hits)
    assert m.gate_budget >= 77 and kno_stages.gate_budget(5) == 32       # 77 tokens measured for «1, …, 22»


def test_a_gate_list_cut_short_is_not_taken_as_a_choice():
    hits = [_hit(1, "medicine", 0.7), _hit(2, "religion", 0.18)]
    m = _Model(gate="1")
    m.complete_gate = m.complete

    def cut_gate(system, user, max_tokens, think=False):
        if system == kno_stages.SYS_GATE:
            return N(answer="1", truncated=True)
        return m.complete_gate(system, user, max_tokens, think)
    m.complete = cut_gate
    _, events = _run(m, LONG_STORY, hits)
    assert len(m.calls) == 2 and not any(e == "gate.domains" for e, _ in events)


def test_an_extraction_cut_at_its_room_says_so_to_the_synthesis():
    hits = [_hit(1, "medicine", 0.7)]
    m = _Model(gate="1", extract="- primo fatto [1]\n- secondo fat", cut_extract=True)
    _, events = _run(m, LONG_STORY, hits)
    assert EXTRACT_CUT.strip() in m.synth_user and "secondo fat" not in m.synth_user
    assert ("synthesis.domain_cut", {"domain": "medicine", "passages": 1}) in events


def test_an_answer_cut_at_its_room_says_so_to_the_reader():
    hits = [_hit(1, "medicine", 0.7)]
    m = _Model(gate="1", synth="Il polso si infiamma [1]. Poi", cut_synth=True)
    out, events = _run(m, "Perché fa male il polso quando pedalo?", hits)
    assert out[0].endswith(SYNTH_CUT["it"].strip()) and any(e == "synthesis.cut" for e, _ in events)
