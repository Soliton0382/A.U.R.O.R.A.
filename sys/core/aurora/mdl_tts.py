# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own voice, made on this machine (owner, 2026-10-06: 🔊 on the good morning said "no Italian voice").

The WebUI reads aloud with the device's own voices; when a device has none (Chrome on Linux often has only online
ones, which would send the text to the browser's maker) it asks here. Piper (rhasspy, piper-tts) speaks on the CPU:
measured 12.7 s of speech in 0.95 s, 248 MB. Piper is GPL-3: it runs as a program of its own (AURORA_TTS_BIN, its own
environment in sys/runtime/piper made by script/sys_tts_install.sh), never imported into Aurora's code. Voices
(config/models.json "tts", rhasspy/piper-voices, MIT): it_IT paola (dataset CC0), en_US ljspeech (public domain).
A sentence already spoken is kept (the user's state, at most CACHE files): the good morning played again costs nothing.
"""
from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

from . import sys_config

VOICES = {"it": "it/it_IT/paola/medium/it_IT-paola-medium.onnx", "en": "en/en_US/ljspeech/medium/en_US-ljspeech-medium.onnx"}
MAX_CHARS = 6000
CACHE = 60


def _bin(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_TTS_BIN")


def voice(cfg: sys_config.Config, lang: str) -> Path | None:
    rel = VOICES.get((lang or "it")[:2].lower())
    p = cfg.path("AURORA_TTS_DIR") / rel if rel else None
    return p if p and p.is_file() and p.with_suffix(".onnx.json").is_file() else None


def available(cfg: sys_config.Config) -> dict:
    """What this machine can say: the engine and the languages with a voice."""
    ok = bool(cfg["AURORA_TTS"]) and _bin(cfg).is_file()
    return {"enabled": ok, "languages": [k for k in VOICES if ok and voice(cfg, k)]}


def _cache_dir(cfg: sys_config.Config) -> Path:
    from . import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user) / "tts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def speak(cfg: sys_config.Config, text: str, lang: str) -> bytes:
    """The text as WAV audio (22 kHz mono). ValueError: nothing to say; RuntimeError: no engine or voice here."""
    text = " ".join(str(text or "").split())[:MAX_CHARS]
    if not text:
        raise ValueError("nothing to say")
    v = voice(cfg, lang)
    if not (cfg["AURORA_TTS"] and _bin(cfg).is_file() and v):
        raise RuntimeError("no voice on this machine: run script/sys_tts_install.sh")
    key = hashlib.sha256(f"{v.name}\n{text}".encode()).hexdigest()[:32]
    cached = _cache_dir(cfg) / f"{key}.wav"
    if cached.is_file():
        cached.touch()
        return cached.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.wav"
        r = subprocess.run([str(_bin(cfg)), "-m", str(v), "-f", str(out)], input=text.encode(), capture_output=True,
                           timeout=120)
        if r.returncode != 0 or not out.is_file():
            raise RuntimeError(f"piper failed: {r.stderr.decode(errors='replace')[-300:]}")
        data = out.read_bytes()
    cached.write_bytes(data)
    old = sorted(_cache_dir(cfg).glob("*.wav"), key=lambda p: p.stat().st_mtime)[:-CACHE]
    for p in old:                                      # the least recently played go first
        p.unlink(missing_ok=True)
    return data
