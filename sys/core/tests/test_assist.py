# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🛟 Assistance (sys_assist; owner, 29 Oct: «Accesso completo come Exchange… il consenso è implicito all'atto di
attivazione»): the user opens a window, the admin enters only inside it and never reaches the account's keys; every
step in the user's log, the user told when it begins and ends. Made-up users."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from aurora import sys_assist as S

HERE = Path(__file__).resolve().parent
WINDOWS = {k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ}


def test_a_window_is_one_of_the_hours_offered_and_ends_by_itself(cfg):
    with pytest.raises(ValueError):
        S.grant(cfg, "ada", 5)
    g = S.grant(cfg, "ada", 8, now=1000.0)
    assert g["until"] == 1000.0 + 8 * 3600 and S.granted(cfg, "ada", now=2000.0)
    with pytest.raises(PermissionError):
        S.enter(cfg, "dev1", "bob", now=2000.0)                               # bob opened nothing
    S.enter(cfg, "dev1", "ada", now=2000.0)
    assert S.acting(cfg, "dev1", now=2000.0)["user"] == "ada" and S.acting(cfg, "dev2", now=2000.0) is None
    assert S.acting(cfg, "dev1", now=g["until"] + 1) is None                  # over at its time, even before the tick
    assert S.expire(cfg, now=g["until"] + 1) == [{"user": "ada", "inside": True}]
    assert not S.granted(cfg, "ada") and S.acting(cfg, "dev1") is None


def test_the_account_s_keys_are_never_reached():
    for p in ("/v1/aurora/me/password", "/v1/aurora/me/totp", "/v1/aurora/me/keys/k1", "/v1/aurora/devices/d1",
              "/v1/aurora/logout", "/v1/aurora/assist/grant", "/v1/aurora/assist/revoke", "/v1/aurora/me/welcomed"):
        assert not S.allowed(p), p
    for p in ("/v1/aurora/me", "/v1/aurora/me/prefs", "/v1/aurora/calendar/items", "/v1/aurora/assist/leave",
              "/v1/aurora/devicesx"):
        assert S.allowed(p), p


def test_the_log_is_sealed_and_a_page_polled_is_one_step(cfg):
    from aurora import sys_user_config
    u = sys_user_config.for_user(cfg, "ada")
    assert S.step(u, "boss", "GET", "/v1/aurora/calendar", now=10.0)
    assert not S.step(u, "boss", "GET", "/v1/aurora/calendar", now=30.0)    # polled again: not a new step
    assert S.step(u, "boss", "POST", "/v1/aurora/calendar/items", now=31.0)
    assert S.step(u, "boss", "GET", "/v1/aurora/calendar", now=100.0)
    assert [s["what"] for s in S.log(u)] == ["GET", "POST", "GET"]
    assert "calendar" not in S._log_file(u).read_text()


def test_the_admin_inside_a_user_s_account(cfg):
    r = subprocess.run([sys.executable, str(HERE / "api_assist.py"), str(cfg.root)], capture_output=True, text=True,
                       timeout=180, env={**WINDOWS, "PATH": "/usr/bin:/bin", "AURORA_ENV_FILE": str(cfg.env_file)})
    assert r.returncode == 0, r.stderr[-3000:]
    o = json.loads(r.stdout.strip().splitlines()[-1])
    assert o["enter_closed"] == 403 and o["grant_bad"] == 422 and o["grant_admin"] == 422 and o["grant"] == 200
    assert o["listed"] and o["guest_enters"] == 403 and o["key_enters"] == 422 and o["enter"] == 200
    assert o["inside_me"] == ["guest", False, "boss"] and o["inside_key"] == "boss"
    assert o["inside_users_page"] == 403                                      # inside, not the admin's pages
    assert set(o["refused"].values()) == {403}, o["refused"]
    assert o["guest_sees_inside"] is True
    assert o["leave"] == {"left": True} and o["after_me"] == "boss"
    assert o["revoke"] == {"revoked": True} and o["after_revoke_me"] == "boss"
    assert o["expired_me"] == "boss" and o["expired_dropped"]
    assert o["log"][0] == "grant" and o["log"].count("enter") == 3 and o["log"].count("end") == 3
    assert "/v1/aurora/me" in o["log_paths"]
    assert o["told"] == ["assist.begin", "assist.end"] * 3 and o["boss_told"] == []
