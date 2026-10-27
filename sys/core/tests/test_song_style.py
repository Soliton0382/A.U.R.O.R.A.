# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How a song is dressed (aud_song_style; owner, 2026-10-27: «vengono tutte un po' uguali… vestire le canzoni»): the
choices reach the writer, the caption (always) and the music model's own fields; redress changes the clothes only."""
import random

import pytest

from aurora import aud_song, aud_song_style as St
from aurora.mdl_llm import Completion


def test_choices_become_tags_fields_and_a_brief():
    r = St.resolve({"genre": "synthwave", "dress": "acoustic", "voice": "female", "tempo": "slow", "key": "minor",
                    "creativity": "bold"}, random.Random(1))
    assert any("synthwave" in t for t in r["tags"]) and any("unplugged" in t for t in r["tags"])
    assert 74 <= r["bpm"] <= 82 and r["key_scale"].endswith(" minor") and r["lm_temperature"] == 1.05
    assert "Synthwave" in r["brief"] and "Acoustic" in r["brief"] and not r["instrumental"]
    assert St.resolve({"genre": "auto"}) == {"tags": [], "instrumental": False, "brief": ""}
    with pytest.raises(ValueError):
        St.check({"genre": "polka"})
    with pytest.raises(ValueError):
        St.check({"colour": "red"})


def test_the_chosen_tags_are_always_in_the_caption_and_redress_keeps_the_genre():
    c = St.dress("dreamy pop, soft synths", ["synthwave, retro 80s", "female vocalist"])
    assert c.startswith("synthwave, retro 80s, female vocalist")
    again = St.redress(c + ", unplugged, acoustic guitars", {"dress": "anthem", "voice": "male"})
    assert "synthwave" in again and "festival anthem" in again and "male vocalist" in again
    assert "unplugged" not in again and "female vocalist" not in again


class LLM:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def complete(self, system, user, max_tokens):
        self.asked.append(user)
        return Completion(self.answer, "", 10, 0.1, False)


def test_the_writer_builds_on_the_dress_and_an_instrumental_has_no_words():
    llm = LLM('{"title": "Neon", "caption": "dreamy pop", "lyrics": "[verse]\\nla"}')
    s = aud_song.write(llm, "a night drive", "en", style={"genre": "synthwave", "tempo": "fast", "voice": "instrumental"})
    assert "STYLE CHOSEN BY THE OWNER" in llm.asked[0] and "Instrumental" in llm.asked[0]
    assert s["caption"].startswith("synthwave") and "instrumental, no vocals" in s["caption"]
    assert s["lyrics"] == "[instrumental]" and 134 <= s["bpm"] <= 142 and s["style"]["genre"] == "synthwave"
