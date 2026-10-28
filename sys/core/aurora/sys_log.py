# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Logging: one folder per component, a structured trace, rotation with gzip, retention.

    <AURORA_LOG_DIR>/<component>/<component>.log         human-readable log of a component
    <AURORA_LOG_DIR>/trace/<component>.jsonl             structured events of that component

Every file rotates at AURORA_LOG_MAX_MB into <name>.<YYYYmmdd-HHMMSS>.<ext>.gz and
rotated files older than their retention are deleted, at each rotation and once a
day by aurora-rem (`python -m aurora.sys_log purge`), so idle components are cleaned
too. The retention is by kind (roadmap 78: the firewall's syslog and the trace were
124 of 150 MB in 9 days): firewall/ AURORA_LOG_RETENTION_FIREWALL_DAYS, trace/
AURORA_LOG_RETENTION_TRACE_DAYS, everything else AURORA_LOG_RETENTION_DAYS.

The trace is one file per component instead of one shared file: each component
runs in its own process, and rotating a file shared by several processes is not
safe. Readers merge the files by timestamp.

No chat's words in the trace (N64 phase 4, owner 29 Oct: «l'admin non può leggere il contenuto delle chat»): the
run events of the components that carry a chat (CHAT: the question, its translation, the draft, the answer, an
agent's goal, thoughts and tool arguments, the search queries, an approval's title) keep their structure plain — ids,
sids, counts, times, modes (PLAIN) — and every other value sealed with the run's user's key (sys_seal.seal_text, bound to
"<run_id>/<event>"); the pieces of a draft (OFF_DISK) are not written at all. A reader opens a line for its own user
only (open_record): another user's values become «(private: <user>)». The listeners and the usage counts still get the
payload as it was, in memory.
"""
from __future__ import annotations

import gzip
import itertools
import json
import logging
import os
import shutil
import sys
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from . import sys_config

MIB = 1024 * 1024
_cfg: sys_config.Config | None = None
_lock = threading.Lock()
_loggers: dict[str, logging.Logger] = {}
_tracers: dict[str, logging.Logger] = {}
_seq = itertools.count(1)
_listeners: list = []          # fn(component, event, payload): a service turns some trace events into notifications


def on_trace(fn) -> None:
    """Call fn for every trace event of this process (it must be quick and must not raise)."""
    _listeners.append(fn)


def configure(cfg: sys_config.Config) -> None:
    """Use this configuration instead of the process one (tests, tools)."""
    global _cfg
    with _lock:
        for lg in list(_loggers.values()) + list(_tracers.values()):
            for h in list(lg.handlers):
                h.close()
                lg.removeHandler(h)
        _loggers.clear()
        _tracers.clear()
        _cfg = cfg


def _config() -> sys_config.Config:
    return _cfg or sys_config.get()


# folder of AURORA_LOG_DIR -> its own retention (roadmap 78)
BY_KIND = {"firewall": "AURORA_LOG_RETENTION_FIREWALL_DAYS", "trace": "AURORA_LOG_RETENTION_TRACE_DAYS"}


def retention(cfg: sys_config.Config, folder: Path) -> int:
    """How many days the rotated files of this folder are kept."""
    key = BY_KIND.get(Path(folder).name)
    return int(cfg[key] if key else cfg["AURORA_LOG_RETENTION_DAYS"])


def purge(folder: Path, retention_days: int, now: float | None = None) -> list[Path]:
    """Delete rotated (.gz) files older than the retention period. The live file is never touched."""
    limit = (now or time.time()) - retention_days * 86400
    removed = []
    for f in Path(folder).glob("*.gz"):
        if f.stat().st_mtime < limit:
            f.unlink()
            removed.append(f)
    return removed


class GzipRotatingFileHandler(RotatingFileHandler):
    """Size-based rotation; the rotated file is gzip-compressed with a timestamp in its name."""

    def __init__(self, filename: Path, max_bytes: int, retention_days: int):
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        super().__init__(filename, maxBytes=max_bytes, backupCount=0, encoding="utf-8", delay=True)
        self.retention_days = retention_days

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None
        live = Path(self.baseFilename)
        if live.exists() and live.stat().st_size > 0:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            target = live.with_name(f"{live.stem}.{stamp}{live.suffix}.gz")
            n = 1
            while target.exists():
                target = live.with_name(f"{live.stem}.{stamp}-{n}{live.suffix}.gz")
                n += 1
            with open(live, "rb") as src, gzip.open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            live.unlink()
        purge(live.parent, self.retention_days)
        self.stream = self._open()


class _Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds")


def _caged() -> bool:
    """Inside the plugin cage the log folder is read-only: the host keeps the plugin's stderr instead
    (sys/logs/plugins/<plugin>.stderr.log), so a caged plugin logs there, every level."""
    return bool(os.environ.get("AURORA_IN_SANDBOX"))


def _handler(path: Path, fmt: str) -> logging.Handler:
    if _caged():
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(_Formatter(fmt))
        return h
    cfg = _config()
    h = GzipRotatingFileHandler(path, cfg["AURORA_LOG_MAX_MB"] * MIB, retention(cfg, Path(path).parent))
    h.setFormatter(_Formatter(fmt))
    return h


def get_logger(component: str) -> logging.Logger:
    """Logger writing to <LOG_DIR>/<component>/<component>.log; warnings also go to stderr."""
    with _lock:
        if component in _loggers:
            return _loggers[component]
        cfg = _config()
        lg = logging.getLogger(f"aurora.{component}")
        lg.setLevel(cfg["AURORA_LOG_LEVEL"])
        lg.propagate = False
        lg.addHandler(_handler(cfg.path("AURORA_LOG_DIR") / component / f"{component}.log",
                               "%(asctime)s %(levelname)s %(name)s %(message)s"))
        if not _caged():                                 # caged, the handler above is stderr already
            err = logging.StreamHandler(sys.stderr)
            err.setLevel(logging.WARNING)
            err.setFormatter(_Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
            lg.addHandler(err)
        _loggers[component] = lg
    if cfg.unknown_keys:
        lg.warning("keys in %s not declared in the settings schema: %s", cfg.env_file, ", ".join(cfg.unknown_keys))
    return lg


def trace(component: str, event: str, payload: dict[str, Any] | None = None,
          run_id: str | None = None, parent: int | None = None) -> int:
    """Append one structured event to <LOG_DIR>/trace/<component>.jsonl and return its sequence number."""
    with _lock:
        tr = _tracers.get(component)
        if tr is None:
            tr = logging.getLogger(f"aurora.trace.{component}")
            tr.setLevel(logging.INFO)
            tr.propagate = False
            tr.addHandler(_handler(_config().path("AURORA_LOG_DIR") / "trace" / f"{component}.jsonl", "%(message)s"))
            _tracers[component] = tr
        seq = next(_seq)
    record = {"ts": datetime.now().astimezone().isoformat(timespec="milliseconds"), "seq": seq,
              "pid": os.getpid(), "component": component, "event": event, "run_id": run_id,
              "parent": parent, "payload": payload or {}}
    from . import sys_context                        # whose work (multi-user): a purge removes a user's lines
    if sys_context.user():
        record["user"] = sys_context.user()
    if not sys_context.anonymous_now() and not (component in CHAT and event in OFF_DISK):
        # an anonymous chat's run: nothing on disk (sys_anon); a chat's words sealed with its user's key (N64)
        if component in CHAT and record["payload"]:
            record["payload"] = seal_fields(_config(), record["payload"], chat_keys(record["payload"]),
                                            f"{run_id}/{event}", record.get("user"))
        tr.info(json.dumps(record, ensure_ascii=False, default=str))
    from . import sys_usage                          # the usage counts (names and numbers only)
    sys_usage.count(_config(), component, event, payload or {}, record.get("user"))
    for fn in _listeners:
        try:
            fn(component, event, payload or {})
        except Exception:  # noqa: BLE001 — a listener never breaks the traced work
            pass
    return seq


# ---- a chat's words sealed (N64 phase 4) ---------------------------------------------------------------------------
# their run events carry a chat's words; "approvals": an approval's title quotes the chat (a tool call's purpose, a post)
CHAT = frozenset({"api", "agent", "search", "approvals"})
# the structure of an event, never a chat's words: ids, modes, names of tools and models, numbers in a dict
PLAIN = frozenset({"mode", "kind", "lang", "from", "effect", "plugin", "tool", "status", "stage", "domain", "provider",
                   "model", "role", "usage", "seconds", "speed", "hits", "reason", "id", "asked", "used", "region",
                   "by", "cloud", "found"})
OFF_DISK = frozenset({"synthesis.delta"})          # every piece of the draft: nobody reads them back from the trace
PRIVATE = "(private: {})"


def chat_keys(payload: dict) -> list[str]:
    """The keys of a run event whose values may hold a chat's words: every one but PLAIN and plain numbers."""
    return [k for k, v in payload.items()
            if k not in PLAIN and v is not None and not isinstance(v, (bool, int, float))]


