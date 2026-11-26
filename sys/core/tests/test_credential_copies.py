# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N167 (owner, 27 Nov: «togli le mie credenziali e token dagli altri utenti»): a credential of the admin's found, the
same value, in another user's settings is found by name and emptied; a user's own different value never touched."""
from aurora import sys_user_config as U


def test_the_admin_s_copies_are_found_and_cleared_only_those(cfg, monkeypatch):
    envs = {"boss": {"AURORA_TELEGRAM_BOT_TOKEN": "t-boss", "AURORA_EMAIL_PASSWORD": "p-boss", "AURORA_OWNER_NAME": "Boss"},
            "ann": {"AURORA_TELEGRAM_BOT_TOKEN": "t-boss", "AURORA_EMAIL_PASSWORD": "p-ann", "AURORA_OWNER_NAME": "Boss"},
            "bob": {"AURORA_TELEGRAM_BOT_TOKEN": ""}}
    written = {}
    monkeypatch.setattr(U, "_own", lambda c, n: dict(envs.get(n, {})))
    monkeypatch.setattr(U.L, "_registered", lambda c: set(envs))
    monkeypatch.setattr(U, "user_keys", lambda c: ["AURORA_TELEGRAM_BOT_TOKEN", "AURORA_EMAIL_PASSWORD", "AURORA_OWNER_NAME"])
    monkeypatch.setattr(U.sys_config, "write_env", lambda f, ch, **k: written.setdefault(f.parent.name, {}).update(ch))
    assert U.copies(cfg, "boss") == {"ann": ["AURORA_TELEGRAM_BOT_TOKEN"]}      # a name is not a credential; ann's own password kept
    assert U.clear_copies(cfg, "boss") == {"ann": ["AURORA_TELEGRAM_BOT_TOKEN"]}
    assert written == {"ann": {"AURORA_TELEGRAM_BOT_TOKEN": ""}}
