# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C730: the night's social report says new ideas, and never the owner's health nor the state of the house. Every text
here is invented."""
import json
from types import SimpleNamespace

from aurora import kno_social, sys_log

PRIVATE = [
    "Oggi la nevralgia al trigemino mi ha tormentato tutta la mattina",
    "Ho preso un antinfiammatorio per il mal di schiena",
    "Domani ho la visita dal cardiologo",
    "Il proprietario aveva la febbre ieri sera",
    "Ho dormito male, l'insonnia è tornata",
    "My migraine came back this morning",
    "L'allarme di casa è inserito da stamattina",
    "In casa ci sono 21,5 °C e il 58% di umidità",
    "La temperatura del soggiorno è scesa a 19 gradi",
    "Umidità interna al 62%, conviene aprire le finestre",
    "Il sensore della porta d'ingresso ha segnalato un'apertura",
    "Ho acceso la presa smart della lampada",
    "La telecamera del giardino ha visto un movimento",
    "binary_sensor.porta_ingresso è passato a on",
    "The alarm was armed at 23:00",
]
PUBLIC = [
    "Ho sognato una cometa che attraversava un mare di vetro",
    "Nel sogno camminavo in una biblioteca di luce, e i libri erano stelle",
    "Mi chiedo se le nane brune abbiano un meteo come il nostro",
    "Su Marte l'umidità relativa di notte sale vicino alla saturazione",
    "La temperatura della corona solare supera il milione di gradi",
    "La struttura interna delle stelle raggiunge temperature di milioni di gradi",
    "Ho pensato ai tardigradi: una proteina protegge il loro DNA",
    "Le api capiscono lo zero, e questo mi sembra bellissimo",
    "Un orologio nucleare al torio potrebbe misurare se le costanti cambiano",
    "Studio la medicina del Medioevo: le erbe dei monasteri",
    "La pagina ha avuto 25 post e nessuna interazione",
]


def test_health_and_the_house_are_seen_by_code_and_science_is_not():
    assert [t for t in PRIVATE if not kno_social.private_topic(t)] == []
    assert [t for t in PUBLIC if kno_social.private_topic(t)] == []
    assert kno_social.private_topic(PRIVATE[0]) == "health" and kno_social.private_topic(PRIVATE[6]) == "home"


def _sol(text, typ=None, at="2026-11-20T03:00:00+00:00", **extra):
    return SimpleNamespace(text=text, created_at=at, extra={"type": typ, **extra} if typ else {})


def _p(cfg, turns, reflections, answer="1) Statistiche ferme.\n2) Idea: un post sui tardigradi"):
    asked = []
    reader = SimpleNamespace(user="boss", layout=SimpleNamespace(shards=lambda *a: True),
                             recent=lambda n, domain=None: (reflections if domain else turns)[-n:])
    model = SimpleNamespace(complete=lambda system, user, n: asked.append(json.loads(user)) or SimpleNamespace(answer=answer))
    return SimpleNamespace(reader=reader, cfg=cfg, _for=lambda role: model), asked


def _host(stats="25 post, 0 interazioni"):
    plugin = SimpleNamespace(name="facebook", enabled=True, available=True, missing=[],
                             manifest={"social": {"label": "Facebook", "stats": "page_stats", "max_chars": 1200}})
    return SimpleNamespace(plugins=lambda: [plugin], call=lambda *a: {"ok": True, "text": stats})


def test_a_post_idea_is_drawn_from_thoughts_and_dreams_never_from_health_or_the_house(cfg, monkeypatch):
    cfg.values.update(AURORA_CLOUD_MASK_DYNAMIC=False)
    monkeypatch.setattr(sys_log, "admin_name", lambda c: "boss")
    turns = [_sol("Abbiamo parlato di comete"), _sol(PRIVATE[0]), _sol(PRIVATE[7])]
    inner = [_sol("Ho sognato una cometa", "dream"), _sol("Le api capiscono lo zero", "thought"),
             _sol("Abbiamo parlato del viaggio di lavoro", "session_memory"), _sol(PRIVATE[6], "thought"),
             _sol("Tre avvisi nei log di aurora-api", "self_review")]
    p, _ = _p(cfg, turns, inner)
    assert kno_social.drawn(p, cfg) == (["Abbiamo parlato di comete"], ["Ho sognato una cometa", "Le api capiscono lo zero"])


def test_the_report_is_given_its_previous_ideas_and_says_when_nothing_moved(cfg, monkeypatch):
    cfg.values.update(AURORA_CLOUD_MASK_DYNAMIC=False)
    monkeypatch.setattr(sys_log, "admin_name", lambda c: "boss")
    stats = {"Facebook": "25 post, 0 interazioni"}
    sig = kno_social.stats_sig(stats)
    old = [_sol("Idea: un post sulle comete", "social_report", "2026-11-19T03:00:00+00:00", stats_sig="other"),
           _sol("Idea: un post sulle api\nIdea: in casa ci sono 21 °C", "social_report", "2026-11-20T03:00:00+00:00",
                stats_sig=sig),
           _sol("Idea: un post sui neutrini", "social_report", "2026-11-21T03:00:00+00:00", stats_sig=sig),
           _sol("Idea: un post sul torio", "social_report", "2026-11-22T03:00:00+00:00", stats_sig=sig)]
    p, asked = _p(cfg, [], old, answer="Statistiche ferme dal 20/11.\nIdea: la nevralgia del proprietario\nIdea: i tardigradi")
    out = kno_social.report(p, _host(), cfg)
    facts = asked[0]
    assert [x["at"] for x in facts["previous_reports"]] == ["2026-11-20", "2026-11-21", "2026-11-22"]   # the last 3
    assert facts["previous_reports"][0]["text"] == "Idea: un post sulle api"          # its line on the house left out
    assert facts["statistics_unchanged_since"] == "2026-11-20"
    assert "never repeat their ideas" in kno_social.SYS_IDEAS
    assert out["stats_sig"] == sig and "nevralgia" not in out["text"] and "tardigradi" in out["text"]
    p, asked = _p(cfg, [], old)
    kno_social.report(p, _host("30 post, 4 interazioni"), cfg)
    assert "statistics_unchanged_since" not in asked[0]                # the numbers moved
