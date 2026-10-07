# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The diet plan followed day by day (roadmap 55) and Word documents read (C178). A plan made up for the tests."""
import io
import zipfile
from datetime import date
from types import SimpleNamespace

from aurora import hlt_diet, hlt_store
from aurora.kno_ingest import read_text

PLAN = """STUDIO DI PROVA
NOTE GENERALI
È concesso 1 pasto libero a settimana.
PIANO ALIMENTARE SETTIMANALE
LUNEDÌ
Colazione
yogurt bianco 150 g
avena 30 g
Pranzo
riso 70 g
merluzzo 150 g
zucchine 200 g
Cena
petto di pollo 150 g
verdure 250 g

MARTEDÌ
Colazione
pane integrale 50 g
2 uova
Pranzo
pasta 70 g al pomodoro
Parmigiano 10 g
lenticchie 150 g
Piatto unico da portare al lavoro.
Cena
hamburger di manzo 150 g
patate 200 g

MERCOLEDI
Colazione
latte 200 ml
Pranzo
farro 70 g
mozzarella 100 g
Cena
salmone 150 g
pane 50 g

INDICAZIONI PRATICHE
Colazione
questa non è un pasto del piano
FREQUENZE:
Carne: 1 volta rossa 2 volte bianca.
Pesce: 2-3 volte a settimana.
Uova: 2-4 uova a settimana.
Formaggi: 1-2 volte a settimana.
Legumi: 2-3 volte a settimana.
RICETTE:
Cena
uova strapazzate
"""


def _docx(paragraphs, rows):
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    ps = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    tbl = "<w:tbl>" + "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in r)
                              + "</w:tr>" for r in rows) + "</w:tbl>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<w:document {w}><w:body>{ps}{tbl}</w:body></w:document>')
    return buf.getvalue()


def test_a_word_document_is_read_with_its_tables(cfg):
    data = _docx(["PIANO ALIMENTARE", "Colazione"], [["Pranzo", "riso 70 g"], ["Cena", "pesce 150 g"]])
    text, title = read_text("piano.docx", data, cfg)
    assert "PIANO ALIMENTARE\nColazione" in text and "Pranzo | riso 70 g" in text and "Cena | pesce 150 g" in text
    it = hlt_store.add_document(cfg, "diet", "piano.docx", data)            # C178: kept with its text, not «non leggibile»
    assert "riso 70 g" in hlt_store.text(cfg, "diet", it["id"])


def test_the_week_is_read_day_by_day_and_ends_at_the_next_section():
    opts = hlt_diet.parse_week(PLAN)
    assert [o["id"] for o in opts] == ["lunedì-colazione", "lunedì-pranzo", "lunedì-cena", "martedì-colazione",
                                       "martedì-pranzo", "martedì-cena", "mercoledì-colazione", "mercoledì-pranzo",
                                       "mercoledì-cena"]                    # MERCOLEDI without its accent too
    by = {o["id"]: o for o in opts}
    assert by["lunedì-pranzo"]["groups"] == {"pesce": 1} and by["lunedì-cena"]["groups"] == {"carne_bianca": 1}
    assert by["martedì-colazione"]["groups"] == {"uova": 2}                   # eggs count at breakfast too
    assert by["martedì-pranzo"]["groups"] == {"legumi": 1}                    # 10 g of Parmigiano: a condiment
    assert by["martedì-pranzo"]["note"] == "Piatto unico da portare al lavoro."
    assert by["martedì-cena"]["groups"] == {"carne_rossa": 1} and by["mercoledì-pranzo"]["groups"] == {"formaggi": 1}


def test_frequencies_and_free_meals_are_read_from_the_text():
    f = hlt_diet.parse_frequencies(PLAN)
    assert f == {"carne_rossa": {"min": 1, "max": 1}, "carne_bianca": {"min": 2, "max": 2},
                 "pesce": {"min": 2, "max": 3}, "uova": {"min": 2, "max": 4}, "formaggi": {"min": 1, "max": 2},
                 "legumi": {"min": 2, "max": 3}}
    assert hlt_diet._free_meals(PLAN) == 1 and hlt_diet._free_meals("niente") is None


class Reader:
    def __init__(self, answer):
        self.answer, self.read = answer, []

    def complete(self, system, user, max_tokens, think=False):
        self.read.append(user)
        return SimpleNamespace(answer=self.answer)


