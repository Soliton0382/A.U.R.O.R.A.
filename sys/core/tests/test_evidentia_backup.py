# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Evidentia's own backup (27 Nov): Aurora's method with its own key and folder — a run, a second run that writes
nothing new, a verify, a restore into an empty folder (never over the live archive), SQLite copied consistently;
the installer makes the key once (its recovery code shown once), the unit and the timer half an hour after Aurora's."""
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sys" / "core" / "script"))
import sys_root_evidentia as E  # noqa: E402


def _backup(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("evd_backup", ROOT / "sys" / "evidentia" / "script" / "evd_backup.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    data, dest = tmp_path / "data", tmp_path / "nas"
    (data / "vectors").mkdir(parents=True)
    dest.mkdir()
    (data / "docids.json").write_text('{"collections": []}')
    (data / "vectors" / "a.bin").write_bytes(os.urandom(5000))
    con = sqlite3.connect(data / "cases.db")
    con.execute("CREATE TABLE c (x)")
    con.execute("INSERT INTO c VALUES ('fascicolo 1')")
    con.commit()
    con.close()
    key = tmp_path / "k"
    key.write_bytes(os.urandom(32))
    env = tmp_path / "evidentia.env"
    env.write_text(f"EVD_DATA_DIR={data}\nEVD_BACKUP_DIR={dest / 'evidentia'}\nEVD_BACKUP_KEY_FILE={key}\n")
    monkeypatch.setattr(m, "ENV", env)
    monkeypatch.setattr(m, "STATE", tmp_path / "state")
    monkeypatch.setattr(m, "STATUS", tmp_path / "status" / "backup.json")
    return m, data, dest


def test_a_run_a_second_run_verify_and_restore(tmp_path, monkeypatch):
    m, data, dest = _backup(tmp_path, monkeypatch)
    a = m.run()
    assert a["ok"] and a["files"] == 3 and a["new_blobs"] == 3
    b = m.run()
    assert b["new_blobs"] in (0, 1)                        # unchanged files not written again (SQLite re-copied)
    assert m.verify(None) >= 3
    status = json.loads((tmp_path / "status" / "backup.json").read_text())
    assert status["ok"] and "docids" not in json.dumps(status)      # the status says how many, never a file's name
    out = m.restore(tmp_path / "back")
    assert out["files"] == 3 and (tmp_path / "back" / "vectors" / "a.bin").read_bytes() == (data / "vectors" / "a.bin").read_bytes()
    assert sqlite3.connect(tmp_path / "back" / "cases.db").execute("SELECT x FROM c").fetchone() == ("fascicolo 1",)
    with pytest.raises(SystemExit):
        m.restore(tmp_path / "back")                       # not empty
    with pytest.raises(SystemExit):
        m.restore(data)                                    # never over the live archive


def test_the_backup_is_unreadable_without_its_key(tmp_path, monkeypatch):
    m, data, dest = _backup(tmp_path, monkeypatch)
    m.run()
    raw = b"".join(p.read_bytes() for p in (dest / "evidentia" / "blobs").rglob("*") if p.is_file())
    assert b"fascicolo 1" not in raw and b"collections" not in raw


def test_the_installer_makes_the_key_once_and_the_timer_after_aurora_s(tmp_path):
    cfg = {"AURORA_BACKUP_DIR": "/mnt/disk/backup", "AURORA_BACKUP_TIME": "23:45", "AURORA_BACKUP_KEEP_DAILY": 7,
           "AURORA_BACKUP_KEEP_WEEKLY": 4, "AURORA_BACKUP_KEEP_MONTHLY": 6}
    b = E.backup_settings(cfg)
    assert b["EVD_BACKUP_DIR"] == "/mnt/disk/backup/evidentia" and b["time"] == "00:15"
    code = E.backup_key(tmp_path)
    assert code and len(code.replace("-", "")) >= 52 and oct((tmp_path / E.BACKUP_KEY).stat().st_mode & 0o777) == "0o600"
    assert E.backup_key(tmp_path) is None                  # made once: the code is never shown again
    unit = E.backup_unit_text(Path("/v"), {}, b)
    assert "/sys/evidentia/script/evd_backup.py\" run" in unit and "ProtectSystem=strict" in unit and "PrivateNetwork=yes" in unit
    assert "Persistent=true" in E.backup_timer_text("00:15") and "OnCalendar=*-*-* 00:15:00" in E.backup_timer_text("00:15")
    assert E.backup_settings({"AURORA_BACKUP_DIR": ""}) == {}



def test_every_key_the_installer_writes_is_in_evidentia_s_schema():
    """C752: the backup's keys written into /etc/aurora/evidentia.env without the schema knowing them stopped the
    service (471 restarts) — Evidentia refuses a key it does not describe."""
    import json
    keys = {s["key"] for s in json.loads((ROOT / "sys" / "evidentia" / "config" / "settings_schema.json").read_text())["settings"]}
    b = E.backup_settings({"AURORA_BACKUP_DIR": "/mnt/d", "AURORA_BACKUP_TIME": "23:00", "AURORA_BACKUP_KEEP_DAILY": 7,
                           "AURORA_BACKUP_KEEP_WEEKLY": 4, "AURORA_BACKUP_KEEP_MONTHLY": 6})
    text = E.env_text({k: Path("/x") for k in E.KEYS}, b)
    written = {line.split("=", 1)[0] for line in text.splitlines() if "=" in line}
    assert written <= keys, written - keys


def test_apply_puts_a_snapshot_in_place_and_today_s_aside(tmp_path, monkeypatch):
    m, data, dest = _backup(tmp_path, monkeypatch)
    m.run()
    status = json.loads((tmp_path / "status" / "backup.json").read_text())
    assert len(status["snapshots"]) == 1                    # the copies' names for Aurora's page, nothing else
    (data / "docids.json").write_text("today")
    (data / "new.txt").write_text("made after the backup")
    calls = []
    monkeypatch.setattr(os, "chown", lambda *a, **k: None)
    out = m.apply("latest", run=lambda cmd, **k: calls.append(cmd[1]))
    assert calls == ["stop", "start"]
    assert (data / "docids.json").read_text() == '{"collections": []}' and not (data / "new.txt").exists()
    aside = Path(out["aside"])
    assert (aside / "new.txt").read_text() == "made after the backup"   # today's kept, never deleted
    with pytest.raises(SystemExit):
        m.apply("../../etc")


def test_every_user_s_archive_is_backed_up_and_one_comes_back_alone(tmp_path, monkeypatch):
    """R15: the other users' archives go into the same snapshot (_users/<user>/), the owner's stays as before; a
    restore of one user only brings that one back, an apply only swaps that one."""
    m, data, dest = _backup(tmp_path, monkeypatch)
    arch = tmp_path / "archives"
    (arch / "ann" / "data").mkdir(parents=True)
    (arch / "ann" / "data" / "cases.db").write_bytes(b"ann's case files")
    env = m.ENV.read_text() + f"EVD_ARCHIVE_DIR={arch}\n"
    m.ENV.write_text(env)
    out = m.run()
    assert out["files"] == 4
    only = m.restore(tmp_path / "back-ann", users={"ann"})
    assert only["files"] == 1 and (tmp_path / "back-ann" / "_users" / "ann" / "cases.db").read_bytes() == b"ann's case files"
    owner = m.restore(tmp_path / "back-owner", users={""})
    assert owner["files"] == 3 and not (tmp_path / "back-owner" / "_users").exists()
    (arch / "ann" / "data" / "cases.db").write_bytes(b"changed today")
    (data / "docids.json").write_text("today")
    monkeypatch.setattr(os, "chown", lambda *a, **k: None)
    m.apply("latest", run=lambda cmd, **k: None, users={"ann"})
    assert (arch / "ann" / "data" / "cases.db").read_bytes() == b"ann's case files"
    assert (data / "docids.json").read_text() == "today"                         # the owner's: untouched
    assert any(p.name.startswith("data.before-restore-") for p in (arch / "ann").iterdir())   # hers kept aside
