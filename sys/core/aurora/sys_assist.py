# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🛟 Assistance: the admin enters a user's account, when the user lets them (owner, 29 Oct: «Accesso completo come
Exchange… il consenso è implicito all'atto di attivazione (basta un disclaimer nella pagina assistenza)»).

- The user opens a window of WINDOWS hours from their account page (the disclaimer beside the button is the consent);
  they close it when they like, and it closes by itself when it ends.
- While it is open the admin's device can enter the account ("Entra come…" on the Users page): every request of that
  device is the user's — the same pages, the same data, a banner with the way out — until the admin leaves, the user
  revokes or the window ends.
- Never, whoever asks: the password, the Authenticator, the API keys, the devices (sessions), the logout of the
  admin's own device while inside (NEVER, refused by the API before the route).
- Every step (the method and the path, no body) goes into the user's log (assist_log.jsonl, each line sealed with the
  user's key), shown on their page; the user is told when the admin enters and when the assistance ends (api.assist).

The grants and the sessions are the machine's (<AURORA_STATUS_DIR>/assist.json, 0600): the admin's process reads
them at every request."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from . import sys_config, sys_seal

WINDOWS = (8, 16, 24, 48, 72)                          # hours a user can open it for
NEVER = ("/v1/aurora/me/password", "/v1/aurora/me/totp", "/v1/aurora/me/keys", "/v1/aurora/devices",
         "/v1/aurora/logout", "/v1/aurora/login", "/v1/aurora/assist/grant", "/v1/aurora/assist/revoke")
STEP_GAP_S = 60                                        # the same page read again within a minute: one step, not many
LOG_MAX = 3000
_lock = threading.Lock()
_last_step: dict[tuple, float] = {}


def _file(base: sys_config.Config) -> Path:
    return base.path("AURORA_STATUS_DIR") / "assist.json"


def _load(base: sys_config.Config) -> dict:
    try:
        d = json.loads(_file(base).read_text(encoding="utf-8"))
        return {"grants": dict(d.get("grants", {})), "sessions": dict(d.get("sessions", {}))}
    except (OSError, ValueError):
        return {"grants": {}, "sessions": {}}


def _save(base: sys_config.Config, d: dict) -> None:
    f = _file(base)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(d, out)
    os.replace(tmp, f)


def grant(base: sys_config.Config, user: str, hours: int, now: float | None = None) -> dict:
    """The user opens the window: {"user", "at", "until", "hours"} (a window open already: started again)."""
    if hours not in WINDOWS:
        raise ValueError(f"hours: one of {', '.join(map(str, WINDOWS))}")
    now = now or time.time()
    g = {"user": user, "at": now, "until": now + hours * 3600, "hours": hours}
    with _lock:
        d = _load(base)
        d["grants"][user] = g
        _save(base, d)
    return g


def granted(base: sys_config.Config, user: str, now: float | None = None) -> dict | None:
    g = _load(base)["grants"].get(user)
    return g if g and g["until"] > (now or time.time()) else None


def revoke(base: sys_config.Config, user: str) -> list[str]:
    """The user closes the window: it and the admin's sessions in it end. → the devices that were inside."""
    with _lock:
        d = _load(base)
        d["grants"].pop(user, None)
        out = [dev for dev, s in d["sessions"].items() if s["user"] == user]
        for dev in out:
            d["sessions"].pop(dev)
        _save(base, d)
    return out


def enter(base: sys_config.Config, device: str, user: str, now: float | None = None) -> dict:
    """The admin's device enters the user's account; only while the user's window is open."""
    now = now or time.time()
    with _lock:
        d = _load(base)
        g = d["grants"].get(user)
        if not g or g["until"] <= now:
            raise PermissionError(f"{user} has not opened the assistance")
        s = {"user": user, "at": now, "until": g["until"]}
        d["sessions"][device] = s
        _save(base, d)
    return s


def leave(base: sys_config.Config, device: str) -> dict | None:
    with _lock:
        d = _load(base)
        s = d["sessions"].pop(device, None)
        if s:
            _save(base, d)
    return s


def acting(base: sys_config.Config, device: str, now: float | None = None) -> dict | None:
    """The session of this device inside a user's account, or None (none, or its window ended: expire() tells)."""
    d = _load(base)
    s = d["sessions"].get(device)
    if not s:
        return None
    g = d["grants"].get(s["user"])
    return s if g and g["until"] > (now or time.time()) else None


def expire(base: sys_config.Config, now: float | None = None) -> list[dict]:
    """The windows ended by their time, dropped with their sessions: [{"user", "inside": bool}] to tell each user."""
    now = now or time.time()
    with _lock:
        d = _load(base)
        ended = [u for u, g in d["grants"].items() if g["until"] <= now]
        if not ended:
            return []
        out = []
        for u in ended:
            d["grants"].pop(u)
            devs = [dev for dev, s in d["sessions"].items() if s["user"] == u]
            for dev in devs:
                d["sessions"].pop(dev)
            out.append({"user": u, "inside": bool(devs)})
        _save(base, d)
    return out


def inside(base: sys_config.Config, user: str) -> bool:
    """Whether the admin is in the user's account now."""
    return any(s["user"] == user for s in _load(base)["sessions"].values())


def allowed(path: str) -> bool:
    """A path the admin may use inside a user's account (NEVER: the account's keys and sessions)."""
    return not any(path == p or path.startswith(p + "/") for p in NEVER)


# ---- the user's log --------------------------------------------------------------------------------------------------
def _log_file(ucfg: sys_config.Config) -> Path:
    from . import sys_users_layout
    d = sys_users_layout.place(ucfg, "state", ucfg.user)
    d.mkdir(parents=True, exist_ok=True)
    return d / "assist_log.jsonl"


def step(ucfg: sys_config.Config, by: str, what: str, path: str = "", now: float | None = None) -> bool:
    """One step into the user's log: what ("GET", "POST"… or "enter", "leave", "grant", "revoke", "end"), the path.
    A GET of the same path within STEP_GAP_S is not written again (a page polls). → whether it was written."""
    now = now or time.time()
    key = (ucfg.user, what, path)
    if what == "GET" and key in _last_step and now - _last_step[key] < STEP_GAP_S:
        return False
    _last_step[key] = now
    line = sys_seal.seal_text(ucfg, json.dumps({"at": round(now, 1), "by": by, "what": what, "path": path}),
                              "assist_log.jsonl", ucfg.user)
    f = _log_file(ucfg)
    with _lock:
        if f.exists() and f.stat().st_size > LOG_MAX * 400:
            keep = f.read_text(encoding="utf-8").splitlines()[-(LOG_MAX // 2):]
            f.write_text("\n".join(keep) + "\n", encoding="utf-8")
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as out:
            out.write(line + "\n")
    return True


def log(ucfg: sys_config.Config, n: int = 200) -> list[dict]:
    """The user's log, newest first."""
    f = _log_file(ucfg)
    out = []
    for line in (f.read_text(encoding="utf-8").splitlines() if f.exists() else [])[-n:]:
        try:
            out.append(json.loads(sys_seal.open_text(ucfg, line, "assist_log.jsonl", ucfg.user)))
        except ValueError:
            continue
    return out[::-1]
