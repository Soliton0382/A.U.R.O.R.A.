# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Groups of users and who may use what (owner, 27 Nov: «a livello admin si deve poter decidere chi può accedere ad
evidentia oppure no… che gli utenti siano inseribili in gruppi e che l'accesso ai plugin etc sia possibile o tramite
la selezione utenti o tramite selezione gruppi»).

  groups    {name: [users]} — a user may be in several;
  access    {feature: {"all": bool, "users": [...], "groups": [...]}} — a feature is «plugin:<name>» or
            «addon:<name>»; «all» lets every user in, otherwise only the users listed and the members of the groups
            listed. The admin always may. A feature with no rule takes its default: a plugin is open to everyone (as
            before), an add-on is the admin's until the admin opens it (Evidentia holds a case's documents).
Kept in <STATUS>/users/groups.json, written atomically.

N165 (owner, 27 Nov: «funzionalità e non plugin»): what is opened or closed is a FEATURE of config/access_features.json
— its pages, its plugins, its API prefixes — and, for a plugin in no feature (a connector, a tool), «plugin:<name>» as
before. A rule kept under an old name (plugin:calendar, addon:evidentia) is read as its feature's."""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from . import sys_config

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
FEATURE = re.compile(r"^([a-z][a-z0-9_]{0,40}|plugin:[a-z0-9_-]{1,64})$")
REGISTRY = Path(__file__).resolve().parents[1] / "config" / "access_features.json"
_registry: list[dict] | None = None


def registry() -> list[dict]:
    global _registry
    if _registry is None:
        _registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["features"]
    return _registry


def feature_ids() -> set[str]:
    return {f["id"] for f in registry()}


def of_plugin(name: str) -> str:
    """The feature a plugin belongs to, or plugin:<name> (a connector, a tool: a feature of its own)."""
    for f in registry():
        if name in f["plugins"]:
            return f["id"]
    return f"plugin:{name}"


def of_page(view: str) -> str | None:
    for f in registry():
        if view in f["pages"]:
            return f["id"]
    return None


def of_path(path: str) -> str | None:
    """The feature an API path belongs to (a listed prefix, whole segments only: /dj is not /dj-song's), or None."""
    best, n = None, 0
    for f in registry():
        for p in f["api"]:
            if (path == p or path.startswith(p + "/")) and len(p) > n:
                best, n = f["id"], len(p)
    return best


def canonical(feature: str) -> str:
    """An old rule's name as its feature's: plugin:calendar → calendar, addon:evidentia → evidentia."""
    if feature.startswith("addon:"):
        return feature[6:]
    if feature.startswith("plugin:"):
        return of_plugin(feature[7:])
    return feature
_lock = threading.Lock()


