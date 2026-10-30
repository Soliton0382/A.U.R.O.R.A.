# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🪪 The people of this Aurora (sys_people; owner, 30 Oct: «chi è per te <il proprietario>… informazioni easy tra gli utenti
ma con un occhio di riguardo nei confronti dell'admin»): closed fields, what the others see chosen per field, the
relations confirmed by both, Aurora's proposals entering only with a yes, and what Aurora reads. Made-up people."""
import pytest

from aurora import sys_people as P

USERS = ["boss", "ada", "luca"]


def test_a_card_its_fields_and_what_the_others_see(cfg):
    P.set_card(cfg, "ada", {"name": "Ada", "birth": "1990-04-12", "city": "Torino", "work": "architetta",
                            "social": [{"label": "Instagram", "url": "https://instagram.com/ada.example"}],
                            "visible": {"city": True}})
    v = P.view(cfg, "boss", USERS, "boss")
    ada = v["cards"]["ada"]
    assert ada["name"] == "Ada" and ada["city"] == "Torino" and "birth" not in ada and "social" not in ada  # name + chosen
    own = P.view(cfg, "ada", USERS, "boss")["cards"]["ada"]
    assert own["birth"] == "1990-04-12" and own["visible"]["city"] and not own["visible"]["birth"]          # hers whole
    assert v["cards"]["boss"]["admin"]
    for bad in ({"birth": "2990-01-01"}, {"birth": "12/04/1990"}, {"social": [{"url": "http://x.example"}]}):
        with pytest.raises(ValueError):
            P.set_card(cfg, "ada", bad)
    raw = (cfg.path("AURORA_STATUS_DIR") / "people.sealed").read_bytes()
    assert b"Torino" not in raw and b"1990" not in raw                                                        # sealed


def test_a_relation_holds_once_both_say_so(cfg):
    r = P.ask_relation(cfg, "ada", "boss", "spouse", USERS)
    assert r["state"] == "pending" and P.view(cfg, "luca", USERS, "boss")["relations"] == []                 # not yet
    with pytest.raises(KeyError):
        P.answer_relation(cfg, "ada", r["id"], True)                                                         # not hers to confirm
    with pytest.raises(ValueError):
        P.ask_relation(cfg, "boss", "ada", "friend", USERS)                                                  # one between two
    P.answer_relation(cfg, "boss", r["id"], True)
    assert [x["kind"] for x in P.view(cfg, "luca", USERS, "boss")["relations"]] == ["spouse"]
    p = P.ask_relation(cfg, "boss", "luca", "parent", USERS)
    assert P.label(p, "luca") == "genitore" and P.label(p, "boss") == "figlia/figlio"
    with pytest.raises(ValueError):
        P.ask_relation(cfg, "boss", "nobody", "friend", USERS)
    P.drop_relation(cfg, "luca", p["id"])
    assert not any(x["id"] == p["id"] for x in P.load(cfg)["relations"])


def test_proposals_enter_with_a_yes_and_a_no_is_for_ever(cfg):
    props = P.propose(cfg, "ada", ["- ama l'astronomia", "costruisce un telescopio", "ama l'astronomia"])
    assert [x["text"] for x in props] == ["ama l'astronomia", "costruisce un telescopio"]
    P.answer_proposal(cfg, "ada", props[0]["id"], True)
    P.answer_proposal(cfg, "ada", props[1]["id"], False)
    card = P.load(cfg)["cards"]["ada"]
    assert [b["text"] for b in card["bio"]] == ["ama l'astronomia"] and card["proposals"] == []
    assert P.propose(cfg, "ada", ["costruisce un telescopio", "ama l'astronomia"]) == []                      # never again


def test_what_aurora_reads_for_the_person_asking(cfg):
    P.set_card(cfg, "boss", {"name": "Boss", "city": "Roma"})
    P.set_card(cfg, "ada", {"name": "Ada", "birth": "1990-04-12", "city": "Torino", "visible": {"city": True}})
    P.add_bio(cfg, "ada", "ama il trekking")
    r = P.ask_relation(cfg, "ada", "boss", "spouse", USERS)
    P.answer_relation(cfg, "boss", r["id"], True)
    for_ada = P.prompt_block(cfg, "ada", USERS, "boss")
    assert "creator and programmer" not in for_ada and "ideatore e programmatore" in for_ada                    # the admin's role
    assert "THE PERSON ASKING: Ada" in for_ada and "1990-04-12" in for_ada and "ama il trekking" in for_ada  # her own, whole
    assert "Roma" not in for_ada                                                                              # his city: private
    assert "ada is wife/husband of boss" in for_ada and "cannot speak of another user's conversations" in for_ada
    for_boss = P.prompt_block(cfg, "boss", USERS, "boss")
    assert "Torino" in for_boss and "1990-04-12" not in for_boss and "trekking" not in for_boss              # her visible part
    assert P.prompt_block(cfg, "boss", ["boss"], "boss") == ""                                                # alone: nothing


