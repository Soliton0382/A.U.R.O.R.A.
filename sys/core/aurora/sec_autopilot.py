# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🤖 Security at 🚀 decides, and the owner stops judging (owner, 3 Nov: «voglio mettere il pilota automatico ad aurora
così fa lei e io basta»). Replayed on a week of the owner's own verdicts (M274): 52 attacks from the Internet blocked by
hand, all judged right; 140 alerts of the house's known devices, none right — and the 🚀 as it stood left both to the
owner, each with a notification.

At 🚀 only, on top of the automatic block (sec_defence):
- an attack she blocks is closed, with no notification and no inquiry; a block that fails is still told;
- a quiet pattern's alert is closed;
- a known device's alert, of a kind the owner judged at least MIN_JUDGED times with at most RIGHT of them right on the
  house's known devices (WINDOW_DAYS), is closed: her own judgement, from theirs.
Always loud, whatever the history: an unknown device (the kind alone never blinds the house, C407), a device with an
address not its own, a new device, a high or critical alert, what sec_quiet never quiets (a decoy, a listed address).
What she closes keeps no verdict of hers: «settled» says why, the scorecard and the patterns count the owner's verdicts
only; a 👍 on one counts against the kind at once. One line a day says what she did (digest), then those incidents leave
the Security page; they stay in the file for the reports."""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path

from . import sec_quiet, sys_config

MIN_JUDGED = 10             # the owner's verdicts on a kind before she judges it: a week gave 28-45 per kind (M274)
RIGHT = sec_quiet.PROPOSE_RIGHT
LOUD_KINDS = {"behaviour:new_device"}
LOUD_SEVERITY = {"high", "critical"}


def on(cfg: sys_config.Config) -> bool:
    from . import sys_autonomy
    return sys_autonomy.levels(cfg).get("security") == 2


def _kinds(items: list[dict], now: float | None = None) -> dict[str, Counter]:
    """The owner's verdicts per kind on the house's known devices, over the verdicts' window."""
    since = (time.time() if now is None else now) - sec_quiet.WINDOW_DAYS * 86400
    out: dict[str, Counter] = {}
    for i in items:
        if i.get("verdict") and i.get("internal") and i.get("known") \
                and float(i.get("verdict_at") or i.get("received_ts") or 0) >= since:
            out.setdefault(str(i.get("kind")), Counter())[i["verdict"]] += 1
    return out


def judged_false(item: dict, items: list[dict]) -> str | None:
    """Why this alert needs nobody, from the owner's verdicts; None when it stays with them."""
    kind, known = str(item.get("kind")), str(item.get("known") or "")
    if not item.get("internal") or not known or "(" in known:    # «name (di solito …)»: not at its own address
        return None
    if kind in LOUD_KINDS or item.get("severity") in LOUD_SEVERITY or sec_quiet.what(item) is None:
        return None
    c = _kinds(items).get(kind, Counter())
    n = sum(c.values())
    return f"{kind}: {n - c['right']} of {n} judged not right" if n >= MIN_JUDGED and c["right"] <= RIGHT * n else None


def settle(item_id: str, cfg: sys_config.Config, why: str) -> dict:
    from .sec_incidents import Incidents
    return Incidents(cfg).update(item_id, status="closed", closed=time.strftime("%Y-%m-%dT%H:%M:%S%z"), settled=why,
                                 settled_at=time.time())


def _file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "autopilot.json"


def digest(cfg: sys_config.Config, items: list[dict], now: float | None = None) -> dict | None:
    """What she decided since the last digest, by reason: {"blocked", "quiet", "judged", "left"}, or None with nothing
    to say. `left`: the alerts of those days that stayed with the owner."""
    now = time.time() if now is None else now
    try:
        since = float(json.loads(_file(cfg).read_text(encoding="utf-8"))["at"])
    except (OSError, ValueError, KeyError, TypeError):
        since = now - 86400
    mine = [i for i in items if float(i.get("settled_at") or 0) > since]
    out = {"blocked": sum(i["settled"] == "blocked" for i in mine), "quiet": sum(i["settled"] == "quiet" for i in mine)}
    out["judged"] = len(mine) - out["blocked"] - out["quiet"]
    out["left"] = sum(not i.get("settled") and i.get("status") == "open" and float(i.get("received_ts") or 0) > since
                      for i in items)
    out["ids"] = [i["id"] for i in mine]
    try:                                               # 🌐 the scanners blocked at Cloudflare, no push of their own (C406)
        from . import net_cfwaf
        out["edge"] = sum(bool(b.get("auto")) and float(b.get("at") or 0) > since for b in net_cfwaf._load(cfg))
    except Exception:                                  # noqa: BLE001 — no Cloudflare here: nothing to count
        out["edge"] = 0
    f = _file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"at": now}), encoding="utf-8")
    os.replace(tmp, f)
    return out if mine or out["left"] or out["edge"] else None


def said(d: dict) -> str:
    edge = f"☁️ {d['edge']} scanner bloccati su Cloudflare · " if d.get("edge") else ""
    return (f"🛡️ {d['blocked']} attacchi bloccati · {edge}🔇 {d['quiet'] + d['judged']} allarmi di casa chiusi · "
            f"👀 {d['left']} lasciati a te")
