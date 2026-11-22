# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📚 The sources chosen in the chat (kno_scope, owner 20 Nov): auto as before, ⚖️ legal only the statutes, a group
only its domains, several together, anything else refused; the menu. Invented questions only."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from aurora import kno_cites, kno_followup, kno_lawgate, kno_scope as S, kno_split, sol_index, sol_search
from aurora.kno_answer import Pipeline
from aurora.sol_schema import Soliton, load_taxonomy
from aurora.sol_search import Hit, Searcher

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "webui" / "js" / "modules"


# ---- the groups and their validation ------------------------------------------------------------------------------
def test_every_knowledge_domain_of_the_taxonomy_is_in_exactly_one_group_and_no_group_invents_one():
    tax = {k: v for k, v in load_taxonomy().items() if not v.get("memory")}
    seen = [d for g in S.GROUPS for d in S.domains_of(g)]
    assert sorted(seen) == sorted(tax)                                  # each once, none missing
    named = [d for _, (_, doms) in S.GROUPS.items() for d in doms]
    assert set(named) <= set(tax) and not any(d.startswith("law_") for d in named)
    assert S.domains_of("legal") == tuple(sorted(d for d in tax if d.startswith("law_"))) and "law_it" in tax


def test_auto_or_nothing_is_no_choice_and_unknown_or_memory_domains_are_refused():
    for raw in (None, "", [], ["auto"], "auto"):
        assert S.parse(raw) is None
    for raw in (["astrology"], ["legal", "nonsense"], ["conversation"], ["reflection"], [3], "legal,../vault", {"a": 1}):
        with pytest.raises(ValueError):
            S.parse(raw)


def test_legal_a_group_a_domain_id_and_several_together():
    legal = S.parse(["legal"])
    assert legal == {"chosen": ["legal"], "domains": ["law_it"], "legal": True}
    sci = S.parse(["science"])
    assert not sci["legal"] and "physics" in sci["domains"] and "law_it" not in sci["domains"] and "medicine" not in sci["domains"]
    both = S.parse("medicine, economics")
    assert both["chosen"] == ["medicine", "economics"] and set(both["domains"]) == {"medicine", "biomedicine", "genomics",
                                                                                      "psychology", "economics"}
    assert S.parse(["physics", "physics"])["domains"] == ["physics"]       # a domain id of the vault, once
    assert S.parse(["legal", "medicine"])["legal"] is True


def test_the_api_reads_the_choice_before_any_work_and_refuses_an_unknown_one_with_422():
    # the API is not imported in-process here (conftest: never the installation's own); its wiring is read
    runs = (ROOT / "aurora" / "api" / "runs.py").read_text()
    ask = runs[runs.index("async def ask"):runs.index("def job(")]
    assert "sources = kno_scope.parse(body.get(\"sources\"))" in ask and "status_code=422" in ask
    assert ask.index("kno_scope.parse") < ask.index("pipeline()")
    assert "or focus or sources:" in runs and "lessons=lessons, sources=sources)" in runs
    assert "not think and not sources:" in runs                          # 🗣️ the quick talk path never skips it


# ---- the search: only the chosen domains, never more ----------------------------------------------------------------
def _sol(domain, text="", kind="knowledge", **extra):
    return Soliton.new(text or f"a passage of {domain}", domain, kind, "en", f"src:{domain}", title=domain, extra=extra or None)


class _Index:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def search(self, qv, k, sections=None, user=None, **kw):
        self.calls.append(kw)
        doms = kw.get("domains")
        return [[(s.sid, 0.5, "memory" if s.domain == "conversation" else "knowledge", s.domain) for s in self.rows
                 if doms is None or s.domain == "conversation" or s.domain in doms]]


def _searcher(cfg, rows, lexical=()):
    s = object.__new__(Searcher)
    s.cfg, s.user, s.log = cfg, None, SimpleNamespace(info=lambda *a: None, warning=lambda *a: None)
    s.embedder = SimpleNamespace(encode_queries=lambda qs: np.zeros((len(qs), 2), np.float32))
    s.reranker = SimpleNamespace(score=lambda pairs: [0.5] * len(pairs))
    by = {x.sid: x for x in rows}
    s.reader = SimpleNamespace(get_many=lambda sids: {k: by[k] for k in sids if k in by})
    s.index = _Index([r for r in rows if r.sid not in lexical])
    s.ahead = SimpleNamespace(take=lambda q, kw: None)
    return s


