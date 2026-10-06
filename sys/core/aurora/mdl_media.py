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

TASKS = ("image", "edit", "video")
CAN = {"openai": {"image": "gpt-image-1", "edit": "gpt-image-1"},
       "google": {"image": "gemini-2.5-flash-image", "edit": "gemini-2.5-flash-image", "video": "veo-3.1-fast-generate-preview"},
       "xai": {"image": "grok-2-image"}}
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