def _file(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "users" / "groups.json"


def load(cfg: sys_config.Config) -> dict:
    try:
        d = json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    out = {"groups": dict(d.get("groups") or {}), "access": dict(d.get("access") or {})}
    for name, on in _old_switches(cfg).items():      # the Plugins page's «👥 anche per gli altri utenti» (4 Oct):
        f = of_plugin(name)                          # kept as its feature's rule when no rule says otherwise
        if f not in out["access"] and not any(canonical(k) == f for k in out["access"]):
            out["access"][f] = {"all": bool(on), "users": [], "groups": [], "from": "plugin_access"}
    return out


def _old_switches(cfg: sys_config.Config) -> dict:
    f = (cfg.base or cfg).path("AURORA_STATUS_DIR") / "plugin_access.json"
    try:
        return {k: bool(v) for k, v in json.loads(f.read_text(encoding="utf-8")).items()} if f.is_file() else {}
    except (OSError, ValueError):
        return {}


def _save(cfg: sys_config.Config, d: dict) -> None:
    f = _file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(f)


_user_plugins: set | None = None


def user_plugins() -> set:
    """The plugins open to everyone by default (access_features.json «user_plugins»); any other plugin in no feature
    is the admin's until opened — a new or a forged one too, as plg_access had it since 4 Oct."""
    global _user_plugins
    if _user_plugins is None:
        _user_plugins = set(json.loads(REGISTRY.read_text(encoding="utf-8")).get("user_plugins") or [])
    return _user_plugins


def default(feature: str) -> bool:
    feature = canonical(feature)
    for f in registry():
        if f["id"] == feature:
            return f.get("default", "all") == "all"
    return feature.startswith("plugin:") and feature[7:] in user_plugins()


def groups_of(cfg: sys_config.Config, user: str) -> list[str]:
    return sorted(g for g, members in load(cfg)["groups"].items() if user in members)


def may_use(cfg: sys_config.Config, user: str | None, feature: str, admin: str | None = None) -> bool:
    if not user:
        return False
    if admin and user == admin:
        return True
    feature = canonical(feature)
    rule = _rules(cfg).get(feature)
    if rule is None:
        return default(feature)
    if rule.get("all"):
        return True
    return user in (rule.get("users") or []) or bool(set(groups_of(cfg, user)) & set(rule.get("groups") or []))


def _rules(cfg: sys_config.Config) -> dict:
    """The rules under their features' names (an old plugin:x / addon:x read as its feature; a new one wins)."""
    out: dict = {}
    for k, v in load(cfg)["access"].items():
        c = canonical(k)
        if c not in out or k == c:
            out[c] = v
    return out


def set_group(cfg: sys_config.Config, name: str, members: list[str] | None) -> dict:
    """A group made, changed (its members) or removed (members None); removed also from every rule."""
    if not NAME.match(name or ""):
        raise ValueError("a group's name: lowercase letters, digits, _ and - (at most 32)")
    with _lock:
        d = load(cfg)
        if members is None:
            d["groups"].pop(name, None)
            for rule in d["access"].values():
                rule["groups"] = [g for g in rule.get("groups") or [] if g != name]
        else:
            d["groups"][name] = sorted({str(m) for m in members if str(m)})
        _save(cfg, d)
        return d


def set_access(cfg: sys_config.Config, feature: str, all_: bool, users: list[str], groups: list[str]) -> dict:
    feature = canonical(feature or "")
    if not FEATURE.match(feature) or (":" not in feature and feature not in feature_ids()):
        raise ValueError("a feature of config/access_features.json, or plugin:<name>")
    with _lock:
        d = load(cfg)
        for old in [k for k in d["access"] if k != feature and canonical(k) == feature]:
            d["access"].pop(old)                       # the old name goes: one rule per feature
        unknown = [g for g in groups if g not in d["groups"]]
        if unknown:
            raise ValueError(f"no such group: {', '.join(unknown)}")
        d["access"][feature] = {"all": bool(all_), "users": sorted({str(u) for u in users if str(u)}),
                                "groups": sorted(set(groups))}
        _save(cfg, d)
        return d


def table(cfg: sys_config.Config, features: list[str]) -> list[dict]:
    """For the admin's page: each feature with its rule (or its default)."""
    acc = _rules(cfg)
    reg = {f["id"]: f for f in registry()}
    out = []
    for f in dict.fromkeys(canonical(x) for x in features):
        r = reg.get(f, {})
        out.append({"feature": f, **(acc.get(f) or {"all": default(f), "users": [], "groups": []}), "default": f not in acc,
                    "area": r.get("area", "tools"), "icon": r.get("icon", "🔌"), "it": r.get("it", f.split(":", 1)[-1]),
                    "en": r.get("en", f.split(":", 1)[-1])})
    return out


def denied_now(cfg: sys_config.Config, path: str) -> str | None:
    """N165: the feature an API path belongs to when the person of this request may not use it, else None."""
    f = of_path(path)
    return f if f is not None and not may_use_now(cfg, f) else None


def denied_pages(cfg: sys_config.Config, user: str | None, admin: str | None) -> list[str]:
    """The pages of the features this person may not use (the menu hides them)."""
    return sorted(p for f in registry() if not may_use(cfg, user, f["id"], admin) for p in f["pages"])


def may_use_now(cfg: sys_config.Config, feature: str) -> bool:
    """For the person of the running request or run (sys_context): an installation without users lets everything
    through, as before; with users, the rules above."""
    from . import sys_context
    from .sys_users import Users
    base = cfg.base or cfg
    admin = Users(base).admin_name()
    if admin is None:
        return True
    return may_use(base, sys_context.user() or admin, feature, admin)
