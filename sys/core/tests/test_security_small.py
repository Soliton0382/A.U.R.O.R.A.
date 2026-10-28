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


def test_changing_an_active_authenticator_keeps_the_old_one_until_the_new_is_confirmed(cfg):
    """C440: a re-enrolment left half done kept the old authenticator in force; the new one only with its code."""
    from aurora import sys_users as U
    users = U.Users(cfg)
    users.add("anna", "user", "a long password")
    uid = users.by_name("anna")["id"]
    first = users.totp_begin(uid)
    assert users.totp_confirm(uid, U.totp_now(first) if hasattr(U, "totp_now") else _code(U, first))
    second = users.totp_begin(uid)                                                   # a change begun, not finished
    with users._db() as con:
        assert con.execute("SELECT totp FROM users WHERE id=?", (uid,)).fetchone()["totp"] == first
    assert users.totp_confirm(uid, _code(U, second))
    with users._db() as con:
        assert con.execute("SELECT totp FROM users WHERE id=?", (uid,)).fetchone()["totp"] == second


def _code(U, secret, at=None):
    import base64, hashlib, hmac, struct, time
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    msg = struct.pack(">Q", int((at or time.time()) // 30))
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[-1] & 15
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7fffffff) % 1000000:06d}"
