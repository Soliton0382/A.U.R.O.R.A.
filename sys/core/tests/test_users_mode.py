# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Single ↔ multi: never a multi-user without login; back to single only after the list and a confirmation."""
import json

import pytest

from aurora import sys_users_layout as L
from aurora import sys_users_mode as M
from aurora.sys_users import Users


def setup(cfg):
    cfg.path("AURORA_STATUS_DIR").mkdir(parents=True, exist_ok=True)
    (cfg.path("AURORA_STATUS_DIR") / L.STATE).write_text(json.dumps({"layout": 1, "admin": "boss"}))
    users = Users(cfg)
    users.add("boss", "admin")
    return users


def test_multi_needs_the_layout_and_the_admin_s_password_and_code(cfg):
    from aurora import sys_users
    with pytest.raises(M.ModeError, match="per-user layout"):
        M.switch(cfg, "multi", None, None)
    users = setup(cfg)
    with pytest.raises(M.ModeError, match="password"):                  # the admin would be locked out
        M.switch(cfg, "multi", "boss", "boss")
    boss = users.by_name("boss")
    users.set_password(boss["id"], "a long password")
    with pytest.raises(M.ModeError, match="Authenticator"):
        M.switch(cfg, "multi", "boss", "boss")
    secret = users.totp_begin(boss["id"])
    assert users.totp_confirm(boss["id"], sys_users.hotp(secret, int(__import__("time").time()) // 30))
    assert M.switch(cfg, "multi", "boss", "boss") == {"removed": []}
    with pytest.raises(M.ModeError, match="only the admin"):
        M.switch(cfg, "multi", "guest", "boss")


def test_back_to_single_lists_then_purges_only_when_confirmed(cfg):
    users = setup(cfg)
    users.add("guest", "user")
    (cfg.root / "usr" / "guest" / "notes").mkdir(parents=True)
    (cfg.root / "usr" / "guest" / "notes" / "n.md").write_text("guest")
    with pytest.raises(M.ModeError) as e:
        M.switch(cfg, "single", "boss", "boss")
    assert "guest" in str(e.value) and e.value.plan[0]["user"] == "guest"
    assert (cfg.root / "usr" / "guest").exists()                      # nothing removed without the confirmation
    assert M.switch(cfg, "single", "boss", "boss", confirm=True) == {"removed": ["guest"]}
    assert not (cfg.root / "usr" / "guest").exists() and [u["name"] for u in users.list()] == ["boss"]
