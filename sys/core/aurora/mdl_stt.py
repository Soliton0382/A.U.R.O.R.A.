# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Speech to text with the local Whisper model (AURORA_STT_MODEL_DIR), on a GPU with room or the CPU — run inside
aurora-models.

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


FREE_GB = 3.0                  # free memory a GPU needs at load: the model takes 1.9 GB (M204), the embedder its batches


def free_bytes() -> list[tuple[int, int]]:
    """(free bytes, index) of each GPU, from nvidia-smi: torch.cuda.mem_get_info(i) opened a CUDA context on every GPU
    it asked, and the one Whisper did not take kept 128 MiB for nothing beside the reasoner (C413). [] = none to ask."""
    import subprocess
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10, check=True).stdout
        return [(int(m) * 2**20, int(i)) for i, m in (line.split(",") for line in out.strip().splitlines())]
    except Exception:                                 # noqa: BLE001 — a GPU that cannot be asked: the CPU, as before
        return []


def place(cfg: sys_config.Config) -> str:
    """Where Whisper runs: «cpu», or with AURORA_STT_DEVICE=auto the GPU with the most free memory if it has FREE_GB
    (M204: 0.14 s a sentence against 5.6 s on the CPU, the same words); the CPU when no GPU has room."""
    if str(cfg["AURORA_STT_DEVICE"]) != "auto":
        return "cpu"
    try:
        import torch
        if not torch.cuda.is_available():             # asks the driver for a count, opens no context
            return "cpu"
    except Exception:                                 # noqa: BLE001
        return "cpu"
    free = free_bytes()
    room, best = max(free, default=(0, 0))
    return f"cuda:{best}" if room >= FREE_GB * 1e9 else "cpu"


def _load(cfg: sys_config.Config) -> None:
    global _asr
    if _asr is None:
        import torch
        from transformers import pipeline
        torch.set_num_threads(min(8, os.cpu_count() or 4))
        where = place(cfg)
        _asr = pipeline("automatic-speech-recognition", model=str(cfg.path("AURORA_STT_MODEL_DIR")), device=where,
                        dtype=torch.float32 if where == "cpu" else torch.float16)
        sys_log.get_logger("senses").info("whisper loaded on %s", where)


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
