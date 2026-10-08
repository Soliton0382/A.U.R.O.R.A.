# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own calendar (owner, 2026-10-08: «un calendario tutto suo… così se c'è bisogno può gestire appuntamenti,
reminder etc.»): each user's appointments and reminders, sealed, with no account and no service needed.

An item is an "event" (an appointment: a start, an end or all-day) or a "reminder" (one moment: «chiama Marco alle 9»).
Times are wall-clock times in AURORA_TIMEZONE ("2026-10-09T10:00"), so a weekly appointment stays at 10:00 across
the change to and from summer time. Repeats: daily, weekly, monthly, yearly, with an interval and an end (a date or a
number of times), expanded by txt_ical's rule engine; one occurrence can be skipped. Alerts: minutes before the start.

Where: AURORA_CALENDAR_DIR/events.sealed (usr/<name>/calendar), sealed with the user's "calendar" key (sys_seal: the
data at rest, not against root). What was already told (the alerts fired, snoozed, answered) is state, apart:
<state>/calendar_fired.json, so the page, the chat and the minute's watcher never write the same file for each other.
The other calendars (Google, Outlook, CalDAV) are cal_external's: read and shown beside, never mixed into this file.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import sys_config, sys_seal, sys_users_layout as L, txt_ical

PURPOSE = "calendar"
KINDS = ("event", "reminder")
FREQS = ("daily", "weekly", "monthly", "yearly")
WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
MAX_ITEMS = 5000
MAX_ALERTS = 5
MAX_ALERT_MIN = 28 * 24 * 60                       # four weeks before: the furthest alert asked of a calendar app
LATE = 12 * 3600                                   # an alert missed while Aurora was off is still told, up to 12 h late
PENDING = 3 * 3600                                 # an alert not answered stays in the chat for 3 h
FMT = "%Y-%m-%dT%H:%M"


# ---- where ------------------------------------------------------------------------------------------------------------
def tz(cfg: sys_config.Config):
    try:
        return ZoneInfo(str(cfg.values.get("AURORA_TIMEZONE") or ""))
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now().astimezone().tzinfo


def _file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_CALENDAR_DIR") / "events.sealed"


def _state(cfg: sys_config.Config) -> Path:
    return L.place(cfg, "state", cfg.user) / "calendar_fired.json"


def ready(cfg: sys_config.Config) -> None:
    """The user's key made (by the API: a plugin's cage cannot write the state folder)."""
    sys_seal._key(cfg, cfg.user, PURPOSE)


# ---- the items --------------------------------------------------------------------------------------------------------
def items(cfg: sys_config.Config) -> list[dict]:
    f = _file(cfg)
    return json.loads(sys_seal.read(cfg, f, cfg.user, PURPOSE)) if f.exists() else []


def _save(cfg: sys_config.Config, rows: list[dict]) -> None:
    sys_seal.write(cfg, _file(cfg), json.dumps(rows, ensure_ascii=False).encode(), cfg.user, PURPOSE)


def _wall(v, field: str, all_day: bool = False) -> str:
    """A wall-clock time as stored: "YYYY-MM-DDTHH:MM" (all-day: the time is 00:00)."""
    s = str(v or "").strip().replace(" ", "T")
    try:
        d = datetime.fromisoformat(s[:16]) if "T" in s else datetime.combine(date.fromisoformat(s[:10]), datetime.min.time())
    except ValueError:
        raise ValueError(f"{field}: YYYY-MM-DD HH:MM") from None
    return (d.replace(hour=0, minute=0) if all_day else d).strftime(FMT)


def _repeat(r) -> dict | None:
    if not r:
        return None
    if isinstance(r, str):
        r = {"freq": r}
    freq = str(r.get("freq", "")).lower()
    if freq not in FREQS:
        raise ValueError(f"repeat: one of {', '.join(FREQS)}")
    out = {"freq": freq, "interval": max(1, min(int(r.get("interval") or 1), 365))}
    if r.get("until"):
        out["until"] = date.fromisoformat(str(r["until"])[:10]).isoformat()
    if r.get("count"):
        out["count"] = max(1, min(int(r["count"]), txt_ical.MAX_OCCURRENCES))
    days = [str(d).upper()[:2] for d in r.get("days") or []]
    if days:
        if freq != "weekly" or not set(days) <= set(WEEKDAYS):
            raise ValueError("repeat days: weekly only, MO…SU")
        out["days"] = sorted(set(days), key=WEEKDAYS.index)
    return out


