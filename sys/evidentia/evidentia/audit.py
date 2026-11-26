# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The case file's audit trail (owner, 27 Nov: «essendo che è per un ufficio legale, il tracing deve esserci, non
dentro aurora… nel caso sia necessario ricostruire i passaggi, evidentia deve avere la possibilità di verificare quei
log… un log dedicato… segue i fascicoli»).

Every step an agent takes for a case — the question, each tool called with its arguments, what came back, the answer —
is appended to <EVD_DATA_DIR>/audit/<case>.jsonl, never rewritten. Each line carries the SHA-256 of the line before
(`prev`) and its own (`hash`, over its number, time, author, event and payload): a line removed, changed or reordered
breaks the chain, and verify() says where. Protected names are masked before they are written, as everywhere the
archive keeps something (B24). Aurora keeps none of it: her side only hands the steps over at the end of a run."""
from __future__ import annotations

import fcntl
import hashlib
import json
import re
import time
from pathlib import Path

CASE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
GENESIS = "0" * 64
MAX_PAYLOAD = 8000                      # characters of one step's payload kept (the rest said as cut)
MAX_ENTRIES = 2000                      # steps in one hand-over


def _file(data: Path, case: str) -> Path:
    if not CASE.match(case or ""):
        raise ValueError("a case's id: letters, digits, _ and - (at most 64)")
    d = data / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{case}.jsonl"


def _digest(prev: str, n: int, t: float, who: str, event: str, payload: str) -> str:
    body = json.dumps([prev, n, round(t, 3), who, event, payload], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _last(f: Path) -> tuple[int, str]:
    if not f.exists() or f.stat().st_size == 0:
        return 0, GENESIS
    with open(f, "rb") as fh:
        fh.seek(max(0, f.stat().st_size - 65536))
        last = fh.read().splitlines()[-1]
    row = json.loads(last)
    return int(row["n"]), row["hash"]


def append(data: Path, case: str, entries: list[dict], who: str, mask=lambda s: s) -> int:
    """Append the steps (each {"event", "payload"}) to the case's trail; returns how many were written."""
    f = _file(data, case)
    entries = list(entries)[:MAX_ENTRIES]
    with open(f.with_suffix(".lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        n, prev = _last(f)
        out = []
        for e in entries:
            if not isinstance(e, dict):
                raise ValueError("entries: a list of {event, payload}")
            payload = json.dumps(e.get("payload"), ensure_ascii=False, default=str)
            if len(payload) > MAX_PAYLOAD:
                payload = payload[:MAX_PAYLOAD] + f"… [cut: {len(payload)} characters]"
            payload = mask(payload)
            n += 1
            t = time.time()
            event = str(e.get("event", ""))[:80]
            h = _digest(prev, n, t, who[:80], event, payload)
            out.append(json.dumps({"n": n, "t": round(t, 3), "who": who[:80], "event": event, "payload": payload,
                                   "prev": prev, "hash": h}, ensure_ascii=False))
            prev = h
        with open(f, "a", encoding="utf-8") as fh:
            fh.write("".join(line + "\n" for line in out))
    return len(out)


def read(data: Path, case: str, limit: int = 500) -> list[dict]:
    f = _file(data, case)
    if not f.exists():
        return []
    rows = f.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(r) for r in rows]


def verify(data: Path, case: str) -> dict:
    """{"ok", "lines", "broken_at", "why"}: the whole chain recomputed from the first line."""
    f = _file(data, case)
    if not f.exists():
        return {"ok": True, "lines": 0, "broken_at": None, "why": ""}
    prev, n = GENESIS, 0
    for i, raw in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(raw)
        except ValueError:
            return {"ok": False, "lines": i - 1, "broken_at": i, "why": "not a JSON line"}
        if row.get("prev") != prev or row.get("n") != n + 1:
            return {"ok": False, "lines": i - 1, "broken_at": i, "why": "a line missing, moved or out of order"}
        if _digest(prev, row["n"], row["t"], row["who"], row["event"], row["payload"]) != row.get("hash"):
            return {"ok": False, "lines": i - 1, "broken_at": i, "why": "a line changed after it was written"}
        prev, n = row["hash"], row["n"]
    return {"ok": True, "lines": n, "broken_at": None, "why": ""}
