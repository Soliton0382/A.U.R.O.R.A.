# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The people who use Aurora: one admin always, other users only in multi-user mode.

    <AURORA_STATUS_DIR>/users.db        SQLite, mode 600, schema versioned in `meta`

A user logs in with name, password and a TOTP code (RFC 6238, the 6 digits of Google
Authenticator). The password is kept only as a scrypt hash, the TOTP secret only here. Single-user mode is
the same table with the admin alone: going back from multi to single removes every other user with all that
is theirs (sys_users_mode), so the two modes never leave traces of each other.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import struct
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from . import sys_config

SCHEMA = 1
DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    password TEXT NOT NULL,                 -- scrypt$n$r$p$salt$hash, '' until the first password is set
    totp TEXT NOT NULL DEFAULT '',          -- base32 secret, '' when not enrolled
    totp_on INTEGER NOT NULL DEFAULT 0,     -- 1 after the first correct code
    totp_last INTEGER NOT NULL DEFAULT 0,   -- last accepted time step: a code is never accepted twice
    created TEXT NOT NULL
);
"""
ROLES = ("admin", "user")
STEP, DIGITS, WINDOW = 30, 6, 1             # RFC 6238 defaults; one step of clock drift either way
SCRYPT = (2 ** 14, 8, 1)


# ---- TOTP (RFC 4226 / 6238) ----------------------------------------------------------------------
def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def hotp(secret: str, counter: int, digits: int = DIGITS, algo: str = "sha1") -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", counter), algo).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 10 ** digits
    return str(code).zfill(digits)


def totp_step(code: str, secret: str, now: float | None = None) -> int | None:
    """The time step a code belongs to (within WINDOW), or None."""
    code = "".join(c for c in str(code) if c.isdigit())
    if len(code) != DIGITS or not secret:
        return None
    t = int((time.time() if now is None else now) // STEP)
    for s in range(t - WINDOW, t + WINDOW + 1):
        if hmac.compare_digest(hotp(secret, s), code):
            return s
    return None


def otpauth_uri(secret: str, user: str, issuer: str = "Aurora") -> str:
    """What the authenticator app reads from the QR code."""
    return (f"otpauth://totp/{quote(issuer)}:{quote(user)}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP}")


# ---- passwords -----------------------------------------------------------------------------------
def hash_password(pw: str) -> str:
    n, r, p = SCRYPT
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${salt.hex()}${h.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got.hex(), h)


# ---- the store -----------------------------------------------------------------------------------
class Users:
    def __init__(self, cfg: sys_config.Config | None = None, path: Path | None = None):
        self.cfg = cfg or sys_config.get()
        self.path = path or self.cfg.path("AURORA_STATUS_DIR") / "users.db"

    @contextmanager
    def _db(self):
        new = not self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            if new:
                os.chmod(self.path, 0o600)
            con.executescript(DDL)
            v = con.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            if v is None:
                con.execute("INSERT INTO meta VALUES ('schema', ?)", (str(SCHEMA),))
            elif int(v[0]) > SCHEMA:
                raise RuntimeError(f"users.db schema {v[0]} is newer than this code ({SCHEMA})")
            yield con
            con.commit()
        finally:
            con.close()

    @staticmethod
    def public(row) -> dict:
        return {"id": row["id"], "name": row["name"], "role": row["role"], "totp_on": bool(row["totp_on"]),
                "has_password": bool(row["password"]), "created": row["created"]}

    def list(self) -> list[dict]:
        with self._db() as con:
            return [self.public(r) for r in con.execute("SELECT * FROM users ORDER BY role, created")]

    def get(self, uid: str) -> dict | None:
        with self._db() as con:
            r = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return self.public(r) if r else None

    def admin_name(self) -> str | None:
        """The admin's name (the key of the per-user folders) without creating the store: None while there are no users."""
        if not self.path.exists():
            return None
        a = self.admin()
        return a["name"] if a else None

    def admin(self) -> dict | None:
        with self._db() as con:
            r = con.execute("SELECT * FROM users WHERE role='admin' ORDER BY created LIMIT 1").fetchone()
        return self.public(r) if r else None

    def add(self, name: str, role: str = "user", password: str = "") -> dict:
        name = name.strip()
        if not name or len(name) > 40 or not all(c.isalnum() or c in "._-" for c in name):
            raise ValueError("name: 1-40 letters, digits, . _ -")
        if role not in ROLES:
            raise ValueError(f"role: one of {ROLES}")
        if password and len(password) < 10:
            raise ValueError("password: at least 10 characters")
        uid = uuid.uuid4().hex[:12]
        with self._db() as con:
            if role == "admin" and con.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
                raise ValueError("there is already an admin")
            try:
                con.execute("INSERT INTO users (id, name, role, password, created) VALUES (?,?,?,?,?)",
                            (uid, name, role, hash_password(password) if password else "",
                             time.strftime("%Y-%m-%dT%H:%M:%S")))
            except sqlite3.IntegrityError:
                raise ValueError(f"user {name} exists") from None
        return self.get(uid)

    def remove(self, uid: str) -> bool:
        """The record only: the data of the user is removed by sys_users_mode.purge, which calls this last."""
        with self._db() as con:
            r = con.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
            if r is None:
                return False
            if r["role"] == "admin":
                raise ValueError("the admin cannot be removed")
            con.execute("DELETE FROM users WHERE id=?", (uid,))
        return True

    def set_password(self, uid: str, password: str) -> None:
        if len(password) < 10:
            raise ValueError("password: at least 10 characters")
        with self._db() as con:
            con.execute("UPDATE users SET password=? WHERE id=?", (hash_password(password), uid))

    def totp_begin(self, uid: str) -> str:
        """A new secret, not active until confirmed with a code (an enrolment that fails leaves the old one)."""
        secret = new_secret()
        with self._db() as con:
            con.execute("UPDATE users SET totp=?, totp_on=0, totp_last=0 WHERE id=?", (secret, uid))
        return secret

    def totp_confirm(self, uid: str, code: str, now: float | None = None) -> bool:
        with self._db() as con:
            r = con.execute("SELECT totp FROM users WHERE id=?", (uid,)).fetchone()
            step = totp_step(code, r["totp"], now) if r else None
            if step is None:
                return False
            con.execute("UPDATE users SET totp_on=1, totp_last=? WHERE id=?", (step, uid))
        return True

    def check_password(self, name: str, password: str) -> dict | None:
        """The user if the password is right (the first step of a login, and of the first TOTP enrolment)."""
        with self._db() as con:
            r = con.execute("SELECT * FROM users WHERE name=?", (name.strip(),)).fetchone()
        if r is None or not r["password"]:
            check_password(password, hash_password("x" * 10))       # same time as a wrong password
            return None
        return {**self.public(r), "totp": r["totp"]} if check_password(password, r["password"]) else None

    def by_name(self, name: str) -> dict | None:
        with self._db() as con:
            r = con.execute("SELECT * FROM users WHERE name=?", (name.strip(),)).fetchone()
        return self.public(r) if r else None

    def totp_reset(self, uid: str) -> None:
        """The admin resets a lost authenticator: the next login asks to enrol again."""
        with self._db() as con:
            con.execute("UPDATE users SET totp='', totp_on=0, totp_last=0 WHERE id=?", (uid,))

    def login(self, name: str, password: str, code: str, mfa: bool = True, now: float | None = None) -> dict | None:
        """The user if name, password and (when MFA is required or enrolled) the TOTP code are right.
        A code already used cannot be used again (replay inside its 30 seconds)."""
        with self._db() as con:
            r = con.execute("SELECT * FROM users WHERE name=?", (name.strip(),)).fetchone()
            if r is None or not r["password"]:
                check_password(password, hash_password("x" * 10))       # same time as a wrong password
                return None
            if not check_password(password, r["password"]):
                return None
            if mfa or r["totp_on"]:
                if not r["totp_on"]:
                    return None
                step = totp_step(code, r["totp"], now)
                if step is None or step <= r["totp_last"]:
                    return None
                con.execute("UPDATE users SET totp_last=? WHERE id=?", (step, r["id"]))
        return self.public(r)
