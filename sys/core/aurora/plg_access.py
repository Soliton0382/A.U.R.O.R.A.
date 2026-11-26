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
             "github", "health", "instagram", "mastodon", "news", "nextcloud", "notes", "projects", "telegram", "tiktok",
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
    """True when every user (not only the admin) may use this plugin. N167 (27 Nov): one rule — the feature's in
    👥 Utenti → Accessi (sys_users_groups); this switch and the old file only read and write it."""
    from . import sys_users_groups as G
    f = G.canonical(f"plugin:{name}")
    rule = G._rules(cfg.base or cfg).get(f)
    return bool(rule["all"]) if rule is not None else G.default(f)


def set_for_users(cfg: sys_config.Config, name: str, on: bool) -> None:
    """The Plugins page's «👥 anche per gli altri utenti»: «Tutti» on or off for the plugin's feature, the users and
    groups chosen there kept."""
    from . import sys_users_groups as G
    base = cfg.base or cfg
    f = G.canonical(f"plugin:{name}")
    rule = G._rules(base).get(f) or {"users": [], "groups": []}
    G.set_access(base, f, bool(on), list(rule.get("users") or []), list(rule.get("groups") or []))


class UserPluginHost(PluginHost):
    """A user's host: the admin's plugins are there, switched off for them (listed as not theirs, never called)."""

    def plugins(self, with_tools: bool = True):
        from . import sys_users_groups as G         # N167: the one rule (👥 Utenti → Accessi), by user and group
        base = self.cfg.base or self.cfg
        from .sys_users import Users
        admin = Users(base).admin_name()
        who = self.cfg.user                         # a host for no one in particular: what every user may
        allowed = (lambda n: G.may_use(base, who, G.of_plugin(n), admin)) if who else (lambda n: for_users(base, n))  # noqa: E731
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


def plugin_on(host, name: str) -> bool:
    """Whether plugin `name` is on in this host, starting none (C600: host.get() lists every plugin's tools — at each
    start of the API every user's host started them all from the routines' tick, 15–35 s a tick). For a caller that
    needs the plugin on, not its tools: the home's scenes, automations and watchers reach Home Assistant directly."""
    p = next((p for p in host.plugins(with_tools=False) if p.name == name), None)
    return p is not None and bool(p.available)
