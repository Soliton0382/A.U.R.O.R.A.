# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A restore asked from the WebUI (owner, 27 Nov): the API asks the password and code again and writes one request;
root (aurora-restore → sys_restore.py --from-request) reads it strictly, once, and only if recent."""
import importlib.util
import json
import os
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _R():
    spec = importlib.util.spec_from_file_location("sys_restore", ROOT / "script" / "sys_restore.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _ask(cfg, **over):
    folder = cfg.path("AURORA_STATUS_DIR") / "backup"
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / "restore-request.json"
    f.write_text(json.dumps({"kind": "aurora", "snapshot": "20261127-230000", "parts": ["memory"], "users": ["ann"],
                             "at": time.time(), "by": "boss", **over}))
    os.chmod(f, 0o600)
    return f


def test_a_good_request_is_read_once(cfg):
    R = _R()
    f = _ask(cfg)
    r = R.read_request(cfg)
    assert r == {"kind": "aurora", "snapshot": "20261127-230000", "parts": ("memory",), "users": ("ann",), "by": "boss"}
    assert not f.exists()
    with pytest.raises(OSError):
        R.read_request(cfg)                               # never run twice


@pytest.mark.parametrize("over", [{"snapshot": "../x"}, {"kind": "root"}, {"parts": ["memory", "etc"]},
                                  {"users": ["../ann"]}, {"at": time.time() - 3600}, {"at": "now"}])
def test_anything_else_is_refused(cfg, over):
    R = _R()
    _ask(cfg, **over)
    with pytest.raises(ValueError):
        R.read_request(cfg)


def test_a_link_or_a_file_others_may_write_is_refused(cfg, tmp_path):
    R = _R()
    f = _ask(cfg)
    os.chmod(f, 0o666)
    with pytest.raises(ValueError):
        R.read_request(cfg)
    real = tmp_path / "elsewhere.json"
    real.write_text("{}")
    f = cfg.path("AURORA_STATUS_DIR") / "backup" / "restore-request.json"
    f.symlink_to(real)
    with pytest.raises(OSError):
        R.read_request(cfg)


def test_the_result_says_a_refusal_and_evidentia_goes_to_its_own_backup(cfg, tmp_path, monkeypatch):
    R = _R()
    monkeypatch.setattr(R, "RESULT", tmp_path / "result.json")
    _ask(cfg, snapshot="bad name")
    assert R.from_request(cfg) == 1 and json.loads((tmp_path / "result.json").read_text())["ok"] is False
    seen = []
    monkeypatch.setattr(R, "evidentia", lambda s, users=(): seen.append(s) or {"files": 3, "aside": "/a"})
    _ask(cfg, kind="evidentia", parts=[], users=[])
    assert R.from_request(cfg) == 0 and seen == ["20261127-230000"]
    assert json.loads((tmp_path / "result.json").read_text())["ok"] is True


def test_the_page_s_route_asks_the_password_again_and_the_unit_is_root_s_restore():
    src = (ROOT / "aurora" / "api" / "backup.py").read_text(encoding="utf-8")
    body = src[src.index("async def restore_ask"):]
    assert body.index("confirm_again(request, body)") < body.index("restore-request.tmp")
    assert "Depends(admin_only)" in src[src.index('@router.post("/v1/aurora/backup/restore"'):][:120]
    gen = (ROOT / "script" / "sys_install_services.py").read_text(encoding="utf-8")
    assert '"aurora-restore.service"' in gen and "--from-request" in gen
    root = (ROOT / "script" / "sys_root.py").read_text(encoding="utf-8")
    assert '"aurora-restore.service": "sys_restore.py"' in root
