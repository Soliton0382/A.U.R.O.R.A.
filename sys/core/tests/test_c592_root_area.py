# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C592 (audit of 12 Nov, area F): what root does for Aurora never goes through a link the services' account planted,
never runs the writable folder's code, and the owner sees all he signs."""
import getpass
import grp
import importlib.util
import os
import stat
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not hasattr(os, "O_PATH"), reason="descriptor calls of Linux")


def _load(name: str, as_name: str):
    spec = importlib.util.spec_from_file_location(as_name, CORE / "script" / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---- F7 / F2: sys_service_account -------------------------------------------------------------------------------
@pytest.fixture()
def account(tmp_path, monkeypatch):
    S = _load("sys_service_account.py", "sas_c592")
    root = tmp_path / "aurora"
    (root / "sys/status").mkdir(parents=True)
    (root / "sys/core/script").mkdir(parents=True)
    monkeypatch.setattr(S, "ROOT", root)
    monkeypatch.setattr(S, "DRY", False)
    monkeypatch.setattr(S, "ACCOUNT", grp.getgrgid(os.getgid()).gr_name)      # a group this test may give files to
    return S, root


def test_the_tree_is_changed_through_descriptors_and_a_link_is_never_followed(account, tmp_path):
    S, root = account
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "shadow"
    victim.write_text("x")
    victim.chmod(0o600)
    outside.chmod(0o700)
    (root / "sys/status/file.json").write_text("{}")
    os.chmod(root / "sys/status/file.json", 0o600)
    (root / "sys/status/link").symlink_to(victim)                 # a link to a file, a link to a folder
    (root / "sys/status/dirlink").symlink_to(outside)
    (root / "install.sh").write_text("#!/bin/sh\n")
    os.chmod(root / "install.sh", 0o775)
    (root / ".env").write_text("A=1\n")
    S.tree()
    assert stat.S_IMODE(victim.stat().st_mode) == 0o600 and stat.S_IMODE(outside.stat().st_mode) == 0o700
    assert stat.S_IMODE((root / "sys/status/file.json").stat().st_mode) == 0o660
    assert stat.S_IMODE((root / "install.sh").stat().st_mode) == 0o755          # the owner's alone to write (C556)
    assert stat.S_IMODE((root / ".env").stat().st_mode) == 0o660
    assert (root / "sys/status").stat().st_mode & stat.S_ISGID
    assert root.stat().st_mode & stat.S_ISVTX and (root / "sys/core/script").stat().st_mode & stat.S_ISVTX


def test_an_entry_swapped_for_a_link_is_left_alone(account, tmp_path):
    S, root = account
    victim = tmp_path / "victim"
    victim.write_text("x")
    victim.chmod(0o600)
    (root / "swapped").symlink_to(victim)
    seen = []
    d = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert S._entry(d, "swapped", lambda target, st: seen.append(target)) is False
        (root / "plain").write_text("x")
        assert S._entry(d, "plain", lambda target, st: os.chmod(target, 0o640)) is True
    finally:
        os.close(d)
    assert not seen and stat.S_IMODE((root / "plain").stat().st_mode) == 0o640


def test_the_data_walk_skips_links_and_a_data_folder_that_is_a_link(account, tmp_path, monkeypatch):
    S, root = account
    monkeypatch.setattr(S, "exists_user", lambda name: False)      # uid -1: nothing changes hands in a test
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a").write_text("x")
    (root / "sys/logs").symlink_to(outside)                        # a whole data folder replaced by a link
    (root / "sys/status/f").write_text("x")
    (root / "sys/status/l").symlink_to(outside / "a")
    (root / ".env").write_text("A=1\n")
    S.said.clear()
    S.data_owner()
    assert " 3 files and folders" in S.said[-1]                    # sys/status, its file, .env — nothing of outside


def test_the_home_is_made_through_no_link(account, tmp_path):
    S, root = account
    me = getpass.getuser()
    S.make_home(root / "sys/status/home", me)
    assert stat.S_IMODE((root / "sys/status/home").stat().st_mode) == 0o750
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir(mode=0o700)
    (root / "sys/status/home2").symlink_to(elsewhere)
    with pytest.raises(OSError):
        S.make_home(root / "sys/status/home2", me)
    assert stat.S_IMODE(elsewhere.stat().st_mode) == 0o700


def test_root_launches_its_own_copy_never_the_folders(account, monkeypatch):
    S, root = account
    assert S.root_launcher() == root / "sys/core/script/sys_root.py"            # the first setup: no copy of root's yet
    monkeypatch.setattr(S, "HERE", S.LIB / "sys/core/script/sys_service_account.py")
    assert S.root_launcher() == S.LIB / "sys/core/script/sys_root.py"
    monkeypatch.setattr(S, "HERE", root / "sys/core/script/sys_service_account.py")
    monkeypatch.setattr(S, "SHIM", root / "install.sh")
    (root / "install.sh").write_text("")
    monkeypatch.setattr(S.os, "geteuid", lambda: 0)
    assert S.main() == 1                                           # once aurora-root exists: only through it


# ---- F2, F7, F8, F9: sys_root ------------------------------------------------------------------------------------
sys.path.insert(0, str(CORE / "script"))
import sys_root as R  # noqa: E402


def test_the_setup_never_runs_compiled_files_of_the_writable_folder():
    src = (CORE / "script" / "sys_root.py").read_text(encoding="utf-8")
    guard, first_import = src.index("sys.pycache_prefix = "), src.index("from aurora import sys_ethics")
    assert guard < first_import and "sys.dont_write_bytecode = True" in src[:first_import]
    assert sys.pycache_prefix is None or "aurora.pycache" not in str(sys.pycache_prefix)   # importing it changes nothing


def test_root_writes_inside_a_folder_it_holds_open(tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("root's")
    folder = tmp_path / "ethics"
    folder.mkdir()
    (folder / ".MANIFEST.json.aurora-root").symlink_to(victim)     # planted at the temporary name
    (folder / "MANIFEST.json").symlink_to(victim)                  # and at the name itself
    R._write(folder / "MANIFEST.json", b"{}", 0o644)
    assert victim.read_text() == "root's" and (folder / "MANIFEST.json").read_bytes() == b"{}"
    assert not (folder / "MANIFEST.json").is_symlink()
    assert stat.S_IMODE((folder / "MANIFEST.json").stat().st_mode) == 0o644
    (tmp_path / "linked").symlink_to(folder)
    with pytest.raises(SystemExit):
        R._write(tmp_path / "linked" / "x.json", b"{}", 0o644)
    assert not (folder / "x.json").exists()


def test_the_owner_sees_every_name_he_signs(capsys):
    names = [f"sys/core/aurora/m{i:03d}.py" for i in range(55)]
    d = {"unsigned": "", "changed": names, "added": ["sys/core/aurora/z\rhidden.py"], "removed": [], "protected": []}
    assert R.show(d) == 56
    out = capsys.readouterr().out
    assert all(n in out for n in names) and "altri" not in out
    assert "\r" not in out and "z\\rhidden.py" in out              # a name cannot wipe its own line
    R.show(d, 40)                                                  # --yes: nobody is asked, the count is said
    assert "… e altri 16" in capsys.readouterr().out


@pytest.mark.parametrize("text", [
    "[Service]\n User=root\nUser=aurora\nExecStart=/bin/true\n",                 # systemd drops the leading space
    "[Service]\nUser = root\nExecStart=/bin/true\n",
    "[Unit]\nDescription=x \\\nUser=aurora\n[Service]\nExecStart=/bin/true\n",   # the User= is the tail of a line
    "[Service]\nUser=aurora\nGroup=root\nExecStart=/bin/true\n",
    "[Service]\nUser=aurora\nSupplementaryGroups=disk\nExecStart=/bin/true\n",
    "[Service]\nUser=aurora\nAmbientCapabilities=CAP_SYS_ADMIN\nExecStart=/bin/true\n",
    "[Service]\nUser=aurora\nCapabilityBoundingSet=~CAP_NET_RAW\nExecStart=/bin/true\n",
    "[Service]\nUser=aurora\nLoadCredential=x:/etc/shadow\nExecStart=/bin/true\n",
    "[Service]\nUser=aurora\nStandardOutput=file:/etc/cron.d/x\nExecStart=/bin/true\n",
    "[Service]\nUser=aurora\nPAMName=login\nExecStart=/bin/true\n",
    "[Service]\nUser=aurora\nRootImage=/x.img\nExecStart=/bin/true\n",
    "[Service]\nUser=aurora\nExecStartPre=/bin/true\nExecStart=/bin/true\n",
    "[Service]\nUser=00\nExecStart=/bin/true\n",
])
def test_a_unit_that_is_root_in_all_but_name_is_refused(text):
    assert R.unit_problems({"sys/deploy/systemd/aurora-api.service": text.encode()}), text


def test_roots_units_keep_their_environment_and_the_generated_ones_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "REPO", tmp_path)
    want = f"ExecStart=/usr/bin/python3 -I {R.LIB}/sys/core/script/sys_nas_mount.py\n"
    env = f"Environment=INSTALL_ROOT={tmp_path}\nEnvironment=AURORA_ENV_FILE={tmp_path / '.env'}\n"
    d = "sys/deploy/systemd/"
    assert R.unit_problems({d + "aurora-mount.service": ("[Service]\nType=oneshot\nUser=root\n" + want + env).encode()}) == []
    for more in ("Environment=LD_PRELOAD=/tmp/x.so\n", "Environment=INSTALL_ROOT=/elsewhere\n",
                 "AmbientCapabilities=CAP_NET_BIND_SERVICE\n"):
        assert R.unit_problems({d + "aurora-mount.service": ("[Service]\nUser=root\n" + want + env + more).encode()}), more
    good = ("# Generated\n[Unit]\nDescription=Aurora — API\nAfter=network-online.target\nWants=network-online.target\n"
            "PartOf=aurora.target\n\n[Service]\nType=simple\nUser=aurora\nWorkingDirectory=/opt/a\n"
            "ExecStart=/opt/a/.venv/bin/python svc.py\nExecReload=/usr/bin/caddy reload\nRestart=on-failure\nRestartSec=5\n"
            "TimeoutStartSec=300\nKillMode=mixed\nKillSignal=SIGTERM\nEnvironment=MALLOC_ARENA_MAX=2\nUMask=0007\n"
            "NoNewPrivileges=yes\nProtectSystem=strict\nProtectHome=read-only\nReadWritePaths=/opt/a -/x\nPrivateTmp=yes\n"
            "InaccessiblePaths=-/x/.ssh/id\nCapabilityBoundingSet=\nAmbientCapabilities=CAP_NET_BIND_SERVICE\n"
            "RestrictSUIDSGID=yes\nLockPersonality=yes\nRestrictRealtime=yes\nLimitNOFILE=8192\nMemorySwapMax=0\n"
            "MemoryHigh=1G\nSystemCallArchitectures=native\nRestrictAddressFamilies=AF_UNIX AF_INET\n"
            "IPAddressDeny=any\nIPAddressAllow=localhost\nNice=10\nCPUWeight=20\nIOSchedulingClass=idle\n"
            "BindReadOnlyPaths=-/a:/b\nStartLimitBurst=3\nOnFailure=aurora-backup-failed.service\n\n"
            "[Install]\nWantedBy=aurora.target\n")
    assert R.unit_problems({d + "aurora-api.service": good.encode()}) == []


# ---- F3, F10: the generator and the uninstaller ------------------------------------------------------------------
def test_a_setting_that_is_more_than_text_never_reaches_the_script_root_runs():
    G = _load("sys_install_services.py", "gen_c592")
    plain = {"AURORA_DOMAIN": "aurora.example.org", "AURORA_API_HOST": "127.0.0.1", "AURORA_MODELS_HOST": "::1",
             "AURORA_LLM_HOST": "localhost", **{k: "sys/x" for k in G.TEXT_SETTINGS}}
    assert G.unsafe_values(plain) == []
    assert G.unsafe_values({**plain, "AURORA_DOMAIN": "localhost; id"}) == ["AURORA_DOMAIN"]
    assert G.unsafe_values({**plain, "AURORA_API_HOST": "$(id)"}) == ["AURORA_API_HOST"]
    assert G.unsafe_values({**plain, "AURORA_BACKUP_DIR": "/mnt/x\nUser=root"}) == ["AURORA_BACKUP_DIR"]
    assert G.unsafe_values({**plain, "AURORA_STATUS_DIR": 'sys/"$(id)"'}) == ["AURORA_STATUS_DIR"]


def _bash(script: str, *args: str) -> tuple[int, str]:
    import subprocess
    r = subprocess.run(["bash", "-c", script, "bash", *args], capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout


CREDS = (("/etc/credstore.encrypted/aurora-key.cred", True), ("/etc/credstore.encrypted/aurora-/../../shadow", False),
         ("/etc/credstore.encrypted/aurora-x/y", False), ("/etc/shadow", False), ("/etc/credstore.encrypted/aurora-a b", False),
         ("/etc/credstore.encrypted/aurora-..", False))


def test_the_sealed_marker_names_a_credential_and_nothing_else(tmp_path):
    G = _load("sys_install_services.py", "gen_c592b")
    text = G.INSTALL.template
    fn = text[text.index("sealed() {"):text.index("if /usr/bin/python3 -I")].replace("$$", "$")
    for value, ok in CREDS:
        marker = tmp_path / "aurora.sealed"
        marker.write_text(value + "\n")
        code, out = _bash(fn + '\nsealed "$1"', str(marker))
        assert (code == 0 and out == value) if ok else (code != 0 and out == ""), value


def test_uninstall_deletes_only_a_credential_of_its_own_name():
    text = (CORE.parents[1] / "uninstall.sh").read_text(encoding="utf-8")
    start = text.index('  case "$CRED" in')
    block = text[start:text.index("  esac\n", start) + len("  esac\n")]
    for value, ok in CREDS:
        code, out = _bash('CRED="$1"\n' + block + '\nprintf %s "$CRED"', value)
        assert code == 0 and out == (value if ok else ""), value


# ---- F4, F5, F11: the restore and the settings -------------------------------------------------------------------
def _snapshot(tmp_path, monkeypatch, mode=0o4755):
    import hashlib
    import hmac
    import json
    from aurora import sys_backup as B, sys_backup_crypto as C
    root, nas = tmp_path / "root", tmp_path / "nas"
    (root / "sys/status/backup").mkdir(parents=True)
    (nas / "snapshots").mkdir(parents=True)
    raw = os.urandom(32)
    enc, idkey = C._subkeys(raw)
    payload = b"restored\n"
    bid = hmac.new(idkey, payload, hashlib.sha256).hexdigest()
    bp = B._blob_path(nas, bid)
    bp.parent.mkdir(parents=True)
    bp.write_bytes(C._encrypt_bytes(payload, enc))
    snap = {"files": [["x.conf", len(payload), 0, mode, bid]], "formats": {}}
    (nas / "snapshots" / "20990101-000000.snap").write_bytes(C._encrypt_bytes(json.dumps(snap).encode(), enc))

    class Cfg:
        def path(self, key):
            return root / "sys/status"

        def __getitem__(self, key):
            return str(nas) if key == "AURORA_BACKUP_DIR" else "sys/status"
    Cfg.root = root
    monkeypatch.setattr(B, "load_key", lambda cfg: raw)
    return B, Cfg(), root


def test_restore_never_follows_a_link_at_the_stage_and_drops_setuid(tmp_path, monkeypatch):
    B, cfg, root = _snapshot(tmp_path, monkeypatch)
    victim = tmp_path / "etc" / "unit.service.d"
    victim.parent.mkdir()
    stage = root / "sys/status/backup/restore-1"
    stage.symlink_to(victim)                                       # dangling: mkdir through it made the folder
    with pytest.raises(B.BackupError):
        B.restore(cfg, stage, "latest")
    victim.mkdir()                                                 # and to a folder that is there
    with pytest.raises(B.BackupError):
        B.restore(cfg, stage, "latest")
    assert list(victim.iterdir()) == []
    (root / "sys/status/backup/deep").symlink_to(tmp_path / "etc")  # a link one step above the stage
    with pytest.raises(B.BackupError):
        B.restore(cfg, root / "sys/status/backup/deep/unit.service.d", "latest")
    assert list(victim.iterdir()) == []
    r = B.restore(cfg, root / "sys/status/backup/restore-2", "latest")
    f = root / "sys/status/backup/restore-2/x.conf"
    assert r["files"] == 1 and f.read_bytes() == b"restored\n"
    assert stat.S_IMODE(f.stat().st_mode) == 0o755                  # the snapshot said 4755
    out = tmp_path / "out"                                          # outside the installation: as before
    assert B.restore(cfg, out, "latest")["files"] == 1
    (tmp_path / "into-root").symlink_to(root / "sys")
    with pytest.raises(B.BackupError):
        B.restore(cfg, tmp_path / "into-root" / "new", "latest")   # the live installation reached through a link


def test_the_proposed_settings_are_a_new_file_never_a_link_followed(tmp_path):
    E = _load("sys_env_sync.py", "envsync_c592")
    victim = tmp_path / "victim"
    victim.write_text("root's")
    folder = tmp_path / "aurora"
    folder.mkdir()
    (folder / ".env.proposed").symlink_to(victim)
    E.write_new(folder / ".env.proposed", "A=1\n")
    assert victim.read_text() == "root's"
    assert not (folder / ".env.proposed").is_symlink() and (folder / ".env.proposed").read_text() == "A=1\n"
    assert stat.S_IMODE((folder / ".env.proposed").stat().st_mode) == 0o600


def test_a_path_setting_stays_inside_the_installation():
    from aurora import sys_config
    spec = {"type": "path"}
    assert sys_config.convert(spec, "sys/status") == "sys/status"
    assert sys_config.convert(spec, "sys/my..folder/x") == "sys/my..folder/x"
    for bad in ("../../etc", "sys/../../etc/cron.d", "..", "sys\\..\\..\\x"):
        with pytest.raises(ValueError):
            sys_config.convert(spec, bad)
