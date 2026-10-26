# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import io
import os
import sqlite3

import pytest

from aurora import sys_backup as B


@pytest.fixture
def setup(cfg, tmp_path_factory):
    """An installation with a vault shard in WAL mode (open, with rows not yet checkpointed), status, user files."""
    root = cfg.root
    dest = tmp_path_factory.mktemp("other-disk")
    cfg.values.update(AURORA_BACKUP_DIR=str(dest), AURORA_BACKUP_KEY_FILE=str(tmp_path_factory.mktemp("key") / "k"),
                      AURORA_BACKUP_KEEP_DAILY=7, AURORA_BACKUP_KEEP_WEEKLY=4, AURORA_BACKUP_KEEP_MONTHLY=6)
    shard = cfg.path("AURORA_VAULT_DIR") / "knowledge" / "law_it" / "0001.db"
    shard.parent.mkdir(parents=True)
    con = sqlite3.connect(shard)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE s (id INTEGER PRIMARY KEY, text TEXT)")
    con.executemany("INSERT INTO s (text) VALUES (?)", [(f"articolo {i}",) for i in range(500)])
    con.commit()                                          # kept open: the rows live in the WAL file
    (cfg.path("AURORA_STATUS_DIR") / "routines.json").parent.mkdir(parents=True, exist_ok=True)
    (cfg.path("AURORA_STATUS_DIR") / "routines.json").write_text('{"r": 1}')
    (cfg.path("AURORA_STATUS_DIR") / "gpu.lock").write_text("busy")
    (cfg.path("AURORA_STATUS_DIR") / "bench").mkdir()
    (cfg.path("AURORA_STATUS_DIR") / "bench" / "big.json").write_text("rebuilt")
    docs = cfg.path("AURORA_DOCUMENTS_DIR")
    docs.mkdir(parents=True)
    (docs / "paper.pdf").write_bytes(b"%PDF" + b"x" * 9_000_000)   # more than two frames
    (docs / "bench").mkdir()
    (docs / "bench" / "mine.txt").write_text("the owner's own folder named bench is kept")
    yield cfg, dest, con, root
    con.close()


def test_a_backup_round_trip_keeps_everything_and_writes_only_what_changed(setup, tmp_path_factory):
    cfg, dest, con, root = setup
    code = B.init_key(cfg)
    with pytest.raises(B.BackupError):
        B.init_key(cfg)                                    # a key is never replaced
    first = B.run(cfg)
    rels = {e[0] for e in B.read_snapshot(B.snapshots(dest)[-1], B._subkeys(B.load_key(cfg))[0])["files"]}
    assert "sys/vault/knowledge/law_it/0001.db" in rels and "usr/documents/paper.pdf" in rels
    assert "usr/documents/bench/mine.txt" in rels and ".env" in rels
    assert not any(r.endswith(("gpu.lock", "0001.db-wal")) or "/status/bench/" in r for r in rels)
    assert first["new_blobs"] == first["files"] and first["checked_blobs"] > 0
    import time
    time.sleep(1.1)                                        # a new snapshot name (one per second)
    second = B.run(cfg)
    assert second["new_blobs"] == 0 and second["bytes_written"] == 0   # 9 MB not written again
    con.execute("INSERT INTO s (text) VALUES ('articolo nuovo')")
    con.commit()
    time.sleep(1.1)
    third = B.run(cfg)
    assert third["new_blobs"] == 1                         # only the changed shard
    out = tmp_path_factory.mktemp("restored")
    r = B.restore(cfg, out, code=code)                     # with the recovery code, as after a lost disk
    assert r["files"] == third["files"]
    back = sqlite3.connect(out / "sys/vault/knowledge/law_it/0001.db")
    assert back.execute("SELECT count(*) FROM s").fetchone()[0] == 501
    back.close()
    assert (out / "usr/documents/paper.pdf").read_bytes() == (root / "usr/documents/paper.pdf").read_bytes()
    assert B.verify(cfg) == len({e[4] for e in B.read_snapshot(B.snapshots(dest)[-1], B._subkeys(B.load_key(cfg))[0])["files"]})


