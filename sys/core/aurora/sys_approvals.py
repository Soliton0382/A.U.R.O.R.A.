# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The approval gate: actions that wait for the owner.

Every action has an effect (ECOSYSTEM §3.3):
  read          automatic
  write_local   automatic, logged
  external      waits for the owner when AURORA_CONFIRM_EXTERNAL_ACTIONS is on (send, publish, push)
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


def needs_owner(effect: str, cfg: sys_config.Config) -> bool:
    from . import sys_ethics
    if effect in ("external", "code_change") and not sys_ethics.exempt(cfg):
        return True                                   # ethics code, level B: not negotiable by .env
    if effect == "external":
        return bool(cfg["AURORA_CONFIRM_EXTERNAL_ACTIONS"])
    if effect == "code_change":
        return cfg["AURORA_FORGE_MODE"] != "auto"
    return False


class Approvals:
    def __init__(self, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.file: Path = self.cfg.path("AURORA_STATUS_DIR") / "approvals.json"
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