def validate(spec: dict, old: dict | None = None) -> dict:
    s = {**(old or {}), **{k: v for k, v in spec.items() if v is not None}}
    title = str(s.get("title") or "").strip()
    if not title:
        raise ValueError("title: an empty title")
    kind = s.get("kind") or "event"
    if kind not in KINDS:
        raise ValueError(f"kind: one of {KINDS}")
    all_day = bool(s.get("all_day")) and kind == "event"
    start = _wall(s.get("start"), "start", all_day)
    if kind == "reminder":
        end = start
    elif spec.get("end"):
        end = _wall(spec["end"], "end", all_day)
    elif spec.get("minutes") or not old or old.get("kind") != "event" or "all_day" in spec:
        mins = int(spec.get("minutes") or 60)
        end = (datetime.strptime(start, FMT) + (timedelta(days=1) if all_day else timedelta(minutes=max(5, min(mins, 24 * 60))))).strftime(FMT)
    else:                                                  # an edit that leaves the length alone: moved with the start
        length = datetime.strptime(old["end"], FMT) - datetime.strptime(old["start"], FMT)
        end = (datetime.strptime(start, FMT) + length).strftime(FMT)
    if all_day and end <= start:
        end = (datetime.strptime(start, FMT) + timedelta(days=1)).strftime(FMT)
    if end < start:
        raise ValueError("end: before the start")
    alerts = s.get("alerts")
    if alerts is None:
        alerts = [0] if kind == "reminder" else ([] if all_day else [30])
    if isinstance(alerts, (int, str)):
        alerts = [alerts]
    alerts = sorted({max(0, min(int(a), MAX_ALERT_MIN)) for a in alerts if str(a).strip() != ""})[:MAX_ALERTS]
    return {"id": s.get("id") or f"e{secrets.token_hex(4)}", "kind": kind, "title": title[:200], "start": start,
            "end": end, "all_day": all_day, "location": str(s.get("location") or "").strip()[:300],
            "notes": str(s.get("notes") or "").strip()[:4000], "alerts": alerts, "repeat": _repeat(s.get("repeat")),
            "skip": sorted(set(s.get("skip") or []))[-500:], "by": s.get("by") or "page",
            "created": s.get("created") or time.time(), "updated": time.time()}


def add(cfg: sys_config.Config, spec: dict) -> dict:
    rows = items(cfg)
    if len(rows) >= MAX_ITEMS:
        raise ValueError(f"the calendar is full ({MAX_ITEMS} items): delete the old ones")
    it = validate({k: v for k, v in spec.items() if k not in ("id", "created")})
    _save(cfg, rows + [it])
    return it


def add_many(cfg: sys_config.Config, specs: list[dict]) -> tuple[int, int]:
    """Several items in one write (an .ics imported): (added, unreadable)."""
    rows, bad = items(cfg), 0
    for spec in specs:
        if len(rows) >= MAX_ITEMS:
            bad += 1
            continue
        try:
            rows.append(validate({k: v for k, v in spec.items() if k not in ("id", "created")}))
        except (ValueError, TypeError):
            bad += 1
    _save(cfg, rows)
    return len(specs) - bad, bad


def get(cfg: sys_config.Config, iid: str) -> dict | None:
    return next((r for r in items(cfg) if r["id"] == iid), None)


def update(cfg: sys_config.Config, iid: str, changes: dict) -> dict:
    rows = items(cfg)
    old = next((r for r in rows if r["id"] == iid), None)
    if old is None:
        raise KeyError(iid)
    if "repeat" in changes and not changes["repeat"]:
        old = {**old, "repeat": None}
        changes = {k: v for k, v in changes.items() if k != "repeat"}
    new = validate({k: v for k, v in changes.items() if k not in ("id", "created", "by")}, old)
    _save(cfg, [new if r["id"] == iid else r for r in rows])
    return new


def delete(cfg: sys_config.Config, iid: str, occurrence: str | None = None) -> dict | None:
    """The whole item, or one occurrence of a repeated one (its start, "YYYY-MM-DDTHH:MM"): that one is skipped."""
    rows = items(cfg)
    old = next((r for r in rows if r["id"] == iid), None)
    if old is None:
        raise KeyError(iid)
    if occurrence and old.get("repeat"):
        new = {**old, "skip": sorted(set(old.get("skip", [])) | {_wall(occurrence, "occurrence", old["all_day"])}),
               "updated": time.time()}
        _save(cfg, [new if r["id"] == iid else r for r in rows])
        return new
    _save(cfg, [r for r in rows if r["id"] != iid])
    return None


# ---- the occurrences --------------------------------------------------------------------------------------------------
def _rule(rep: dict) -> dict:
    r = {"FREQ": rep["freq"].upper(), "INTERVAL": str(rep.get("interval", 1))}
    if rep.get("count"):
        r["COUNT"] = str(rep["count"])
    if rep.get("until"):
        r["UNTIL"] = rep["until"].replace("-", "")                  # a DATE: the whole last day included
    if rep.get("days"):
        r["BYDAY"] = ",".join(rep["days"])
    return r


