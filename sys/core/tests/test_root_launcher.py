# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-root (sys_root.py, 9 Nov): root signs, copies and installs only the bytes the owner signed, from root's own
folder; what changed is asked first; a link in the code base is refused."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
import sys_root as R  # noqa: E402
from aurora import sys_ethics  # noqa: E402


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    root = tmp_path / "aurora"
    for f in (*sys_ethics.PROTECTED, "sys/core/aurora/x.py", "sys/core/script/sys_root.py",
              "sys/deploy/systemd/install.sh", "sys/deploy/systemd/aurora-api.service", "install.sh"):
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {f}\n")
    (root / "sys/deploy/systemd/install.sh").write_text('#!/usr/bin/env bash\ncp "$AURORA_DEPLOY/aurora-api.service" '
                                                         '"$INSTALL_ROOT/installed.service"\n')
    key = Ed25519PrivateKey.generate()
    pem = tmp_path / "owner_ed25519"
    pem.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    monkeypatch.setattr(sys_ethics, "PRIVATE_KEY", pem)
    monkeypatch.setattr(sys_ethics, "owner_public_key", lambda path=None: (pub, ""))
    monkeypatch.setattr(R, "REPO", root)
    monkeypatch.setattr(R, "LIB", tmp_path / "lib" / "aurora")
    monkeypatch.setattr(R, "CONF", tmp_path / "etc" / "root.conf")
    monkeypatch.setattr(R, "SHIM", tmp_path / "sbin" / "aurora-root")
    monkeypatch.setattr(R, "SUDOERS", tmp_path / "sudoers.d")           # C574: never the machine's own
    (tmp_path / "sbin").mkdir()
    import types
    monkeypatch.setitem(sys.modules, "sys_root_sync", types.SimpleNamespace(never_list=lambda: [], write_never=lambda n: None))
    return root


def test_signs_what_changed_then_copies_only_the_signed_bytes(repo):
    snap = R.snapshot()
    assert R.drift(snap)["unsigned"]                                   # nothing signed yet
    assert R.sign(snap, yes=True)
    assert not any(R.drift(R.snapshot())[k] for k in ("changed", "added", "removed"))
    from aurora import sys_ethics as E                                # the package (its protected files and x.py) and
    want = {f for f in E.PROTECTED if f.startswith("sys/core/aurora/")} | {"sys/core/aurora/x.py"} | {
        f"sys/core/script/{n}" for n in R.LIB_SCRIPTS if f"sys/core/script/{n}" in R.snapshot()}
    assert R.sync_lib(R.snapshot()) == len(want)                       # the scripts root runs, nothing else
    assert not (R.LIB / "install.sh").exists() and not (R.LIB / "sys/deploy").exists()
    assert (R.LIB / "sys/core/aurora/x.py").read_text() == "# sys/core/aurora/x.py\n"
    assert R.CONF.read_text() == f"{repo}\n" and "sys_root.py" in R.SHIM.read_text()
    (repo / "sys/core/aurora/x.py").write_text("changed by the services' account\n")
    d = R.drift(R.snapshot())
    assert d["changed"] == ["sys/core/aurora/x.py"] and not d["protected"]
    with pytest.raises(SystemExit):
        R.sync_lib(R.snapshot())                                       # not as signed: root's copy left as it was
    assert (R.LIB / "sys/core/aurora/x.py").read_text() == "# sys/core/aurora/x.py\n"


def test_an_install_runs_from_roots_copy_and_waits_for_the_signature(repo, monkeypatch):
    R.sign(R.snapshot(), yes=True)
    (repo / "sys/deploy/systemd/aurora-api.service").write_text("[Service]\nUser=aurora\nExecStart=/bin/true\n")
    monkeypatch.setattr(R.sys.stdin, "isatty", lambda: False)
    assert R.install("systemd", [], yes=False) == 1                    # nobody said yes: nothing installed
    assert not (repo / "installed.service").exists()
    assert R.install("systemd", [], yes=True) == 0                     # the owner signs what he saw, then it runs
    assert (repo / "installed.service").read_text() == "[Service]\nUser=aurora\nExecStart=/bin/true\n"


