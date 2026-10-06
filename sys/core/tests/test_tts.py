# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own voice (owner, 2026-10-06): Piper as a program of its own, the voice by language, a sentence spoken once."""
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
    cfg.values.update(AURORA_TTS=True, AURORA_TTS_BIN=str(b), AURORA_TTS_DIR=str(tmp_path / "voices"))
    return calls


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