def test_a_picture_is_square_small_sealed_and_seen_only_when_let(cfg):
    """Owner, 30 Oct: «il profilo classico… la foto… un avatar con aurora». A photo of 1200×800 with a GPS tag:
    its middle square at 512 px, the metadata dropped, sealed; the others see it only when its owner says."""
    import io
    from PIL import Image
    img = Image.new("RGB", (1200, 800), (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "MadeUpCamera"                                   # a tag that must not survive
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    P.set_picture(cfg, "ada", "photo", buf.getvalue())
    data, mime = P.picture(cfg, "ada", "ada")
    with Image.open(io.BytesIO(data)) as out:
        assert out.size == (512, 512) and mime == "image/jpeg" and not out.getexif()
    raw = (cfg.path("AURORA_STATUS_DIR") / "people" / "ada.photo.sealed").read_bytes()
    assert b"JFIF" not in raw[:64] and b"MadeUpCamera" not in raw
    assert P.picture(cfg, "boss", "ada") is None                    # private by default
    P.set_card(cfg, "ada", {"visible": {"picture": True}})
    assert P.picture(cfg, "boss", "ada")[1] == "image/jpeg"
    assert P.picture(cfg, "boss", "ada", "avatar")[1] == "image/jpeg"  # not his to ask another kind: the one shown
    with pytest.raises(ValueError):
        P.use_picture(cfg, "ada", "avatar")                          # none made yet
    P.use_picture(cfg, "ada", "")
    assert P.picture(cfg, "boss", "ada") is None
    with pytest.raises(ValueError):
        P.set_picture(cfg, "ada", "photo", b"not a picture")
    assert P.view(cfg, "ada", USERS, "boss")["cards"]["ada"]["pictures"] == ["photo"]


def test_a_new_person_is_asked_once_and_the_first_proposals_come_once(cfg):
    """Owner, 30 Oct: «un nuovo utente alla prima interazione… conosciamoci meglio… così già comincia a popolare la
    biografia»; and the biography «un po' più esteso»."""
    assert not P.intro_due(cfg, "boss", "boss")                           # the admin made her: never asked
    assert P.intro_due(cfg, "ada", "boss")
    P.mark_intro(cfg, "ada")
    assert not P.intro_due(cfg, "ada", "boss")                            # once
    assert P.intro_due(cfg, "luca", "boss")
    P.add_bio(cfg, "luca", "x" * 550)                                     # a short paragraph fits
    assert not P.intro_due(cfg, "luca", "boss") and len(P.load(cfg)["cards"]["luca"]["bio"][0]["text"]) == 550
    assert P.auto_due(cfg, "ada")
    P.mark_auto(cfg, "ada")
    assert not P.auto_due(cfg, "ada")
    P.add_bio(cfg, "boss", "y" * 600)
    P.add_bio(cfg, "boss", "z" * 600)
    P.add_bio(cfg, "boss", "w" * 600)
    P.set_card(cfg, "boss", {"visible": {"bio": True}})
    block = P.prompt_block(cfg, "ada", USERS, "boss")
    assert "…" in block and "w" * 400 not in block                        # the prompt kept small: 1500 a person


def test_the_agent_s_tool_tells_the_asker_s_own_card_even_alone(cfg):
    """Owner, 30 Oct: «ho chiesto ad aurora di dirmi di me… non c'è riuscita e ora si sta costruendo un plugin»: the
    agent's runs had no card; the core's own read-only tool gives it, alone too."""
    assert "no card yet" in P.tool_text(cfg, "boss", ["boss"], "boss")
    P.set_card(cfg, "boss", {"name": "Boss", "city": "Roma"})
    P.add_bio(cfg, "boss", "costruisce telescopi")
    alone = P.tool_text(cfg, "boss", ["boss"], "boss")
    assert "Roma" in alone and "costruisce telescopi" in alone
    assert "cannot speak of another user's conversations" in P.tool_text(cfg, "boss", USERS, "boss")
    assert P.TOOL["name"] == "people_cards" and P.TOOL["input_schema"]["properties"] == {}
