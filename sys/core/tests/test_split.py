# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A case told as a story, searched as the questions it holds (kno_split, C183)."""
from types import SimpleNamespace

from aurora import kno_split

CASE = ("Abitiamo in affitto in un bilocale. Vogliamo andarcene prima della scadenza, ma il proprietario manda lettere "
        "di avvocati e minaccia di trattenere la cauzione. In più un vicino ci accusa di aver rovinato il muro comune, "
        "quando è stato l'idraulico del proprietario a romperlo.")


class Model:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def complete(self, system, user, max_tokens, think=False):
        self.asked.append(user)
        return SimpleNamespace(answer=self.answer)


def _hit(sid, rerank, kind="law", role=None, text="testo"):
    return SimpleNamespace(sid=sid, rerank=rerank, soliton=SimpleNamespace(kind=kind, text=text, extra={"role": role} if role else {}))


def test_only_a_long_message_is_split():
    assert kno_split.wanted(CASE, 220) and not kno_split.wanted("cos'è l'entropia?", 220) and not kno_split.wanted(CASE, 0)


def test_the_model_s_lines_become_at_most_four_clean_searches():
    m = Model("1. recesso anticipato dal contratto di affitto: il preavviso\n- Recesso anticipato dal contratto "
              "di affitto: il preavviso\n• trattenuta della cauzione da parte del proprietario\n\n"
              "«danni al muro comune causati da altri: responsabilità»\n4) a\nobblighi del conduttore\nquinta ricerca")
    assert kno_split.split(m, CASE) == ["recesso anticipato dal contratto di affitto: il preavviso",
                                        "trattenuta della cauzione da parte del proprietario",
                                        "danni al muro comune causati da altri: responsabilità",
                                        "obblighi del conduttore"]


def test_the_owner_s_same_message_asked_again_is_not_a_source():
    again = _hit("c1", 1.0, kind="conversation", role="user", text=CASE.upper() + "  ")
    other = _hit("c2", 0.9, kind="conversation", role="user", text="Il mio appartamento è il numero 4.")
    assert kno_split.same_message(again, CASE) and not kno_split.same_message(other, CASE)
    assert not kno_split.same_message(_hit("l1", 1.0, text=CASE), CASE)          # a law is never «the same message»


def test_each_search_brings_its_best_first_then_the_rest_by_score():
    whole = [_hit("w1", 0.18), _hit("w2", 0.09)]
    found = [[_hit("a1", 0.97), _hit("a2", 0.96), _hit("a3", 0.5), _hit("a4", 0.4)],
             [_hit("b1", 0.81), _hit("w1", 0.79), _hit("b3", 0.2)]]
    out = [h.sid for h in kno_split.merge(whole, found, top_k=4)]
    assert out == ["a1", "a2", "a3", "b1", "w1", "b3"]                          # top_k + one per search; each once


def test_the_gate_reads_the_problems_too():
    q = kno_split.with_searches("storia", ["recesso dal contratto", "danni al muro comune"])
    assert q.startswith("storia\n\nTHE PROBLEMS IT HOLDS") and "- danni al muro comune" in q
    assert kno_split.with_searches("storia", []) == "storia"


def test_verified_sentences_keep_their_paragraphs_and_headings():
    from aurora.kno_stages import PARA, _layout
    kept = ["**Il recesso**", "Serve il preavviso [2].", "Lo dice il contratto [1].", PARA,
            "**Il muro comune**", PARA, "**La cauzione**", "Va restituita [3].", PARA]
    assert _layout(kept) == ("**Il recesso**\nServe il preavviso [2]. Lo dice il contratto [1]."
                             "\n\n**La cauzione**\nVa restituita [3].")      # a heading left alone goes


def test_a_provision_is_read_from_its_number():
    from aurora import kno_cites
    assert kno_cites.parse("art. 1590-bis c.c.") == ("1590-bis", kno_cites.CODES["c.c."])
    assert kno_cites.parse("Art. 9 d.lgs. 102/2014") == ("9", "normattiva:urn:nir:stato:decreto.legislativo:2014-%;102")
    assert kno_cites.parse("art. 6 d.P.R. 380/2001")[1].endswith("presidente.della.repubblica:2001-%;380")
    assert kno_cites.parse("il contratto") is None and kno_cites.parse("art. 3 Costituzione") is None


def test_a_case_whose_provisions_were_refused_is_read_again_as_the_story():
    """C189: with the problems listed the extraction said NONE to the civil code; once more on the story alone."""
    import pytest
    from aurora.kno_stages import Stages

    asked, answers = [], iter(["NONE", "- Art. 1590: il conduttore restituisce la cosa come l'ha ricevuta [1]."])

    def complete(system, user, max_tokens, think=False):
        asked.append(user)
        return SimpleNamespace(answer=next(answers))

    events = []
    me = SimpleNamespace(cfg={"AURORA_PIPELINE_GATE": False}, _for=lambda role: SimpleNamespace(complete=complete))
    hit = SimpleNamespace(sid="a", rerank=0.9, query_used="cited",
                          soliton=SimpleNamespace(domain="law_it", title="Codice civile", source_id="cc", text="Art. 1590"))
    question = kno_split.with_searches(CASE, ["chi paga i danni al muro comune?"])
    with pytest.raises(KeyError):                  # no synthesis settings: it stops there, the extraction is under test
        Stages._answer(me, question, [hit], "", lambda e, p: events.append((e, p)))
    assert kno_split.MARK in asked[0] and asked[1].startswith(f"QUESTION: {CASE}\n\nPASSAGES")
    assert [p["kept"] for e, p in events if e == "synthesis.domain"] == [True]


