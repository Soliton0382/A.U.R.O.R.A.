# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A full backup, a selective restore (sys_backup_parts): a part goes back whole, the rest is not touched."""
import importlib.util
from pathlib import Path

import pytest

from aurora import sys_backup as B
from aurora import sys_backup_parts as P


def test_each_path_has_its_part(cfg):
    cases = {".env": "config", "usr/ann/.env": "config", "sys/https/cert/a.pem": "config", "sys/app/keys/k": "config",
             "sys/core/ethics/exemption.sig": "config", "usr/ann/documents/a.pdf": "files", "usr/ann/projects/p/x.py": "files",
             "external/mnt/a": "files"}
    status = str(cfg.path("AURORA_STATUS_DIR").relative_to(cfg.root))
    vault, index = (str(cfg.path(k).relative_to(cfg.root)) for k in ("AURORA_VAULT_DIR", "AURORA_INDEX_DIR"))
    plugins = str(cfg.path("AURORA_PLUGINS_DIR").relative_to(cfg.root))
    cases.update({f"{status}/models/roles.json": "config", f"{status}/users/ann/routines.json": "config", f"{status}/keys/x": "config",
                  f"{status}/something_new.json": "config", f"{status}/users/ann/shadow.db": "memory", f"{status}/lessons.jsonl": "memory",
                  f"{status}/people.sealed": "memory", f"{status}/incidents.json": "history", f"{status}/usage/d.json": "history",
                  f"{vault}/memory/users/ann/conversation/0001.db": "memory", f"{vault}/memory/users/ann/registry.db": "memory",
                  f"{index}/memory/users/ann/conversation/vectors.f16": "memory", f"{vault}/knowledge/law/0001.db": "vault",
                  f"{index}/knowledge/lexical.db": "vault", f"{plugins}/mine/plugin.py": "plugins"})
    assert {r: P.part_of(cfg, r) for r in cases} == cases


def test_an_unknown_part_stops_before_anything():
    assert P.chosen("memory, config") == ("config", "memory")
    with pytest.raises(ValueError):
        P.chosen("config,nonsense")
    with pytest.raises(ValueError):
        P.chosen("")


@pytest.fixture
def installed(cfg, tmp_path_factory, monkeypatch):
    dest = tmp_path_factory.mktemp("other-disk")
    cfg.values.update(AURORA_BACKUP_DIR=str(dest), AURORA_BACKUP_KEY_FILE=str(tmp_path_factory.mktemp("key") / "k"),
                      AURORA_BACKUP_KEEP_DAILY=7, AURORA_BACKUP_KEEP_WEEKLY=4, AURORA_BACKUP_KEEP_MONTHLY=6)
    st, vault = cfg.path("AURORA_STATUS_DIR"), cfg.path("AURORA_VAULT_DIR")
    for f, text in ((st / "routines.json", "backup"), (st / "incidents.json", "backup"), (vault / "memory" / "conversation" / "0001.db", "backup"),
                    (vault / "knowledge" / "law" / "0001.db", "backup"), (cfg.root / ".env", "AURORA_X=backup\n")):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    B.init_key(cfg)
    return cfg


