# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import io
import json
import zipfile

import pytest

from aurora import kno_sources as K

AKN = b"""<?xml version="1.0" encoding="UTF-8"?>
<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0"><act><meta><identification>
<FRBRWork><FRBRthis value="/akn/it/act/legge/stato/1990-08-07/241/!main"/>
<FRBRalias name="urn:nir" value="urn:nir:stato:legge:1990-08-07;241"/></FRBRWork></identification></meta>
<preface><docTitle>Nuove norme in materia di procedimento amministrativo. (090G0294)</docTitle></preface>
<body><article><num>Art. 1.</num><heading>Principi generali</heading><paragraph><content><p>L'attivita'
amministrativa persegue i fini determinati dalla legge.</p></content></paragraph></article>
<article><num>Art. 2.</num><heading>Conclusione del procedimento</heading><paragraph><content><p>Ove il
procedimento consegua obbligatoriamente ad una istanza, le pubbliche amministrazioni hanno il dovere di
concluderlo.</p></content></paragraph></article><article><num>Art. 3.</num></article></body></act></akomaNtoso>"""

JATS = b"""<article><front><article-meta><title-group><article-title>Sleep and memory</article-title></title-group>
<abstract><p>We show that sleep consolidates memory.</p></abstract></article-meta></front>
<body><sec><title>Methods</title><p>Forty volunteers slept <xref>[1]</xref> eight hours.</p></sec></body>
<back><ref-list><ref>Smith J. A reference that must not be read.</ref></ref-list></back></article>"""


class Resp:
    def __init__(self, content=b"", data=None):
        self.content, self._data = content, data

    def json(self):
        return self._data

    @property
    def text(self):
        return self.content.decode()


def test_akn_articles_keep_number_heading_and_urn():
    title, urn, arts = K.akn_articles(AKN)
    assert title == "Nuove norme in materia di procedimento amministrativo."
    assert urn == "urn:nir:stato:legge:1990-08-07;241"
    assert len(arts) == 2 and arts[0].startswith("Art. 1. Principi generali L'attivita'")


def test_akn_codes_in_attachments_and_base64_files_are_read():
    import base64
    code = AKN.replace(b"</body></act>", b"""</body><attachments><attachment><doc name="all"><mainBody><paragraph>
<content><p>CODICE DELLA NAVIGAZIONE Art. 1. (Fonti del diritto della navigazione). In materia di navigazione si
applica il presente codice.</p></content></paragraph></mainBody></doc></attachment></attachments></act>""")
    title, urn, arts = K.akn_articles(base64.b64encode(code))
    assert len(arts) == 3 and arts[-1].startswith("CODICE DELLA NAVIGAZIONE Art. 1. (Fonti")


def test_jats_reads_abstract_and_body_not_references():
    title, text = K.jats_text(JATS)
    assert title == "Sleep and memory"
    assert "consolidates memory" in text and "Methods" in text and "Forty volunteers" in text
    assert "must not be read" not in text


def test_domain_modes_default_from_categories_then_owner_choice(cfg):
    m = K.modes(cfg)
    assert set(m.values()) <= set(K.MODES) and "law_it" in m
    cats = set(cfg["AURORA_HARVEST_CATEGORIES"])
    assert m["relativity"] == ("round" if "gr-qc" in cats else "off")
    assert m["law_it"] == "off"
    K.set_modes(cfg, {"law_it": "exhaust", "medicine": "round"})
    m2 = K.modes(cfg)
    assert m2["law_it"] == "exhaust" and m2["medicine"] == "round"
    with pytest.raises(ValueError):
        K.set_modes(cfg, {"law_it": "always"})
    with pytest.raises(ValueError):
        K.set_modes(cfg, {"astrology": "round"})


def test_every_domain_of_the_catalogue_is_a_knowledge_domain():
    from aurora.sol_schema import load_taxonomy
    tax = load_taxonomy()
    for dom, srcs in K.catalogue()["domains"].items():
        assert dom in tax and not tax[dom].get("memory"), dom
        assert all(s["source"] in K.SOURCES for s in srcs), dom