def test_a_link_in_the_code_base_is_refused(repo, tmp_path):
    secret = tmp_path / "shadow"
    secret.write_text("root's")
    (repo / "sys/core/aurora/y.py").symlink_to(secret)
    with pytest.raises(SystemExit):
        R.snapshot()


def test_a_link_in_a_plugins_sub_folder_is_refused_but_its_fetched_programs_are_not_signed(repo, tmp_path):
    """C558: the plugins' sub-folders are signed and walked, so a link planted there is seen and refused like any other;
    .bin and .deps are what plg_deps fetched (ngspice's tree carries links) — the services' writes, outside the signature,
    or the owner could not sign at all."""
    p = repo / "sys/plugins/circ"
    (p / "lib").mkdir(parents=True)
    (p / ".bin/ngspice/doc").mkdir(parents=True)
    (p / "plugin.json").write_text(json.dumps({"name": "circ"}))
    (p / "lib/models.py").write_text("# the owner's\n")
    (p / ".bin/ngspice/doc/COPYING").symlink_to(tmp_path / "GPL-2")
    snap = R.snapshot()                                                 # the link under .bin is not in the code base
    assert "sys/plugins/circ/lib/models.py" in snap and not any(f.startswith("sys/plugins/circ/.bin") for f in snap)
    (tmp_path / "shadow").write_text("root's")
    (p / "lib/shadow.py").symlink_to(tmp_path / "shadow")
    with pytest.raises(SystemExit):
        R.snapshot()


def test_root_never_writes_through_a_link(repo, tmp_path):
    target = tmp_path / "victim"
    target.write_text("intact")
    (repo / sys_ethics.MANIFEST).symlink_to(target)
    R.sign(R.snapshot(), yes=True)                                     # the manifest written beside, by a rename
    assert target.read_text() == "intact" and not (repo / sys_ethics.MANIFEST).is_symlink()
    assert json.loads((repo / sys_ethics.MANIFEST).read_text())["code_signature"]


def test_aurora_s_own_plugins_are_outside_the_signature_and_shown_with_their_contract(repo, capsys):
    """9 Nov (owner: «senza che debba ogni volta firmare»): a forged plugin is not in the signed code; the status says
    what its contract lets it do. An owner's plugin not signed is not loaded (sys_ethics.unsigned_plugins)."""
    p = repo / "sys/plugins/sly"
    p.mkdir(parents=True)
    (p / "plugin.json").write_text(json.dumps({"name": "sly", "forged": {"request": "r"}, "sandbox": {"network": False},
                                               "effects": {"*": "read"}}))
    (p / "server.py").write_text("# sly\n")
    R.sign(R.snapshot(), yes=True)
    assert not any(f.startswith("sys/plugins/sly/") for f in R.snapshot())
    (p / "server.py").write_text("# sly changed by Aurora\n")
    assert not any(R.drift(R.snapshot())[k] for k in ("changed", "added", "removed"))     # nothing to sign
    R.status()
    out = capsys.readouterr().out
    assert "🔨 sly (di Aurora, sotto contratto)" in out and "🌐 nessuna rete" in out
    mine = repo / "sys/plugins/mine"
    mine.mkdir()
    (mine / "plugin.json").write_text(json.dumps({"name": "mine"}))
    assert "mine" in sys_ethics.unsigned_plugins(repo)                                     # the owner's, unsigned
    R.sign(R.snapshot(), yes=True)
    sys_ethics._unsigned_cache.clear()
    assert sys_ethics.unsigned_plugins(repo) == set()


def test_a_protected_list_that_grows_is_signed_in_one_go(repo, monkeypatch):
    """C542 again, 9 Nov: the list of protected files is read from the code being signed, not from root's copy."""
    R.sign(R.snapshot(), yes=True)
    extra = "sys/core/aurora/x.py"
    (repo / "sys/core/aurora/sys_ethics.py").write_text(f"PROTECTED = {(*sys_ethics.PROTECTED, extra)!r}\n")
    d = R.drift(R.snapshot())
    assert d["unsigned"] and extra in d["protected"]                # said, though root's copy has the old list
    R.sign(R.snapshot(), yes=True)
    signed = json.loads((repo / sys_ethics.MANIFEST).read_text())["files"]
    assert extra in signed and not R.drift(R.snapshot())["unsigned"]


