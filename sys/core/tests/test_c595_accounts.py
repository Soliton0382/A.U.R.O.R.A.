# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C595 (security audit of 12 Nov, area A — accounts and API): what a user could do beyond the admin's policy, and
what a stranger could have the API keep. Made-up users and addresses."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from aurora import ast_advice, sys_routine_templates as T, sys_routines, sys_user_config, sys_users_layout as L
from aurora.sys_csrf import foreign
from aurora.sys_devices import Devices
from aurora.sys_replay import MAX_KEPT, Replay

HERE = Path(__file__).resolve().parent
WINDOWS = {k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ}
sys.path.insert(0, str(HERE.parent / "script"))


@pytest.fixture(scope="module")
def o(tmp_path_factory):
    from conftest import write_env
    root = tmp_path_factory.mktemp("c595")
    env = write_env(root, AURORA_USER_MODE="multi", AURORA_AUTH_MAX_FAILS="3")
    r = subprocess.run([sys.executable, str(HERE / "api_c595.py"), str(root)], capture_output=True, text=True,
                       timeout=300, env={**WINDOWS, "PATH": "/usr/bin:/bin", "AURORA_ENV_FILE": str(env)})
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


# ---- A1: the admin's saved set never gives a user the firewall's restart -----------------------------------------
def test_a_saved_set_never_gives_a_user_the_firewall_restart(cfg):
    sys_routines.create(cfg, {"kind": "firewall", "title": "Riavvio firewall",
                              "schedule": {"every": "week", "weekday": 0, "at": "04:00"}})
    T.save_mine(cfg, "miei", "boss")
    pack = T.saved(cfg)[0]
    assert [r.get("admin") for r in pack["routines"]] == [True]
    for r in sys_routines.all_routines(cfg):
        sys_routines.delete(cfg, r["id"])
    assert [p["items"] for p in T.view(cfg, "it", set(), False, "guest") if p["id"] == pack["id"]] == [[]]
    assert T.apply(cfg, pack["id"], "it", set(), False) == {"created": [], "skipped": []}
    assert sys_routines.all_routines(cfg) == []
    assert T.apply(cfg, pack["id"], "it", set(), True)["created"] == ["Riavvio firewall"]       # the admin still may


def test_a_set_saved_before_the_fix_is_judged_by_what_its_routines_are(cfg):
    d = T._dir(cfg)
    d.mkdir(parents=True)
    spec = {"kind": "firewall", "title": "Riavvio", "schedule": {"every": "week", "weekday": 0, "at": "04:00"}}
    (d / "mine-old.json").write_text(json.dumps({"id": "mine-old", "title": {"it": "old"}, "saved_by": "boss",
                                                 "routines": [spec]}))                         # no "admin" flag kept
    assert T.apply(cfg, "mine-old", "it", set(), False)["created"] == []
    assert T.admin_only({"kind": "story"}) and T.admin_only({"kind": "tool", "plugin": "backup"})
    assert not T.admin_only({"kind": "agent", "plugins": ["web"]})


# ---- A4: the replay cache keeps work done, not refusals; and it has a ceiling ------------------------------------
def _app(status: int):
    async def app(scope, receive, send):
        body = b'{"detail":"x"}'
        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})
    return app


async def _post(r: Replay, i: int) -> None:
    scope = {"type": "http", "method": "POST", "path": "/v1/aurora/ask",
             "headers": [(b"authorization", b"Bearer x"), (b"x-aurora-request", b"k%011d" % i), (b"content-length", b"0")]}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(m):
        pass
    await r(scope, receive, send)


def test_a_refusal_is_not_kept_and_the_kept_answers_have_a_ceiling():
    async def run():
        refused = Replay(_app(401))
        for i in range(50):
            await _post(refused, i)
        await asyncio.sleep(0)
        done = Replay(_app(200))
        for i in range(MAX_KEPT + 50):
            await _post(done, i)
        await asyncio.sleep(0)
        return len(refused.done), len(done.done), done.bytes
    refused, kept, size = asyncio.run(run())
    assert refused == 0 and kept == MAX_KEPT and size == MAX_KEPT * len(b'{"detail":"x"}')


def test_expired_answers_leave_from_the_front(monkeypatch):
    import aurora.sys_replay as R
    r = Replay(_app(200))
    r._keep(("w", b"a", "POST", "/"), {"status": 200}, b"12345")
    r._keep(("w", b"b", "POST", "/"), {"status": 200}, b"12")
    now = R.time.time()
    monkeypatch.setattr(R.time, "time", lambda: now + R.TTL + 1)
    r._expire()
    assert r.done == {} and r.bytes == 0


# ---- A5: devices made with the installation's key go with the admin's -------------------------------------------
def test_devices_with_no_user_are_revoked_with_the_admins(cfg):
    d = Devices(cfg)
    _, by_key = d.register("made with the key", "ua")
    _, boss = d.register("boss phone", "ua", user="boss")
    _, guest = d.register("guest phone", "ua", user="guest")
    assert d.revoke_user("guest", unowned=False) == 1 and len(d.list()) == 2          # a user's reset: theirs only
    assert d.revoke_user("boss", keep=boss["id"], unowned=True) == 1
    assert [x["id"] for x in d.list()] == [boss["id"]]