def test_normattiva_walks_collections_act_by_act_until_done(cfg):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("LEGGE_19900807_241/a.xml", AKN)
        z.writestr("LEGGE_19900807_242/b.xml", AKN.replace(b"1990-08-07;241", b"1990-08-07;242"))
    calls = []

    def fetch(url, **p):
        calls.append(p)
        return Resp(buf.getvalue())

    spec = {"source": "normattiva", "collections": ["Codici"]}
    st, seen = {}, set()
    docs = K.normattiva(fetch, cfg, "law_it", spec, st, 1, True, seen)
    assert len(docs) == 1 and docs[0].lang == "it" and docs[0].key == "normattiva:urn:nir:stato:legge:1990-08-07;241"
    assert docs[0].passages[0].startswith("Nuove norme in materia di procedimento amministrativo. — Art. 1.")
    assert "L. 633/1941" in docs[0].licence and not st.get("done")
    assert calls[0] == {"nome": "Codici", "formato": "AKN", "formatoRichiesta": "V"}
    seen.add(docs[0].key)
    docs = K.normattiva(fetch, cfg, "law_it", spec, st, 5, True, seen)
    assert [d.key[-3:] for d in docs] == ["242"] and st["done"]
    assert len(calls) == 1                                   # the collection was downloaded once


def test_pack_never_leaves_a_fragment_shorter_than_the_vault_accepts():
    arts = ["Art. 1. Breve."] * 7 + ["Art. 8. " + "lungo " * 400] + ["Art. 9. Abrogato."]
    out = K.pack("Legge", arts, 1000, 300)
    assert all(len(p) >= 300 for p in out) and out[0].startswith("Legge — Art. 1.")
    assert sum(p.count("Art. ") for p in out) == 9                   # nothing lost
    assert K.pack("Legge", ["Art. 1. Solo."], 1000, 300) == ["Legge — Art. 1. Solo."]


def test_wikipedia_reads_the_list_then_one_article_at_a_time(cfg):
    body = "Stoicism is a school of Hellenistic philosophy. " * 30 + "\n== References ==\nnot this"

    def fetch(url, **p):
        if p.get("prop") == "links":
            return Resp(data={"query": {"pages": {"1": {"links": [{"title": "Stoicism"}, {"title": "Ethics"}]}}}})
        return Resp(data={"query": {"pages": {"2": {"title": p["titles"], "extract": body}}}})

    st = {}
    docs = K.wikipedia(fetch, cfg, "philosophy", {"lists": ["Wikipedia:Vital articles/Level/4/Philosophy and religion"]},
                       st, 1, False, set())
    assert [d.title for d in docs] == ["Stoicism"] and "References" not in docs[0].data.decode()
    assert docs[0].licence.startswith("CC BY-SA") and not st["done"]
    docs = K.wikipedia(fetch, cfg, "philosophy", {"lists": []}, st, 5, False, {"wikipedia:Stoicism"})
    assert [d.title for d in docs] == ["Ethics"] and st["done"]


def test_progress_reports_done_only_when_every_source_is(cfg):
    K.save_state(cfg, "medicine", 0, {"done": True, "taken": 4})
    p = K.progress(cfg, "medicine")
    assert p["taken"] == 4 and not p["done"] and "europepmc" in p["sources"]
    for n in range(len(K.catalogue()["domains"]["medicine"])):
        K.save_state(cfg, "medicine", n, {"done": True})
    assert K.progress(cfg, "medicine")["done"]
    assert json.loads(json.dumps(K.progress(cfg, "patents"))) == {"sources": [], "taken": 0, "done": False}


def test_chunker_never_emits_a_short_chunk_between_long_ones():
    from aurora.kno_ingest import chunk
    text = "\n\n".join(["A" * 900, "Art. 2. Abrogato.", "B. " * 400, "C" * 950])
    parts = chunk(text, 1000, 300)
    assert all(len(p) >= 300 for p in parts) and "Abrogato" in "".join(parts)


def test_normattiva_network_error_is_retried_not_taken_for_a_missing_collection(cfg):
    import httpx

    def down(url, **p):
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    st = {"collection": 0}
    with pytest.raises(httpx.ConnectError):
        K.normattiva(down, cfg, "law_it", {"collections": ["Codici", "DPR"]}, st, 1, True, set())
    assert st == {"collection": 0}

    def absent(url, **p):
        req = httpx.Request("GET", url)
        raise httpx.HTTPStatusError("400", request=req, response=httpx.Response(400, request=req))

    st = {}
    assert K.normattiva(absent, cfg, "law_it", {"collections": ["Codici"]}, st, 1, True, set()) == []
    assert st["missing"] == ["Codici"] and st["done"]