def test_a_picture_attached_to_the_question_is_never_closed_by_the_gate():
    """C318: «Descrivi la foto che ti allego» — the gate said NONE to the picture's description, Aurora abstained."""
    import pytest
    from aurora.kno_stages import Stages

    answers = iter(["NONE", "- Una persona in armatura sotto la pioggia [1].", "NONE"])   # gate, two domains
    me = SimpleNamespace(cfg={"AURORA_PIPELINE_GATE": True, "AURORA_PIPELINE_GATE_KEEP": 0},
                         _for=lambda role: SimpleNamespace(complete=lambda s, u, n, think=False: SimpleNamespace(answer=next(answers))))
    hit = SimpleNamespace(sid="p", rerank=0.003, query_used="attachment",
                          soliton=SimpleNamespace(domain="attachment", title="foto.png", source_id="attachment:r:foto.png",
                                                  text="A person in futuristic armour, standing in the rain."))
    other = SimpleNamespace(sid="v", rerank=0.001, query_used="describe the photo",
                            soliton=SimpleNamespace(domain="general", title="x", source_id="x", text="Photography basics."))
    events = []
    with pytest.raises(KeyError):                  # it gets past the gate to the extraction; synthesis settings missing
        Stages._answer(me, "Describe the photo I attach", [hit, other], "", lambda e, p: events.append((e, p)))
    gate = [p for e, p in events if e == "gate"][0]
    assert gate["open"] and gate["passages"] == [1]


def test_only_the_attached_picture_skips_the_gate():
    """D3: the passages are all the attached file's — the gate would keep them anyway, it is not asked."""
    import pytest
    from aurora.kno_stages import Stages

    asked = []
    me = SimpleNamespace(cfg={"AURORA_PIPELINE_GATE": True, "AURORA_PIPELINE_GATE_KEEP": 0},
                         _for=lambda role: SimpleNamespace(complete=lambda s, u, n, think=False: asked.append(role)
                                                           or SimpleNamespace(answer="- A dog [1].")))
    hit = SimpleNamespace(sid="p", rerank=0.003, query_used="attachment",
                          soliton=SimpleNamespace(domain="attachment", title="foto.png", source_id="attachment:r:foto.png",
                                                  text="A dog on a sofa."))
    events = []
    with pytest.raises(KeyError):
        Stages._answer(me, "Describe the photo", [hit], "", lambda e, p: events.append((e, p)))
    assert "gate" not in asked and not [e for e, _ in events if e == "gate"]
    assert asked == ["extract"]


def test_a_question_only_about_the_picture_is_told_apart():
    """D3: «descrivi la foto» → ONLY (no vault); a document attached, or no file, never."""
    from aurora.kno_attach import Attached, only_about

    def model(out):
        return SimpleNamespace(complete=lambda s, u, n: SimpleNamespace(answer=out))
    pic, doc = Attached("f.jpg", "image", []), Attached("a.pdf", "document", [])
    assert only_about(model("ONLY"), "Descrivi la foto", [pic])
    assert not only_about(model("MORE"), "Che pianta è? Come si cura?", [pic])
    assert not only_about(model("ONLY"), "Riassumi", [pic, doc])
    assert not only_about(model("ONLY"), "Descrivi", [])
    sure = SimpleNamespace(decide=lambda s, u, opts: {"ONLY": 0.9, "MORE": 0.1})
    assert only_about(sure, "Cosa c'è scritto?", [pic])


def test_a_citation_after_the_full_stop_stays_with_its_sentence():
    """C319: «Il cielo è azzurro.\n[1]» — the sentence was dropped for «no citation» and the lone «[1]» kept (too short
    to verify): the answer came out as «[1] [1] [1]»."""
    from aurora.kno_stages import Stages

    me = SimpleNamespace(cfg={"AURORA_VERIFY_MODE": "all"},
                         _for=lambda role: SimpleNamespace(complete=lambda s, u, n: SimpleNamespace(answer="YES")))
    hit = SimpleNamespace(soliton=SimpleNamespace(text="A blue sky over a red house."))
    events = []
    text, dropped = Stages._verify(me, "Il cielo in alto è di un azzurro uniforme.\n[1]\n\nLa casa a sinistra è rossa scura. [1]",
                                   [hit], lambda e, p: events.append((e, p)))
    assert not dropped
    assert text == "Il cielo in alto è di un azzurro uniforme [1].\n\nLa casa a sinistra è rossa scura [1]."
    # the live run: the citation opening the next sentence, a list item's first sentence without one
    text, dropped = Stages._verify(me, "Nel cartello c'è scritto **APERTO 9-18**, in nero.\n[1] Il cartello è bianco e "
                                   "rettangolare. [1]\n\n- **Edificio**: si trova sulla sinistra. È un rettangolo rosso [1].",
                                   [hit], lambda e, p: events.append((e, p)))
    assert not dropped
    assert text == ("Nel cartello c'è scritto **APERTO 9-18**, in nero [1]. Il cartello è bianco e rettangolare [1].\n\n"
                    "- **Edificio**: si trova sulla sinistra. È un rettangolo rosso [1].")


def test_a_verified_list_keeps_one_item_a_line():
    from aurora.kno_stages import PARA, _layout

    kept = ["Gli elementi:", "- **Cielo**: azzurro chiaro uniforme [1].", "- **Sole**: un cerchio giallo [1].", PARA]
    assert _layout(kept) == "Gli elementi:\n- **Cielo**: azzurro chiaro uniforme [1].\n- **Sole**: un cerchio giallo [1]."
