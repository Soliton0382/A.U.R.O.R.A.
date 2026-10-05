# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The Autonomy panel (owner, 2026-10-05): how free Aurora is, area by area, in one place.

Each area has levels — 0 🔒 ask always, 1 🤝 propose and the owner decides, 2 🚀 by herself within limits — and a level
IS a set of existing settings: the level shown is read from them, a choice writes them. Nothing new to keep in sync.
Ready profiles (careful / balanced / free) choose every area at once. The ethics code's limits are never crossed by
a level: level A always; level B (an action outside the machine, a change of her code) only on an installation the
owner exempted — without it the 🚀 of social and security does nothing more than 🤝.

Who decides (owner): the machine's areas only the admin; a user's own areas (scope user: social) the user, if the
admin lets them choose (may_choose), else the admin for them. A new user starts careful.

What she did by herself is written to a ledger (log): the daily line of the panel. The statistics of her proposals
(approved, refused, done alone, undone by the owner) are counted per area; an area where she has proved good is
SUGGESTED for more freedom — never raised by herself.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter
from pathlib import Path

from . import sys_config

_lock = threading.Lock()
# area: (scope, {level: {setting: value}}) — the levels an area has are the keys
AREAS: dict[str, tuple[str, dict[int, dict[str, str]]]] = {
    "social": ("user", {0: {"AURORA_SOCIAL_AUTONOMY": "0"}, 2: {"AURORA_SOCIAL_AUTONOMY": "1"}}),
    "forge": ("machine", {0: {"AURORA_FORGE_MODE": "ask"}, 2: {"AURORA_FORGE_MODE": "auto"}}),
    "repairs": ("machine", {0: {"AURORA_SELF_REPAIR": "0"}, 1: {"AURORA_SELF_REPAIR": "1"}}),
    "security": ("machine", {0: {"AURORA_SENTINEL_INVESTIGATE": "0", "AURORA_DEFENCE_MODE": "suggest"},
                             1: {"AURORA_SENTINEL_INVESTIGATE": "1", "AURORA_DEFENCE_MODE": "suggest"},
                             2: {"AURORA_SENTINEL_INVESTIGATE": "1", "AURORA_DEFENCE_MODE": "auto"}}),
    "updates": ("machine", {0: {"AURORA_UPDATE_MODE": "off"}, 1: {"AURORA_UPDATE_MODE": "notify"},
                            2: {"AURORA_UPDATE_MODE": "auto"}}),
    "knowledge": ("machine", {0: {"AURORA_ACQUIRE_AUTO": "0"}, 2: {"AURORA_ACQUIRE_AUTO": "1"}}),
    "inner": ("machine", {0: {"AURORA_REM_ENABLED": "0"}, 2: {"AURORA_REM_ENABLED": "1"}}),
}
PROFILES = {
    "careful": {"social": 0, "forge": 0, "repairs": 0, "security": 1, "updates": 1, "knowledge": 0, "inner": 2},
    "balanced": {"social": 0, "forge": 0, "repairs": 1, "security": 1, "updates": 1, "knowledge": 2, "inner": 2},
    "free": {"social": 2, "forge": 2, "repairs": 1, "security": 2, "updates": 2, "knowledge": 2, "inner": 2},
}
EXTERNAL = {"social", "security"}       # their 🚀 acts outside the machine: level B decides
PROVED = {"days": 30, "decided": 10, "approved": 0.9}   # what "proved good" means; shown, never acted on alone


def _same(spec_type: str, a, b: str) -> bool:
    if spec_type == "bool":
        return bool(a) == (str(b).lower() in ("1", "true", "yes", "on"))
    return str(a) == str(b)


def levels(cfg: sys_config.Config) -> dict[str, int | None]:
    """Each area's level as its settings say now (None: a mix no level describes — changed by hand)."""
    types = {s["key"]: s["type"] for s in sys_config.load_schema()["settings"]}
    out = {}
    for area, (_, lv) in AREAS.items():
        out[area] = next((n for n, sets in sorted(lv.items())
                          if all(_same(types.get(k, "str"), cfg[k], v) for k, v in sets.items())), None)
    return out


def profile_of(lv: dict[str, int | None]) -> str:
    return next((name for name, p in PROFILES.items() if all(lv.get(a) == n for a, n in p.items())), "custom")