def test_the_search_without_a_choice_is_unchanged_and_with_one_keeps_only_its_domains(cfg, monkeypatch):
    cfg.values.update(AURORA_SEARCH_LEXICAL=5, AURORA_SYNAPSE_EXPAND=0, AURORA_SEARCH_TOPK=10)
    law, med, phys, conv = _sol("law_it"), _sol("medicine"), _sol("physics"), _sol("conversation", kind="conversation")
    words = _sol("law_it", "found by its words")
    from aurora import sol_lexical
    monkeypatch.setattr(sol_lexical, "search", lambda c, texts, k: [words.sid])
    s = _searcher(cfg, [law, med, phys, conv, words], lexical={words.sid})
    hits = s.search("How does a vaccine train the immune system?")
    assert s.index.calls == [{}]                                       # auto: the index asked exactly as before
    assert {h.soliton.domain for h in hits} == {"law_it", "medicine", "physics", "conversation"}
    token = sol_search.ONLY.set(frozenset({"medicine"}))
    try:
        hits = s.search("How does a vaccine train the immune system?")
    finally:
        sol_search.ONLY.reset(token)
    assert s.index.calls[-1] == {"domains": frozenset({"medicine"})}
    assert {h.soliton.domain for h in hits} == {"medicine", "conversation"}   # the memory stays for kno_about


def test_the_index_skips_the_knowledge_domains_not_chosen_and_never_the_memory(cfg, monkeypatch):
    dirs = [("knowledge", "law_it", "f-law"), ("knowledge", "physics", "f-phys"), ("memory", "conversation", "f-conv")]
    monkeypatch.setattr(sol_index, "_index_dirs", lambda c, u=None: dirs)
    ix = object.__new__(sol_index.IndexSet)
    ix.cfg, loaded = cfg, []
    ix._load = lambda f: loaded.append(f)                              # None: nothing to read, only who was opened
    ix.search(np.zeros((1, 2), np.float32), 5, None, None, domains=frozenset({"physics"}))
    assert loaded == ["f-phys", "f-conv"]
    loaded.clear()
    ix.search(np.zeros((1, 2), np.float32), 5)
    assert loaded == ["f-law", "f-phys", "f-conv"]


def test_legal_names_provisions_for_a_short_question_too(cfg, monkeypatch):
    cfg.values.update(AURORA_PIPELINE_SPLIT_CHARS=400, AURORA_SEARCH_TOPK=8)
    art = Hit("c1", _sol("law_it", "Art. 1 the landlord must repair"), 1.0, 0.9, "cited")
    monkeypatch.setattr(kno_cites, "hits", lambda p, q, ev: [art])
    p = SimpleNamespace(cfg=cfg)
    whole = [Hit("w1", _sol("law_it"), 0.5, 0.4, "original")]
    hits, subs = kno_split.search(p, "Who repairs a broken boiler in a rented flat?", lambda: whole, lambda e, x: None,
                                  short_cites=True)
    assert [h.sid for h in hits] == ["c1", "w1"] and subs == []
    hits, _ = kno_split.search(p, "Who repairs a broken boiler in a rented flat?", lambda: whole, lambda e, x: None)
    assert [h.sid for h in hits] == ["w1"]                             # without the choice: as before


# ---- the whole run ------------------------------------------------------------------------------------------------
def _pipe(cfg, monkeypatch, gate=False):
    p = object.__new__(Pipeline)
    p.cfg, p.user, p.speed = cfg, None, None
    p.log = SimpleNamespace(warning=lambda *a: None, info=lambda *a: None)
    p.reader = SimpleNamespace(recent=lambda n: [])
    p._route = lambda *a: "knowledge"
    rows = [_sol("law_it", "Art. 1571 a lease is a contract"), _sol("medicine", "Vaccines train the immune system"),
            _sol("physics", "Light bends near a mass"), _sol("economics", "Inflation erodes savings"),
            _sol("conversation", "I asked about this before", kind="conversation", role="user")]
    seen = {"only": [], "gate": 0, "cites": 0, "answered": []}

    def search(q, tr=None, **kw):
        seen["only"].append(sol_search.ONLY.get())
        return [Hit(r.sid, r, 0.5, 0.5, "original") for r in rows]
    p.search = SimpleNamespace(search=search, embedder=None)
    monkeypatch.setattr(kno_followup, "standalone", lambda self, q, recent, ev, quote=None: (q, []))
    monkeypatch.setattr(kno_lawgate, "legal", lambda *a, **k: seen.__setitem__("gate", seen["gate"] + 1) or gate)
    monkeypatch.setattr(kno_cites, "hits", lambda pp, q, ev: seen.__setitem__("cites", seen["cites"] + 1) or [])

    def answer(question, hits, recent, ev):
        seen["answered"].append(sorted(h.soliton.domain for h in hits))
        return "An answer [1].", [{"n": 1, "sid": hits[0].sid, "title": "t", "source": "s", "domain": hits[0].soliton.domain}], []
    p._answer = answer
    cfg.values.update(AURORA_PIPELINE_SPLIT_CHARS=400, AURORA_PIPELINE_SUGGEST=False)
    return p, seen


def _ask(p, question, **kw):
    events = []
    ans = p.run(question, emit=lambda e, x: events.append((e, x)), remember=False, **kw)
    return ans, events


