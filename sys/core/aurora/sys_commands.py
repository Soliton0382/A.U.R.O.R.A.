# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Command cards (owner, 2026-10-09: «indicare la cosa nella WebUI indicando il comando da lanciare… guidiamo l'utente
su cosa deve fare»): what only the owner can do from a shell — an update that touches the code of conduct, a
signature — said in the WebUI with the exact command for this system, a copy button, and Aurora checking afterwards
that it was done. No terminal in the WebUI: a shell reachable from the browser is what an attacker looks for first.

The commands come from config/commands.json (Linux) or from <STATUS>/commands.json, which each port's installer
writes in its own system's words (Windows: PowerShell as administrator; the Mac; Docker), with the clone it was
installed from («source»): where an update is fetched when Aurora's own folder is not a git clone (Windows, the Mac:
their installers build it from the clone — 9 Oct, the Windows VM: «not a git repository» at every check).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import sys_config

DEFAULTS = Path(__file__).resolve().parents[1] / "config" / "commands.json"

TEXT = {
    "update": {"it": ("⬆️ Aggiornamento da applicare a mano",
                      "{n} novità. {why} Lancia il comando, poi premi «Verifica»."),
               "en": ("⬆️ An update to apply by hand",
                      "{n} changes. {why} Run the command, then press «Check»."),
               "why_protected": {"it": "Tocca file protetti del codice etico ({f}): serve la tua firma.",
                                 "en": "It touches protected files of the code of conduct ({f}): your signature is needed."},
               "why_port": {"it": "Su questo sistema l'aggiornamento passa dall'installer.",
                            "en": "On this system an update goes through the installer."}},
    "sign": {"it": ("✍️ Codice protetto non firmato",
                    "Questi file del codice etico sono cambiati e non hai ancora firmato: {f}. Finché non firmi, i "
                    "servizi non ripartono."),
             "en": ("✍️ Protected code not signed",
                    "These files of the code of conduct changed and are not signed yet: {f}. Until you sign, the "
                    "services do not start again.")},
    # U6 (owner, 28 Oct: «l'aggiornamento dovrà prevedere la migrazione di ambiente già configurato»)
    "account": {"it": ("🔐 I servizi sul loro account",
                       "I servizi girano ancora come «{u}», il tuo account. Il comando crea l'account «aurora» (niente "
                       "login, solo i gruppi della GPU), gli dà i dati e lascia a te il codice; poi riavvia i servizi. "
                       "Una volta sola; poi rifai il login di Claude da ☁️ Account."),
                "en": ("🔐 The services on their own account",
                       "The services still run as «{u}», your own account. The command makes the account «aurora» (no "
                       "login, only the GPU's groups), gives it the data and leaves the code to you; then restarts the "
                       "services. Once; then log in to Claude again from ☁️ Accounts.")},
}


def _installed(cfg: sys_config.Config) -> dict:
    try:
        return json.loads((cfg.path("AURORA_STATUS_DIR") / "commands.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def templates(cfg: sys_config.Config) -> dict:
    out = json.loads(DEFAULTS.read_text(encoding="utf-8"))
    out.update({k: v for k, v in _installed(cfg).items() if isinstance(v, str)})
    return out


def source(cfg: sys_config.Config) -> Path:
    """The git clone updates come from: the installer's, or Aurora's own folder (Linux: the clone itself)."""
    s = _installed(cfg).get("source")
    return Path(s) if s and Path(s, ".git").exists() else cfg.root


def by_hand(cfg: sys_config.Config) -> bool:
    """An update here is applied by the owner through the installer (the ports, Docker), never from the WebUI."""
    return bool(_installed(cfg).get("by_hand")) or not (cfg.root / ".git").exists()


def command(cfg: sys_config.Config, name: str) -> str:
    return templates(cfg)[name].format(root=str(cfg.root), source=str(source(cfg)))


def cards(cfg: sys_config.Config, lang: str = "it") -> list[dict]:
    """The cards the owner has to act on now."""
    from . import sys_ethics, sys_update
    lang = "en" if lang.startswith("en") else "it"
    out = []
    u = sys_update.last(cfg)
    if u.get("behind") and (u.get("protected") or by_hand(cfg)):
        t = TEXT["update"]
        why = (t["why_protected"][lang].format(f=", ".join(u["protected"])) if u.get("protected")
               else t["why_port"][lang])
        title, body = t[lang]
        out.append({"id": "update", "title": title, "text": body.format(n=u["behind"], why=why),
                    "command": command(cfg, "update"), "admin": False})
    drift = sys_ethics.code_drift()
    changed = sorted(set(drift.get("changed", []) + drift.get("added", [])) & set(sys_ethics.PROTECTED))
    if changed:
        title, body = TEXT["sign"][lang]
        out.append({"id": "sign", "title": title, "text": body.format(f=", ".join(changed)),
                    "command": command(cfg, "sign"), "admin": True})
    who = sys_config.service_user(cfg)
    if os.name == "posix" and who != sys_config.SERVICE_GROUP and (cfg.root / ".git").exists() and not by_hand(cfg):
        title, body = TEXT["account"][lang]               # Linux's systemd installation only: the ports have their own
        out.append({"id": "account", "title": title, "text": body.format(u=who), "command": command(cfg, "account"),
                    "admin": True})
    return out


def verify(cfg: sys_config.Config, card: str) -> dict:
    """Done? The update: nothing behind any more (fetched again); the signature: no protected file left unsigned."""
    from . import sys_update
    if card == "update":
        info = sys_update.check(cfg)
        return {"done": not info.get("behind"), "behind": info.get("behind"), "error": info.get("error")}
    if card in ("sign", "account"):
        return {"done": not any(c["id"] == card for c in cards(cfg))}
    raise ValueError(f"no such card: {card}")