def test_a_blob_write_that_fails_once_is_tried_again(tmp_path, monkeypatch):
    """C400: Errno 14 on the NAS in a night's copy; a later try writes the whole blob, a third failure is raised."""
    import errno
    real, fails = B.encrypt_stream, []

    def flaky(src, dst, key):
        if len(fails) < want:
            fails.append(1)
            dst.write(b"half")
            raise OSError(errno.EFAULT, "Bad address")
        real(src, dst, key)
    monkeypatch.setattr(B, "encrypt_stream", flaky)
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    (tmp_path / "f").write_bytes(b"data" * 1000)
    key, bp, log = os.urandom(32), tmp_path / "ab" / "blob", __import__("logging").getLogger("t")
    bp.parent.mkdir()
    want = 2
    B._write_blob(tmp_path / "f", bp, key, log)
    out = io.BytesIO()
    B.decrypt_stream(io.BytesIO(bp.read_bytes()), out, key)
    assert out.getvalue() == b"data" * 1000 and not (bp.parent / "blob.part").exists()
    fails.clear()
    want, bp2 = 3, tmp_path / "ab" / "blob2"
    with pytest.raises(OSError):
        B._write_blob(tmp_path / "f", bp2, key, log)
    assert not bp2.exists() and not (bp.parent / "blob2.part").exists()


def test_a_changed_or_cut_blob_and_a_wrong_key_are_refused():
    key = bytes(32)
    blob = io.BytesIO()
    B.encrypt_stream(io.BytesIO(b"a" * (B.FRAME * 2 + 5)), blob, key)
    data = blob.getvalue()
    assert B._decrypt_bytes(data, key) == b"a" * (B.FRAME * 2 + 5)
    bad = bytearray(data)
    bad[100] ^= 1
    for wrong, k in ((bytes(bad), key), (data[:B.FRAME + 50], key), (data, b"\x01" * 32)):
        with pytest.raises(B.BackupError):
            B._decrypt_bytes(wrong, k)
    assert B._decrypt_bytes(B._encrypt_bytes(b"", key), key) == b""


def test_the_backup_folder_and_the_restore_folder_are_checked(setup, tmp_path_factory):
    cfg, dest, con, root = setup
    for bad in ("", "relative/dir", str(root / "inside"), str(dest / "missing")):
        cfg.values["AURORA_BACKUP_DIR"] = bad
        if bad == str(root / "inside"):
            (root / "inside").mkdir()
        with pytest.raises(B.BackupError):
            B.target(cfg)
    cfg.values["AURORA_BACKUP_DIR"] = str(dest)
    B.init_key(cfg)
    B.run(cfg)
    with pytest.raises(B.BackupError):
        B.restore(cfg, root / "restore-here")              # never inside the live installation
    full = tmp_path_factory.mktemp("full")
    (full / "x").write_text("x")
    with pytest.raises(B.BackupError):
        B.restore(cfg, full)                               # never over files


def test_retention_keeps_days_weeks_months_and_always_the_newest():
    names = [f"202610{d:02d}-033000" for d in range(1, 31)] + [f"2026{m:02d}15-033000" for m in range(1, 10)]
    kept = B.keep(names, daily=7, weekly=4, monthly=6)
    days = {f"202610{d}-033000" for d in range(24, 31)}            # the last 7 days
    weeks = {"20261018-033000", "20261011-033000"}                 # + the newest of 2 older ISO weeks (4 in all)
    months = {f"2026{m:02d}15-033000" for m in range(5, 10)}       # + the newest of 5 older months (6 in all)
    assert kept == days | weeks | months
    assert B.keep(["20261001-000000"], 0, 0, 0) == {"20261001-000000"}
    assert B.key_from_code(B.recovery_code(b"\x07" * 32)) == b"\x07" * 32


@pytest.mark.skipif(os.name == "nt", reason="systemd unit and timer: the Windows backup task is not written yet")
def test_the_backup_unit_and_timer_are_made_only_with_a_folder_and_may_write_only_there(setup, monkeypatch):
    import getpass
    import importlib.util
    cfg, dest, con, root = setup
    spec = importlib.util.spec_from_file_location("sis", B.__file__.replace("aurora/sys_backup.py", "script/sys_install_services.py"))
    sis = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sis)
    cfg.values.update(AURORA_CADDY_BIN="true", AURORA_SERVICE_USER=getpass.getuser(), AURORA_BACKUP_TIME="03:30")
    monkeypatch.setattr(sis.sys_config, "get", lambda: cfg)
    out = root / "sys" / "deploy" / "systemd"
    cfg.path("AURORA_HTTPS_DIR").mkdir(parents=True, exist_ok=True)
    cfg.values["AURORA_BACKUP_DIR"] = ""
    assert sis.main() == 0 and not (out / "aurora-backup.timer").exists()
    assert "$backup" not in (out / "install.sh").read_text()
    cfg.values["AURORA_BACKUP_DIR"] = str(dest)
    assert sis.main() == 0
    unit, timer = (out / "aurora-backup.service").read_text(), (out / "aurora-backup.timer").read_text()
    assert "Type=oneshot" in unit and "svc_backup.py run" in unit and f" {dest}" in unit and "IOSchedulingClass=idle" in unit and "MemoryHigh=2G" in unit
    assert "OnCalendar=*-*-* 03:30:00" in timer and "Persistent=true" in timer
    assert "enable --now aurora-backup.timer" in (out / "install.sh").read_text()
    assert not (out / "aurora-mount.service").exists()          # a local folder needs no mount
    cfg.values["AURORA_BACKUP_DIR"] = "smb://192.168.1.20/backups/aurora/"
    assert sis.main() == 0
    mount, unit = (out / "aurora-mount.service").read_text(), (out / "aurora-backup.service").read_text()
    assert "User=root" in mount and "sys_nas_mount.py" in mount
    assert "ReadWritePaths=-" in mount and "status/backup" in mount           # the result reaches the card (C90)
    assert " /mnt/aurora-nas" in unit and "smb://" not in unit.split("ReadWritePaths=")[1].split("\n")[0]
    assert "aurora-mount.service" in (out / "install.sh").read_text()
    cfg.values["AURORA_BACKUP_TIME"] = "25:99"
    assert sis.main() == 1


