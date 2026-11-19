# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📚 The literature check (prj_novelty, N146), the network mocked: close work is FOUND and cited, nothing close is
NOT FOUND «in the literature checked» (never «new»), every source down is NOT CHECKED, a source down is named; only
a masked query on the subject leaves; the phase's summary and the referee's input list the checks. Invented claims."""
import json

import pytest

from aurora import prj_act as A
from aurora import prj_conduct as C
from aurora import prj_novelty as N
from aurora import prj_prereg as P
from aurora import prj_referee
from aurora.sec_mask import Pseudonymizer


@pytest.fixture(autouse=True)
def _engines_on(cfg):
    """N145-N147 are off by default while under review (C642): their own tests switch them on."""
    for k in ("AURORA_LONGRUN_ENABLED", "AURORA_DISCOVER_ENABLED", "AURORA_NOVELTY_ENABLED"):
        cfg.values[k] = True


CLAIM = "The mean number of cycles of a xor multiplication permutation grows quadratically with the bit length"
CLOSE = {"title": "Cycle structure of xor multiplication permutations: the mean number of cycles grows quadratically",
         "url": "https://doi.org/10.0000/invented", "year": "2024", "authors": ["A. Invented"],
         "text": "We study the bit length dependence of xor multiplication maps."}
FAR = {"title": "Rainfall in an invented valley", "url": "https://example.org/x", "year": "2020", "authors": [],
       "text": "Weather records."}


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "cicli"
    p.mkdir(parents=True)
    return p


def src(*recs):
    return lambda q, n, get: list(recs)


def down(q, n, get):
    raise ConnectionError("network unreachable")


def test_close_work_is_found_and_cited(cfg, proj):
    r = N.check(cfg, CLAIM, project="cicli", sources={"a": src(FAR), "b": src(CLOSE)})
    assert r["status"] == "found" and r["sources"][0]["url"] == CLOSE["url"] and r["sources"][0]["close"]
    t = N.text(r)
    assert t.startswith("CLOSE WORK FOUND") and "do not call the result new" in t
    rep = json.loads((proj / r["report"]).read_text())
    assert rep["status"] == "found" and P.locked(r["report"])


def test_nothing_close_is_not_found_never_new(cfg, proj):
    r = N.check(cfg, CLAIM, project="cicli", sources={"a": src(FAR), "b": src()})
    assert r["status"] == "not_found" and r["answered"] == ["a", "b"]
    t = N.text(r)
    assert "NOT FOUND in the literature checked" in t and "never «new»" in t
    assert " is new" not in t.lower() and "novel" not in t.lower()


def test_network_down_is_not_checked(cfg, proj):
    r = N.check(cfg, CLAIM, project="cicli", sources={"a": down, "b": down})
    assert r["status"] == "not_checked" and set(r["failed"]) == {"a", "b"}
    assert "say nothing about novelty" in N.text(r)


def test_one_source_down_is_named(cfg, proj):
    r = N.check(cfg, CLAIM, project="cicli", sources={"a": down, "b": src(FAR)})
    assert r["status"] == "not_found" and "a" in r["failed"] and "sources that failed: a" in N.text(r)


def test_only_a_masked_query_on_the_subject_leaves(cfg, proj):
    sent = []

    def spy(q, n, get):
        sent.append(q)
        return []
    claim = "Mario Rossi at mario.rossi@example.com phone 333 1234567 found that xor multiplication cycles grow"
    r = N.check(cfg, claim, sources={"s": spy}, record=False)
    assert sent and "@" not in sent[0] and "1234567" not in sent[0] and "333" not in sent[0]
    assert len(sent[0].split()) <= int(cfg["AURORA_NOVELTY_QUERY_WORDS"])
    assert r["query"] == sent[0]
    k = N.check(cfg, claim, keywords=["xor", "multiplication", "cycles"], sources={"s": spy}, record=False)
    assert k["query"] == "xor multiplication cycles"


def test_real_parsers_on_invented_answers():
    class Resp:
        def __init__(self, text="", data=None):
            self.text, self._d = text, data

        def json(self):
            return self._d
    atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/0000.00001v1</id>'
            '<title>An invented title</title><summary>An invented abstract.</summary><published>2023-01-01</published>'
            '<author><name>A. Invented</name></author></entry></feed>')
    a = N.arxiv("xor cycles", 5, lambda url, **p: Resp(text=atom))
    assert a[0]["title"] == "An invented title" and a[0]["url"].startswith("https://") and a[0]["year"] == "2023"
    oa = N.openalex("xor cycles", 5, lambda url, **p: Resp(data={"results": [{"title": "T", "publication_year": 2021,
         "doi": "https://doi.org/10.0/x", "authorships": [], "abstract_inverted_index": {"cycles": [1], "xor": [0]}}]}))
    assert oa[0]["text"] == "xor cycles" and oa[0]["year"] == "2021"
    cr = N.crossref("xor cycles", 5, lambda url, **p: Resp(data={"message": {"items": [{"title": ["T2"], "DOI": "10.0/y",
         "issued": {"date-parts": [[2019]]}, "abstract": "<jats:p>xor</jats:p>"}]}}))
    assert cr[0]["url"] == "https://doi.org/10.0/y" and cr[0]["year"] == "2019" and "xor" in cr[0]["text"]


def test_short_or_off(cfg, proj):
    assert N.check(cfg, "short", sources={}, record=False)["status"] == "refused"
    cfg.values["AURORA_NOVELTY_ENABLED"] = False
    r = N.check(cfg, CLAIM, sources={"a": src(CLOSE)}, record=False)
    assert r["status"] == "error" and "AURORA_NOVELTY_ENABLED" in r["errors"][0] and not N.rule(cfg)


def test_phase_summary_and_referee_input_list_the_checks(cfg, proj):
    t0 = 0.0
    N.check(cfg, CLAIM, project="cicli", sources={"b": src(CLOSE)})
    assert "→ found" in N.balance(cfg, "cicli", t0)
    assert "literature checks (novelty_check)" in C.folder_facts(cfg, "cicli", "goal", t0)
    part = prj_referee.inputs(cfg, "cicli", "goal", t0)
    assert "Literature checks of the phase" in part and CLOSE["url"] in part


def test_tool_wiring_and_referee_writes_no_report(cfg, proj, monkeypatch):
    assert N.NAME in {t["name"] for t in A.TOOLS} and N.NAME in {t["name"] for t in prj_referee.TOOLS}
    monkeypatch.setattr(N, "SOURCES", {"b": src(CLOSE)})
    cfg.values["AURORA_NOVELTY_SOURCES"] = "b"
    run = A.Run(cfg, "cicli", Pseudonymizer(cfg), "goal")
    run.readonly = True
    out = A._do(run, N.NAME, {"claim": CLAIM})
    assert "CLOSE WORK FOUND" in out and not (proj / "novelty").exists()
    assert N.history(cfg, "cicli")[-1]["status"] == "found"
    assert "novelty_check" in C.draft_system(cfg, "cicli", "")
