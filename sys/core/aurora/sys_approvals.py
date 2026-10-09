# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The approval gate: actions that wait for the owner.

Every action has an effect (ECOSYSTEM §3.3):
  read          automatic
  write_local   automatic, logged
  external      waits for the owner when AURORA_CONFIRM_EXTERNAL_ACTIONS is on (send, publish, push); Aurora's own
                posts on her social pages may go without waiting (AURORA_SOCIAL_AUTONOMY, a level-B-exempt
                installation only, the listed tools, at most AURORA_SOCIAL_POSTS_PER_DAY a day): each is recorded
                here with status "auto" and told to the owner
  code_change   a change to Aurora's own code: waits for the owner when AURORA_FORGE_MODE is "ask"

A request keeps what is needed to decide and to act: who asks, why, the preview (a message,
a diff with the test results), and what to execute once approved. Requests live in
<AURORA_STATUS_DIR>/approvals.json; every change of state is logged and traced.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

from . import sys_config, sys_log

EFFECTS = ("read", "write_local", "external", "code_change")
_lock = threading.Lock()


def needs_owner(effect: str, cfg: sys_config.Config, action: str = "") -> bool:
    """`action` is "plugin.tool": a post of Aurora's own may be autonomous (social_auto)."""
    from . import sys_ethics
    if effect in ("external", "code_change") and not sys_ethics.exempt(cfg):
        return True                                   # ethics code, level B: not negotiable by .env
    if effect == "external":
        if action and social_auto(cfg, action):
            return False
        return bool(cfg["AURORA_CONFIRM_EXTERNAL_ACTIONS"])
    if effect == "code_change":
        return cfg["AURORA_FORGE_MODE"] != "auto"
    return False


def auto_tools(cfg: sys_config.Config) -> set[str]:
    return {t.strip() for t in str(cfg["AURORA_SOCIAL_AUTO_TOOLS"]).split(",") if t.strip()}


def social_auto(cfg: sys_config.Config, action: str) -> bool:
    """A post Aurora may publish by herself now: switched on by the owner, a listed tool, under today's number."""
    if not cfg["AURORA_SOCIAL_AUTONOMY"] or action not in auto_tools(cfg):
        return False
    return Approvals(cfg).auto_today(auto_tools(cfg)) < int(cfg["AURORA_SOCIAL_POSTS_PER_DAY"])


# where an approval is decided, and its icon (owner, 9 Oct: «un alert che lampeggia nella barra in alto che mi porta
# nella pagina corretta (è un post, icona specifica che mi manda sui social)»)
SECURITY_PLUGINS = {"security"}


def social_plugins(cfg: sys_config.Config, folder: Path | None = None) -> set[str]:
    """The plugins whose manifest says «social» (their posts are approved in the Social page)."""
    out = set()
    for f in (folder or cfg.path("AURORA_PLUGINS_DIR")).glob("*/plugin.json"):
        try:
            if json.loads(f.read_text(encoding="utf-8")).get("social"):
                out.add(f.parent.name)
        except (OSError, ValueError):
            continue
    return out


def destination(item: dict, social: set[str]) -> dict:
    """{"view", "icon"}: the page where this request is read and decided."""
    kind = item.get("kind")
    target = item.get("action") or item.get("preview") or {}
    plugin, tool = str(target.get("plugin") or ""), str(target.get("tool") or "")
    if kind == "update":
        return {"view": "updates", "icon": "🔄"}
    if kind in ("forge_cloud", "plugin_install"):
        return {"view": "plugins", "icon": "🔨"}
    if kind == "code_change":
        return {"view": "approvals", "icon": "🧬"}
    if plugin in social:
        return {"view": "social", "icon": "🎬" if "video" in tool or "reel" in tool else "📣"}
    if plugin in SECURITY_PLUGINS:
        return {"view": "security", "icon": "🛡️"}
    return {"view": "approvals", "icon": "📤"}


