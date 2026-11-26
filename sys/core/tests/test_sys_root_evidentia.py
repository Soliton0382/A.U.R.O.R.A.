# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Evidentia as an add-on (27 Nov): installed in a folder of its own by the test — root's venv built offline from the
hash-locked wheelhouse, its settings, a confined unit running root's copy; an earlier installation's archive kept
where it is; a reinstall never moves to a new empty archive; uninstall leaves the archive."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
import sys_root_evidentia as E  # noqa: E402


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _archive(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "ARCHIVE", tmp_path / "var-lib-evidentia")
    monkeypatch.setattr(E, "backup_settings", lambda cfg=None: {})   # never the machine's own backup settings


def _write(path, data, mode, owner):
    path.write_bytes(data)
    path.chmod(mode)


class Runs(list):
    def __call__(self, cmd, check=False):
        self.append(cmd)
        if cmd[:3] == ["/usr/bin/python3", "-I", "-m"]:
            (Path(cmd[-1]) / "bin").mkdir(parents=True, exist_ok=True)


def _repo(tmp_path):
    repo = tmp_path / "repo"
    lock = repo / E.LOCK
    lock.parent.mkdir(parents=True)
    lock.write_text("numpy==2.5.3 --hash=sha256:" + "0" * 64 + "\n")
    return repo


def test_install_builds_the_venv_offline_with_hashes_and_writes_a_confined_unit(tmp_path):
    repo, root, runs = _repo(tmp_path), tmp_path / "root", Runs()
    root.mkdir()
    out = E.install(_write, repo, "owner", prefix=root, run=runs)
    pip = next(c for c in runs if "pip" in c)
    assert "--no-index" in pip and "--require-hashes" in pip and "--no-deps" in pip and "--only-binary=:all:" in pip
    assert str(repo / E.WHEELS) not in pip                             # the wheels copied into root's own folder first (A1)
    unit = (root / E.UNIT_PATH).read_text()
    for must in ("PrivateNetwork=yes", "RestrictAddressFamilies=AF_UNIX", "ProtectHome=tmpfs", "ProtectSystem=strict",
                 "NoNewPrivileges=yes", "User=evidentia", "CapabilityBoundingSet=", "/usr/local/lib/aurora/sys/evidentia/script/svc_api.py",
                 f"EVD_SOCKET={E.SOCKET}", "EVD_ROOT=/usr/local/lib/aurora", "ReadWritePaths=/var/lib/evidentia-api"):
        assert must in unit, must
    assert out["folders"]["EVD_DATA_DIR"] == str(E.ARCHIVE / "owner" / "data")   # outside Aurora's tree (A2)
    assert "/var/lib/evidentia" in (Path(__file__).resolve().parents[1] / "script" / "sys_root_evidentia.py").read_text()
    env = (root / E.ENV).read_text()
    assert "EVD_DATA_DIR=" in env and oct((root / E.ENV).stat().st_mode & 0o777) == "0o640"
    runs.clear()
    E.install(_write, repo, "owner", prefix=root, run=runs)
    assert not any("pip" in c for c in runs)                          # the same lock: the venv is not rebuilt


def test_an_earlier_installation_keeps_its_archive_and_a_reinstall_never_moves_it(tmp_path):
    repo, root = _repo(tmp_path), tmp_path / "root"
    root.mkdir()
    old = tmp_path / "old"
    old.mkdir()
    (old / ".env").write_text("EVD_DATA_DIR=sys/data\nEVD_MODELS_DIR=/m\nEVD_SOURCES_DIR=/s\n")
    out = E.install(_write, repo, "owner", prefix=root, run=Runs(), old_root=old)
    assert out["folders"]["EVD_DATA_DIR"] == str(old / "sys" / "data") and out["folders"]["EVD_MODELS_DIR"] == "/m"
    out2 = E.install(_write, repo, "owner", prefix=root, run=Runs(), old_root=None)   # the unit now points at LIB
    assert out2["folders"] == out["folders"]