def test_a_backup_unit_that_could_not_start_is_reported(monkeypatch):
    """A18: the NAS asleep at 03:30 → the unit failed before Aurora's code ran (226/NAMESPACE): no log, no push."""
    import subprocess

    from aurora import sys_backup

    def show(out):
        return lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out, stderr="")
    monkeypatch.setattr(subprocess, "run", show("Result=exit-code\nExecMainStatus=226\nLoadState=loaded\n"))
    assert "NAS" in sys_backup.unit_failure()
    monkeypatch.setattr(subprocess, "run", show("Result=success\nExecMainStatus=0\nLoadState=loaded\n"))
    assert sys_backup.unit_failure() is None
    monkeypatch.setattr(subprocess, "run", show("Result=success\nExecMainStatus=0\nLoadState=not-found\n"))
    assert sys_backup.unit_failure() is None
    # C400: the unit failed at 1000, then a run by hand succeeded at 1100: the failure is past
    monkeypatch.setattr(subprocess, "run", show("Result=exit-code\nExecMainStatus=1\nLoadState=loaded\n"
                                                "InactiveEnterTimestamp=@1000\n"))
    assert sys_backup.unit_failure(after=1100.0) is None
    assert "codice 1" in sys_backup.unit_failure(after=900.0)


def test_the_copy_of_a_database_leaves_no_descriptor_open(tmp_path):
    """C207: mkstemp's descriptor was never closed — on Windows the copy could not be deleted (a real run), on Linux
    one descriptor stayed open for each database of each backup."""
    import os
    import sqlite3
    if not os.path.isdir("/proc/self/fd"):
        pytest.skip("counts this process's descriptors through /proc")
    db = tmp_path / "a.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t (x)")
    con.commit()
    con.close()
    (tmp_path / "copies").mkdir()
    before = len(os.listdir("/proc/self/fd"))
    for _ in range(20):
        B._sqlite_copy(db, tmp_path / "copies").unlink()
    assert len(os.listdir("/proc/self/fd")) == before


def test_the_sampled_check_goes_round_every_blob_instead_of_drawing_by_chance(setup, monkeypatch):
    cfg, dest, con, root = setup
    B.init_key(cfg)
    B.run(cfg)
    blobs = {e[4] for e in B.read_snapshot(B.snapshots(dest)[-1], B._subkeys(B.load_key(cfg))[0])["files"]}
    assert len(blobs) > 2
    checked, path = [], B._blob_path
    monkeypatch.setattr(B, "_blob_path", lambda d, bid: (checked.append(bid), path(d, bid))[1])
    for _ in range(len(blobs)):                            # one blob per run: all of them in as many runs
        assert B.verify(cfg, sample=1) == 1
    assert sorted(checked) == sorted(blobs)                # each once, none drawn twice by chance


def test_the_apps_signing_key_is_kept_and_its_toolchain_is_not(cfg):
    """sys/app/keys is in the backup (an app update installs only with the same key); sys/app/tools, 8 GB that can
    be downloaded again, is not."""
    for d, name in (("keys", "aurora-app.jks"), ("tools", "javac")):
        (cfg.root / "sys" / "app" / d).mkdir(parents=True, exist_ok=True)
        (cfg.root / "sys" / "app" / d / name).write_bytes(b"x")
    kept = {rel for rel, _ in B.files(cfg)}
    assert "sys/app/keys/aurora-app.jks" in kept and not any(r.startswith("sys/app/tools") for r in kept)
