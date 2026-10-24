# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📶 The line (aurora-app F2): the notifications kept for the app, delivered after the id it got last."""
import json
import re
import time
from pathlib import Path

from aurora import sys_line
from conftest import private  # noqa: E402 — who may read a file, asked of this system

ROOT = Path(__file__).resolve().parents[1]


def test_events_come_after_the_id_the_phone_got_last(cfg):
    start = sys_line.last(cfg)
    a = sys_line.post({"title": "Aurora", "body": "uno", "view": "chat"}, cfg)
    b = sys_line.post({"title": "Aurora", "body": "due", "view": "chat"}, cfg)
    assert int(b["id"]) > int(a["id"]) > int(start)
    assert [e["body"] for e in sys_line.since(start, cfg)] == ["uno", "due"]
    assert [e["body"] for e in sys_line.since(a["id"], cfg)] == ["due"]
    assert sys_line.since(b["id"], cfg) == [] and sys_line.last(cfg) == b["id"]
    assert private(sys_line._file(cfg))


def test_only_the_last_events_and_not_the_stale_ones(cfg, monkeypatch):
    monkeypatch.setattr(sys_line, "KEEP", 3)
    for n in range(5):
        sys_line.post({"body": str(n)}, cfg)
    assert [e["body"] for e in sys_line.since("0", cfg)] == ["2", "3", "4"]
    f = sys_line._file(cfg)
    rows = [json.loads(x) for x in f.read_text().splitlines()]
    rows[0]["at"] = time.time() - sys_line.TTL - 1                    # older than a push would live
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert [e["body"] for e in sys_line.since("0", cfg)] == ["3", "4"]
    assert sys_line.since("not a number", cfg) == sys_line.since("0", cfg)


def test_the_route_needs_a_login_and_every_chosen_notification_goes_on_the_line():
    src = (ROOT / "aurora" / "api" / "line.py").read_text()
    assert re.findall(r'@router\.\w+\("([^"]+)", dependencies=\[Depends\((\w+)\)\]\)', src) == [("/v1/aurora/line", "auth")]
    assert "'line'" in (ROOT / "aurora" / "api" / "__init__.py").read_text()
    core = (ROOT / "aurora" / "api" / "core.py").read_text()
    push = core.split("def _push(")[1].split("\n\n\n")[0]
    assert "sys_line.post(msg" in push and push.index("sys_line.post") < push.index("sys_push.count(cfg)")