def seal_fields(cfg: sys_config.Config, d: dict, keys, label: str, user: str | None) -> dict:
    """A copy of `d` with the values at `keys` sealed with `user`'s key (sys_seal.seal_text of the value as JSON, bound to
    `label`; no user: the admin's). A key that does not open here (a tool outside the services, sys_keyring.Locked)
    drops the value and keeps its length: never written in plaintext."""
    from . import sys_seal
    out = dict(d)
    for k in keys:
        v = out.get(k)
        if v is None or sys_seal.is_sealed(v):
            continue
        raw = json.dumps(v, ensure_ascii=False, default=str)
        try:
            out[k] = sys_seal.seal_text(cfg, raw, label, user, "state")
        except Exception:  # noqa: BLE001 — no key here: the length only
            out[k] = f"(not kept: {len(raw)} chars)"
    return out


def open_fields(cfg: sys_config.Config, d: dict, label: str, user: str | None) -> dict:
    """`d` with its sealed values opened with `user`'s key (a value of before N64 comes back as it is)."""
    from . import sys_seal
    out = dict(d)
    for k, v in d.items():
        if isinstance(v, str) and sys_seal.is_sealed(v):
            try:
                out[k] = json.loads(sys_seal.open_text(cfg, v, label, user, "state"))
            except Exception:  # noqa: BLE001 — changed, or not this user's
                out[k] = "(does not open)"
    return out


