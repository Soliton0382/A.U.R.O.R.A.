# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A song from an idea (aud_song; owner, 2026-10-27): the reasoner writes it, the music model sings it with the
reasoner out of the GPU, and the reasoner always comes back — even when the song fails."""
import contextlib
import json
from types import SimpleNamespace

import pytest

from aurora import aud_analysis as A, aud_song as S, mdl_image


class LLM:
    def __init__(self, text):
        self.text, self.asked = text, []

    def complete(self, system, user, max_tokens):
        self.asked.append(user)
        return SimpleNamespace(text=self.text)


def test_the_reasoner_writes_title_caption_and_lyrics_or_keeps_the_users():
    llm = LLM('ok {"title": "Abyss", "caption": "90s trance, female vocalist, 138 BPM", "lyrics": "[verse]\\nIn the dark wood"}')
    s = S.write(llm, "a 90s trance on Dante's Inferno", "en")
    assert s == {"title": "Abyss", "caption": "90s trance, female vocalist, 138 BPM", "lyrics": "[verse]\nIn the dark wood",
                 "language": "en"}
    assert "LANGUAGE: English" in llm.asked[0]
    mine = S.write(llm, "the same", "it", lyrics="[chorus]\nmio testo")
    assert mine["lyrics"] == "[chorus]\nmio testo" and "Use these lyrics" in llm.asked[1]
    with pytest.raises(RuntimeError):
        S.write(LLM("no json here"), "x", "en")


@pytest.fixture
def stage(cfg, monkeypatch, tmp_path):
    home, models = tmp_path / "ace", tmp_path / "weights"
    home.mkdir(); (home / "pyproject.toml").write_text("")
    models.mkdir(); (models / "acestep-v15-turbo").mkdir()
    cfg.values.update(AURORA_SONG_DIR=str(home), AURORA_SONG_MODELS=str(models), AURORA_SONG_PORT=8011,
                      AURORA_SONG_TIMEOUT_S=120, AURORA_SONG_THINKING=True, AURORA_SONG_CMD="uv run acestep-api")
    units = []
    monkeypatch.setattr(mdl_image, "gpu_lock", lambda c, w, what: contextlib.nullcontext())
    monkeypatch.setattr(mdl_image, "_active", lambda u: True)
    monkeypatch.setattr(mdl_image, "_unit", lambda verb, u: units.append((verb, u)))
    monkeypatch.setattr(mdl_image, "_wait", lambda cond, limit, step=2.0: cond())
    monkeypatch.setattr(mdl_image, "_llm_ok", lambda c: True)
    proc = SimpleNamespace(poll=lambda: None, terminate=lambda: units.append(("terminate", "ace")), wait=lambda t: 0)
    monkeypatch.setattr(S, "_server", lambda c, key, port: proc)
    monkeypatch.setattr(A, "load", lambda p, s=None: "audio")
    monkeypatch.setattr(A, "save", lambda x, out, title="": out.write_bytes(b"mp3"))
    return units


def test_the_song_is_sung_with_the_reasoner_out_and_back(cfg, stage, monkeypatch, tmp_path):
    sent = {}

    def post(url, headers=None, timeout=None, json=None):
        if url.endswith("/release_task"):
            sent.update(json)
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": {"task_id": "t1"}})
        return SimpleNamespace(json=lambda: {"data": [{"status": 1, "result": '[{"file": "/v1/audio?path=x.mp3"}]'}]})
    monkeypatch.setattr(S.httpx, "post", post)
    monkeypatch.setattr(S.httpx, "get", lambda url, headers=None, timeout=None: SimpleNamespace(
        status_code=200, raise_for_status=lambda: None, content=b"raw"))
    song = {"title": "Abyss", "caption": "90s trance", "lyrics": "[verse]\nla", "language": "en"}
    out = tmp_path / "abyss.mp3"
    r = S.sing(cfg, song, 180, out)
    assert r["swap"] is True and out.read_bytes() == b"mp3"
    assert stage == [("stop", "aurora-llm"), ("terminate", "ace"), ("start", "aurora-llm")]
    assert sent["vocal_language"] == "en" and sent["audio_duration"] == 180 and sent["thinking"] is True
    assert json.loads(out.with_suffix(".song.json").read_text())["title"] == "Abyss"


def test_a_failed_song_still_brings_the_reasoner_back(cfg, stage, monkeypatch, tmp_path):
    def post(url, headers=None, timeout=None, json=None):
        raise S.httpx.ConnectError("refused")
    monkeypatch.setattr(S.httpx, "post", post)
    monkeypatch.setattr(S.httpx, "get", lambda *a, **k: SimpleNamespace(status_code=200))
    with pytest.raises(S.httpx.ConnectError):
        S.sing(cfg, {"title": "x", "caption": "c", "lyrics": "l", "language": "en"}, 60, tmp_path / "x.mp3")
    assert stage[-1] == ("start", "aurora-llm") and ("stop", "aurora-llm") in stage


def test_not_installed_says_where(cfg, tmp_path):
    cfg.values.update(AURORA_SONG_DIR=str(tmp_path / "none"), AURORA_SONG_MODELS=str(tmp_path / "none2"))
    have = S.installed(cfg)
    assert have["code"] is False and have["weights"] is False
    with pytest.raises(RuntimeError, match="not installed"):
        S.sing(cfg, {"title": "x", "caption": "c", "lyrics": "l", "language": "en"}, 60, tmp_path / "x.mp3")