def test_process_keeps_the_plan_sealed_and_the_model_reads_no_recipes(cfg):
    hlt_store.add_document(cfg, "diet", "piano.txt", PLAN.encode())
    llm = Reader('{"free_meals_per_week": 1, "limits": [{"what": "liquore", "max": 1, "per": "week"}], "rules": ["Acqua 1,5 L"]}')
    p = hlt_diet.process(cfg, llm)
    assert len(p["options"]) == 9 and p["frequencies"]["pesce"] == {"min": 2, "max": 3}
    assert p["limits"] == [{"what": "liquore", "max": 1, "per": "week"}] and p["rules"] == ["Acqua 1,5 L"]
    assert "uova strapazzate" not in llm.read[0]                            # cut before the recipes
    raw = (hlt_store._dir(cfg, "diet") / "plan.sealed").read_bytes()
    assert b"merluzzo" not in raw                                             # sealed, not readable on disk
    assert hlt_diet.plan(cfg)["source_id"] == p["source_id"]


def test_the_suggestion_follows_the_week_and_says_why(cfg):
    hlt_store.add_document(cfg, "diet", "piano.txt", PLAN.encode())
    p = hlt_diet.process(cfg)
    wed = date(2026, 10, 7)                                                   # a Wednesday
    s = hlt_diet.suggest(p, [], wed, "cena")
    assert s["suggested"]["id"] == "mercoledì-cena" and "previsto dal piano per oggi" in s["suggested"]["why"]
    # fish three times already this week (max 3): the salmon steps back, its reason said
    for d, m in (("2026-10-05", "pranzo"), ("2026-10-06", "pranzo"), ("2026-10-06", "cena")):
        hlt_diet.choose(cfg, d, m, "lunedì-pranzo")
    s = hlt_diet.suggest(p, hlt_diet.choices(cfg), wed, "cena")
    assert s["suggested"]["id"] != "mercoledì-cena"
    salmon = next(o for o in s["alternatives"] if o["id"] == "mercoledì-cena")
    assert "pesce: già 3 su massimo 3 questa settimana" in salmon["why"]
    assert s["free_left"] == 1


def test_a_choice_replaces_the_one_before_and_variety_is_suggested(cfg):
    hlt_store.add_document(cfg, "diet", "piano.txt", PLAN.encode())
    p = hlt_diet.process(cfg)
    hlt_diet.choose(cfg, "2026-10-07", "colazione", "lunedì-colazione")
    row = hlt_diet.choose(cfg, "2026-10-07", "colazione", "martedì-colazione")
    assert len(hlt_diet.choices(cfg)) == 1 and row["groups"] == {"uova": 2}
    for d in ("2026-09-28", "2026-09-30", "2026-10-02", "2026-10-04", "2026-10-06"):
        hlt_diet.choose(cfg, d, "colazione", "lunedì-colazione")
    s = hlt_diet.suggest(p, hlt_diet.choices(cfg), date(2026, 10, 8), "colazione")
    assert s["hints"] and s["hints"][0].startswith("Scegli spesso «yogurt bianco 150 g, avena 30 g» (5 volte")
    assert hlt_diet.unchoose(cfg, row["id"]) and not hlt_diet.unchoose(cfg, "nope")


def test_reminder_times_and_the_meal_of_now():
    from datetime import datetime
    times = hlt_diet.parse_times("colazione=07:30, pranzo=12:30,cena=25:00,brunch=10:00")
    assert times == {"colazione": "07:30", "pranzo": "12:30"}
    assert hlt_diet.meal_now(times, datetime(2026, 10, 7, 12, 34)) == "pranzo"
    assert hlt_diet.meal_now(times, datetime(2026, 10, 7, 12, 41)) is None


def test_the_chat_reads_the_processed_plan_with_the_codes_date(cfg):
    hlt_store.add_document(cfg, "diet", "piano.txt", PLAN.encode())
    p = hlt_diet.process(cfg)
    wed = date(2026, 10, 7)
    assert hlt_diet.when("oggi", wed) == wed and hlt_diet.when("domani", wed) == date(2026, 10, 8)
    assert hlt_diet.when("Martedì", wed) == date(2026, 10, 13) and hlt_diet.when("mercoledi", wed) == wed
    txt = hlt_diet.meal_text(p, [], wed, ["pranzo"], wed)
    assert txt.startswith("Oggi è mercoledì 7 ottobre 2026.") and "PRANZO — PROPOSTO: farro 70 g; mozzarella 100 g" in txt
    assert "alternativa 1:" in txt and "Settimana (mangiato / frequenza del piano): carne rossa 0/1" in txt
    other = hlt_diet.meal_text(p, [], hlt_diet.when("domani", wed), ["cena"], wed)
    assert "Il giorno chiesto è giovedì 8 ottobre 2026." in other
    full = hlt_diet.plan_text(p)
    assert "MARTEDÌ pranzo: pasta 70 g al pomodoro; Parmigiano 10 g; lenticchie 150 g" in full and "uova strapazzate" not in full
