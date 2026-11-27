# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""R22 (owner, 27 Nov): Evidentia's sources on the NAS — one folder of the share, read only, for its account and
group, the backup's credentials copied (never in fstab); the address only in /etc/aurora/evidentia.env; the
originals' bind optional, so an unplugged disk never stops the service; the proxy lets the page browse, the admin read."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sys" / "core" / "script"))
import sys_root_evidentia as E  # noqa: E402
import sys_root_evidentia_nas as N  # noqa: E402


def test_a_folder_of_the_share_read_only_never_the_whole_share():
    assert N.parse("smb://nas.example/share/Epstein") == ("nas.example", "share", "Epstein")
    for bad in ("smb://nas.example/share", "smb://nas.example/share/../etc", "smb://x;ls/share/f", "http://a/b/c"):
        with pytest.raises((ValueError, SystemExit)):
            N.parse(bad)
    line = N.fstab_line("nas.example", "share", "Epstein", 990, 991)
    assert line.startswith("//nas.example/share/Epstein /mnt/evidentia-nas cifs ro,") and line.endswith("# evidentia-nas")
    assert "credentials=/etc/aurora/evidentia-nas.cred" in line and "password" not in line
    assert "file_mode=0440,dir_mode=0550" in line and "nofail" in line and "x-systemd.automount" in line


def test_the_env_keeps_the_address_and_the_schema_knows_it():
    text = E.env_text({k: Path("/x") for k in E.KEYS}, {}, "smb://nas.example/share/Epstein")
    assert "EVD_NAS_SOURCES=smb://nas.example/share/Epstein" in text and "EVD_NAS_DIR=/mnt/evidentia-nas" in text
    keys = {s["key"] for s in json.loads((ROOT / "sys" / "evidentia" / "config" / "settings_schema.json").read_text())["settings"]}
    assert {line.split("=", 1)[0] for line in text.splitlines()} <= keys           # C752: never a key it refuses


def test_the_originals_bind_is_optional():
    u = E.unit_text(Path("/v"), {"EVD_DATA_DIR": Path("/d"), "EVD_MODELS_DIR": Path("/m"), "EVD_SOURCES_DIR": Path("/run/media/x/f")})
    line = next(l for l in u.splitlines() if l.startswith("BindReadOnlyPaths="))
    assert '"-/run/media/x/f"' in line and '"/m"' in line and '"-/m"' not in line


def test_aurora_root_passes_the_nas_and_copies_the_module():
    src = (ROOT / "sys" / "core" / "script" / "sys_root.py").read_text(encoding="utf-8")
    assert 'sys_root_evidentia.main("install", _write, REPO, yes, extra)' in src and '"sys_root_evidentia_nas.py"' in src
    assert E.main.__code__.co_varnames[:5] == ("action", "write", "repo", "yes", "extra")


def test_the_proxy_browses_for_who_may_and_reads_in_for_the_admin():
    src = (ROOT / "sys" / "evidentia" / "addon" / "api_evidentia.py").read_text(encoding="utf-8")
    assert "sources(/(browse|ingest))?" in src
    assert 'if path in ("sources/ingest", "money/run") and method != "GET":' in src and "only the admin reads a folder" in src


def test_a_user_s_request_is_read_strictly_and_once(tmp_path):
    """N168: a request of Aurora's own, small, recent, not writable by others — read once; anything else refused."""
    import os
    import time
    uid = os.getuid()
    good = tmp_path / "nas-ann.json"
    good.write_text(json.dumps({"at": time.time(), "url": "smb://nas.example/share/Ann", "nas_user": "ann", "password": "pw"}))
    os.chmod(good, 0o600)
    old = tmp_path / "nas-bob.json"
    old.write_text(json.dumps({"at": time.time() - 3600}))
    os.chmod(old, 0o600)
    loose = tmp_path / "nas-cid.json"
    loose.write_text(json.dumps({"at": time.time()}))
    os.chmod(loose, 0o666)
    (tmp_path / "nas-dan.json").symlink_to(good)
    (tmp_path / "nas-../x.json".replace("/", "_")).write_text("{}")
    got = {r["user"]: r for r in N.read_requests(tmp_path, uid)}
    assert got["ann"]["url"] == "smb://nas.example/share/Ann" and "error" in got["bob"]
    assert "cid" not in got and "dan" not in got                                  # loose or a link: refused
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["nas-.._x.json", "nas-dan.json"]          # read ones gone; a bad name never read, a link never followed


def test_a_user_s_folder_is_their_own_line_and_mount():
    line = N.user_line("nas.example", "share", "Ann", 990, 991, "ann")
    assert line.startswith("//nas.example/share/Ann /mnt/evidentia-nas-ann cifs ro,") and line.endswith("# evidentia-nas-ann")
    assert "credentials=/etc/aurora/evidentia-nas-ann.cred" in line
    with pytest.raises(ValueError):
        N.mount_user({"user": "../root", "url": "smb://a/b/c", "nas_user": "x", "password": "y"}, 1, 1, "evidentia", run=None)


def test_the_unit_and_the_route_are_wired():
    gen = (ROOT / "sys" / "core" / "script" / "sys_install_services.py").read_text(encoding="utf-8")
    assert '"aurora-evidentia-nas.service"' in gen and 'sys_root_evidentia_nas.py"' in gen
    root = (ROOT / "sys" / "core" / "script" / "sys_root.py").read_text(encoding="utf-8")
    assert '"aurora-evidentia-nas.service": "sys_root_evidentia_nas.py"' in root
    api = (ROOT / "sys" / "evidentia" / "addon" / "api_evidentia.py").read_text(encoding="utf-8")
    assert '@router.post("/v1/aurora/evidentia-nas", dependencies=[Depends(USE)])' in api and "u == _admin()" in api
