# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner's list of 2026-10-04: plugins of the admin or of everyone, notifications nobody got, the trash,
routines with several times and groups of days, Aurora's code run in a cage of its own."""
import json
import shutil
import subprocess
import time
from datetime import date, datetime
from pathlib import Path

import pytest

from aurora import plg_access, prj_run, sys_log, sys_push, sys_routines as R, sys_trash, sys_uploads
from aurora.plg_host import PluginHost

from conftest import write_env


def _plugins(cfg, *names):
    for n in names:
        d = cfg.path("AURORA_PLUGINS_DIR") / n
        d.mkdir(parents=True)
        (d / "plugin.json").write_text(json.dumps({"name": n, "command": ["true"]}))


# ---- plugins: the admin's or everyone's ----------------------------------------------------------------------------
def test_the_machine_s_plugins_are_off_for_a_user_and_the_admin_shares_them(cfg):
    _plugins(cfg, "backup", "notes", "forged-thing")
    seen = {p.name: p.enabled for p in plg_access.UserPluginHost(cfg).plugins(with_tools=False)}
    assert seen == {"backup": False, "notes": True, "forged-thing": False}      # a new plugin: the admin's
    assert all(p.enabled for p in PluginHost(cfg).plugins(with_tools=False))   # the admin's host: unchanged
    plg_access.set_for_users(cfg, "forged-thing", True)
    plg_access.set_for_users(cfg, "notes", False)
    seen = {p.name: p.enabled for p in plg_access.UserPluginHost(cfg).plugins(with_tools=False)}
    assert seen == {"backup": False, "notes": False, "forged-thing": True}
    out = plg_access.UserPluginHost(cfg).call("backup", "status", {})
    assert out["ok"] is False and "not available" in out["text"]                # never called for the user


# ---- notifications ---------------------------------------------------------------------------------------------
def test_the_cloud_ceiling_and_a_stopped_plugin_can_be_notified(cfg):
    for ev in ("cloud.budget", "cloud.fallback", "plugin.refused"):
        assert ev in sys_push.TEXTS and sys_push.TEXTS[ev][0] in sys_push.KINDS
    assert "cloud" in sys_push.PRESETS["suggested"] and "cloud" in sys_push.MACHINE
    heard = []
    sys_log.on_trace(lambda c, e, p: heard.append(e))
    try:
        sys_log.trace("llm_client", "cloud.budget", {"provider": "xai", "spent": 600001, "cap": 600000})
    finally:
        sys_log._listeners.pop()
    assert heard == ["cloud.budget"]


def test_a_listener_that_fails_never_breaks_the_traced_work(cfg):
    sys_log.on_trace(lambda c, e, p: 1 / 0)
    try:
        assert sys_log.trace("t", "x", {}) > 0
    finally:
        sys_log._listeners.pop()


# ---- trash -------------------------------------------------------------------------------------------------------
def test_a_deleted_upload_goes_to_the_trash_and_comes_back(cfg):
    item = sys_uploads.save(cfg, "r1", "nota.txt", "text/plain", b"ciao")
    assert sys_uploads.delete(cfg, item["id"])
    assert sys_uploads.get(cfg, item["id"]) is None
    [t] = sys_trash.items(cfg)
    assert t["name"] == "nota.txt" and t["kind"] == "upload" and t["bytes"] == 4
    path, meta = sys_trash.restore(cfg, t["id"])
    sys_uploads.reindex(cfg, meta["record"], path)
    back = sys_uploads.get(cfg, item["id"])
    assert back and back[0].read_bytes() == b"ciao" and sys_trash.items(cfg) == []


