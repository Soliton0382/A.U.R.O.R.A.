# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Logging: one folder per component, a structured trace, rotation with gzip, retention.

    <AURORA_LOG_DIR>/<component>/<component>.log         human-readable log of a component
    <AURORA_LOG_DIR>/trace/<component>.jsonl             structured events of that component

Every file rotates at AURORA_LOG_MAX_MB into <name>.<YYYYmmdd-HHMMSS>.<ext>.gz and
rotated files older than AURORA_LOG_RETENTION_DAYS are deleted, at each rotation
and by `python -m aurora.sys_log purge` (for a daily timer, so idle components
are cleaned too).

The trace is one file per component instead of one shared file: each component
runs in its own process, and rotating a file shared by several processes is not
safe. Readers merge the files by timestamp.
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


def _handler(path: Path, fmt: str) -> GzipRotatingFileHandler:
    cfg = _config()
    h = GzipRotatingFileHandler(path, cfg["AURORA_LOG_MAX_MB"] * MIB, cfg["AURORA_LOG_RETENTION_DAYS"])
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
    tr.info(json.dumps(record, ensure_ascii=False, default=str))
    return seq


def purge_all(cfg: sys_config.Config | None = None) -> list[Path]:
    cfg = cfg or _config()
    removed = []
    root = cfg.path("AURORA_LOG_DIR")
    for folder in [root] + [p for p in root.rglob("*") if p.is_dir()]:
        removed += purge(folder, cfg["AURORA_LOG_RETENTION_DAYS"])
    return removed


def main(argv: list[str]) -> int:
    if argv[:1] != ["purge"]:
        print("usage: python -m aurora.sys_log purge", file=sys.stderr)
        return 2
    removed = purge_all()
    get_logger("sys_log").info("purge: %d rotated files older than %d days removed",
                               len(removed), _config()["AURORA_LOG_RETENTION_DAYS"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
