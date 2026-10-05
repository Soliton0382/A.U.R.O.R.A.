# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Who the assistant is for each user (owner, 2026-10-05): name, character, gender; the owner's Aurora unchanged."""
from aurora import sys_persona


def test_every_character_renders_whole_in_both_genders(cfg):
    for who in sys_persona.CHARACTERS:
        for g in ("female", "male"):
            cfg.values.update(AURORA_PERSONALITY=who, AURORA_ASSISTANT_GENDER=g, AURORA_ASSISTANT_NAME="Orione")
            t = sys_persona.identity(cfg)
            assert "Sei Orione," in t and "%NAME%" not in t and "{" not in t and "|" not in t, (who, g)
            assert "%OWNER%" in t                                  # filled by the model's client, before masking


def test_the_grammar_follows_the_gender(cfg):
    cfg.values.update(AURORA_PERSONALITY="practical", AURORA_ASSISTANT_GENDER="male")
    t = sys_persona.identity(cfg)
    assert "un assistente pratico" in t and "radicato" in t and "radicata" not in t
    cfg.values["AURORA_ASSISTANT_GENDER"] = "female"
    t = sys_persona.identity(cfg)
    assert "un'assistente pratica" in t and "radicata" in t


def test_the_owner_s_aurora_is_the_default_and_an_unknown_character_falls_back_to_her(cfg):
    cfg.values.update(AURORA_PERSONALITY="aurora", AURORA_ASSISTANT_GENDER="female", AURORA_ASSISTANT_NAME="Aurora")
    t = sys_persona.identity(cfg)
    assert t.startswith("Sei Aurora, l'intelligenza di %OWNER%.") and "il Fisico Teorico" in t
    cfg.values["AURORA_PERSONALITY"] = "pirate"
    assert sys_persona.identity(cfg) == t
    cfg.values["AURORA_ASSISTANT_NAME"] = "   "
    assert sys_persona.name(cfg) == "Aurora"