def test_the_trash_expires_and_can_be_switched_off(cfg, tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF")
    tid = sys_trash.discard(cfg, f, "document")
    assert not f.exists() and sys_trash.expire(cfg, now=time.time() + 29 * 86400) == 0
    assert sys_trash.expire(cfg, now=time.time() + 31 * 86400) == 1 and sys_trash.items(cfg) == []
    assert sys_trash.remove(cfg, tid) is False
    off = type(cfg).__new__(type(cfg))
    off.__dict__.update(cfg.__dict__)
    off.values = {**cfg.values, "AURORA_TRASH_ENABLED": False}
    g = tmp_path / "b.pdf"
    g.write_bytes(b"%PDF")
    assert sys_trash.discard(off, g, "document") is None and not g.exists()
    assert sys_trash._item(cfg, "../x") is None


# ---- routines --------------------------------------------------------------------------------------------------
def test_italian_holidays_and_easter():
    assert [R.easter(y) for y in (2025, 2026, 2027)] == [date(2025, 4, 20), date(2026, 4, 5), date(2027, 3, 28)]
    assert R.holiday_it(date(2026, 4, 6)) and R.holiday_it(date(2026, 6, 2)) and not R.holiday_it(date(2026, 6, 3))


def test_several_times_on_working_days():
    s = {"every": "custom", "times": ["08:00", "18:30"], "group": "workdays"}
    R.validate({"kind": "agent", "goal": "x", "schedule": s})
    at = lambda x: R._slot(datetime.fromisoformat(x), s)  # noqa: E731
    assert at("2026-10-05 07:00") == datetime(2026, 10, 2, 18, 30)       # Monday early: Friday evening's
    assert at("2026-10-05 09:00") == datetime(2026, 10, 5, 8, 0)
    assert at("2026-10-05 19:00") == datetime(2026, 10, 5, 18, 30)
    assert at("2026-12-08 12:00") == datetime(2026, 12, 7, 18, 30)       # a holiday is skipped
    r = {"enabled": True, "schedule": s, "created": datetime(2026, 10, 1).timestamp(),
         "last_run": datetime(2026, 10, 5, 8, 1).timestamp()}
    assert not R.is_due(r, datetime(2026, 10, 5, 12, 0)) and R.is_due(r, datetime(2026, 10, 5, 18, 31))


def test_chosen_days_and_bad_schedules():
    s = {"every": "custom", "times": ["07:15"], "days": [1, 3]}           # Tuesday and Thursday
    assert R._slot(datetime(2026, 10, 5, 9, 0), s) == datetime(2026, 10, 1, 7, 15)
    for bad in ({"every": "custom", "times": [], "group": "all"}, {"every": "custom", "times": ["25:00"], "group": "all"},
                {"every": "custom", "times": ["08:00"], "group": "sometimes"}, {"every": "custom", "times": ["08:00"]},
                {"every": "custom", "times": ["08:00"], "days": [7]}, {"every": "custom", "times": ["08:00"] * 13, "group": "all"}):
        with pytest.raises(ValueError):
            R.validate({"kind": "agent", "goal": "x", "schedule": bad})


# ---- Aurora's code in its own cage ------------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("bwrap"), reason="bubblewrap not installed")
def test_a_project_runs_its_tests_with_no_network_and_no_secrets(cfg):
    if subprocess.run(["bwrap", "--ro-bind", "/", "/", "--", "true"], capture_output=True).returncode != 0:
        pytest.skip("no user namespaces here")
    p = cfg.path("AURORA_PROJECTS_DIR") / "demo"
    p.mkdir(parents=True)
    (p / "test_a.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    r = prj_run.run(cfg, "demo", "python -m pytest -q -p no:cacheprovider")
    assert r["exit"] == 0 and "1 passed" in r["output"]
    r = prj_run.run(cfg, "demo", "python -c \"import socket; socket.create_connection(('1.1.1.1', 443), 3)\"")
    assert r["exit"] != 0                                               # no network
    r = prj_run.run(cfg, "demo", f"cat {cfg.env_file}; env")
    assert "test-secret-" not in r["output"] and "AURORA_" not in r["output"]
    r = prj_run.run(cfg, "demo", "echo x > made.txt && echo y > /etc/aurora-test")
    assert (p / "made.txt").exists() and r["exit"] != 0
    for bad in ("../x", "Demo", ""):
        with pytest.raises(ValueError):
            prj_run.run(cfg, bad, "true")