def test_root_never_runs_the_trees_copy_once_aurora_root_exists(tmp_path, monkeypatch, capsys):
    """Audit, 10 Nov: install.sh ran «sudo python3 -I sys/core/script/sys_root.py setup --yes» from the folder the
    services write, also on an update: once the shim exists, only root's own copy acts."""
    shim = tmp_path / "aurora-root"
    shim.write_text("#!/bin/sh\n")
    monkeypatch.setattr(R, "SHIM", shim)
    for action in ("setup", "sign", "install"):
        with pytest.raises(SystemExit):
            R.main([action, "--yes"])
        assert "questa copia sta nella cartella" in capsys.readouterr().err      # refused for that, not for sudo
    text = (Path(R.__file__).resolve().parents[3] / "install.sh").read_text()
    assert 'SIGN="sudo /usr/local/sbin/aurora-root sign"' in text


def test_verify_is_0_only_when_every_file_is_as_signed(repo, capsys):
    """C556: the owner's scripts (publish, uninstall) ask root's copy before running the folder's code as him."""
    assert R.verify() == 1                                             # nothing signed yet
    R.sign(R.snapshot(), yes=True)
    assert R.verify() == 0
    (repo / "sys/core/aurora/x.py").write_text("changed by the services' account\n")
    assert R.verify() == 1 and "sys/core/aurora/x.py" in capsys.readouterr().out


def test_the_account_and_gpu_steps_run_from_roots_copy_as_signed(repo, monkeypatch):
    """C556: never «sudo .venv/bin/python sys/core/script/…»: root's copy of the script, the system's Python."""
    for name in ("sys_service_account.py", "sys_nvidia.sh"):
        (repo / "sys/core/script" / name).write_text(f"# {name} as the owner wrote it\n")
    R.sign(R.snapshot(), yes=True)
    (repo / "sys/core/script/sys_service_account.py").write_text("# planted by the services' account\n")
    ran = []
    monkeypatch.setattr(R.subprocess, "run", lambda cmd, **k: ran.append((cmd, k)) or type("P", (), {"returncode": 0}))
    monkeypatch.setattr(R.sys.stdin, "isatty", lambda: False)
    cmd = ["/usr/bin/python3", "-I", str(R.LIB / "sys/core/script/sys_service_account.py")]
    assert R._signed_run(cmd, yes=False) == 1 and not ran           # changed and nobody said yes: nothing runs
    assert R._signed_run(cmd, yes=True) == 0                         # the owner signs what he saw, then root's copy
    assert ran[0][0] == cmd and ran[0][1]["env"]["INSTALL_ROOT"] == str(repo)
    assert (R.LIB / "sys/core/script/sys_service_account.py").read_text() == "# planted by the services' account\n"
    assert (R.LIB / "sys/core/script/sys_nvidia.sh").exists()


def test_a_code_list_that_grows_is_signed_in_one_command(repo):
    """C580: new CODE_PATTERNS in the sys_ethics.py being signed — its new files signed by the same `sign`, not left
    for a second one (root's copy, the previous signature, did not list them)."""
    R.sign(R.snapshot(), yes=True)
    (repo / "docs").mkdir()
    (repo / "docs" / "extra.txt").write_text("now code\n")
    (repo / "sys/core/aurora/sys_ethics.py").write_text(
        f"PROTECTED = {tuple(sys_ethics.PROTECTED)!r}\n"
        "def code_files(root):\n"
        "    from aurora import sys_ethics as E\n"
        "    return sorted(E.code_files(root) + ['docs/extra.txt'])\n")
    assert "docs/extra.txt" not in R.snapshot()                       # root's copy's list
    signed = R.sign_all(R.snapshot(), yes=True)
    assert "docs/extra.txt" in signed
    code = json.loads((repo / sys_ethics.MANIFEST).read_text())["code"]
    assert "docs/extra.txt" in code and code["sys/core/aurora/sys_ethics.py"]


def test_a_signed_list_that_cannot_be_read_leaves_root_s_list(repo, capsys):
    (repo / "sys/core/aurora/sys_ethics.py").write_text("raise RuntimeError('broken')\n")
    assert R.sign_all(R.snapshot(), yes=True) is not None
    assert "non riletto" in capsys.readouterr().out