def changes(choice: dict[str, int]) -> tuple[dict[str, str], dict[str, str]]:
    """({machine settings}, {user settings}) for the chosen levels; ValueError for a level an area does not have."""
    machine, user = {}, {}
    for area, n in choice.items():
        if area not in AREAS:
            raise ValueError(f"unknown area: {area}")
        scope, lv = AREAS[area]
        if int(n) not in lv:
            raise ValueError(f"{area}: levels {sorted(lv)}")
        (user if scope == "user" else machine).update(lv[int(n)])
    return machine, user


# ---- who may choose -------------------------------------------------------------------------------------------------
def _policy_file(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "autonomy.json"


def policy(cfg: sys_config.Config) -> dict:
    f = _policy_file(cfg)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"may_choose": {}}
    except ValueError:
        return {"may_choose": {}}


def set_may_choose(cfg: sys_config.Config, user: str, allowed: bool) -> dict:
    with _lock:
        p = policy(cfg)
        p.setdefault("may_choose", {})[user] = bool(allowed)
        f = _policy_file(cfg)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(p, indent=1), encoding="utf-8")
        os.replace(tmp, f)
    return p


# ---- what she did by herself: the ledger and the daily line ---------------------------------------------------------
def _ledger(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "autonomy_ledger.jsonl"


def log(cfg: sys_config.Config, area: str, text: str, user: str | None = None) -> None:
    """One thing Aurora did by herself (a post, a block, an update, a search, a plugin)."""
    row = {"at": round(time.time(), 1), "day": time.strftime("%Y-%m-%d"), "area": area, "text": text[:240],
           "user": user or cfg.user}
    _ledger(cfg).parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(_ledger(cfg), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def days(cfg: sys_config.Config, n: int = 14, user: str | None = None) -> list[dict]:
    """[{"day", "count", "areas": {area: count}, "items": [...]}] newest first: the daily line."""
    f = _ledger(cfg)
    since = time.time() - n * 86400
    by: dict[str, list] = {}
    for line in f.read_text(encoding="utf-8").splitlines() if f.exists() else []:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r["at"] >= since and (user is None or r.get("user") in (user, None)):
            by.setdefault(r["day"], []).append(r)
    return [{"day": d, "count": len(rows), "areas": dict(Counter(r["area"] for r in rows)), "items": rows[-20:][::-1]}
            for d, rows in sorted(by.items(), reverse=True)]


# ---- statistics of her proposals, per area --------------------------------------------------------------------------
def area_of(item: dict, social_tools: set[str]) -> str:
    kind, title = item.get("kind", ""), item.get("title", "")
    if kind in ("forge_cloud", "plugin_install"):
        return "forge"
    if kind == "code_change":
        return "repairs"
    if title in social_tools or title.split(".")[0] in ("facebook", "instagram", "mastodon", "telegram"):
        return "social"
    return "other"


def statistics(cfg: sys_config.Config, approvals: list[dict], social_tools: set[str]) -> dict[str, dict]:
    """Per area over PROVED["days"]: proposed, approved, refused, done alone, and whether she proved good."""
    since = time.time() - PROVED["days"] * 86400
    out: dict[str, Counter] = {a: Counter() for a in AREAS}
    for it in approvals:
        try:
            t = time.mktime(time.strptime(str(it.get("created", ""))[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            continue
        if t < since:
            continue
        a = area_of(it, social_tools)
        if a not in out:
            continue
        st = it.get("status")
        out[a]["proposed"] += 1
        out[a]["approved" if st in ("approved", "executed") else "refused" if st == "rejected"
               else "alone" if st == "auto" else "failed" if st == "failed" else "pending"] += 1
    from . import sec_defence
    for b in sec_defence._load(cfg):
        if b.get("auto") and b["at"] >= since:
            out["security"]["alone"] += 1
            if b.get("released_by") == "owner":
                out["security"]["undone"] += 1
    res = {}
    for a, c in out.items():
        decided = c["approved"] + c["refused"]
        rate = c["approved"] / decided if decided else None
        res[a] = {**{k: c[k] for k in ("proposed", "approved", "refused", "alone", "failed", "pending", "undone")},
                  "rate": round(rate, 2) if rate is not None else None,
                  "proved": bool(decided >= PROVED["decided"] and rate >= PROVED["approved"] and not c["undone"])}
    return res