def occurrences(cfg: sys_config.Config, a: datetime, b: datetime, rows: list[dict] | None = None) -> list[dict]:
    """Every occurrence overlapping [a, b), sorted: the item's fields with this occurrence's start and end (aware,
    ISO) and "at" (the stored wall time of this occurrence: what a skip or an alert names)."""
    z, out = tz(cfg), []
    for it in items(cfg) if rows is None else rows:
        s0 = datetime.strptime(it["start"], FMT).replace(tzinfo=z)
        length = datetime.strptime(it["end"], FMT) - datetime.strptime(it["start"], FMT)
        ev = {"start": s0, **({"rrule": _rule(it["repeat"])} if it.get("repeat") else {})}
        skip = set(it.get("skip") or [])
        for s in txt_ical._occurrences(ev, b):
            at = s.strftime(FMT)
            e = (s.replace(tzinfo=None) + length).replace(tzinfo=z)          # wall-clock length (a day stays a day)
            if at in skip or e <= a and not (length == timedelta(0) and s >= a) or s >= b:
                continue
            out.append({**it, "at": at, "start_iso": s.isoformat(), "end_iso": e.isoformat()})
    return sorted(out, key=lambda o: (o["start_iso"], o["title"]))


# ---- the alerts -------------------------------------------------------------------------------------------------------
def _fired(cfg: sys_config.Config) -> dict:
    try:
        return json.loads(_state(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_fired(cfg: sys_config.Config, data: dict) -> None:
    f = _state(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, f)


def alert_key(o: dict, minutes: int) -> str:
    return f"{o['id']}|{o['at']}|{minutes}"


def due(cfg: sys_config.Config, now: datetime | None = None) -> list[dict]:
    """The alerts whose moment came (up to LATE ago) and were not told yet, plus the snoozed ones whose time came;
    each marked told here, once. {key, item (the occurrence), minutes, late}."""
    now = now or datetime.now(tz(cfg))
    told = _fired(cfg)
    horizon = now + timedelta(minutes=MAX_ALERT_MIN + 1)
    out = []
    for o in occurrences(cfg, now - timedelta(seconds=LATE), horizon):
        start = datetime.fromisoformat(o["start_iso"])
        for m in o.get("alerts") or []:
            when = start - timedelta(minutes=m)
            k = alert_key(o, m)
            if k in told or not (now - timedelta(seconds=LATE) < when <= now):
                continue
            out.append({"key": k, "item": o, "minutes": m, "late": (now - when).total_seconds() > 300})
    for k, v in told.items():                                        # snoozed: told again when their time comes
        if v.get("snooze") and v["snooze"] <= now.timestamp() and not v.get("done"):
            iid, at, m = k.split("|")
            o = next((x for x in occurrences(cfg, datetime.strptime(at, FMT).replace(tzinfo=tz(cfg)) - timedelta(seconds=1),
                                             datetime.strptime(at, FMT).replace(tzinfo=tz(cfg)) + timedelta(days=2))
                      if x["id"] == iid and x["at"] == at), None)
            if o:
                out.append({"key": k, "item": o, "minutes": int(m), "late": False, "snoozed": True})
    if out:
        stamp = now.timestamp()
        for d in out:
            told[d["key"]] = {"at": stamp}
        cut = stamp - 3 * 24 * 3600                                  # the file stays small: three days of alerts
        _save_fired(cfg, {k: v for k, v in told.items() if v.get("at", 0) >= cut or v.get("snooze", 0) > stamp})
    return out


def pending(cfg: sys_config.Config, now: datetime | None = None) -> list[dict]:
    """The alerts told in the last PENDING seconds and not answered: the chat shows them when it opens."""
    now_ts = (now or datetime.now(tz(cfg))).timestamp()
    told = _fired(cfg)
    keys = [k for k, v in told.items() if not v.get("done") and not v.get("snooze") and now_ts - v.get("at", 0) < PENDING]
    if not keys:
        return []
    z, out = tz(cfg), []
    for k in keys:
        iid, at, m = k.split("|")
        w = datetime.strptime(at, FMT).replace(tzinfo=z)
        o = next((x for x in occurrences(cfg, w - timedelta(seconds=1), w + timedelta(days=2)) if x["id"] == iid and x["at"] == at), None)
        if o:
            out.append({"key": k, "item": o, "minutes": int(m), "told": told[k]["at"]})
    return sorted(out, key=lambda d: d["told"])


def answer(cfg: sys_config.Config, key: str, snooze_min: int = 0, now: datetime | None = None) -> dict:
    """An alert answered: done («ok»), or told again in `snooze_min` minutes."""
    told = _fired(cfg)
    if key not in told:
        raise KeyError(key)
    stamp = (now or datetime.now(tz(cfg))).timestamp()
    told[key] = ({"at": told[key]["at"], "snooze": stamp + max(1, min(int(snooze_min), 24 * 60)) * 60} if snooze_min
                 else {"at": told[key]["at"], "done": stamp})
    _save_fired(cfg, told)
    return told[key]
