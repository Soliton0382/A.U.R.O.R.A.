# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🕶️ The anonymous chat (owner, 2026-10-20: «una chat anonima… la chat normale, però senza salvataggio dei messaggi
in stm e ltm, con svuotamento automatico in 24 ore… il file della chat che viene creato lo cifrerei»).

Its questions are answered with nothing remembered (remember: false, tools on) and no trace written (the run is
anonymous: sys_context.anonymous, sys_log.trace writes nothing for it). Its conversation is kept only so that the page
can show it again: one sealed file per user (sys_seal, its own key "anon"), emptied ANON_HOURS after its first message
— or at once by the person — and then its key is deleted too, so a copy of the old file can never be opened again; the
next message starts a new file with a new key."""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import sys_config, sys_seal
from . import sys_users_layout as L

ANON_HOURS = 24
MAX_TURNS = 400
PURPOSE = "anon"


def _file(cfg: sys_config.Config, user: str | None) -> Path:
    return L.place(cfg, "state", user) / "anon_chat.sealed"


def _key(cfg: sys_config.Config, user: str | None) -> Path:
    return L.place(cfg, "state", user) / "keys" / f"{PURPOSE}.key"


def clear(cfg: sys_config.Config, user: str | None = None) -> bool:
    """The conversation and its key, gone."""
    gone = False
    for f in (_file(cfg, user), _key(cfg, user)):
        if f.exists():
            f.unlink()
            gone = True
    return gone


def load(cfg: sys_config.Config, user: str | None = None, now: float | None = None) -> dict:
    """{"started", "expires", "turns"}; an old one (past ANON_HOURS) or one that does not open is emptied first."""
    f, now = _file(cfg, user), now or time.time()
    if not f.exists():
        return {"started": None, "expires": None, "turns": []}
    try:
        d = json.loads(sys_seal.read(cfg, f, user, PURPOSE))
    except Exception:                                  # noqa: BLE001 — a key lost or a file broken: nothing to show
        clear(cfg, user)
        return {"started": None, "expires": None, "turns": []}
    if now - d.get("started", now) >= ANON_HOURS * 3600:
        clear(cfg, user)
        return {"started": None, "expires": None, "turns": []}
    return {**d, "expires": d["started"] + ANON_HOURS * 3600}


def add(cfg: sys_config.Config, turns: list[dict], user: str | None = None, now: float | None = None) -> dict:
    """Turns appended ({role: user | aurora, text, created_at}); the first one starts the 24 hours."""
    d, now = load(cfg, user, now), now or time.time()
    kept = [{"role": "user" if t.get("role") == "user" else "aurora", "text": str(t.get("text", ""))[:20000],
             "created_at": str(t.get("created_at", ""))[:40]} for t in turns if str(t.get("text", "")).strip()]
    d = {"started": d["started"] or now, "turns": (d["turns"] + kept)[-MAX_TURNS:]}
    sys_seal.write(cfg, _file(cfg, user), json.dumps(d, ensure_ascii=False).encode(), user, PURPOSE)
    return {**d, "expires": d["started"] + ANON_HOURS * 3600}


def purge_due(cfg: sys_config.Config, user: str | None = None) -> bool:
    """The routines' tick: an anonymous chat past its hours, emptied even when nobody opens it."""
    f = _file(cfg, user)
    return f.exists() and not load(cfg, user)["turns"]


LOOP_ACTS = ("create_artifact", "create_picture", "propose_change", "request_capability", "run_in_project",
             "home_scene", "home_automation")


def refusal(name: str, index: dict, host) -> str:
    """The agent's call in an anonymous run (owner, 2026-10-20: «niente file da lei»): only reading — no file made (a
    read tool's own output, a PDF, too), no action, no request kept for the owner (its arguments would stay), nothing
    asked of the forge. "" when it may go on, or when the run is not anonymous."""
    from . import sys_context
    if not sys_context.anonymous_now():
        return ""
    plugin, tool, effect = index.get(name, ("", "", ""))
    makes = bool(plugin) and bool((host.get(plugin).manifest.get("outputs") or {}).get(tool))
    if name in LOOP_ACTS or (plugin and (effect != "read" or makes)):
        return ("REFUSED: this is the anonymous chat — you only read and answer in text: no file, no action, nothing "
                "kept. Answer with what you can read.")
    return ""
