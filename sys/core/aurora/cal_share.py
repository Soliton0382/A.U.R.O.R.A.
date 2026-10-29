# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""👥 The people of an appointment (owner, 30 Oct: «io e mia moglie abbiamo un appuntamento… vorrei aggiungere anche
lei… così ad entrambi aurora manda il promemoria… magari anche indirizzi email»).

- Another user of this installation: the appointment enters their calendar at once (owner's choice), «da <name>»,
  with its alerts — a copy in their own sealed file, so their reminders are theirs. Changed or deleted by its maker,
  the copies follow; a participant who deletes it leaves it (taken off the maker's list), and may change only their
  own alerts.
- An address: an invitation (.ics, METHOD:REQUEST; CANCEL when it is called off) sent from the maker's own mailbox
  (the ✉️ plugin), so the other calendar — Google, Outlook, Apple — adds it and reminds by itself. Only on the maker's
  word in the form (a notice: «to addresses outside Aurora's users, go on?» — owner, 30 Oct: the confirmation in the
  form, not a request to approve elsewhere); the text says it was sent with Aurora, an AI assistant.

The copies are written in the other user's own configuration (sys_user_config.for_user): the API's process writes
each user's calendar as the minute's watcher already reads it."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from . import cal_store, sys_config, sys_user_config

MAX_PEOPLE = 20
EMAIL = re.compile(r"^[^@\s<>\"',;]{1,64}@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
FIELDS = ("kind", "title", "start", "end", "all_day", "location", "notes", "repeat", "skip", "people")


def normalize(people, me: str | None, users: list[str]) -> list[dict]:
    """[{"user": name} | {"email": address}] from what the form sent: a user of this installation (never oneself), an
    address well formed; doubles dropped, at most MAX_PEOPLE. A name that is not a user is refused, said."""
    out, seen = [], set()
    for p in people or []:
        if isinstance(p, str):
            p = {"email": p} if "@" in p else {"user": p}
        if p.get("user"):
            u = str(p["user"]).strip()
            if u not in users:
                raise ValueError(f"people: {u} is not a user of this installation")
            k = ("user", u)
            if u == me or k in seen:
                continue
            out.append({"user": u})
        elif p.get("email"):
            e = str(p["email"]).strip().lower()
            if not EMAIL.match(e):
                raise ValueError(f"people: {e} is not an e-mail address")
            k = ("email", e)
            if k in seen:
                continue
            out.append({"email": e})
        else:
            continue
        seen.add(k)
    if len(out) > MAX_PEOPLE:
        raise ValueError(f"people: at most {MAX_PEOPLE}")
    return out


def users_of(item: dict) -> set[str]:
    return {p["user"] for p in item.get("people") or [] if p.get("user")}


def emails_of(item: dict) -> list[str]:
    return [p["email"] for p in item.get("people") or [] if p.get("email")]


def copy_id(maker: str, iid: str) -> str:
    """The copy's id in a participant's calendar: the same for the same appointment, never one of theirs."""
    return "s" + hashlib.sha256(f"{maker}|{iid}".encode()).hexdigest()[:10]


def _cfg(base: sys_config.Config, name: str) -> sys_config.Config:
    c = sys_user_config.for_user(base, name)
    cal_store.ready(c)
    return c


def _put(c: sys_config.Config, row: dict) -> None:
    rows = cal_store.items(c)
    old = next((r for r in rows if r["id"] == row["id"]), None)
    if old:                                                  # their own alerts stay theirs
        row = {**row, "alerts": old.get("alerts", row["alerts"]), "created": old.get("created", row["created"])}
    cal_store._save(c, [row if r["id"] == row["id"] else r for r in rows] if old else rows + [row])


def _drop(c: sys_config.Config, cid: str) -> None:
    rows = cal_store.items(c)
    if any(r["id"] == cid for r in rows):
        cal_store._save(c, [r for r in rows if r["id"] != cid])


def sync(base: sys_config.Config, maker: str, item: dict, before: dict | None = None) -> list[str]:
    """The maker's appointment saved: in every invited user's calendar as it is now; out of the ones no longer
    invited. → the users whose calendar changed."""
    cid = copy_id(maker, item["id"])
    now = set(users_of(item))
    for u in now:
        row = {**{k: item.get(k) for k in FIELDS}, "id": cid, "alerts": item.get("alerts") or [],
               "shared_from": {"user": maker, "id": item["id"]}, "by": "shared",
               "created": item.get("created"), "updated": item.get("updated")}
        _put(_cfg(base, u), row)
    gone = users_of(before or {}) - now
    for u in gone:
        _drop(_cfg(base, u), cid)
    return sorted(now | gone)


def unshare(base: sys_config.Config, maker: str, item: dict) -> list[str]:
    """The maker deleted it: out of every participant's calendar."""
    cid = copy_id(maker, item["id"])
    for u in users_of(item):
        _drop(_cfg(base, u), cid)
    return sorted(users_of(item))


def leave(base: sys_config.Config, user: str, copy: dict) -> None:
    """A participant deleted their copy: taken off the maker's list (the maker's appointment stays)."""
    src = copy.get("shared_from") or {}
    if not src.get("user"):
        return
    m = _cfg(base, src["user"])
    rows = cal_store.items(m)
    for r in rows:
        if r["id"] == src.get("id"):
            r["people"] = [p for p in r.get("people") or [] if p.get("user") != user]
    cal_store._save(m, rows)


# ---- the invitation by e-mail -----------------------------------------------------------------------------------------
def invitation(item: dict, z, maker: str, organizer: str, method: str = "REQUEST") -> tuple[str, str, str]:
    """(subject, body, .ics) for the addresses of `item`: METHOD:REQUEST (new or changed) or CANCEL; the same UID
    each time and a SEQUENCE that grows, so the other calendar updates the one it has."""
    from . import cal_text
    ics = cal_text.to_ics([item], z)
    seq = int(item.get("updated") or 0) - int(item.get("created") or 0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    extra = [f"ORGANIZER:mailto:{organizer}"] + [f"ATTENDEE;RSVP=TRUE;ROLE=REQ-PARTICIPANT:mailto:{e}" for e in emails_of(item)]
    extra += [f"SEQUENCE:{max(0, seq)}", f"LAST-MODIFIED:{stamp}"] + (["STATUS:CANCELLED"] if method == "CANCEL" else [])
    ics = ics.replace("CALSCALE:GREGORIAN\r\n", f"CALSCALE:GREGORIAN\r\nMETHOD:{method}\r\n", 1)
    ics = ics.replace("BEGIN:VEVENT\r\n", "BEGIN:VEVENT\r\n" + "".join(x + "\r\n" for x in extra), 1)
    when = item["start"].replace("T", " ") if not item.get("all_day") else item["start"][:10]
    where = f" — {item['location']}" if item.get("location") else ""
    if method == "CANCEL":
        subject = f"Annullato: {item['title']} ({when})"
        body = f"{maker} ha annullato l'appuntamento «{item['title']}» del {when}{where}."
    else:
        subject = f"Invito: {item['title']} ({when})"
        body = (f"{maker} ti invita: «{item['title']}», {when}{where}.\n"
                + (f"\n{item['notes']}\n" if item.get("notes") else "")
                + "\nL'invito allegato (.ics) lo aggiunge al tuo calendario, che ti avviserà.")
    return subject, body, ics