def hide_fields(d: dict, owner: str | None) -> dict:
    """`d` as another user sees it: every sealed value «(private: <owner>)»."""
    from . import sys_seal
    return {k: PRIVATE.format(owner or "?") if isinstance(v, str) and sys_seal.is_sealed(v) else v for k, v in d.items()}


def admin_name(cfg: sys_config.Config) -> str | None:
    """The admin's name after the per-user layout; None before it (one user: every line is theirs)."""
    from . import sys_users_layout
    return (sys_users_layout.migrated(cfg.base or cfg) or {}).get("admin")


def open_record(cfg: sys_config.Config, record: dict, viewer: str | None, admin: str | None = None) -> dict | None:
    """A trace line as `viewer` may see it: opened when it is theirs (no user on the line: the admin's), None when it
    is another user's — nobody reads another user's run (the admin neither)."""
    admin = admin if admin is not None else admin_name(cfg)
    if (record.get("user") or admin) != (viewer or admin):
        return None
    p = record.get("payload")
    if not isinstance(p, dict):
        return record
    return {**record, "payload": open_fields(cfg, p, f"{record.get('run_id')}/{record.get('event')}", record.get("user"))}


def scan_secrets(cfg: sys_config.Config | None = None) -> list[tuple[str, str]]:
    """(log file, secret name) for every .env secret whose value appears in a log of the last 2 days: no log
    must ever hold a key or a token (the daily check of aurora-rem; a hit becomes a security incident)."""
    import gzip
    cfg = cfg or _config()
    specs = {s["key"]: s for s in sys_config.load_schema()["settings"]}
    secrets = {k: str(cfg.values.get(k) or "") for k, s in specs.items() if s.get("secret")}
    secrets = {k: v for k, v in secrets.items() if len(v) >= 8 and v != "redacted"}
    hits, since = [], time.time() - 2 * 86400
    for f in cfg.path("AURORA_LOG_DIR").rglob("*"):
        if not f.is_file() or f.stat().st_mtime < since:
            continue
        try:
            data = (gzip.open(f, "rt", errors="replace") if f.suffix == ".gz" else open(f, errors="replace")).read()
        except OSError:
            continue
        hits += [(str(f.relative_to(cfg.root)), k) for k, v in secrets.items() if v in data]
    return hits


# written in append mode by programs without a rotating handler: the plugins' stderr, kept by the plugin host, and
# the music model's output (aud_song) — rotated here on every system, no logrotate of the machine needed (C452)
LOOSE = ("plugins/*.stderr.log", "song.log")


def rotate_loose(cfg: sys_config.Config | None = None) -> list[Path]:
    """Above AURORA_LOG_MAX_MB a loose log is compressed with a timestamp, as the handlers do, and emptied in
    place (copy, then cut to zero: a writer in append mode goes on at the new end; lines written between the copy
    and the cut, a few milliseconds, are lost)."""
    cfg = cfg or _config()
    root, limit, out = cfg.path("AURORA_LOG_DIR"), cfg["AURORA_LOG_MAX_MB"] * MIB, []
    for pattern in LOOSE:
        for live in sorted(root.glob(pattern)):
            if live.stat().st_size <= limit:
                continue
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            target = live.with_name(f"{live.stem}.{stamp}{live.suffix}.gz")
            with open(live, "r+b") as src:
                with gzip.open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                src.truncate(0)
            out.append(target)
    return out


def purge_all(cfg: sys_config.Config | None = None) -> list[Path]:
    """Daily (aurora-rem): rotate the loose logs, then delete every rotated file older than the retention."""
    cfg = cfg or _config()
    rotated = rotate_loose(cfg)
    if rotated:
        get_logger("sys_log").info("rotated %d loose logs: %s", len(rotated), ", ".join(f.name for f in rotated))
    removed = []
    root = cfg.path("AURORA_LOG_DIR")
    for folder in [root] + [p for p in root.rglob("*") if p.is_dir()]:
        removed += purge(folder, retention(cfg, folder))
    return removed


def main(argv: list[str]) -> int:
    if argv[:1] != ["purge"]:
        print("usage: python -m aurora.sys_log purge", file=sys.stderr)
        return 2
    removed = purge_all()
    cfg = _config()
    get_logger("sys_log").info("purge: %d rotated files removed (kept: %d days, firewall %d, trace %d)", len(removed),
                               cfg["AURORA_LOG_RETENTION_DAYS"], cfg["AURORA_LOG_RETENTION_FIREWALL_DAYS"],
                               cfg["AURORA_LOG_RETENTION_TRACE_DAYS"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
