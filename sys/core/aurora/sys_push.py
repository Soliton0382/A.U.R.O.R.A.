# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Web Push to the owner's browsers (VAPID): Aurora speaks up even when the WebUI is closed.

The VAPID key pair is made on first use in <AURORA_STATUS_DIR>/push (0600) and never leaves the
machine; browsers subscribe from the bell in the top bar (a registered device is required).
Which events notify, and where (push on the devices, a toast in the WebUI), is the owner's choice in the
Notifications page, kept in <AURORA_STATUS_DIR>/push/prefs.json and read at every event (no restart);
AURORA_PUSH_EVENTS is only the starting point. Subscriptions the push service reports gone (404/410)
are dropped. Payloads carry a title, a short text and the page to open, nothing more.
"""
from __future__ import annotations

import base64
import json
import os
import threading
from pathlib import Path

from . import sys_config, sys_log

_lock = threading.Lock()

TEXTS = {   # event -> (kind the owner chooses, view to open, {lang: title})
    "incident": ("incident", "security", {"it": "🛡️ Incidente di sicurezza", "en": "🛡️ Security incident"}),
    "approval.pending": ("approval", "approvals", {"it": "🛎️ Aurora aspetta la tua approvazione",
                                                   "en": "🛎️ Aurora is waiting for your approval"}),
    "rem.dream": ("dream", "chat", {"it": "🌙 Aurora ha sognato", "en": "🌙 Aurora had a dream"}),
    "rem.thought": ("thought", "diary", {"it": "💭 Un pensiero di Aurora", "en": "💭 A thought from Aurora"}),
    "rem.self_review": ("self_review", "diary", {"it": "🩺 Autodiagnosi di Aurora", "en": "🩺 Aurora's self-review"}),
    "update.available": ("update", "approvals", {"it": "⬆️ Aggiornamento di Aurora disponibile", "en": "⬆️ Aurora update available"}),
    "update.done": ("update", "status", {"it": "⬆️ Aggiornamento di Aurora", "en": "⬆️ Aurora update"}),
    "harvest.batch_end": ("harvest", "harvester", {"it": "🌾 Batch di paper scaricato", "en": "🌾 Batch of papers downloaded"}),
    "harvest.end": ("harvest", "harvester", {"it": "🌾 Giro dell'harvester finito", "en": "🌾 Harvester round finished"}),
    "test": ("test", "chat", {"it": "🔔 Notifiche attive", "en": "🔔 Notifications on"}),
}
KINDS = {   # what the owner chooses from, in the Notifications page
    "incident": {"it": "Incidenti di sicurezza", "en": "Security incidents"},
    "approval": {"it": "Approvazioni in attesa", "en": "Approvals waiting"},
    "update": {"it": "Aggiornamenti di Aurora", "en": "Aurora updates"},
    "dream": {"it": "Sogni", "en": "Dreams"},
    "self_review": {"it": "Autodiagnosi", "en": "Self-reviews"},
    "thought": {"it": "Pensieri", "en": "Thoughts"},
    "harvest": {"it": "Harvester (paper scaricati)", "en": "Harvester (papers downloaded)"},
}
PRESETS = {"suggested": ["incident", "approval", "update", "dream", "self_review"], "all": list(KINDS), "none": []}
CHANNELS = ("push", "webui")


def prefs(cfg: sys_config.Config) -> dict:
    """{"push": [kinds], "webui": [kinds]}: the saved choice, else the suggested one (push from AURORA_PUSH_EVENTS)."""
    f = _dir(cfg) / "prefs.json"
    try:
        p = json.loads(f.read_text(encoding="utf-8"))
        return {c: [k for k in p.get(c, []) if k in KINDS] for c in CHANNELS}
    except (OSError, ValueError):
        push = [k.strip() for k in cfg["AURORA_PUSH_EVENTS"].split(",") if k.strip() in KINDS]
        return {"push": push, "webui": list(PRESETS["suggested"])}


def set_prefs(cfg: sys_config.Config, choice: dict) -> dict:
    p = {c: [k for k in KINDS if k in set(choice.get(c, []))] for c in CHANNELS}
    _write_private(_dir(cfg) / "prefs.json", json.dumps(p, indent=1).encode())
    return p


def _dir(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "push"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_private(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _vapid_pem(cfg: sys_config.Config) -> Path:
    pem = _dir(cfg) / "vapid_private.pem"
    with _lock:
        if not pem.exists():
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            key = ec.generate_private_key(ec.SECP256R1())
            _write_private(pem, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                  serialization.NoEncryption()))
    return pem


def public_key(cfg: sys_config.Config) -> str:
    """The applicationServerKey: the uncompressed P-256 point, base64url without padding."""
    from cryptography.hazmat.primitives import serialization
    key = serialization.load_pem_private_key(_vapid_pem(cfg).read_bytes(), password=None)
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _load(cfg: sys_config.Config) -> list[dict]:
    f = _dir(cfg) / "subscriptions.json"
    return json.loads(f.read_text()) if f.exists() else []


def _save(cfg: sys_config.Config, subs: list[dict]) -> None:
    _write_private(_dir(cfg) / "subscriptions.json", json.dumps(subs, indent=1).encode())


def subscribe(sub: dict, device: str | None, cfg: sys_config.Config) -> int:
    if not (isinstance(sub, dict) and str(sub.get("endpoint", "")).startswith("https://")
            and {"p256dh", "auth"} <= set(sub.get("keys") or {})):
        raise ValueError("not a push subscription")
    with _lock:
        subs = [s for s in _load(cfg) if s["endpoint"] != sub["endpoint"]]
        subs.append({"endpoint": sub["endpoint"], "keys": {k: sub["keys"][k] for k in ("p256dh", "auth")}, "device": device})
        _save(cfg, subs)
    return len(subs)


def unsubscribe(endpoint: str, cfg: sys_config.Config) -> int:
    with _lock:
        subs = [s for s in _load(cfg) if s["endpoint"] != endpoint]
        _save(cfg, subs)
    return len(subs)


def count(cfg: sys_config.Config) -> int:
    return len(_load(cfg))


def message(event: str, payload: dict, cfg: sys_config.Config, channel: str = "push") -> dict | None:
    """The notification for an activity event on a channel, or None when the owner did not ask for it."""
    if event not in TEXTS:
        return None
    kind, view, titles = TEXTS[event]
    if kind != "test" and kind not in prefs(cfg)[channel]:
        return None
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    body = str(payload.get("text") or payload.get("title") or "").strip()
    body = body if len(body) <= 180 else body[:177].rsplit(" ", 1)[0] + "…"
    return {"title": titles[lang], "body": body, "view": view, "tag": f"aurora-{kind}"}


def send(msg: dict, cfg: sys_config.Config) -> dict:
    """Deliver to every subscription; returns {"sent", "dropped", "failed"}."""
    from pywebpush import WebPushException, webpush
    log = sys_log.get_logger("push")
    pem = str(_vapid_pem(cfg))
    sent, dropped, failed = 0, [], 0
    for s in _load(cfg):
        try:
            webpush({"endpoint": s["endpoint"], "keys": s["keys"]}, json.dumps(msg), vapid_private_key=pem,
                    vapid_claims={"sub": cfg["AURORA_PUSH_SUBJECT"]}, ttl=12 * 3600, timeout=20)
            sent += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):
                dropped.append(s["endpoint"])
            else:
                failed += 1
                log.warning("push to %s… failed: %s", s["endpoint"][:40], str(e)[:200])
        except Exception as e:                           # network: the next event tries again
            failed += 1
            log.warning("push to %s… failed: %s", s["endpoint"][:40], str(e)[:200])
    for ep in dropped:
        unsubscribe(ep, cfg)
    log.info("push %s: sent %d, dropped %d, failed %d", msg.get("tag"), sent, len(dropped), failed)
    return {"sent": sent, "dropped": len(dropped), "failed": failed}
