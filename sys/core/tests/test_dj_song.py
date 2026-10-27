# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A song from an idea (aud_song; owner, 2026-10-27): the reasoner writes it, the music model sings it with the
reasoner out of the GPU, and the reasoner always comes back — even when the song fails."""
import contextlib
import json
from types import SimpleNamespace

import pytest

from aurora import aud_analysis as A, aud_song as S, mdl_image
from aurora.mdl_llm import Completion


class LLM:
    def __init__(self, text):
        self.text, self.asked = text, []

    def complete(self, system, user, max_tokens):
        self.asked.append(user)
        return Completion(self.text, "", 10, 0.1, False)      # the real shape (it was .text: C408)


def test_the_reasoner_writes_title_caption_and_lyrics_or_keeps_the_users():
    llm = LLM('ok {"title": "Abyss", "caption": "90s trance, female vocalist, 138 BPM", "lyrics": "[verse]\\nIn the dark wood"}')
    s = S.write(llm, "a 90s trance on Dante's Inferno", "en")
    assert s == {"title": "Abyss", "caption": "90s trance, female vocalist, 138 BPM", "lyrics": "[verse]\nIn the dark wood",
                 "language": "en", "style": {}}
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
    monkeypatch.setattr(A, "save", lambda x, out, title="", made="": out.write_bytes(made.encode()))
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
    assert r["swap"] is True and out.read_bytes() == b"AI-generated song"
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


def test_the_command_finds_uv_in_the_users_own_folder(cfg, monkeypatch, tmp_path):
    """The services' PATH lacks ~/.local/bin, where uv installs itself (the first song: «No such file: 'uv'»)."""
    (tmp_path / ".local/bin").mkdir(parents=True)
    (tmp_path / ".local/bin/uv").write_text("")
    monkeypatch.setattr(S.Path, "home", lambda: tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: None)
    cfg.values["AURORA_SONG_CMD"] = "uv run acestep-api"
    assert S.command(cfg) == [str(tmp_path / ".local/bin/uv"), "run", "acestep-api"]
    cfg.values["AURORA_SONG_CMD"] = "/opt/x/uv run acestep-api"
    assert S.command(cfg)[0] == "/opt/x/uv"


def test_the_server_gets_the_planner_by_its_whole_path(cfg, monkeypatch, tmp_path):
    """ACE-Step looked for acestep-5Hz-lm-1.7B in its own checkpoints/ (the third song): the whole path is given."""
    models = tmp_path / "w"
    (models / "acestep-5Hz-lm-1.7B").mkdir(parents=True)
    cfg.values.update(AURORA_SONG_MODELS=str(models), AURORA_SONG_DIR=str(tmp_path), AURORA_SONG_CMD="uv run acestep-api")
    seen = {}
    monkeypatch.setattr(S.subprocess, "Popen", lambda cmd, cwd=None, env=None, **k: seen.update(env) or "proc")
    S._server(cfg, "k", 8011)
    assert seen["ACESTEP_LM_MODEL_PATH"] == str(models / "acestep-5Hz-lm-1.7B")
    assert seen["ACESTEP_API_HOST"] == "127.0.0.1" and seen["HF_HUB_OFFLINE"] == "1"


def test_everything_of_the_music_model_stays_inside_aurora(cfg, tmp_path):
    """Owner, 27 Oct: «tutto dentro la cartella di installazione di aurora»: uv's cache and Python, ACE-Step's caches."""
    env = S.inside(tmp_path)
    assert all(v.startswith(str(tmp_path / "sys" / "runtime")) for k, v in env.items() if k.endswith(("DIR", "HOME", "CACHE")))
    assert env["UV_PYTHON_PREFERENCE"] == "only-managed" and env["UV_NO_CONFIG"] == "1"
    own = cfg.root / "sys" / "runtime" / "uv" / "bin" / "uv"
    own.parent.mkdir(parents=True)
    own.write_text("")
    cfg.values["AURORA_SONG_CMD"] = "uv run --no-sync acestep-api"
    assert S.command(cfg) == [str(own), "run", "--no-sync", "acestep-api"]   # Aurora's own uv, never the user's


def test_songs_are_offered_where_the_gpu_allows():
    """The installer offers them by default from a 4 GB GPU (under 10 GB ACE-Step offloads by itself); not without one."""
    from aurora import sys_features as F
    gpu = lambda gb: {"gpus": [{"vram_gb": gb}], "ram_gb": 32}   # noqa: E731
    assert F.GROUPS["songs"]["default"] is True
    assert F.fits(gpu(16), "songs")[0] and F.fits(gpu(6), "songs")[0]
    assert not F.fits(gpu(3), "songs")[0] and not F.fits({"gpus": [], "ram_gb": 64}, "songs")[0]


def test_more_genres_the_mix_and_an_inspiration_in_words():
    """Owner, 28 Oct: vocal trance, cosmic instrumental trance, 2000s techno, metal; each element of the arrangement
    0 (left out: the negative prompt) to 3 (up front); a track's style in words, never its name in the caption."""
    from aurora import aud_song_style as S
    for g in ("vocal_trance", "cosmic_trance", "techno2000", "hard_trance", "metal", "symphonic_metal"):
        assert g in S.GENRES and S.resolve({"genre": g})["tags"]
    assert 134 <= S.resolve({"genre": "vocal_trance"})["bpm"] <= 140                 # its own tempo when «auto»
    assert 74 <= S.resolve({"genre": "vocal_trance", "tempo": "slow"})["bpm"] <= 82   # a tempo chosen wins
    r = S.resolve({"genre": "cosmic_trance", "mix": {"lead": 3, "guitars": 0, "pads": 2, "piano": 1}})
    assert "prominent supersaw lead up front, supersaw lead-driven" in r["tags"] and "subtle piano" in r["tags"]
    assert r["negative"] == "distorted electric guitars" and "pads" not in r["brief"].split("mix:")[1]   # 2 is not kept
    assert S.resolve({"mix": {"vocals": 0}})["instrumental"]
    insp = S.resolve({"inspiration": "  un brano   trance del 2000  "})
    assert "STYLE of «un brano trance del 2000»" in insp["brief"] and "never name" in insp["brief"]
    assert {o["id"] for o in S.options("it")["mix"]} == set(S.MIX)
    for bad in ({"mix": {"lead": 4}}, {"mix": {"cowbell": 3}}, {"mix": "lead"}):
        with pytest.raises(ValueError):
            S.check(bad)


def test_the_music_model_s_own_fields():
    """Owner, 28 Oct: the model's parameters in the page — those that act on the turbo model: the time signature, the
    steps (1-20 on turbo), the planner's CFG; guidance_scale is the base model's only, so it is not offered."""
    from aurora import aud_song_style as S
    r = S.resolve({"meter": "3", "steps": "fine", "adherence": "strict"})
    assert r["time_signature"] == "3" and r["inference_steps"] == 14 and r["lm_cfg_scale"] == 3.5 and "3/4" in r["brief"]
    assert all(1 <= v[2] <= 20 for v in S.STEPS.values()) and "guidance" not in " ".join(S.AXES)
    assert {o["id"] for o in S.options("en")["meter"]} == {"2", "3", "4", "6"}