def test_the_previous_installation_is_found_from_its_unit_only_when_it_is_not_roots_copy(tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    (old / ".env").write_text("x=1\n")
    unit = tmp_path / "u.service"
    unit.write_text(f"[Service]\nWorkingDirectory={old}\n")
    assert E.previous_install(unit) == old
    unit.write_text(f"[Service]\nWorkingDirectory={E.LIB}\n")
    assert E.previous_install(unit) is None
    assert E.previous_install(tmp_path / "none.service") is None


def test_uninstall_leaves_the_archive(tmp_path):
    repo, root = _repo(tmp_path), tmp_path / "root"
    root.mkdir()
    out = E.install(_write, repo, "owner", prefix=root, run=Runs())
    archive = Path(out["folders"]["EVD_DATA_DIR"])
    archive.mkdir(parents=True)
    (archive / "corpus.db").write_text("x")
    gone = E.uninstall(prefix=root, run=Runs())
    assert str(root / E.UNIT_PATH) in gone and str(root / E.ENV) in gone and not (root / E.VENV).exists()
    assert (archive / "corpus.db").exists()


def test_root_copy_and_signature_carry_evidentia():
    src = (Path(__file__).resolve().parents[1] / "script" / "sys_root.py").read_text(encoding="utf-8")
    assert '"sys_root_evidentia.py"' in src and 'rel.startswith("sys/evidentia/")' in src
    from aurora import sys_ethics
    assert "sys/evidentia/**/*" in sys_ethics.CODE_PATTERNS


def test_the_lock_comes_from_roots_signed_copy_not_from_the_repository(tmp_path):
    src = (Path(__file__).resolve().parents[1] / "script" / "sys_root_evidentia.py").read_text(encoding="utf-8")
    assert "lock = (signed or Path(LIB)) / LOCK" in src                # review A1
    assert 'v = venv(prefix, repo, run, signed=None if prefix == Path("/") else repo)' in src


def test_a_settings_file_missing_a_folder_stops_the_install(tmp_path):
    import pytest
    repo, root = _repo(tmp_path), tmp_path / "root"
    (root / "etc" / "aurora").mkdir(parents=True)
    (root / E.ENV).write_text("EVD_DATA_DIR=/a\n")
    with pytest.raises(SystemExit):
        E.install(_write, repo, "owner", prefix=root, run=Runs())


def test_a_link_is_never_followed_when_the_archive_folder_is_made(tmp_path):
    target = tmp_path / "victim"
    target.mkdir()
    link = tmp_path / "evidentia"
    link.symlink_to(target)
    import pytest
    with pytest.raises(OSError):
        E._mkdir_safe(link, -1, -1, 0o2770)
    assert oct(target.stat().st_mode & 0o7777) != "0o2770"


def test_an_earlier_installation_s_unwritten_folders_take_its_own_schema_defaults(tmp_path):
    """27 Nov, measured on the owner's: the old .env relied on its schema (sys/data, sys/models, no sources)."""
    repo, root = _repo(tmp_path), tmp_path / "root"
    root.mkdir()
    old = tmp_path / "old"
    (old / "sys" / "core" / "config").mkdir(parents=True)
    (old / "sys" / "core" / "config" / "settings_schema.json").write_text(json.dumps({"settings": [
        {"key": "EVD_DATA_DIR", "recommended": "sys/data"}, {"key": "EVD_MODELS_DIR", "recommended": "sys/models"},
        {"key": "EVD_SOURCES_DIR", "recommended": ""}]}))
    (old / ".env").write_text("EVD_GPUS=0\n")
    out = E.install(_write, repo, "owner", prefix=root, run=Runs(), old_root=old)
    assert out["folders"]["EVD_DATA_DIR"] == str(old / "sys" / "data") and out["folders"]["EVD_SOURCES_DIR"] in ("", ".")
    unit = (root / E.UNIT_PATH).read_text()
    assert f'"{old / "sys" / "data"}"' in unit and '""' not in unit.split("BindReadOnlyPaths=")[1].split("\n")[0]
    assert "EVD_SOURCES_DIR=\n" in (root / E.ENV).read_text()


def test_an_earlier_installation_whose_archive_is_unknown_stops_the_install(tmp_path):
    repo, root = _repo(tmp_path), tmp_path / "root"
    root.mkdir()
    old = tmp_path / "old"
    old.mkdir()
    (old / ".env").write_text("EVD_SOURCES_DIR=/s\n")              # no schema beside it: the archive unknown
    with pytest.raises(SystemExit):
        E.install(_write, repo, "owner", prefix=root, run=Runs(), old_root=old)
