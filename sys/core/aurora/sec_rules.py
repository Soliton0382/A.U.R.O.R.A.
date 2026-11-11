# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner's own checks on the firewall's syslog (owner, 2026-10-04): proposed by Aurora from the firewall's
documentation and from what it really sends (sec_profile), switched on by the owner in the Security page.

A rule: {"id", "title", "why", "match": {field: [values]}, "threshold": n, "window_min": m, "per_source": bool,
"action": text, "on": bool}. A syslog line matches when every field named has one of its values (case does not
matter; "log_id" may be given as its first digits). With per_source the count is per source address. n lines in m
minutes raise an incident of kind "rule:<id>", at most once an hour per source. Kept in
<AURORA_STATUS_DIR>/security/rules.json; aurora-sentinel reads the file again every minute. Defensive only.

C596: the rule set holds no more than it can count, like the detector (C566): a source's lines are counted by the
second (sec_sentinel.Window), a source silent for its rule's window and an alarm's mark older than its hour are
forgotten, new sources a minute and incidents a minute and an hour have a budget, and MAX_COUNTED sources at once
(measured before: 200,000 one-line sources kept 200,000 queues for ever, with every whole line).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from . import sys_config
from .sec_sentinel import Budget, Window

ID = re.compile(r"[a-z0-9_]{1,40}")
FIELD = re.compile(r"[a-z_]{1,40}")


def _file(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "security" / "rules.json"


def check(rule: dict) -> dict:
    """A rule as kept; ValueError for anything malformed (a rule comes from a model: never trusted as it is)."""
    if not ID.fullmatch(str(rule.get("id", ""))):
        raise ValueError("id: lowercase letters, digits, _ (max 40)")
    match = rule.get("match") or {}
    if not isinstance(match, dict) or not match or len(match) > 6:
        raise ValueError("match: 1 to 6 fields")
    clean = {}
    for k, v in match.items():
        vals = v if isinstance(v, list) else [v]
        if not FIELD.fullmatch(str(k).lower()) or not vals or len(vals) > 20:
            raise ValueError(f"match field {k!r}: a field name and 1 to 20 values")
        clean[str(k).lower()] = [str(x).lower()[:100] for x in vals]
    n, m = int(rule.get("threshold", 1)), int(rule.get("window_min", 10))
    if not 1 <= n <= 100000 or not 1 <= m <= 1440:
        raise ValueError("threshold 1-100000, window_min 1-1440")
    return {"id": rule["id"], "title": str(rule.get("title", rule["id"]))[:120], "why": str(rule.get("why", ""))[:400],
            "match": clean, "threshold": n, "window_min": m, "per_source": bool(rule.get("per_source", True)),
            "action": str(rule.get("action", ""))[:300], "on": bool(rule.get("on", False)),
            **({"tried": {k: int(rule["tried"][k]) for k in ("incidents", "sources", "hours")}}
               if isinstance(rule.get("tried"), dict) else {})}


def load(cfg: sys_config.Config) -> list[dict]:
    try:
        return [check(r) for r in json.loads(_file(cfg).read_text(encoding="utf-8"))]
    except (OSError, ValueError, TypeError):
        return []


def save(cfg: sys_config.Config, rules: list[dict]) -> list[dict]:
    rules = [check(r) for r in rules]
    f = _file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(rules, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)
    return rules


def matches(rule: dict, f: dict) -> bool:
    for k, vals in rule["match"].items():
        v = str(f.get(k, "")).lower()
        if k == "log_id":
            if not any(v.startswith(x) for x in vals):
                return False
        elif v not in vals:
            return False
    return True


class RuleSet:
    """The rules switched on, fed every line; raises (rule, source, count, samples) as they trip."""

    NEW_PER_MIN, MAX_COUNTED = 600, 20000               # the detector's own ceiling for new sources (C566)
    RAISED_PER_MIN, RAISED_PER_HOUR = 20, 60

    def __init__(self, rules: list[dict]):
        self.rules = [r for r in rules if r["on"]]
        self.seen: dict[tuple[str, str], Window] = {}
        self.raised: dict[tuple[str, str], float] = {}
        self.fresh = Budget(self.NEW_PER_MIN)
        self.alarms = Budget(self.RAISED_PER_MIN, self.RAISED_PER_HOUR)
        self._swept: float | None = None

    def prune(self, now: float) -> None:
        self._swept = now
        span = {r["id"]: r["window_min"] * 60 for r in self.rules}
        for key in [k for k, q in self.seen.items() if now - q.last > span.get(k[0], 0)]:
            del self.seen[key]
        for key in [k for k, t in self.raised.items() if now - t >= 3600]:
            del self.raised[key]

    def feed(self, f: dict, src: str | None, now: float | None = None) -> list[tuple[dict, str, int, list[str]]]:
        now = time.time() if now is None else now
        out = []
        if self._swept is None or now - self._swept >= 60 or now < self._swept:
            self.prune(now)
        for r in self.rules:
            if not matches(r, f):
                continue
            who = (src or "-") if r["per_source"] else "*"
            q = self.seen.get((r["id"], who))
            if q is None:                               # a new source: within the minute's budget and the ceiling
                if len(self.seen) >= self.MAX_COUNTED or not self.fresh.take(now):
                    continue
                q = self.seen[(r["id"], who)] = Window()
            q.add(now, f.get("_raw", ""))
            q.trim(now, r["window_min"] * 60)
            last = self.raised.get((r["id"], who))
            if len(q) >= r["threshold"] and (last is None or now - last >= 3600) and self.alarms.take(now):
                self.raised[(r["id"], who)] = now
                out.append((r, who, len(q), list(q.samples)))
        return out
