# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's eyes and ears on the machine: cameras (V4L2) and microphones (PipeWire/PulseAudio, ALSA).

devices()   what is connected, for the owner to choose (AURORA_SENSES_CAMERA / AURORA_SENSES_MIC, "auto" = first)
photo()     one JPEG from the chosen camera (ffmpeg)
record()    N seconds of 16 kHz mono audio from the chosen microphone (ffmpeg)
decode()    audio recorded by the owner's browser (phone or PC) to 16 kHz mono (ffmpeg)
transcribe() speech to text with the local Whisper model (AURORA_STT_MODEL_DIR), on the CPU: the GPUs belong
            to the reasoner and the encoder. Whisper invents text on silence ("Grazie.", repetitions): those
            outputs are reported as no clear speech.

Services run without the desktop session, so PipeWire is reached through XDG_RUNTIME_DIR of the same user.
Nothing leaves the machine.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import numpy as np

from . import sys_config, sys_log

HALLUCINATIONS = {"grazie", "grazie a tutti", "grazie per la visione", "grazie per l'attenzione",
                  "sottotitoli creati dalla comunità amara.org", "sottotitoli a cura di qtss",
                  "thank you", "thanks for watching", "thank you for watching", "you"}
_asr = None


def _env() -> dict:
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return env


def cameras() -> list[dict]:
    """Capture nodes only: a webcam also exposes a metadata node (index 1) that gives no images."""
    out = []
    for d in sorted(Path("/sys/class/video4linux").glob("video*"), key=lambda p: int(p.name[5:])):
        try:
            if (d / "index").read_text().strip() != "0":
                continue
            out.append({"id": f"/dev/{d.name}", "name": (d / "name").read_text().strip().split(":")[0]})
        except OSError:
            continue
    return out


def microphones() -> list[dict]:
    """PipeWire/PulseAudio sources (not the monitors of the outputs)."""
    r = subprocess.run(["pactl", "list", "sources"], capture_output=True, text=True, env=_env(), timeout=10)
    mics, cur = [], {}
    for line in r.stdout.splitlines():
        s = line.strip()
        if s.startswith("Name:") or s.startswith("Nome:"):
            cur = {"id": s.split(":", 1)[1].strip()}
        elif (s.startswith("Description:") or s.startswith("Descrizione:")) and cur:
            cur["name"] = s.split(":", 1)[1].strip()
            if not cur["id"].endswith(".monitor"):
                mics.append(cur)
            cur = {}
    return mics


def devices() -> dict:
    return {"cameras": cameras(), "microphones": microphones()}


def _pick(setting: str, options: list[dict], kind: str) -> str:
    if setting and setting != "auto":
        return setting
    if not options:
        raise RuntimeError(f"no {kind} connected")
    return options[0]["id"]


def photo(cfg: sys_config.Config | None = None) -> bytes:
    cfg = cfg or sys_config.get()
    cam = _pick(cfg["AURORA_SENSES_CAMERA"], cameras(), "camera")
    w, h = (int(x) for x in cfg["AURORA_SENSES_PHOTO_SIZE"].lower().split("x"))
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "v4l2", "-video_size", f"{w}x{h}",
                        "-i", cam, "-frames:v", "1", "-f", "image2", "-c:v", "mjpeg", "-q:v", "3", "-"],
                       capture_output=True, timeout=30, env=_env())
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"camera {cam}: {r.stderr.decode(errors='replace').strip()[-300:]}")
    sys_log.get_logger("senses").info("photo from %s: %d bytes", cam, len(r.stdout))
    return r.stdout


def record(seconds: float, cfg: sys_config.Config | None = None) -> np.ndarray:
    cfg = cfg or sys_config.get()
    seconds = max(1.0, min(float(seconds), cfg["AURORA_SENSES_LISTEN_MAX_S"]))
    mic = _pick(cfg["AURORA_SENSES_MIC"], microphones(), "microphone")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "pulse", "-i", mic, "-t", str(seconds),
                        "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, timeout=seconds + 30, env=_env())
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"microphone {mic}: {r.stderr.decode(errors='replace').strip()[-300:]}")
    sys_log.get_logger("senses").info("recorded %.1f s from %s", seconds, mic)
    return np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768


def decode(data: bytes, cfg: sys_config.Config | None = None) -> np.ndarray:
    """Audio recorded by a browser (WebM/Opus on Android, MP4/AAC on iOS, anything ffmpeg reads) as 16 kHz mono,
    at most AURORA_SENSES_LISTEN_MAX_S. Through a private temporary file: an MP4 keeps its index at the end and
    ffmpeg cannot read it from a pipe."""
    import tempfile
    cfg = cfg or sys_config.get()
    with tempfile.NamedTemporaryFile(prefix="aurora-voice-", suffix=".bin") as f:
        f.write(data)
        f.flush()
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", f.name,
                            "-t", str(cfg["AURORA_SENSES_LISTEN_MAX_S"]), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                           capture_output=True, timeout=120)
    if r.returncode != 0 or not r.stdout:
        raise ValueError(f"audio not readable: {r.stderr.decode(errors='replace').strip()[-200:]}")
    return np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768


def clear_speech(text: str) -> bool:
    """False for Whisper's inventions on silence: known phrases and repetitions."""
    t = re.sub(r"[.!?…]+$", "", text.strip().lower())
    words = t.split()
    if not words or t in HALLUCINATIONS:
        return False
    if len(words) > 6 and len(set(words)) / len(words) < 0.35:
        return False
    return not (len(t) > 20 and len(set(t.replace(" ", ""))) < 4)


def transcribe(audio: np.ndarray, lang: str, cfg: sys_config.Config | None = None) -> dict:
    """{"text", "clear", "seconds", "audio_s"} — the model is loaded once per process, on the CPU."""
    global _asr
    cfg = cfg or sys_config.get()
    import torch
    from transformers import pipeline
    if _asr is None:
        torch.set_num_threads(min(8, os.cpu_count() or 4))
        _asr = pipeline("automatic-speech-recognition", model=str(cfg.path("AURORA_STT_MODEL_DIR")), device="cpu",
                        dtype=torch.float32)
    sec = len(audio) / 16000
    t0 = time.time()
    out = _asr({"raw": audio, "sampling_rate": 16000},
               generate_kwargs={"task": "transcribe", "language": lang, "max_new_tokens": int(8 + sec * 6)})
    text = out["text"].strip()
    res = {"text": text, "clear": clear_speech(text), "seconds": round(time.time() - t0, 1), "audio_s": round(sec, 1)}
    sys_log.get_logger("senses").info("transcribed %.1f s of audio in %.1f s (clear: %s)", sec, res["seconds"], res["clear"])
    return res
