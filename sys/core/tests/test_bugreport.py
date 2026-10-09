# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import json
import zipfile
from datetime import datetime, timedelta

import pytest

from aurora import sys_bugreport as R
from conftest import private  # noqa: E402 — who may read a file, asked of this system


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
        f"{stamp(1)} ERROR aurora.api upstream 172.16.5.205 refused for Mario Rossi, key {key}\n"
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
    for leak in (key, "Mario", "172.16.5.205", "10.1.2.3", "example.net", "X99000AB1CDEF23"):
        assert leak not in everything, leak
    api = z.read("logs/api.log").decode()
    assert "old line outside the window" not in api and "Traceback" in api       # the window, with its tracebacks
    assert "[IP_1]" in api and "[PRIVATE_" in api
    settings = z.read("settings.txt").decode()
    assert "AURORA_API_KEY=(set)" in settings
    assert out["masked"]["IP"] >= 2 and "Mario" not in out["issue_url"]
    assert out["leaks"] == [], out["leaks"]
    assert out["issue_url"].startswith("https://github.com/someone/A.U.R.O.R.A./issues/new?title=")
    assert private(cfg.path("AURORA_BUGREPORT_DIR") / out["name"])
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


def test_a_public_report_carries_no_computer_name_account_or_profile_and_is_checked_before_it_leaves(cfg, monkeypatch):
    """C222 (owner, 9 Oct: «che non sia inviato mezzo dato personale sulla issue e il log raccolto»)."""
    import socket
    from pathlib import Path
    from urllib.parse import unquote
    from aurora.sec_mask import Pseudonymizer
    monkeypatch.setattr(socket, "gethostname", lambda: "studio-rossi")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: Path("/home/mrossi")))
    cfg.values.update(AURORA_OWNER_NAME="Mario Rossi", AURORA_DOMAIN_ALIASES="studio-rossi.local,localhost",
                      AURORA_UPDATE_REMOTE="git@github.com:someone/A.U.R.O.R.A..git")
    logs = cfg.path("AURORA_LOG_DIR")
    (logs / "api").mkdir(parents=True)
    lines = [f"{stamp(1)} ERROR aurora.api è fallito: STUDIO-ROSSI.local, usr/mrossi/notes, C:\\Users\\mrossi\\x, "
             f"mario rossi n.{i}" for i in range(400)]
    (logs / "api" / "api.log").write_text("\n".join(lines) + "\n")
    out = R.build(cfg, "La pagina note di mario rossi non si apre", health={"level": "warn", "problems": []})
    z = zipfile.ZipFile(cfg.path("AURORA_BUGREPORT_DIR") / out["name"])
    everything = ("\n".join(z.read(n).decode() for n in z.namelist()) + unquote(out["issue_url"])).lower()
    for leak in ("studio-rossi", "mrossi", "mario", "rossi"):
        assert leak not in everything, leak
    assert out["leaks"] == [] and "Latest errors" in out["issue_text"]
    assert len(out["issue_url"]) <= R.URL_MAX and "[Bug]" in unquote(out["issue_url"])
    # the final check finds what a masker missed
    mask = Pseudonymizer(cfg)
    mask.private = ["studio-rossi"]
    assert R.leaks("errore su studio-rossi, mail mario@example.com", mask) == ["EMAIL", "PRIVATE"]


def test_an_idea_goes_to_github_masked_with_its_own_label(cfg):
    from urllib.parse import unquote
    from aurora import sys_ideas
    cfg.values.update(AURORA_OWNER_NAME="Mario Rossi", AURORA_UPDATE_REMOTE="git@github.com:someone/A.U.R.O.R.A..git")
    it = sys_ideas.add(cfg, {"title": "Calendario condiviso con Mario Rossi", "text": "scrivimi a mario@example.com",
                             "areas": ["phone"]})
    out = R.idea_issue(cfg, it)
    url = unquote(out["issue_url"])
    assert out["leaks"] == [] and "[Idea]" in url and "labels=enhancement" in url
    assert "Mario" not in url and "mario@example.com" not in url and "[EMAIL_" in url
