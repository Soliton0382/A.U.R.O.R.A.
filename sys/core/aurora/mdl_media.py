# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Who makes pictures, picture edits and videos (owner, 2026-10-06: "use the configured API providers for images,
edits and videos too: a more complete choice of who does what").

The Models page assigns each media task to the local models (SDXL, FLUX.2 klein, Wan 2.2) or to a cloud provider that
really does that task, with its key in the settings:
  image  OpenAI gpt-image-1 · Google gemini-2.5-flash-image · xAI grok-2-image
  edit   OpenAI gpt-image-1 · Google gemini-2.5-flash-image
  video  Google veo-3.1-fast-generate-preview (a long-running job, polled; on a 404 the key's own Veo models are
         listed and the closest one taken — 6 October: veo-3.0 was not offered to the owner's key)
  voice  Aurora's voice (owner, 2026-10-09: «aurora full cloud può usare modelli on line … per la voce»): OpenAI
         gpt-4o-mini-tts · Google gemini-2.5-flash-preview-tts. The text leaves masked, and each placeholder is spoken
         as its kind («un indirizzo email»): nothing private leaves, and nothing like «[EMAIL_1]» is read aloud
  speech dictation and the speech of videos: OpenAI gpt-4o-mini-transcribe · Google gemini-2.5-flash. A voice cannot
         be masked: only on an exempted installation, as pictures; the text it becomes goes on masked as usual
The words of a request are masked like any cloud call (sec_mask); a picture cannot be masked, so an edit, or a video
from a picture, goes to the cloud only on an installation the owner exempted (as for vision), else it is refused and
the local model is used. Every call is counted in "What went out" (cloud.call, cloud.mask with the pictures sent).
The endpoints follow each provider's documentation as of 2025-2026; not tried live from here (each call is billed):
the owner's first use is the test (N86).
"""
from __future__ import annotations

import base64
import json
import time

import httpx

from . import sys_config, sys_log

TASKS = ("image", "edit", "video", "voice", "speech")
CAN = {"openai": {"image": "gpt-image-1", "edit": "gpt-image-1", "voice": "gpt-4o-mini-tts", "speech": "gpt-4o-mini-transcribe"},
       "google": {"image": "gemini-2.5-flash-image", "edit": "gemini-2.5-flash-image", "video": "veo-3.1-fast-generate-preview",
                  "voice": "gemini-2.5-flash-preview-tts", "speech": "gemini-2.5-flash"},
       "xai": {"image": "grok-2-image"}}
# a placeholder said aloud as what it stands for (sec_mask's kinds), in the answer's language
SPOKEN = {"it": {"EMAIL": "un indirizzo email", "PHONE": "un numero di telefono", "IBAN": "un IBAN", "CARD": "una carta",
                 "CF": "un codice fiscale", "VAT": "una partita IVA", "PLATE": "una targa", "ADDRESS": "un indirizzo",
                 "IP": "un indirizzo di rete", "MAC": "un indirizzo di rete", "TOKEN": "un codice", "SECRET": "un codice",
                 "PRIVATE": "un dato privato", "NAME": "una persona", "ID": "un codice", "FIELD": "un valore"},
          "en": {"EMAIL": "an e-mail address", "PHONE": "a phone number", "IBAN": "an IBAN", "CARD": "a card",
                 "CF": "a tax code", "VAT": "a VAT number", "PLATE": "a number plate", "ADDRESS": "an address",
                 "IP": "a network address", "MAC": "a network address", "TOKEN": "a code", "SECRET": "a code",
                 "PRIVATE": "something private", "NAME": "a person", "ID": "a code", "FIELD": "a value"}}
GOOGLE = "https://generativelanguage.googleapis.com/v1beta"


def _file(cfg: sys_config.Config):
    d = cfg.path("AURORA_STATUS_DIR") / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d / "media.json"


def assignments(cfg: sys_config.Config) -> dict[str, dict]:
    try:
        saved = json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {t: {"provider": (saved.get(t) or {}).get("provider", "local"), "model": (saved.get(t) or {}).get("model", "")}
            for t in TASKS}


def choices(cfg: sys_config.Config) -> dict:
    """For the Models page: per task, the providers that can do it and whether their key is there."""
    from .mdl_router import PROVIDERS
    out = {}
    for t in TASKS:
        rows = [{"provider": "local", "label": "Locale", "model": "", "ready": True}]
        for p, can in CAN.items():
            if t in can:
                key = PROVIDERS[p]["key"]
                rows.append({"provider": p, "label": PROVIDERS[p]["label"], "model": can[t], "ready": bool(cfg.values.get(key))})
        out[t] = rows
    return out


def set_assignments(cfg: sys_config.Config, changes: dict) -> dict:
    from .mdl_router import PROVIDERS
    cur = assignments(cfg)
    for t, a in changes.items():
        if t not in TASKS or not isinstance(a, dict):
            raise ValueError(f"task: one of {TASKS}")
        p = a.get("provider", "local")
        if p != "local":
            if t not in CAN.get(p, {}):
                raise ValueError(f"{p} cannot do {t}")
            if not cfg.values.get(PROVIDERS[p]["key"]):
                raise ValueError(f"{PROVIDERS[p]['key']} is empty")
        cur[t] = {"provider": p, "model": str(a.get("model") or "")[:80]}
    _file(cfg).write_text(json.dumps(cur, indent=1), encoding="utf-8")
    return cur


def provider(cfg: sys_config.Config, task: str) -> tuple[str, str]:
    a = assignments(cfg)[task]
    return a["provider"], a["model"] or CAN.get(a["provider"], {}).get(task, "")


def _key(cfg: sys_config.Config, p: str) -> str:
    from .mdl_router import PROVIDERS
    k = cfg.values.get(PROVIDERS[p]["key"]) or ""
    if not k:
        raise RuntimeError(f"{PROVIDERS[p]['key']} is empty")
    return str(k)


def _masked(cfg: sys_config.Config, text: str, task: str, p: str, model: str, pictures: int) -> str:
    from .sec_mask import Pseudonymizer
    m = Pseudonymizer(cfg)
    out = m.mask(text)
    sys_log.trace("llm_client", "cloud.mask", {"role": task, "provider": p, "model": model,
                                               "masked": dict(getattr(m, "counts", {}) or {}), "images": pictures})
    return out


def _picture_allowed(cfg: sys_config.Config, task: str) -> None:
    from . import sys_ethics
    if not sys_ethics.exempt(cfg):
        raise PermissionError(f"{task}: a picture cannot be masked and goes to the cloud only on an exempted installation")


def _allowed(cfg: sys_config.Config, p: str) -> None:
    """The provider's free tier (if the owner keeps it there) or the daily ceiling: else the local model does it."""
    from . import mdl_budget
    if mdl_budget.over(cfg, p):
        raise RuntimeError(f"{p}: limit reached ({mdl_budget.free_reason(cfg, p) or 'daily ceiling'})")


def _account(p: str, model: str, t0: float, task: str, cfg: sys_config.Config | None = None) -> None:
    if cfg is not None:
        from . import mdl_budget
        mdl_budget.record(cfg, p, {})                  # a request counted (pictures are not billed in tokens)
    sys_log.trace("llm_client", "cloud.call", {"provider": p, "model": model, "usage": {}, "seconds": round(time.time() - t0, 2),
                                               "task": task})


def _openai_like(base: str, key: str, model: str, prompt: str, src: bytes | None) -> bytes:
    head = {"Authorization": f"Bearer {key}"}
    if src is None:
        body = {"model": model, "prompt": prompt, "n": 1}
        if "x.ai" in base:
            body["response_format"] = "b64_json"
        r = httpx.post(f"{base}/images/generations", headers=head, json=body, timeout=300)
    else:
        r = httpx.post(f"{base}/images/edits", headers=head, timeout=300,
                       data={"model": model, "prompt": prompt}, files={"image": ("in.png", src, "image/png")})
    r.raise_for_status()
    d = r.json()["data"][0]
    if d.get("b64_json"):
        return base64.b64decode(d["b64_json"])
    return httpx.get(d["url"], timeout=120).content


def _google_image(key: str, model: str, prompt: str, src: bytes | None) -> bytes:
    parts = [{"text": prompt}] + ([{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(src).decode()}}] if src else [])
    r = httpx.post(f"{GOOGLE}/models/{model}:generateContent", headers={"x-goog-api-key": key}, timeout=300,
                   json={"contents": [{"parts": parts}]})
    r.raise_for_status()
    for part in r.json()["candidates"][0]["content"]["parts"]:
        data = (part.get("inline_data") or part.get("inlineData") or {}).get("data")
        if data:
            return base64.b64decode(data)
    raise RuntimeError("the provider answered without a picture")