def test_auto_is_unchanged_the_law_gate_decides_and_no_sources_line(cfg, monkeypatch):
    p, seen = _pipe(cfg, monkeypatch, gate=False)
    # a lawgate case (test_lawgate): an everyday question whose margin keeps the law out
    ans, events = _ask(p, "Why does my phone get hot while charging?", think="vault")
    assert seen["gate"] == 1 and seen["cites"] == 0 and seen["only"] == [None]
    assert "law_it" not in seen["answered"][0] and "conversation" in seen["answered"][0]
    assert ("retrieval.filter", {"dropped_law": 1}) in events
    assert not any(e == "sources" for e, _ in events) and "📚" not in ans.text and "⚖️" not in ans.text
    assert sol_search.ONLY.get() is None


def test_legal_only_the_statutes_with_cites_the_note_and_no_web(cfg, monkeypatch):
    p, seen = _pipe(cfg, monkeypatch)
    ans, events = _ask(p, "Can a landlord keep the deposit for normal wear?", think="medium", sources=S.parse(["legal"]))
    assert seen["gate"] == 0 and seen["cites"] == 1                    # the choice decides; provisions on a short one
    assert seen["only"] == [frozenset({"law_it"})] and seen["answered"] == [["law_it"]]
    assert ("think", {"asked": "vault", "used": "vault", "why": ""}) in events    # medium asked: the vault only
    assert kno_split.CASE_NOTE["en"] in ans.text
    src = [x for e, x in events if e == "sources"]
    assert src == [{"chosen": ["legal"], "searched": ["law_it"], "legal": True, "used": {"law_it": 1}}]
    assert ans.text.rstrip().endswith("📚 Searched only in: ⚖️ Legal · sources cited: law_it (1).")
    assert sol_search.ONLY.get() is None                                # reset after the run


def test_a_scientific_group_keeps_only_its_domains(cfg, monkeypatch):
    p, seen = _pipe(cfg, monkeypatch)
    ans, events = _ask(p, "Why does light bend around a star?", think="vault", sources=S.parse(["science"]))
    assert seen["gate"] == 0 and seen["cites"] == 0 and seen["answered"] == [["physics"]]
    assert ("retrieval.filter", {"outside_sources": 3}) in events      # medicine, economics, the conversation
    assert ("law.gate", {"legal": False, "uncertain": False, "why": "sources chosen"}) in events
    assert kno_split.CASE_NOTE["en"] not in ans.text and "🔬 Science" in ans.text


def test_several_groups_together(cfg, monkeypatch):
    p, seen = _pipe(cfg, monkeypatch)
    _, events = _ask(p, "How do vaccines affect healthcare costs?", think="vault", sources=S.parse(["medicine", "economics"]))
    assert seen["answered"] == [["economics", "medicine"]]
    assert [x["chosen"] for e, x in events if e == "sources"] == [["medicine", "economics"]]


# ---- the menu -----------------------------------------------------------------------------------------------------
def test_the_menu_offers_the_server_s_groups_with_their_icons_in_both_languages():
    src = (JS / "chat_sources.js").read_text()
    ids = re.findall(r'"(\w+)"', re.search(r"SOURCES = \[(.*?)\]", src).group(1))
    assert ids == list(S.GROUPS)
    icons = dict(re.findall(r'(\w+): "([^"]+)"', re.search(r"SOURCE_ICON = \{(.*?)\};", src, re.S).group(1)))
    assert icons == {"auto": "🤖", **{g: S.GROUPS[g][0] for g in S.GROUPS}}
    for f in ("it_IT.json", "en_US.json"):
        words = json.loads((ROOT / "webui" / "i18n" / f).read_text())
        for k in ["auto", *S.GROUPS]:
            assert f"chat.menu.sources.{k}" in words and f"chat.sources.{k}" in words, (f, k)
        assert "chat.menu.sources" in words and "ev.sources" in words
    assert "sources: sourcesChoice()" in (JS / "chat.js").read_text()
    menu = (JS / "chat_menu.js").read_text()
    assert "toggleSource(s)" in menu and "gear.dataset.sources" in menu


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_choice_toggles_auto_clears_it_and_the_badge_is_short():
    for f in ("chat_sources.js", "chat_menu.js", "chat.js", "trace.js"):
        subprocess.run(["node", "--check", str(JS / f)], check=True)
    out = subprocess.run(["node", str(ROOT / "tests" / "js" / "chat_sources.mjs"), (JS / "chat_sources.js").as_uri()],
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == {"start": [], "one": ["legal"], "two": ["legal", "medicine"], "badge2": "⚖️🩺",
                               "three": ["legal", "medicine", "science"], "badge3": "⚖️🩺+1", "off": ["legal", "science"],
                               "auto": [], "badge0": ""}