def _restore_script():
    spec = importlib.util.spec_from_file_location("sys_restore", Path(__file__).resolve().parents[1] / "script" / "sys_restore.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_only_the_chosen_parts_go_back_and_today_s_stay_aside(installed, monkeypatch, tmp_path_factory):
    cfg, tmp_path = installed, tmp_path_factory.mktemp("next-to-it")
    B.run(cfg)
    st, vault = cfg.path("AURORA_STATUS_DIR"), cfg.path("AURORA_VAULT_DIR")
    new_shard = vault / "memory" / "conversation" / "0002.db"                # today's, not in the backup
    new_shard.write_text("today")
    (vault / "memory" / "conversation" / "0001.db").write_text("today")
    (vault / "memory" / "conversation" / "0001.db-wal").write_text("today's journal")
    (vault / "knowledge" / "law" / "0001.db").write_text("today")
    (st / "routines.json").write_text("today")
    R = _restore_script()
    monkeypatch.setattr(R.subprocess, "run", lambda *a, **k: type("X", (), {"returncode": 0, "stdout": "inactive"})())
    p = {"snapshot": "latest", "compat": {"verdict": "same", "why": ""}, "stage": str(tmp_path / "stage"), "aside": str(tmp_path / "aside")}
    R.apply_parts(cfg, p, ("memory",))
    assert (vault / "memory" / "conversation" / "0001.db").read_text() == "backup"
    assert not new_shard.exists() and not (vault / "memory" / "conversation" / "0001.db-wal").exists()
    assert (vault / "knowledge" / "law" / "0001.db").read_text() == "today"  # another part: not touched
    assert (st / "routines.json").read_text() == "today"
    aside = (tmp_path / "aside" / new_shard.relative_to(cfg.root))
    assert aside.read_text() == "today" and aside.with_name("0001.db-wal").read_text() == "today's journal"


def test_the_configuration_alone_on_a_new_installation(installed, monkeypatch, tmp_path_factory):
    cfg, tmp_path = installed, tmp_path_factory.mktemp("next-to-it")
    B.run(cfg)
    st = cfg.path("AURORA_STATUS_DIR")
    (st / "routines.json").write_text("new install")
    (cfg.path("AURORA_VAULT_DIR") / "knowledge" / "law" / "0001.db").write_text("new install")
    R = _restore_script()
    monkeypatch.setattr(R.subprocess, "run", lambda *a, **k: type("X", (), {"returncode": 0, "stdout": "inactive"})())
    R.apply_parts(cfg, {"snapshot": "latest", "compat": {"verdict": "same", "why": ""}, "stage": str(tmp_path / "s"), "aside": str(tmp_path / "a")}, ("config",))
    assert (st / "routines.json").read_text() == "backup" and (cfg.root / ".env").read_text() == "AURORA_X=backup\n"
    assert (cfg.path("AURORA_VAULT_DIR") / "knowledge" / "law" / "0001.db").read_text() == "new install"
    assert (st / "incidents.json").read_text() == "backup"                  # history: not in the choice, nothing changed


def test_a_failure_half_way_puts_all_back_and_aurora_starts_again(installed, monkeypatch, tmp_path_factory):
    cfg, tmp_path = installed, tmp_path_factory.mktemp("next-to-it")
    B.run(cfg)
    st = cfg.path("AURORA_STATUS_DIR")
    (st / "routines.json").write_text("today")
    (cfg.root / ".env").write_text("AURORA_X=today\n")
    R = _restore_script()
    asked = []
    monkeypatch.setattr(R.subprocess, "run", lambda cmd, **k: asked.append(cmd) or type("X", (), {"returncode": 0, "stdout": "inactive"})())
    real, moved = R.shutil.move, []

    def fails(src, dst):
        if str(dst) == str(st / "routines.json") and not moved:              # the backup's copy going in place
            moved.append(1)
            raise PermissionError("no")
        return real(src, dst)
    monkeypatch.setattr(R.shutil, "move", fails)
    with pytest.raises(SystemExit):
        R.apply_parts(cfg, {"snapshot": "latest", "compat": {"verdict": "same", "why": ""}, "stage": str(tmp_path / "s"), "aside": str(tmp_path / "a")}, ("config",))
    assert (st / "routines.json").read_text() == "today" and (cfg.root / ".env").read_text() == "AURORA_X=today\n"
    assert asked[-1][:2] == ["systemctl", "start"]


def test_the_backup_s_own_key_never_goes_in_it(installed):
    cfg = installed
    st = cfg.path("AURORA_STATUS_DIR")
    for rel in (".config/aurora/backup.key", ".cache/x/big", ".config/caddy/autosave.json"):
        (st / "home" / rel).parent.mkdir(parents=True, exist_ok=True)
        (st / "home" / rel).write_text("x")
    names = {r for r, _ in B.files(cfg)}
    assert not any(n.endswith("backup.key") or "/.cache/" in n for n in names) and any(n.endswith("autosave.json") for n in names)


def test_a_restore_goes_only_into_the_backup_s_own_folder_of_the_installation(installed):
    cfg = installed
    B.run(cfg)
    with pytest.raises(B.BackupError):
        B.restore(cfg, cfg.root / "restore-here")
    r = B.restore(cfg, cfg.path("AURORA_STATUS_DIR") / "backup" / "restore-1", parts=("config",))
    assert r["files"] >= 1


def test_nothing_changes_when_aurora_cannot_be_stopped(installed, monkeypatch, tmp_path_factory):
    cfg, tmp_path = installed, tmp_path_factory.mktemp("next-to-it")
    B.run(cfg)
    st = cfg.path("AURORA_STATUS_DIR")
    (st / "routines.json").write_text("today")
    R = _restore_script()
    monkeypatch.setattr(R.subprocess, "run", lambda *a, **k: type("X", (), {"returncode": 0, "stdout": "active"})())
    with pytest.raises(SystemExit):
        R.apply_parts(cfg, {"snapshot": "latest", "compat": {"verdict": "same", "why": ""}, "stage": str(tmp_path / "s"), "aside": str(tmp_path / "a")}, ("config",))
    assert (st / "routines.json").read_text() == "today"


def test_what_today_s_keys_sealed_goes_aside_when_the_backup_s_keys_come_back(installed, monkeypatch, tmp_path_factory):
    from aurora import sys_seal
    cfg, tmp_path = installed, tmp_path_factory.mktemp("next-to-it")
    st, vault = cfg.path("AURORA_STATUS_DIR"), cfg.path("AURORA_VAULT_DIR")
    key = st / "users" / "ann" / "keys" / "memory.key"
    key.parent.mkdir(parents=True)
    key.write_text("the backup's")
    B.run(cfg)
    key.write_text("today's")                                                # a new installation's
    plain, sealed = cfg.root / "usr" / "ann" / "a.txt", cfg.root / "usr" / "ann" / "cal.sealed"
    plain.parent.mkdir(parents=True)
    plain.write_text("mine")
    sealed.write_bytes(sys_seal.MAGIC + b"x")
    R = _restore_script()
    monkeypatch.setattr(R.subprocess, "run", lambda *a, **k: type("X", (), {"returncode": 0, "stdout": "inactive"})())
    R.apply_parts(cfg, {"snapshot": "latest", "compat": {"verdict": "same", "why": ""}, "stage": str(tmp_path / "s"), "aside": str(tmp_path / "a")}, ("config",))
    assert key.read_text() == "the backup's" and plain.read_text() == "mine"
    assert not sealed.exists() and (tmp_path / "a" / "usr" / "ann" / "cal.sealed").exists()
    assert not (vault / "memory" / "conversation" / "0001.db").exists()     # today's memory: unreadable now, kept aside
    assert (vault / "knowledge" / "law" / "0001.db").exists()


def test_on_a_new_machine_the_backup_s_key_comes_back_from_its_code(installed):
    cfg = installed
    B.run(cfg)
    code = B.recovery_code(B.load_key(cfg))
    B.key_path(cfg).unlink()
    assert B.init_key(cfg, code) == code
    assert B.run(cfg)["ok"] and len(B.snapshots(B.target(cfg))) >= 1