def picture(cfg: sys_config.Config, task: str, prompt: str, src: bytes | None = None) -> tuple[bytes, dict]:
    """A new picture (task "image") or an edited one ("edit") from the assigned cloud provider: (bytes, measures)."""
    p, model = provider(cfg, task)
    if src is not None:
        _picture_allowed(cfg, task)
    _allowed(cfg, p)
    t0 = time.time()
    said = _masked(cfg, prompt, task, p, model, 1 if src is not None else 0)
    if p == "google":
        data = _google_image(_key(cfg, p), model, said, src)
    else:
        data = _openai_like({"openai": "https://api.openai.com/v1", "xai": "https://api.x.ai/v1"}[p], _key(cfg, p), model, said, src)
    _account(p, model, t0, task, cfg)
    return data, {"provider": p, "model": model, "seconds": round(time.time() - t0, 1)}


def _google_video_model(key: str) -> str | None:
    """The Veo model this key offers (the fast one first): a listing, no cost."""
    r = httpx.get(f"{GOOGLE}/models", headers={"x-goog-api-key": key}, params={"pageSize": 1000}, timeout=60)
    names = [m["name"].split("/", 1)[-1] for m in r.json().get("models", []) if "predictLongRunning" in (m.get("supportedGenerationMethods") or [])
             and "veo" in m["name"]]
    return next((n for n in names if "fast" in n), names[0] if names else None)


