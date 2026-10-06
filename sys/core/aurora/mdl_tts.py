# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own voice, made on this machine (owner, 2026-10-06: 🔊 on the good morning said "no Italian voice").

The WebUI reads aloud with the device's own voices; when a device has none (Chrome on Linux often has only online
ones, which would send the text to the browser's maker) it asks here. Piper (rhasspy, piper-tts) speaks on the CPU:
measured 12.7 s of speech in 0.95 s, 248 MB. Piper is GPL-3: it runs as a program of its own (AURORA_TTS_BIN, its own
environment in sys/runtime/piper made by script/sys_tts_install.sh), never imported into Aurora's code. Voices
(config/models.json "tts", rhasspy/piper-voices, MIT): it_IT paola (dataset CC0), en_US ljspeech (public domain).
A sentence already spoken is kept (the user's state, at most CACHE files): the good morning played again costs nothing.

The natural voice (owner, 2026-10-06, "la 5! è la voce di Aurora"): with AURORA_TTS_ENGINE=qwen, Qwen3-TTS 0.6B on
AURORA_TTS_GPU clones a Piper voice from a reference clip (AURORA_TTS_QWEN_REF: the owner's own, in the private state
folder, never published — owner, 2026-10-06: «almeno la voce la vorrei solo mia») and says the text with a natural rhythm
(M122: 16.1 s of speech in 11.6 s on the GPU, 61 s on the CPU). It runs in a process of its own
(script/tts_qwen_worker.py, its own transformers in sys/runtime/qwen-tts), one per place: on the GPU for the chat, on
the CPU for the videos (slow, but it takes nothing from anyone). The GPU it shares with the reasoner and the re-ranker:
on 2026-10-06 the voice's 3.5 GB left the re-ranker without memory and a run failed (C173). So it is loaded only with
AURORA_TTS_QWEN_MIN_FREE_GB free on that GPU and no run going (BUSY), closed when a run starts, after
AURORA_TTS_QWEN_IDLE_S of silence and before any GPU job (mdl_image.gpu_lock); otherwise, or when it fails, Piper
speaks — the voice never goes missing. The owner's choice (2026-10-06): the chat with Piper tuned steadier and slower (sample 3), the videos with the
natural voice (sample 5): two voices close to each other, one per purpose (AURORA_TTS_ENGINE, AURORA_VIDEO_VOICE).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import sys_config, sys_log

VOICES = {"it": "it/it_IT/paola/medium/it_IT-paola-medium.onnx", "en": "en/en_US/ljspeech/medium/en_US-ljspeech-medium.onnx"}
MAX_CHARS = 6000
CACHE = 60
ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "script" / "tts_qwen_worker.py"
_lock = threading.Lock()
_workers: dict[str, dict] = {}                         # place -> {"proc", "last"} while the natural voice is loaded
BUSY: list = []                                        # callables: True while the answer pipeline needs the GPU (api.core)


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


def speak(cfg: sys_config.Config, text: str, lang: str, use: str = "chat") -> bytes:
    """The text as WAV audio. `use`: "chat" (AURORA_TTS_ENGINE; the natural voice on the GPU when it has room) or
    "video" (AURORA_VIDEO_VOICE; the natural voice on the CPU: a video may wait).
    ValueError: nothing to say; RuntimeError: no engine or voice here."""
    text = " ".join(str(text or "").split())[:MAX_CHARS]
    if not text:
        raise ValueError("nothing to say")
    v = voice(cfg, lang)
    if not (cfg["AURORA_TTS"] and _bin(cfg).is_file() and v):
        raise RuntimeError("no voice on this machine: run script/sys_tts_install.sh")
    tune = [str(float(cfg[k])) for k in ("AURORA_TTS_LENGTH", "AURORA_TTS_NOISE", "AURORA_TTS_NOISE_W", "AURORA_TTS_PAUSE")]
    place = "cpu" if use == "video" else f"cuda:{int(cfg['AURORA_TTS_GPU'])}"
    natural = cfg["AURORA_VIDEO_VOICE" if use == "video" else "AURORA_TTS_ENGINE"] == "qwen" and qwen_ready(cfg, place)
    engine = "qwen" if natural else v.name
    key = hashlib.sha256(f"{engine}\n{' '.join(tune)}\n{text}".encode()).hexdigest()[:32]     # a new tuning, a new clip
    cached = _cache_dir(cfg) / f"{key}.wav"
    if cached.is_file():
        cached.touch()
        return cached.read_bytes()
    data = None
    if natural:
        try:
            data = _qwen(cfg, text, lang, place)
        except Exception as e:  # noqa: BLE001 — the natural voice failed: Piper says it, and it is logged
            sys_log.get_logger("tts").warning("natural voice failed, Piper instead: %s", e)
            key = hashlib.sha256(f"{v.name}\n{' '.join(tune)}\n{text}".encode()).hexdigest()[:32]
            cached = _cache_dir(cfg) / f"{key}.wav"
    if data is None:
        data = _piper(cfg, text, v, tune)
    cached.write_bytes(data)
    old = sorted(_cache_dir(cfg).glob("*.wav"), key=lambda p: p.stat().st_mtime)[:-CACHE]
    for p in old:                                      # the least recently played go first
        p.unlink(missing_ok=True)
    return data


def _piper(cfg: sys_config.Config, text: str, v: Path, tune: list[str]) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.wav"
        r = subprocess.run([str(_bin(cfg)), "-m", str(v), "-f", str(out), "--length-scale", tune[0], "--noise-scale", tune[1],
                            "--noise-w-scale", tune[2], "--sentence-silence", tune[3]], input=text.encode(), capture_output=True,
                           timeout=120)
        if r.returncode != 0 or not out.is_file():
            raise RuntimeError(f"piper failed: {r.stderr.decode(errors='replace')[-300:]}")
        return out.read_bytes()


# ---- the natural voice (Qwen3-TTS) ------------------------------------------------------------------------------------
def _runtime(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_TTS_QWEN_RUNTIME")


def ref(cfg: sys_config.Config) -> Path:
    """The clip the natural voice clones (its words in the .txt beside it): the owner's, never in the repository."""
    return cfg.path("AURORA_TTS_QWEN_REF")


def qwen_installed(cfg: sys_config.Config) -> bool:
    return ((_runtime(cfg) / "qwen_tts").is_dir() and (cfg.path("AURORA_TTS_QWEN_DIR") / "model.safetensors").is_file()
            and ref(cfg).is_file() and ref(cfg).with_suffix(".txt").is_file())


def qwen_ready(cfg: sys_config.Config, place: str = "cuda:1") -> bool:
    """The natural voice may speak now: installed; on a GPU only with room for it and no run going (C173)."""
    if not qwen_installed(cfg):
        return False
    if place == "cpu":
        return True
    from . import mdl_image
    if mdl_image.gpu_busy(cfg) or any(b() for b in BUSY):
        return False
    w = _workers.get(place)
    if w and w["proc"].poll() is None:
        return True                                    # already loaded: its memory is counted
    return mdl_image.free_gb(int(place.split(":")[1])) >= float(cfg["AURORA_TTS_QWEN_MIN_FREE_GB"])


def _start(cfg: sys_config.Config, place: str) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(_runtime(cfg)), "HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"}
    proc = subprocess.Popen([sys.executable, str(WORKER), "--model", str(cfg.path("AURORA_TTS_QWEN_DIR")), "--ref", str(ref(cfg)),
                             "--ref-text", str(ref(cfg).with_suffix(".txt")), "--device", place],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
    first = _reply(proc, 180)
    if not first.get("ready"):
        proc.kill()
        raise RuntimeError(f"the natural voice did not start: {first}")
    sys_log.get_logger("tts").info("natural voice loaded on %s in %s s", place, first.get("load_s"))
    threading.Thread(target=_idle_close, args=(place, proc, float(cfg["AURORA_TTS_QWEN_IDLE_S"])), daemon=True,
                     name="tts-idle").start()
    return proc


def _reply(proc: subprocess.Popen, timeout: float) -> dict:
    """The worker's next JSON line (a stray line of a library is skipped: C172)."""
    box: list = []

    def read():
        for line in proc.stdout:
            if line.lstrip().startswith("{"):
                try:
                    box.append(json.loads(line))
                    return
                except ValueError:
                    continue
    t = threading.Thread(target=read, daemon=True)
    t.start()
    t.join(timeout)
    if not box:
        proc.kill()
        raise RuntimeError("the natural voice did not answer")
    return box[0]


def _qwen(cfg: sys_config.Config, text: str, lang: str, place: str) -> bytes:
    with _lock:
        w = _workers.get(place)
        if w is None or w["proc"].poll() is not None:
            w = _workers[place] = {"proc": _start(cfg, place), "last": time.time()}
        w["last"] = time.time()
        speed = 4.0 if place == "cpu" else 0.8           # seconds of work per second of speech (M122)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.wav"
            w["proc"].stdin.write(json.dumps({"text": text, "lang": lang, "out": str(out)}) + "\n")
            w["proc"].stdin.flush()
            r = _reply(w["proc"], 60 + speed * len(text) / 10)    # ~15 characters a second of speech: generous
            w["last"] = time.time()
            if not r.get("ok") or not out.is_file():
                raise RuntimeError(r.get("error") or "no audio")
            return out.read_bytes()


def _idle_close(place: str, proc: subprocess.Popen, idle_s: float) -> None:
    while proc.poll() is None:
        time.sleep(15)
        w = _workers.get(place)
        if w and w["proc"] is proc and time.time() - w["last"] > idle_s:
            release(place)


def release(place: str | None = None) -> None:
    """Close the natural voice (on `place`, or on every GPU) and give its memory back: before a GPU job, when a run
    starts, after the idle time. A sentence being said is cut: Piper says it."""
    for where in [place] if place else [k for k in list(_workers) if k != "cpu"]:
        w = _workers.pop(where, None)
        if not w or w["proc"].poll() is not None:
            continue
        try:
            w["proc"].kill()
            w["proc"].wait(10)
        except Exception:  # noqa: BLE001 — it must go anyway
            pass
        sys_log.get_logger("tts").info("natural voice closed on %s: memory given back", where)
