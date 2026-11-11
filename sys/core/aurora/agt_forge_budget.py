# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The forge's budget (C560, 12 Nov): how often a missing capability may become a build.

A build is up to 3 attempts of the reasoner, the tests in the cage and, when the local forge fails, an approval asked
of the owner for the cloud. Before, only «pending», «building» and «proposed» joined an open request: a need whose
build had failed, was declined by the owner or was waiting for the cloud was queued again at the next run — an hourly
routine whose report says «no tool» started one every hour. Now, per user:

 join      the same need (the same words, or nearly: SAME) with a request still alive (LIVE) joins it
 cooldown  the same need failed or declined in the last COOLDOWN_S is not queued again: said to the agent
 daily     at most DAILY new requests in 24 hours
 routine   a routine that queued a request in the last ROUTINE_S is not checked for gaps again (no reasoner call)
The numbers are the code's, not settings: nothing here widens with an .env.
"""
from __future__ import annotations

import difflib
import re
import time

LIVE = ("pending", "building", "proposed", "awaiting_cloud")
DEAD = ("failed", "declined")
COOLDOWN_S = 7 * 86400
ROUTINE_S = 86400
DAILY = 3                 # ceiling: 3 builds × 3 attempts = 9 reasoner calls and 3 cloud questions a day per user
SAME = 0.8                # difflib ratio of the two needs' words from which they are one need


def words(need: str) -> str:
    """The need without case, punctuation and spacing: «Read the UPS log!» and «read the ups log» are one."""
    return " ".join(re.findall(r"\w+", str(need).lower()))


def same(a: str, b: str) -> bool:
    a, b = words(a), words(b)
    return bool(a) and (a == b or difflib.SequenceMatcher(None, a, b).ratio() >= SAME)


def decide(mine: list[dict], need: str, now: float | None = None) -> tuple[str, dict | None]:
    """What becomes of a new need among this user's requests (opened: their «need» readable), newest counted first:
    ("join", the live request) · ("cooldown", the failed or declined one) · ("daily", None) · ("new", None)."""
    now = now or time.time()
    alike = [i for i in mine if same(i.get("need", ""), need)]
    live = next((i for i in alike if i.get("status") in LIVE), None)
    if live is not None:
        return "join", live
    dead = next((i for i in reversed(alike) if i.get("status") in DEAD
                 and now - float(i.get("decided") or i.get("started") or i.get("created") or 0) < COOLDOWN_S), None)
    if dead is not None:
        return "cooldown", dead
    if sum(1 for i in mine if now - float(i.get("created") or 0) < 86400) >= DAILY:
        return "daily", None
    return "new", None


def said(verdict: str, item: dict | None) -> str:
    """The refusal the agent reads (and repeats to the owner): no build, and why."""
    if verdict == "cooldown":
        how = "was declined by the owner" if item and item.get("status") == "declined" else "was tried and failed"
        return (f"REFUSED: this capability {how} less than {COOLDOWN_S // 86400} days ago (forge request "
                f"{(item or {}).get('id', '?')}): it is not built again now. Say in your report that it is missing "
                "and that the owner can ask for it again in 🔨 Plugin.")
    return (f"REFUSED: the forge already took {DAILY} new requests in the last 24 hours, its daily limit. Say in your "
            "report which capability is missing; it can be asked again tomorrow.")


def routine_quiet(items: list[dict], routine: str | None, now: float | None = None) -> bool:
    """A routine that queued a request in the last ROUTINE_S (whatever became of it): its report is not read for
    gaps again — the reasoner is not asked every round what it already answered."""
    now = now or time.time()
    return bool(routine) and any(i.get("routine") == routine and now - float(i.get("created") or 0) < ROUTINE_S
                                 for i in items)
