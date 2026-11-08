# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C406: at 🚀 her routine (a block lifted on time, a scanner blocked at Cloudflare) is in the feed and the digest,
never a push of its own."""
import importlib
import json
import sys
import time

from aurora import sec_autopilot, sys_config


def test_a_quiet_note_is_in_the_feed_and_pushes_nothing(cfg, monkeypatch):
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    core = importlib.import_module("aurora.api.core")
    pushed = []
    monkeypatch.setattr(core, "_push", lambda event, payload: pushed.append(event))
    core.note("security", "defence.release", {"title": "x"}, quiet=True)
    assert pushed == [] and core._activity[-1]["event"] == "defence.release"
    core.note("security", "defence.failed", {"title": "y"})
    assert pushed == ["defence.failed"]


def test_the_digest_counts_the_scanners_blocked_at_cloudflare(cfg):
    now = time.time()
    f = cfg.path("AURORA_STATUS_DIR") / "security" / "cf_blocks.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps([{"ip": "198.51.100.1", "at": now - 60, "auto": True},
                             {"ip": "198.51.100.2", "at": now - 60, "auto": False},          # the owner's own
                             {"ip": "198.51.100.3", "at": now - 3 * 86400, "auto": True}]))   # before the window
    d = sec_autopilot.digest(cfg, [], now)
    assert d is not None and d["edge"] == 1 and "1 scanner bloccati su Cloudflare" in sec_autopilot.said(d)
