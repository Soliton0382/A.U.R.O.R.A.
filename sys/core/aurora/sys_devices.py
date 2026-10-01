# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Registered devices: a browser logs in once with the API key and receives a device token.

The token travels in an HttpOnly cookie (never readable by page scripts) and is
stored here only as a SHA-256 hash, in <AURORA_STATUS_DIR>/devices.json (mode 600).
A device can be revoked from the WebUI; the API key itself keeps working for
third-party clients (Chatbox, LibreChat).
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
import uuid
from pathlib import Path

from . import sys_config

COOKIE = "aurora_device"
_lock = threading.Lock()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Devices:
    def __init__(self, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.file: Path = self.cfg.path("AURORA_STATUS_DIR") / "devices.json"
        self._last_touch: dict[str, float] = {}

    def _load(self) -> list[dict]:
        return json.loads(self.file.read_text(encoding="utf-8")) if self.file.exists() else []

    def _save(self, items: list[dict]) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=1)
        os.replace(tmp, self.file)

    def register(self, name: str, agent: str) -> tuple[str, dict]:
        """A new device: returns (token, public record). The token is shown only now."""
        token = secrets.token_urlsafe(32)
        rec = {"id": uuid.uuid4().hex[:12], "name": name.strip()[:80] or "device", "agent": agent[:200],
               "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "last_seen": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "token_sha256": _hash(token)}
        with _lock:
            items = self._load()
            items.append(rec)
            self._save(items)
        return token, self.public(rec)

    def check(self, token: str) -> dict | None:
        """The device of a token, or None. Updates last_seen at most once a minute."""
        if not token:
            return None
        h = _hash(token)
        with _lock:
            items = self._load()
            rec = next((d for d in items if secrets.compare_digest(d["token_sha256"], h)), None)
            if rec and time.time() - self._last_touch.get(rec["id"], 0) > 60:
                rec["last_seen"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._last_touch[rec["id"]] = time.time()
                self._save(items)
        return rec

    def list(self) -> list[dict]:
        with _lock:
            return [self.public(d) for d in self._load()]

    def revoke(self, device_id: str) -> bool:
        with _lock:
            items = self._load()
            kept = [d for d in items if d["id"] != device_id]
            if len(kept) == len(items):
                return False
            self._save(kept)
        return True

    @staticmethod
    def public(rec: dict) -> dict:
        return {k: v for k, v in rec.items() if k != "token_sha256"}
