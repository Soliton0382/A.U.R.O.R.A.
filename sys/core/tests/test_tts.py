# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own voice (owner, 2026-10-06): Piper as a program of its own, the voice by language, a sentence spoken once."""
import os

import pytest

from aurora import mdl_tts


def fake(tmp_path, cfg):
    calls = tmp_path / "calls"
    b = tmp_path / "piper"
    b.write_text(f'#!/bin/sh\necho x >> {calls}\nwhile [ "$1" ]; do [ "$1" = -f ] && cat > "$2" && exit 0; shift; done\n')
    b.chmod(0o755)
    v = tmp_path / "voices" / mdl_tts.VOICES["it"]
    v.parent.mkdir(parents=True)
    v.write_bytes(b"onnx")
    v.with_suffix(".onnx.json").write_text("{}")
    cfg.values.update(AURORA_TTS=True, AURORA_TTS_BIN=str(b), AURORA_TTS_DIR=str(tmp_path / "voices"), AURORA_TTS_ENGINE="piper")
    return calls


@pytest.mark.skipif(os.name == "nt", reason="a stand-in voice program without an extension: Aurora's voice is not on Windows yet")
def test_spoken_by_the_program_and_kept(cfg, tmp_path):
    calls = fake(tmp_path, cfg)
    assert mdl_tts.available(cfg) == {"enabled": True, "languages": ["it"]}
    assert mdl_tts.speak(cfg, "Buongiorno!\n  Ecco la mia notte.", "it_IT") == b"Buongiorno! Ecco la mia notte."
    assert mdl_tts.speak(cfg, "Buongiorno! Ecco la mia notte.", "it-IT") == b"Buongiorno! Ecco la mia notte."
    assert calls.read_text().count("x") == 1                    # the second time from the kept audio
    with pytest.raises(RuntimeError):
        mdl_tts.speak(cfg, "Good morning", "en")                  # no English voice here
    with pytest.raises(ValueError):
        mdl_tts.speak(cfg, "   ", "it")
    cfg.values["AURORA_TTS"] = False
    assert mdl_tts.available(cfg)["enabled"] is False


@pytest.mark.skipif(os.name == "nt", reason="a stand-in voice program without an extension: Aurora's voice is not on Windows yet")
def test_the_natural_voice_first_piper_when_it_fails_or_the_gpu_is_busy(cfg, tmp_path, monkeypatch):
    """Owner, 2026-10-06: «la 5! è la voce di Aurora» — Qwen3-TTS, and the voice never goes missing."""
    calls = fake(tmp_path, cfg)
    cfg.values["AURORA_TTS_ENGINE"] = "qwen"
    monkeypatch.setattr(mdl_tts, "qwen_installed", lambda c: True)
    said = []
    monkeypatch.setattr("aurora.mdl_image.free_gb", lambda gpu: 8.0)
    monkeypatch.setattr(mdl_tts, "_qwen", lambda c, text, lang, place: said.append((text, place)) or b"natural")
    assert mdl_tts.speak(cfg, "Ciao.", "it") == b"natural" and not calls.exists()
    assert mdl_tts.speak(cfg, "Ciao.", "it") == b"natural" and said == [("Ciao.", "cuda:1")]   # kept
    cfg.values.update(AURORA_TTS_ENGINE="piper", AURORA_VIDEO_VOICE="qwen")        # the owner's choice, 2026-10-06
    assert mdl_tts.speak(cfg, "In chat.", "it") == b"In chat."                      # Piper
    assert mdl_tts.speak(cfg, "Nel video.", "it", use="video") == b"natural" and said[-1] == ("Nel video.", "cpu")
    cfg.values["AURORA_TTS_ENGINE"] = "qwen"
    def broken(c, text, lang, place):
        raise RuntimeError("out of memory")
    monkeypatch.setattr(mdl_tts, "_qwen", broken)
    assert mdl_tts.speak(cfg, "Seconda frase.", "it") == b"Seconda frase."              # Piper said it
    monkeypatch.setattr("aurora.mdl_image.gpu_busy", lambda c: True)                  # a picture is being painted
    assert mdl_tts.qwen_ready(cfg, "cuda:1") is False and mdl_tts.qwen_ready(cfg, "cpu") is True


def test_the_natural_voice_never_takes_the_answers_memory(cfg, monkeypatch):
    """C173: its 3.5 GB left the re-ranker without memory and a run failed."""
    cfg.values.update(AURORA_TTS_ENGINE="qwen", AURORA_TTS_QWEN_MIN_FREE_GB=5.0)
    monkeypatch.setattr(mdl_tts, "qwen_installed", lambda c: True)
    monkeypatch.setattr("aurora.mdl_image.gpu_busy", lambda c: False)
    monkeypatch.setattr("aurora.mdl_image.free_gb", lambda gpu: 4.0)             # 2026-10-06 on GPU 1
    assert mdl_tts.qwen_ready(cfg, "cuda:1") is False
    monkeypatch.setattr("aurora.mdl_image.free_gb", lambda gpu: 6.0)
    assert mdl_tts.qwen_ready(cfg, "cuda:1") is True
    monkeypatch.setattr(mdl_tts, "BUSY", [lambda: True])                         # a run is answering
    assert mdl_tts.qwen_ready(cfg, "cuda:1") is False


def test_a_gpu_job_is_seen_without_waiting(cfg):
    from aurora import mdl_image
    assert mdl_image.gpu_busy(cfg) is False
    with mdl_image.gpu_lock(cfg, 1, "a test"):
        assert mdl_image.gpu_busy(cfg) is True
    assert mdl_image.gpu_busy(cfg) is False