def test_the_first_aurora_s_sudo_fragments_are_shown_and_removed_only_on_a_yes_asked(tmp_path, monkeypatch, capsys):
    """C574: shown whole; --yes never removes them; the owner's «s» does; aurora-nft (v2's) is kept."""
    d = tmp_path / "sudoers.d"
    d.mkdir()
    for n, text in (("aurora-services", "someone ALL=(root) NOPASSWD: /bin/true\n"), ("aurora-agi.bak_1", "x\n"),
                    ("aurora-nft", "kept\n"), ("README", "not ours\n")):
        (d / n).write_text(text)
    assert R.old_sudoers(True, d) == [] and (d / "aurora-services").exists()
    assert "NOPASSWD: /bin/true" in capsys.readouterr().out
    monkeypatch.setattr(R, "ask", lambda q, yes: True)
    monkeypatch.setattr(R.shutil, "which", lambda n: None)
    assert R.old_sudoers(False, d) == ["aurora-agi.bak_1", "aurora-services"]
    assert sorted(p.name for p in d.iterdir()) == ["README", "aurora-nft"]


def test_a_link_to_a_folder_or_a_dangling_link_is_refused_not_left_out(repo, tmp_path):
    """C579: code_files never lists them (glob does not enter a linked folder, a dangling link is no file)."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evil.py").write_text("x = 1\n")
    (repo / "sys/core/aurora/more").symlink_to(outside, target_is_directory=True)
    with pytest.raises(SystemExit):
        R.snapshot()
    (repo / "sys/core/aurora/more").unlink()
    (repo / "sys/deploy/systemd/gone.service").symlink_to(tmp_path / "nothing")
    with pytest.raises(SystemExit):
        R.snapshot()
    (repo / "sys/deploy/systemd/gone.service").unlink()
    assert R.snapshot()


def test_root_installs_only_units_that_run_what_they_should(repo, monkeypatch):
    """C539: root only for its three units and their one script from root's copy; any other unit as a non-root user,
    no «+»/«!» command; the install stops before install.sh runs."""
    d = "sys/deploy/systemd/"
    good = {d + "aurora-api.service": b"[Service]\nUser=aurora\nExecStart=/opt/a/.venv/bin/python svc_api.py\n",
            d + "aurora-mount.service": f"[Service]\nExecStart=/usr/bin/python3 -I {R.LIB}/sys/core/script/sys_nas_mount.py\n".encode()}
    assert R.unit_problems(good) == []
    for name, text in (("aurora-api.service", b"[Service]\nExecStart=/bin/sh -c id\n"),                 # no User: root
                       ("aurora-api.service", b"[Service]\nUser=root\nExecStart=/bin/true\n"),
                       ("aurora-api.service", b"[Service]\nUser=aurora\nExecStartPre=-+/bin/sh -c id\nExecStart=/bin/true\n"),
                       ("aurora-api.service", b"[Service]\nUser=aurora\nPermissionsStartOnly=true\nExecStart=/bin/true\n"),
                       ("aurora-mount.service", b"[Service]\nExecStart=/bin/sh -c id\n")):
        assert R.unit_problems({d + name: text}), text
    (repo / "sys/deploy/systemd/aurora-api.service").write_text("[Service]\nUser=root\nExecStart=/bin/true\n")
    R.sign_all(R.snapshot(), yes=True)
    ran = []
    monkeypatch.setattr(R.subprocess, "run", lambda *a, **k: ran.append(a) or R.subprocess.CompletedProcess(a, 0))
    with pytest.raises(SystemExit):
        R.install("systemd", [], yes=True)
    assert not ran                                                       # install.sh never started


def test_root_shows_what_it_changes_in_the_units(tmp_path, capsys):
    live = tmp_path / "etc"
    live.mkdir()
    (live / "aurora-api.service").write_text("[Service]\nUser=aurora\nExecStart=/old\n")
    n = R.show_unit_diff({"sys/deploy/systemd/aurora-api.service": b"[Service]\nUser=aurora\nExecStart=/new\n"}, live=live)
    out = capsys.readouterr().out
    assert n and "-ExecStart=/old" in out and "+ExecStart=/new" in out
