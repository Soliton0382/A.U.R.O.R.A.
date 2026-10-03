# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Users, passwords and TOTP (RFC 6238 test vectors)."""
import pytest

from aurora import sys_users
from aurora.sys_users import Users

RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"         # base32 of "12345678901234567890"


@pytest.mark.parametrize("t,code", [(59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
                                    (1234567890, "89005924"), (2000000000, "69279037")])
def test_rfc6238_vectors(t, code):
    assert sys_users.hotp(RFC_SECRET, t // 30, digits=8) == code


def test_totp_window():
    assert sys_users.totp_step("287082", RFC_SECRET, now=59) == 1
    assert sys_users.totp_step("287082", RFC_SECRET, now=59 + 30) == 1          # one step of drift
    assert sys_users.totp_step("287082", RFC_SECRET, now=59 + 90) is None
    assert sys_users.totp_step("28708", RFC_SECRET, now=59) is None


def test_password_hash():
    h = sys_users.hash_password("correct horse")
    assert h.startswith("scrypt$") and "correct" not in h
    assert sys_users.check_password("correct horse", h)
    assert not sys_users.check_password("wrong horse", h)
    assert not sys_users.check_password("x", "garbage")


def store(tmp_path):
    return Users(cfg=object(), path=tmp_path / "users.db")


def test_one_admin_and_never_removed(tmp_path):
    u = store(tmp_path)
    a = u.add("owner", "admin", "a long password")
    with pytest.raises(ValueError):
        u.add("other", "admin")
    with pytest.raises(ValueError):
        u.remove(a["id"])
    b = u.add("guest", "user")
    with pytest.raises(ValueError):
        u.add("GUEST", "user")                                                    # names ignore case
    assert u.remove(b["id"]) and [x["name"] for x in u.list()] == ["owner"]
    assert (tmp_path / "users.db").stat().st_mode & 0o777 == 0o600


def test_login_needs_totp_and_refuses_replay(tmp_path):
    u = store(tmp_path)
    a = u.add("owner", "admin", "a long password")
    assert u.login("owner", "a long password", "", mfa=True) is None         # MFA required, not enrolled
    secret = u.totp_begin(a["id"])
    now = 1_800_000_000
    assert u.totp_confirm(a["id"], sys_users.hotp(secret, now // 30 - 1), now=now)
    code = sys_users.hotp(secret, now // 30)
    assert u.login("owner", "wrong password", code, now=now) is None
    assert u.login("owner", "a long password", code, now=now)["role"] == "admin"
    assert u.login("owner", "a long password", code, now=now) is None        # the same code twice
    assert u.login("nobody", "a long password", code, now=now) is None


def test_uri():
    uri = sys_users.otpauth_uri("ABC", "guest")
    assert uri.startswith("otpauth://totp/Aurora:guest?secret=ABC") and "period=30" in uri
