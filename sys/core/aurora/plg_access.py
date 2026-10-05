# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Which plugins the other users may use, and which stay the admin's (owner, 2026-10-04).

The machine's plugins (backup, security, the camera and microphone, the house, the cloud's keys, Aurora's own
self-repair) stay the admin's; the personal ones (calendar, notes, social pages, expenses...) are everyone's, each
with their own settings (sys_user_config). The admin changes any of them on the Plugins page; the choice is kept in
<AURORA_STATUS_DIR>/plugin_access.json. A plugin not in the list (a new one, a forged one) is the admin's until the
admin shares it. Only restricts: for the admin and in single-user nothing changes (plg_host, signed, is untouched).
"""
from __future__ import annotations

import json
import os
import threading

from . import sys_config
from .plg_host import PluginHost, _explain

ADMIN_ONLY = {"backup", "security", "netintel", "self", "senses", "homeassistant", "cloud"}
FOR_USERS = {"calendar", "cinema", "diary", "discord", "dj", "documents", "dropbox", "email", "expenses", "facebook",
             "github", "instagram", "mastodon", "news", "nextcloud", "notes", "projects", "telegram", "tiktok",
             "twitch", "weather", "web", "whatsapp"}
_lock = threading.Lock()


def _file(cfg: sys_config.Config):
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "plugin_access.json"


def choices(cfg: sys_config.Config) -> dict[str, bool]:
    f = _file(cfg)
    try:
        return {k: bool(v) for k, v in json.loads(f.read_text(encoding="utf-8")).items()} if f.exists() else {}
    except ValueError:
        return {}


def for_users(cfg: sys_config.Config, name: str) -> bool:
    """True when the users (not only the admin) may use this plugin."""
    return choices(cfg).get(name, name in FOR_USERS)


def set_for_users(cfg: sys_config.Config, name: str, on: bool) -> None:
    with _lock:
        st = choices(cfg)
        st[name] = bool(on)
        f = _file(cfg)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
        os.replace(tmp, f)


class UserPluginHost(PluginHost):
    """A user's host: the admin's plugins are there, switched off for them (listed as not theirs, never called)."""

    def plugins(self, with_tools: bool = True):
        st = choices(self.cfg)
        allowed = lambda n: st.get(n, n in FOR_USERS)  # noqa: E731
        out = super().plugins(with_tools=False)
        for p in out:
            if not allowed(p.name):
                p.enabled = False
                p.admin_only = True
        if with_tools:                                  # tools only of what the user may use: nothing else started
            for p in out:
                if p.enabled and not p.missing and not p.error:
                    try:
                        p.tools = self._tools(p, (p.folder / "plugin.json").stat().st_mtime)
                    except Exception as e:  # noqa: BLE001 — a broken plugin must not break the others
                        p.error = _explain(e)
        return out
