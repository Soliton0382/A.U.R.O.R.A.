# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N64 phases 4 and 6 (owner, 29 Oct: «l'admin non può leggere il contenuto delle chat»): the shared forge requests and
autonomy ledger keep a user's words sealed, opened for that user only; what leaves for the paper archives is masked;
a post idea never draws another user's memory or a private value. Every name and question here is invented."""
from types import SimpleNamespace

from aurora import agt_forge as F, kno_social, sys_autonomy as A, sys_context, sys_log


def _file(cfg, *parts) -> str:
    return cfg.path("AURORA_STATUS_DIR").joinpath(*parts).read_text(encoding="utf-8")


def test_a_forge_request_is_sealed_and_shown_only_to_who_asked(cfg):
    with sys_context.acting_as("giulia"):
        item = F.request(cfg, "Leggere il diario di Ernestina Quaglio", "per la routine del lunedì", "run7")
        again = F.request(cfg, "leggere il diario di ernestina quaglio", "di nuovo", "run8")
    assert item["need"] == "Leggere il diario di Ernestina Quaglio" and again["id"] == item["id"]
    raw = _file(cfg, "forge", "requests.json")
    assert "Quaglio" not in raw and "lunedì" not in raw and '"user": "giulia"' in raw
    [stored] = F.requests(cfg)
    assert F.shown(cfg, stored, "giulia")["need"] == "Leggere il diario di Ernestina Quaglio"
    other = F.shown(cfg, stored, "boss")
    assert other["need"] == "(private: giulia)" and other["why"] == "(private: giulia)"
    assert F.opened(cfg, stored)["why"] == "per la routine del lunedì"      # the build reads it


def test_a_forge_request_of_before_stays_readable(cfg):
    F._save(cfg, [{"id": "old1", "need": "Contare le righe dei log", "why": "x", "status": "pending"}])
    assert F.shown(cfg, F.requests(cfg)[0])["need"] == "Contare le righe dei log"


def test_the_ledger_seals_a_user_s_words_and_keeps_the_machine_s_plain(cfg):
    A.log(cfg, "knowledge", "searched the sources by herself: chi è Teodolinda Sbrozzi?", user="giulia")
    A.log(cfg, "security", "blocked 45.33.32.156 for 24 h", user="boss")
    raw = _file(cfg, "autonomy_ledger.jsonl")
    assert "Sbrozzi" not in raw and "45.33.32.156" in raw
    own = A.days(cfg, user="giulia", viewer="giulia")[0]["items"]
    assert [r["text"] for r in own] == ["searched the sources by herself: chi è Teodolinda Sbrozzi?"]
    texts = {r["area"]: r["text"] for r in A.days(cfg, viewer="boss")[0]["items"]}
    assert texts == {"knowledge": "(private: giulia)", "security": "blocked 45.33.32.156 for 24 h"}


class _Model:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, user, n):
        return SimpleNamespace(answer=self.reply)


def test_the_archives_queries_are_masked_like_the_web_search(cfg):
    from aurora.kno_acquire import ArxivAgent
    cfg.values.update(AURORA_CLOUD_MASK_DYNAMIC=False, AURORA_CLOUD_MASK_MINE="Gualtiero Pezzolla", AURORA_ARXIV_QUERIES=3)
    agent = ArxivAgent.__new__(ArxivAgent)
    agent.cfg = cfg
    agent.p = SimpleNamespace(_for=lambda role: _Model("1. Gualtiero Pezzolla knee surgery recovery\n"
                                                        "2. rehabilitation mario@example.org 3391234567\n"
                                                        "3. ACL reconstruction outcomes"))
    qs = agent._queries("Come recupera il ginocchio Gualtiero Pezzolla?", [], [])
    joined = " ".join(qs)
    assert "Pezzolla" not in joined and "example.org" not in joined and "3391234567" not in joined
    assert "ACL reconstruction outcomes" in qs and any("knee surgery recovery" in q for q in qs)


def _pipeline(user, turns, thoughts):
    reader = SimpleNamespace(user=user, layout=SimpleNamespace(shards=lambda *a: True),
                             recent=lambda n, domain=None: [SimpleNamespace(text=t)
                                                            for t in (thoughts if domain else turns)])
    return SimpleNamespace(reader=reader)


def test_a_post_idea_draws_only_the_admin_s_memory_and_nothing_private(cfg, monkeypatch):
    cfg.values.update(AURORA_CLOUD_MASK_DYNAMIC=False, AURORA_CLOUD_MASK_MINE="Rosalba Fenocchio")
    monkeypatch.setattr(sys_log, "admin_name", lambda c: "boss")
    p = _pipeline("boss", ["Abbiamo parlato di comete", "Rosalba Fenocchio ha la febbre"],
                  ["Ho sognato una cometa", "Il numero di Rosalba Fenocchio è 3391234567"])
    assert kno_social.drawn(p, cfg) == (["Abbiamo parlato di comete"], ["Ho sognato una cometa"])
    assert kno_social.drawn(_pipeline("giulia", ["una cometa"], ["un sogno"]), cfg) == ([], [])