# ---- A2: only the admin's frames share is mounted ----------------------------------------------------------------
def test_only_the_admins_frames_share_is_mounted(cfg, tmp_path, monkeypatch):
    import sys_nas_mount as N
    from aurora.sys_users import Users
    monkeypatch.setattr(L, "usr", lambda c: tmp_path)
    for name in ("boss", "guest"):
        (tmp_path / name).mkdir()
    (tmp_path / "guest" / ".env").write_text("AURORA_ASTRO_FRAMES_DIR=smb://198.51.100.9/anything\n")
    cfg.values["AURORA_ASTRO_FRAMES_DIR"] = ""
    assert N.admin_name(cfg) == ""                                                      # no users' store: nobody's
    Users(cfg).add("boss", "admin", "a long password of the boss")
    Users(cfg).add("guest", "user", "a long password of the guest")
    before = (cfg.path("AURORA_STATUS_DIR") / "users.db").stat().st_mtime_ns
    assert N.admin_name(cfg) == "boss" and N.astro_url(cfg) == ""                       # the guest's: never
    (tmp_path / "boss" / ".env").write_text("AURORA_ASTRO_FRAMES_DIR=smb://192.168.1.20/astro\n")
    assert N.astro_url(cfg) == "smb://192.168.1.20/astro"
    assert (cfg.path("AURORA_STATUS_DIR") / "users.db").stat().st_mtime_ns == before    # read, never written (root)


# ---- A3: the telescope's PC ---------------------------------------------------------------------------------------
def test_a_users_telescope_pc_is_never_the_house_or_this_machine(cfg, tmp_path, monkeypatch):
    (cfg.path("AURORA_STATUS_DIR")).mkdir(parents=True, exist_ok=True)
    (cfg.path("AURORA_STATUS_DIR") / "users_layout.json").write_text(json.dumps({"layout": 1, "admin": "boss"}))
    for name in ("boss", "guest"):
        L.make_home(cfg, name)
    host = lambda who: ast_advice.telescope_host(sys_user_config.for_user(cfg, who), {})   # noqa: E731
    sys_user_config.write(cfg, "guest", {"AURORA_ASTRO_PC": "127.0.0.1:22"})
    assert host("guest")[0] == ""
    sys_user_config.write(cfg, "guest", {"AURORA_ASTRO_PC": "192.168.1.9:4400"})
    assert host("guest")[0] == ""
    assert ast_advice.telescope_host(sys_user_config.for_user(cfg, "guest"),
                                     {"links": {"addresses": ["127.0.0.1/8"]}})[0] == ""  # nor from their inventory
    sys_user_config.write(cfg, "boss", {"AURORA_ASTRO_PC": "192.168.1.9"})
    assert host("boss") == ("192.168.1.9", 4400)                                         # the admin: as before
    assert host("guest") == ("192.168.1.9", 4400)                                        # the admin's too: allowed
    sys_user_config.write(cfg, "guest", {"AURORA_ASTRO_PC": "192.168.1.9:22"})
    assert host("guest")[0] == ""                                                        # another port of it: not


def test_the_api_refuses_a_users_house_address_for_the_telescope(o):
    assert o["astro_pc"] == [422, 422, 422, 200]
    assert o["astro_pc_admin"] == 200 and o["astro_pc_same_as_admin"] == 200


# ---- A6, A7, A8, A9 through the API -------------------------------------------------------------------------------
def test_the_routines_permission_holds_for_sets_and_advice(o):
    assert o["apply_kept"] == [403, 403] and o["apply_allowed"] == [404, 404]


def test_a_users_autonomy_is_not_set_through_the_settings(o):
    assert o["autonomy_kept"] == 403 and o["autonomy_allowed"] == 200


def test_the_factory_state_and_the_services_details_are_the_admins(o):
    assert o["factory"] == [403, 200]
    assert o["status_guest_keys"] == ["status"] and o["status_boss_has_more"]


def test_wrong_logins_are_counted_per_account_too(o):
    assert o["guesses"] == [401]                         # twelve addresses, one guess each: none of them refused
    assert o["thirteenth_elsewhere"] == 429              # the account is: no more guesses from outside
    assert o["right_password_from_outside"] == 429
    assert o["right_password_at_home"] == 200            # the house's own network is never kept out by strangers


def test_the_same_name_over_plain_http_is_another_site():
    host = {"host": "aurora.example", "x-forwarded-proto": "https"}
    cookie = {"aurora_device": "x"}
    assert foreign("POST", {**host, "origin": "http://aurora.example"}, cookie)
    assert not foreign("POST", {**host, "origin": "https://aurora.example"}, cookie)
    assert not foreign("POST", {"host": "127.0.0.1:9700", "origin": "http://127.0.0.1:9700"}, cookie)   # no proxy: as before
