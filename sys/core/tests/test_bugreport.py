# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import json
import zipfile
from datetime import datetime, timedelta

import pytest

from aurora import sys_bugreport as R


def stamp(hours_ago: float) -> str:
    return (datetime.now().astimezone() - timedelta(hours=hours_ago)).isoformat(timespec="milliseconds")


def test_a_report_carries_the_logs_needed_and_nothing_private(cfg):
    cfg.values.update(AURORA_OWNER_NAME="Mario Rossi", AURORA_DOMAIN="aurora.example.net",
                      AURORA_UPDATE_REMOTE="git@github.com:someone/A.U.R.O.R.A..git")
    key = cfg.values["AURORA_API_KEY"]
    logs = cfg.path("AURORA_LOG_DIR")
    (logs / "api").mkdir(parents=True)
    (logs / "api" / "api.log").write_text(
        f"{stamp(30)} INFO aurora.api old line outside the window\n"
        f"{stamp(1)} ERROR aurora.api upstream 192.168.0.205 refused for Mario Rossi, key {key}\n"
        "Traceback (most recent call last):\n  File \"x.py\", line 1\n"
        f"{stamp(0.5)} WARNING aurora.api aurora.example.net slow\n")
    (logs / "firewall").mkdir()
    (logs / "firewall" / "firewall.log").write_text(
        f'{stamp(2)} INFO aurora.firewall device_name="xg.example.net" device_serial_id="X99000AB1CDEF23"\n')
    (logs / "plugins").mkdir()
    (logs / "plugins" / "web.stderr.log").write_text("Traceback: ConnectError to 10.1.2.3\n")
    (logs / "trace").mkdir()
    (logs / "trace" / "api.jsonl").write_text(json.dumps({"ts": stamp(1), "run_id": "abc123def456", "event": "route",
                                                          "payload": {"q": "Mario Rossi chiede"}}) + "\n")
    out = R.build(cfg, "La chat si blocca quando Mario Rossi allega un video", "1. allego\n2. aspetto", "una risposta",
                  ["abc123def456"], hours=6, health={"level": "warn", "problems": ["api: slow"]}, features={"x": 1})
    z = zipfile.ZipFile(cfg.path("AURORA_BUGREPORT_DIR") / out["name"])
    names = set(z.namelist())
    assert {"report.md", "environment.json", "settings.txt", "health.json", "logs/api.log", "logs/problems.log",
            "logs/plugins/web.stderr.log", "runs/abc123def456.jsonl"} <= names
    everything = "\n".join(z.read(n).decode() for n in names)
    for leak in (key, "Mario", "192.168.0.205", "10.1.2.3", "example.net", "X99000AB1CDEF23"):
        assert leak not in everything, leak
    api = z.read("logs/api.log").decode()
    assert "old line outside the window" not in api and "Traceback" in api       # the window, with its tracebacks
    assert "[IP_1]" in api and "[PRIVATE_" in api
    settings = z.read("settings.txt").decode()
    assert "AURORA_API_KEY=(set)" in settings
    assert out["masked"]["IP"] >= 2 and "Mario" not in out["issue_url"]
    assert out["issue_url"].startswith("https://github.com/someone/A.U.R.O.R.A./issues/new?title=")
    assert (cfg.path("AURORA_BUGREPORT_DIR") / out["name"]).stat().st_mode & 0o777 == 0o600
    assert R.listing(cfg)[0]["name"] == out["name"]


def test_an_empty_description_is_refused_and_odd_run_ids_are_ignored(cfg):
    with pytest.raises(ValueError):
        R.build(cfg, "  rotto ")
    out = R.build(cfg, "Descrizione abbastanza lunga del problema", run_ids=["../../etc/passwd"])
    assert not any(n.startswith("runs/") for n in out["files"])
    cfg.values["AURORA_UPDATE_REMOTE"] = "https://example.org/repo.git"
    assert R.issue_url(cfg, "t", "b") == ""                                     # not GitHub: no link


def test_a_private_name_in_the_description_is_masked_everywhere(cfg):
    from types import SimpleNamespace

    class Reader:                                      # the local model reads the names of the description
        def complete(self, *a, **k):
            return SimpleNamespace(answer='[{"name": "Giulia", "type": "private"}]')
    logs = cfg.path("AURORA_LOG_DIR")
    (logs / "api").mkdir(parents=True)
    (logs / "api" / "api.log").write_text(f"{stamp(1)} ERROR aurora.api upload of Giulia failed\n")
    out = R.build(cfg, "Il caricamento di Giulia si blocca", hours=6, llm=Reader())
    z = zipfile.ZipFile(cfg.path("AURORA_BUGREPORT_DIR") / out["name"])
    assert not any("Giulia" in z.read(n).decode() for n in z.namelist()) and "Giulia" not in out["issue_url"]
