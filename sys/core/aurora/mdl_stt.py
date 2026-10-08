# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Speech to text with the local Whisper model (AURORA_STT_MODEL_DIR), on the CPU — run inside aurora-models.

Moved out of the API's process on 8 Oct 2026 (M145): the API holds faiss (the vault's index) and loading torch beside it
put two OpenMP runtimes in one process — on a Mac the wheels of faiss and torch each carry a libomp, and the second
aborts the process (SIGABRT at torch's import, seen on a real Mac). aurora-models already holds torch and no faiss;
the API asks it over HTTP (sns_av.transcribe), as it asks for embeddings. The model is loaded at the first request.

transcribe(audio, lang)  {"text", "clear", "seconds", "audio_s"} of a short recording (a voice message)
segments(audio, lang)    [(start, end, text)] of a long one (a video's track), 30 s windows with timestamps
"""
from __future__ import annotations

import os
import threading
import time

import numpy as np

from . import sys_config, sys_log
from .sns_av import clear_speech

_asr = None
_lock = threading.Lock()


def _load(cfg: sys_config.Config) -> None:
    global _asr
    if _asr is None:
        import torch
        from transformers import pipeline
        torch.set_num_threads(min(8, os.cpu_count() or 4))
        _asr = pipeline("automatic-speech-recognition", model=str(cfg.path("AURORA_STT_MODEL_DIR")), device="cpu",
                        dtype=torch.float32)


def transcribe(audio: np.ndarray, lang: str, cfg: sys_config.Config) -> dict:
    with _lock:
        _load(cfg)
        sec = len(audio) / 16000
        t0 = time.time()
        out = _asr({"raw": audio, "sampling_rate": 16000},
                   generate_kwargs={"task": "transcribe", "language": lang, "max_new_tokens": int(8 + sec * 6)})
    text = out["text"].strip()
    res = {"text": text, "clear": clear_speech(text), "seconds": round(time.time() - t0, 1), "audio_s": round(sec, 1)}
    sys_log.get_logger("senses").info("transcribed %.1f s of audio in %.1f s (clear: %s)", sec, res["seconds"], res["clear"])
    return res


def segments(audio: np.ndarray, lang: str, cfg: sys_config.Config) -> list[tuple[float, float, str]]:
    with _lock:
        _load(cfg)
        sec = len(audio) / 16000
        t0 = time.time()
        out = _asr({"raw": audio, "sampling_rate": 16000}, chunk_length_s=30, return_timestamps=True,
                   generate_kwargs={"task": "transcribe", "language": lang})
    segs = []
    for c in out.get("chunks", []):
        start, end = c.get("timestamp") or (0.0, None)
        text = (c.get("text") or "").strip()
        if text and clear_speech(text):
            segs.append((float(start or 0.0), float(end if end is not None else sec), text))
    sys_log.get_logger("senses").info("transcribed %.1f s of audio in %d segments in %.1f s", sec, len(segs), time.time() - t0)
    return segs