def video(cfg: sys_config.Config, prompt: str, image: bytes | None = None, limit_s: float = 900) -> tuple[bytes, dict]:
    """A video from Google Veo: a long-running operation polled every 10 s, then the file downloaded."""
    p, model = provider(cfg, "video")
    if p != "google":
        raise RuntimeError(f"{p} cannot make videos")
    if image is not None:
        _picture_allowed(cfg, "video")
    _allowed(cfg, p)
    key, t0 = _key(cfg, p), time.time()
    inst = {"prompt": _masked(cfg, prompt, "video", p, model, 1 if image is not None else 0)}
    if image is not None:
        inst["image"] = {"bytesBase64Encoded": base64.b64encode(image).decode(), "mimeType": "image/png"}
    head = {"x-goog-api-key": key}
    r = httpx.post(f"{GOOGLE}/models/{model}:predictLongRunning", headers=head, json={"instances": [inst]}, timeout=120)
    if r.status_code == 404:                               # a name the key does not have: its own Veo models
        model = _google_video_model(key) or model
        r = httpx.post(f"{GOOGLE}/models/{model}:predictLongRunning", headers=head, json={"instances": [inst]}, timeout=120)
    r.raise_for_status()
    name = r.json()["name"]
    while True:
        op = httpx.get(f"{GOOGLE}/{name}", headers=head, timeout=60).json()
        if op.get("done"):
            break
        if time.time() - t0 > limit_s:
            raise TimeoutError(f"the video was not ready after {limit_s:.0f} s")
        time.sleep(10)
    if op.get("error"):
        raise RuntimeError(f"Veo: {op['error'].get('message', op['error'])}")
    uri = op["response"]["generateVideoResponse"]["generatedSamples"][0]["video"]["uri"]
    data = httpx.get(uri, headers=head, timeout=300, follow_redirects=True).content
    _account(p, model, t0, "video", cfg)
    return data, {"provider": p, "model": model, "seconds_total": round(time.time() - t0, 1), "bytes": len(data)}


# ---- voice and speech ---------------------------------------------------------------------------------------------
def say_masked(cfg: sys_config.Config, text: str, lang: str, p: str, model: str) -> str:
    """The text a cloud voice reads: masked, each placeholder replaced by the words for its kind."""
    from .sec_mask import PLACEHOLDER
    said = _masked(cfg, text, "voice", p, model, 0)
    words = SPOKEN["it" if lang.startswith("it") else "en"]
    return PLACEHOLDER.sub(lambda m: words.get(m.group(1), words["PRIVATE"]), said)


