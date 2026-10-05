# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What left this machine (owner, 2026-10-05, from what people ask of an AI: "57% would use assistants more with
strong data protection"): one view of every way out, measured from the traces and stores the code writes — never
estimated.

- cloud models: calls per provider and model, per step, the private items masked before sending (by kind), the
  pictures sent (they cannot be masked) — mdl_router.stats;
- posts published on social pages, by the owner's click or by Aurora alone (approvals);
- push notifications sent to the devices' push services (title and short text only) — sys_push's ledger;
- firewall actions: addresses blocked and lifted (trace "security").
"""
from __future__ import annotations

import json
import time
from collections import Counter

from . import sys_config


def _security(cfg: sys_config.Config, since: float) -> Counter:
    out: Counter = Counter()
    f = cfg.path("AURORA_LOG_DIR") / "trace" / "security.jsonl"
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines() if f.exists() else []:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        try:
            t = time.mktime(time.strptime(e["ts"][:19], "%Y-%m-%dT%H:%M:%S"))
        except (KeyError, ValueError):
            continue
        if t >= since and e.get("event") in ("firewall.blocked", "firewall.unblocked", "defence.block", "defence.release"):
            out[e["event"]] += 1
    return out


def summary(cfg: sys_config.Config, approvals: list[dict], social_tools: set[str], days: float = 1) -> dict:
    from . import mdl_router, sys_autonomy, sys_push
    since = time.time() - days * 86400
    cloud = mdl_router.stats(cfg, days)
    posts = []
    for a in approvals:
        try:
            t = time.mktime(time.strptime(str(a.get("created", ""))[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            continue
        if t >= since and a.get("status") in ("executed", "auto") \
                and sys_autonomy.area_of(a, social_tools) == "social":
            posts.append({"at": t, "title": a.get("title"), "by": "aurora" if a["status"] == "auto" else "owner"})
    push = sys_push.delivery(cfg, days)
    return {"days": days,
            "cloud": {"calls": sum(c["calls"] for c in cloud["calls"].values()),
                      "models": {k: v["calls"] for k, v in cloud["calls"].items()},
                      "by_step": cloud["masked_calls_by_role"], "masked": cloud["masked"],
                      "pictures": cloud["pictures_sent"]},
            "posts": sorted(posts, key=lambda p: -p["at"]),
            "push": {"sent": push["pushes"], "devices": push["accepted"]},
            "firewall": dict(_security(cfg, since))}
