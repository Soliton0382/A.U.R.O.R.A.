# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Sets of agents and routines by use, and the owner's own configuration as a set (owner, 2026-10-08: «template di
agenti e routine basati sulla mia configurazione e su configurazioni per diversi utilizzi come social, cyber security»).

 built-in   config/routine_templates.json: social, cyber security, research, home, development
 saved      a user's routines as they are now, kept as a set (<AURORA_STATUS_DIR>/routine_templates/<id>.json): seen
            by every user, deleted by whoever saved it or the admin
Applying a set creates only what is missing and can work: a routine already there (the same title, the same tool, the
same kind of video routine) is left alone; one whose plugins are not ready for this user is said and skipped; one
marked "admin" (the firewall, the videos on the GPU) is never offered to another user. What is created says where it
came from ("by": "template:<id>") and is the owner's click, like a plugin's suggestion.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from . import sys_config, sys_routines

BUILT_IN = Path(__file__).resolve().parents[1] / "config" / "routine_templates.json"
LEAD = re.compile(r"^[^\w«]+", re.U)
KEEP = ("kind", "plugin", "tool", "args", "goal", "schedule", "notify", "event", "propose", "icon", "plugins", "memory",
        "steps", "minutes", "action", "format", "title")


def _dir(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "routine_templates"


def _text(v, lang: str) -> str:
    return (v.get(lang) or v.get("en") or "") if isinstance(v, dict) else str(v or "")


def _name(title: str) -> str:
    return LEAD.sub("", title or "").strip().lower()


def saved(cfg: sys_config.Config) -> list[dict]:
    d = _dir(cfg)
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def packs(cfg: sys_config.Config) -> list[dict]:
    return json.loads(BUILT_IN.read_text(encoding="utf-8"))["packs"] + saved(cfg)


def needs(spec: dict) -> list[str]:
    """The plugins a routine cannot work without (an agent's first plugin; the others help when ready)."""
    if spec.get("needs"):
        return list(spec["needs"])
    if spec.get("kind") == "tool":
        return [spec["plugin"]]
    return list(spec.get("plugins") or [])[:1]


STOP = {"ogni", "della", "delle", "degli", "dalla", "dallo", "sulla", "nella", "the", "every", "from", "with"}


def _roots(title: str) -> set[str]:
    """The title's meaningful words, cut to their root (notturno ~ notturni)."""
    return {w[:6] for w in re.findall(r"[a-zà-ù]{4,}", _name(title)) if w not in STOP}


def _present(spec: dict, title: str, routines: list[dict]) -> dict | None:
    mine = _roots(title)
    for r in routines:
        theirs = _roots(r.get("title", ""))
        if _name(r.get("title", "")) == _name(title) or (len(mine) >= 3 and len(theirs) >= 3
                                                          and len(mine & theirs) >= 0.75 * min(len(mine), len(theirs))):
            return r
        if spec.get("kind") == "tool" and r.get("kind") == "tool" and (r.get("plugin"), r.get("tool")) == (spec.get("plugin"), spec.get("tool")):
            return r
        if spec.get("kind") == "story" and r.get("kind") == "story" and r.get("action", "make") == spec.get("action", "make"):
            return r
    return None


def view(cfg: sys_config.Config, lang: str, ready: set[str], admin: bool, user: str | None = None) -> list[dict]:
    """Every set this user may apply, each routine with its state: new | present | missing (plugins) ."""
    routines = sys_routines.all_routines(cfg)
    out = []
    for p in packs(cfg):
        if p.get("admin") and not admin:
            continue
        items = []
        for spec in p["routines"]:
            if spec.get("admin") and not admin:
                continue
            title = _text(spec.get("title"), lang)
            missing = [n for n in needs(spec) if n not in ready]
            there = _present(spec, title, routines)
            items.append({"title": title, "kind": spec.get("kind"), "icon": spec.get("icon", ""),
                          "schedule": spec.get("schedule"), "state": "present" if there else "missing" if missing else "new",
                          "missing": missing})
        out.append({"id": p["id"], "icon": p.get("icon", "🧩"), "title": _text(p.get("title"), lang),
                    "description": _text(p.get("description"), lang), "saved_by": p.get("saved_by"),
                    "mine": bool(p.get("saved_by")) and (p.get("saved_by") == user or admin), "items": items})
    return out


def apply(cfg: sys_config.Config, pack_id: str, lang: str, ready: set[str], admin: bool) -> dict:
    """{"created": [titles], "skipped": [{"title", "why"}]}: the set's missing routines, made."""
    pack = next((p for p in packs(cfg) if p["id"] == pack_id), None)
    if pack is None or (pack.get("admin") and not admin):
        raise KeyError(pack_id)
    created, skipped = [], []
    for spec in pack["routines"]:
        title = _text(spec.get("title"), lang)
        if spec.get("admin") and not admin:
            continue
        if _present(spec, title, sys_routines.all_routines(cfg)):
            skipped.append({"title": title, "why": "present"})
            continue
        missing = [n for n in needs(spec) if n not in ready]
        if missing:
            skipped.append({"title": title, "why": "missing", "plugins": missing})
            continue
        r = {k: spec[k] for k in KEEP if k in spec}
        r["title"], r["by"] = title, f"template:{pack['id']}"[:39]
        if "goal" in spec:
            r["goal"] = _text(spec["goal"], lang)
        if r.get("plugins"):
            r["plugins"] = [n for n in r["plugins"] if n in ready]
        sys_routines.create(cfg, r)
        created.append(title)
    return {"created": created, "skipped": skipped}


def save_mine(cfg: sys_config.Config, title: str, user: str | None, description: str = "") -> dict:
    """The user's routines switched on, as a set others can apply (their state, results and memory left out)."""
    rs = [r for r in sys_routines.all_routines(cfg) if r.get("enabled", True)]
    if not rs:
        raise ValueError("no routine switched on to save")
    pid = "mine-" + (re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:20] or "set")
    items = []
    for r in rs:
        spec = {k: r[k] for k in KEEP if k in r}
        if r.get("kind") == "story" or r.get("plugin") in ("security", "netintel", "backup", "self") \
                or set(r.get("plugins") or []) & {"security", "netintel", "backup", "self"}:
            spec["admin"] = True                                # never offered to another user
        items.append(spec)
    pack = {"id": pid, "icon": "📸", "title": {"it": title, "en": title}, "description": {"it": description, "en": description},
            "saved_by": user, "saved_at": time.time(), "routines": items}
    d = _dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{pid}.json.tmp"
    tmp.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, d / f"{pid}.json")
    return {"id": pid, "routines": len(items)}


def delete_saved(cfg: sys_config.Config, pack_id: str, user: str | None, admin: bool) -> None:
    f = _dir(cfg) / f"{pack_id}.json"
    if not re.fullmatch(r"mine-[a-z0-9-]{1,30}", pack_id) or not f.is_file():
        raise KeyError(pack_id)
    if not admin and json.loads(f.read_text(encoding="utf-8")).get("saved_by") != user:
        raise PermissionError("only who saved it, or the admin")
    f.unlink()