def stats(items: list[dict]) -> dict:
    """The approvals page's numbers: each kind's requests, approved, rejected, waiting, and the time to decide."""
    from datetime import datetime
    out: dict[str, dict] = {}
    for a in items:
        k = out.setdefault(a.get("kind", "?"), {"requested": 0, "approved": 0, "rejected": 0, "pending": 0, "minutes": []})
        k["requested"] += 1
        st = a.get("status")
        if st == "pending":
            k["pending"] += 1
        elif st == "rejected":
            k["rejected"] += 1
        else:                                           # approved, executed, failed: the owner said yes
            k["approved"] += 1
        if a.get("decided") and a.get("created"):
            try:
                dt = datetime.fromisoformat(a["decided"]) - datetime.fromisoformat(a["created"])
                k["minutes"].append(dt.total_seconds() / 60)
            except (TypeError, ValueError):
                pass
    for k in out.values():
        m = sorted(k.pop("minutes"))
        k["median_minutes"] = round(m[len(m) // 2], 1) if m else None
    return out


class Approvals:
    def __init__(self, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        from . import sys_users_layout                 # the user's (the admin's after the migration: U3)
        self.file: Path = sys_users_layout.place(self.cfg, "state", self.cfg.user) / "approvals.json"
        self.log = sys_log.get_logger("approvals")

    def _load(self) -> list[dict]:
        return json.loads(self.file.read_text(encoding="utf-8")) if self.file.exists() else []

    def _save(self, items: list[dict]) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.file)

    def request(self, kind: str, effect: str, title: str, purpose: str, preview: dict, action: dict,
                run_id: str | None = None) -> dict:
        """A new pending request. `action` says what to execute once approved (plugin call, change id)."""
        item = {"id": uuid.uuid4().hex[:10], "kind": kind, "effect": effect, "title": title[:200],
                "purpose": purpose[:2000], "preview": preview, "action": action, "run_id": run_id,
                "status": "pending", "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "decided": None, "result": None}
        with _lock:
            items = self._load()
            items.append(item)
            self._save(items[-500:])
        self.log.info("audit: approval requested %s (%s, %s): %s", item["id"], kind, effect, title)
        sys_log.trace("approvals", "approval.request", {"id": item["id"], "kind": kind, "effect": effect, "title": title},
                      run_id=run_id)
        return item

    def record_auto(self, title: str, purpose: str, action: dict, result: str, run_id: str | None = None) -> dict:
        """An external action done without waiting (an autonomous post): kept with the others, status "auto"."""
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        item = {"id": uuid.uuid4().hex[:10], "kind": "tool_call", "effect": "external", "title": title[:200],
                "purpose": purpose[:2000], "preview": action, "action": action, "run_id": run_id, "status": "auto",
                "created": now, "decided": now, "result": result[:2000]}
        with _lock:
            items = self._load()
            items.append(item)
            self._save(items[-500:])
        self.log.info("audit: autonomous action %s: %s", item["id"], title)
        sys_log.trace("approvals", "approval.auto", {"id": item["id"], "title": title}, run_id=run_id)
        return item

    def auto_today(self, titles: set[str]) -> int:
        today = time.strftime("%Y-%m-%d")
        with _lock:
            return sum(1 for a in self._load() if a["status"] == "auto" and a["title"] in titles
                       and str(a.get("created", "")).startswith(today))

    def get(self, approval_id: str) -> dict | None:
        with _lock:
            return next((a for a in self._load() if a["id"] == approval_id), None)

    def list(self, status: str | None = None) -> list[dict]:
        with _lock:
            items = self._load()
        return [a for a in reversed(items) if status is None or a["status"] == status]

    def update(self, approval_id: str, **fields) -> dict:
        with _lock:
            items = self._load()
            item = next((a for a in items if a["id"] == approval_id), None)
            if item is None:
                raise KeyError(approval_id)
            item.update(fields)
            self._save(items)
        self.log.info("audit: approval %s -> %s", approval_id, fields.get("status", item["status"]))
        sys_log.trace("approvals", "approval.update", {"id": approval_id, **{k: v for k, v in fields.items()
                                                                          if k in ("status", "decided")}})
        return item