def _wav(pcm: bytes, rate: int, channels: int = 1, width: int = 2) -> bytes:
    import io
    import wave
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def spoken(cfg: sys_config.Config, text: str, lang: str) -> bytes:
    """Aurora's voice from the assigned cloud provider: WAV bytes."""
    p, model = provider(cfg, "voice")
    _allowed(cfg, p)
    t0 = time.time()
    said = say_masked(cfg, text, lang, p, model)
    female = str(cfg["AURORA_ASSISTANT_GENDER"]) != "male"
    if p == "openai":
        r = httpx.post("https://api.openai.com/v1/audio/speech", headers={"Authorization": f"Bearer {_key(cfg, p)}"},
                       json={"model": model, "input": said, "voice": "nova" if female else "onyx", "response_format": "wav"},
                       timeout=180)
        r.raise_for_status()
        data = r.content
    elif p == "google":
        body = {"contents": [{"parts": [{"text": said}]}],
                "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": "Kore" if female else "Puck"}}}}}
        r = httpx.post(f"{GOOGLE}/models/{model}:generateContent", headers={"x-goog-api-key": _key(cfg, p)}, json=body,
                       timeout=180)
        r.raise_for_status()
        part = r.json()["candidates"][0]["content"]["parts"][0]
        pcm = base64.b64decode((part.get("inlineData") or part.get("inline_data"))["data"])
        data = _wav(pcm, 24000)                           # Gemini's speech: 16-bit PCM, 24 kHz, mono
    else:
        raise RuntimeError(f"{p} has no voice")
    _account(p, model, t0, "voice", cfg)
    return data


def heard(cfg: sys_config.Config, audio, lang: str) -> dict:
    """A recording (16 kHz float32, as mdl_stt takes it) written as text by the assigned cloud provider:
    {"text", "clear", "seconds", "audio_s"}, the same answer as the local Whisper's."""
    import numpy as np
    p, model = provider(cfg, "speech")
    from . import sys_ethics
    if not sys_ethics.exempt(cfg):
        raise PermissionError("speech: a voice cannot be masked and goes to the cloud only on an exempted installation")
    _allowed(cfg, p)
    t0 = time.time()
    a = np.clip(np.asarray(audio, dtype=np.float32), -1, 1)
    wav = _wav((a * 32767).astype("<i2").tobytes(), 16000)
    sys_log.trace("llm_client", "cloud.mask", {"role": "speech", "provider": p, "model": model, "masked": {},
                                               "audio_s": round(len(a) / 16000, 1)})
    if p == "openai":
        r = httpx.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": f"Bearer {_key(cfg, p)}"},
                       data={"model": model, "language": lang[:2]}, files={"file": ("audio.wav", wav, "audio/wav")},
                       timeout=300)
        r.raise_for_status()
        text = r.json().get("text", "")
    elif p == "google":
        ask = ("Trascrivi esattamente il parlato, senza aggiungere nulla." if lang.startswith("it")
               else "Transcribe the speech exactly, adding nothing.")
        body = {"contents": [{"parts": [{"text": ask}, {"inline_data": {"mime_type": "audio/wav",
                                                                        "data": base64.b64encode(wav).decode()}}]}]}
        r = httpx.post(f"{GOOGLE}/models/{model}:generateContent", headers={"x-goog-api-key": _key(cfg, p)}, json=body,
                       timeout=300)
        r.raise_for_status()
        text = "".join(x.get("text", "") for x in r.json()["candidates"][0]["content"]["parts"])
    else:
        raise RuntimeError(f"{p} cannot transcribe")
    _account(p, model, t0, "speech", cfg)
    text = " ".join(text.split())
    return {"text": text, "clear": bool(text), "seconds": round(time.time() - t0, 1), "audio_s": round(len(a) / 16000, 1)}


def heard_segments(cfg: sys_config.Config, audio, lang: str, window_s: int = 30) -> list[tuple[float, float, str]]:
    """A long track (a video's) in windows, each written by the cloud: (start, end, text) like the local segments."""
    out, n = [], 16000 * window_s
    for i in range(0, len(audio), n):
        piece = audio[i:i + n]
        t = heard(cfg, piece, lang)["text"]
        if t:
            out.append((i / 16000, (i + len(piece)) / 16000, t))
    return out
