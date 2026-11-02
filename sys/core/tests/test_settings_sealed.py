# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔐 N69 (C463): the secrets of an .env sealed with Aurora's key, opened for her services, empty for anyone else."""
from aurora import sys_config as C


def _env(cfg, **kw):
    C.write_env(cfg.env_file, kw)
    return C.load(cfg.env_file, check_root=False)


def test_sealed_secrets_open_for_her_and_stay_out_of_the_file(cfg, monkeypatch):
    c = _env(cfg, AURORA_GITHUB_TOKEN="ghp_visible", AURORA_NAS_USER="someone")
    assert C.seal_env(c, c.env_file) >= 1
    text = c.env_file.read_text()
    assert "ghp_visible" not in text and "AURORA_GITHUB_TOKEN=aurseal1:" in text and "AURORA_NAS_USER=someone" in text
    back = C.load(c.env_file, check_root=False)
    assert back["AURORA_GITHUB_TOKEN"] == "ghp_visible" and back.raw["AURORA_GITHUB_TOKEN"] == "ghp_visible" and not back.locked
    assert C.seal_env(back, back.env_file) == 0                                  # once
    monkeypatch.setattr(C, "get", lambda: back)                                  # a new one in a sealed file: sealed
    C.write_env(back.env_file, {"AURORA_GITHUB_TOKEN": "ghp_new"})
    assert "ghp_new" not in back.env_file.read_text()
    assert C.load(back.env_file, check_root=False)["AURORA_GITHUB_TOKEN"] == "ghp_new"
    assert C.seal_env(back, back.env_file, seal=False) >= 1                      # and back
    assert "AURORA_GITHUB_TOKEN=ghp_new" in back.env_file.read_text()


def test_a_process_with_no_key_gets_them_empty_and_the_scripts_their_own_key(cfg, monkeypatch, tmp_path):
    c = _env(cfg, AURORA_GITHUB_TOKEN="ghp_visible")
    C.seal_env(c, c.env_file)
    C._opened.clear()
    from aurora import sys_seal

    def locked(*a, **k):
        raise RuntimeError("no key here")
    monkeypatch.setattr(sys_seal, "open_text", locked)
    key = tmp_path / "maintenance.key"
    key.write_text("for-the-scripts\n")
    monkeypatch.setattr(C, "MAINTENANCE_KEY", key)
    other = C.load(c.env_file, check_root=False)
    assert other.locked and other["AURORA_GITHUB_TOKEN"] == "" and "ghp_visible" not in str(other.raw)
    assert other["AURORA_API_KEY"] == "for-the-scripts"


def test_a_process_with_no_key_and_no_maintenance_key_still_loads(cfg, monkeypatch, tmp_path):
    """Root's mount found it: the API key is a required secret, and empty it made the whole settings fail to load."""
    C.seal_env(cfg, cfg.env_file)
    C._opened.clear()
    from aurora import sys_seal

    def locked(*a, **k):
        raise RuntimeError("no key here")
    monkeypatch.setattr(sys_seal, "open_text", locked)
    monkeypatch.setattr(C, "MAINTENANCE_KEY", tmp_path / "none")
    root = C.load(cfg.env_file, check_root=False)
    assert root.locked and root["AURORA_API_KEY"] == ""


def test_the_nas_password_is_never_lost_by_a_mount_with_no_key(tmp_path):
    """Root's unit opens nothing: it keeps the credentials file, or takes the password the API handed over, once."""
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
    import sys_nas_mount as N
    f = tmp_path / "nas_pass.json"
    f.write_text(json.dumps({"AURORA_NAS_PASSWORD": "new"}))
    assert N.taken(tmp_path) == {"AURORA_NAS_PASSWORD": "new"} and not f.exists() and N.taken(tmp_path) == {}
    src = (Path(__file__).resolve().parents[1] / "script" / "sys_nas_mount.py").read_text()
    assert "cfg.locked and cred_file.is_file()" in src


def test_the_maintenance_key_works_from_this_machine_only():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "aurora" / "api" / "core.py").read_text()
    assert 'request.client.host in ("127.0.0.1", "::1")' in src and '"x-forwarded-for" not in request.headers' in src
