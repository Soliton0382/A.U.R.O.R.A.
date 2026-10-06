# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's narrated videos (owner, 2026-10-06): a script only from the verified answer, sentences it does not support
cut, subtitles in time with the voice, a scene made by ffmpeg."""
import io
import shutil
import subprocess
import wave
from types import SimpleNamespace

import pytest

from aurora import kno_story


def llm(*outs):
    it = iter(outs)
    return SimpleNamespace(complete=lambda s, u, n: SimpleNamespace(answer=next(it)))


def test_the_scenes_are_read_from_the_model_and_cleaned():
    out = ('Ecco: [{"say": "La luce si piega [2].", "image": "a prism, cinematic"}, {"say": "", "image": "x"}, '
           '{"say": "Il cielo è blu [1, 3].", "image": "blue sky"}] fine')
    got = kno_story.scenes(llm(out), "risposta")
    assert got == [{"say": "La luce si piega.", "image": "a prism, cinematic"}, {"say": "Il cielo è blu.", "image": "blue sky"}]
    assert kno_story.scenes(llm("non JSON"), "x") == []


def test_what_the_answer_does_not_say_is_cut():
    items = [{"say": "Il cielo è blu. La Luna è di formaggio.", "image": "a"}, {"say": "Lo scattering di Rayleigh.", "image": "b"},
             {"say": "Einstein lo scoprì nel 1950.", "image": "c"}]
    kept, cut = kno_story.check(llm("2, 4"), "risposta", items)
    assert [k["say"] for k in kept] == ["Il cielo è blu.", "Lo scattering di Rayleigh."]
    assert cut == ["La Luna è di formaggio.", "Einstein lo scoprì nel 1950."]
    assert kno_story.check(llm("NONE"), "r", items)[0] == items


def test_subtitles_follow_the_voice():
    srt = kno_story.subtitles([("Uno. Due due.", 4.0), ("Tre.", 2.0)])
    assert "1\n00:00:00,000 --> 00:00:01,333\nUno." in srt                      # 4 of 12 characters of 4 s
    assert "00:00:01,333 --> 00:00:04,000\nDue due." in srt and "00:00:04,000 --> 00:00:06,000\nTre." in srt


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_a_scene_is_a_clip_of_its_words(tmp_path):
    from PIL import Image
    Image.new("RGB", (96, 160), (30, 60, 120)).save(tmp_path / "p.png")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(b"\0\0" * 22050)
    (tmp_path / "v.wav").write_bytes(buf.getvalue())
    assert kno_story._seconds(buf.getvalue()) == 1.0
    kno_story._clip(tmp_path / "p.png", tmp_path / "v.wav", 1.6, tmp_path / "c.mp4")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "csv=p=0",
                            str(tmp_path / "c.mp4")], capture_output=True, text=True).stdout
    assert "video,1080,1920" in probe and "audio" in probe


def test_the_music_follows_the_mood_and_is_credited(cfg, monkeypatch, tmp_path):
    monkeypatch.setattr(kno_story, "music_dir", lambda c: tmp_path)
    assert kno_story.pick_music(cfg, "calm") is None                         # nothing downloaded: a video without music
    tracks = kno_story.catalog()["tracks"]
    assert all(t["license"].lower().startswith(("cc0", "public domain")) for t in tracks)
    wonder = next(t for t in tracks if t["mood"] == "wonder")
    (tmp_path / kno_story.track_name(wonder)).write_bytes(b"ogg")
    assert kno_story.pick_music(cfg, "wonder")[1] == wonder
    assert kno_story.pick_music(cfg, "calm")[1] == wonder                    # another mood rather than silence
    assert kno_story.mood(llm("Mood: Mystery."), "Paradosso di Zenone", "x") == "mystery"
    assert kno_story.mood(llm("boh"), "t", "x") == "calm"
    post = kno_story._post("Laser", [{"say": "Ciao."}], [{"title": "Laser"}], cfg, wonder)
    assert "Musica: " + wonder["credit"] in post and "Wikimedia Commons" in post
