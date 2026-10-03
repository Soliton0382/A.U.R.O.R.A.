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


def test_multi_is_refused_until_the_login_exists(cfg, monkeypatch):
    with pytest.raises(M.ModeError, match="per-user layout"):
        M.switch(cfg, "multi", None, None)
    setup(cfg)
    with pytest.raises(M.ModeError, match="U5"):
        M.switch(cfg, "multi", "boss", "boss")
    monkeypatch.setattr(M, "MULTI_READY", True)
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
