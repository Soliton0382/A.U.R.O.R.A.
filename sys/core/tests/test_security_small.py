# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The small ones of the security review (28 Oct): a .docx whose text unpacks to more than 64 MB is not read whole
(C433); an unknown login name costs one scrypt like a known one, the dummy hash made once (C432)."""
import io
import zipfile

import pytest

from aurora import kno_ingest, sys_users


def test_a_docx_bomb_is_not_read_whole():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"<a>" + b"0" * (65 * 1024 * 1024) + b"</a>")
    assert len(buf.getvalue()) < 2 * 1024 * 1024                         # small on disk, huge unpacked
    with pytest.raises(ValueError, match="64 MB"):
        kno_ingest._office_text("bomb.docx", buf.getvalue(), "docx")


def test_an_unknown_name_costs_one_hash_made_once(monkeypatch):
    made = []
    real = sys_users.hash_password
    monkeypatch.setattr(sys_users, "hash_password", lambda pw: made.append(1) or real(pw))
    sys_users._DUMMY.clear()
    a, b = sys_users._dummy(), sys_users._dummy()
    assert a == b and len(made) == 1


def test_a_session_unused_too_long_ends_on_the_server(cfg):
    """C437: a device unused for longer than AURORA_DEVICE_DAYS is refused, whatever its cookie still says."""
    import time as _t
    from aurora.sys_devices import Devices
    cfg.values["AURORA_DEVICE_DAYS"] = 30
    d = Devices(cfg)
    token, rec = d.register("phone", "ua", user="anna")
    assert d.check(token)
    items = d._load()
    items[0]["last_seen"] = _t.strftime("%Y-%m-%dT%H:%M:%S", _t.localtime(_t.time() - 31 * 86400))
    d._save(items)
    assert d.check(token) is None
