# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C535 (security audit of 9 Nov), the API and the accounts: a body counted before anyone reads it, live streams
that ask again who their caller is, the assistance as a list of what may change, a changed address that forgets its
secret, a user's own address never one of the house's. Made-up users (api_guard.py)."""
import asyncio

import httpx
import pytest
from fastapi import FastAPI, Request

from aurora import net_https, sys_assist as S
from aurora.sys_bodylimit import ANON, CAP, BodyLimit
from test_c570_accounts import guard


@pytest.fixture(scope="module")
def o(tmp_path_factory):
    return guard(tmp_path_factory.mktemp("c535"), "c535")


def _app(cap):
    app = FastAPI()
    app.state.read = []

    @app.post("/take")
    async def take(request: Request):
        n = 0
        async for piece in request.stream():
            n += len(piece)
            app.state.read.append(n)
        return {"bytes": n}

    app.add_middleware(BodyLimit, cap=cap, anon=1000)
    return app


def _post(app, **k):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://a") as c:
            return await c.post("/take", **k)
    return asyncio.run(go())


def _pieces(n: int, size: int = 500):
    async def gen():
        for _ in range(n):
            yield b"z" * size
    return gen()


def test_a_stranger_s_body_is_refused_before_it_is_read():
    asked = []
    app = _app(lambda path, headers: asked.append(path) or 0)
    assert _post(app, content=b"z" * 900).json() == {"bytes": 900} and asked == []    # small: nobody is asked who
    r = _post(app, content=b"z" * 5000)
    assert r.status_code == 413 and asked == ["/take"] and max(app.state.read) == 900  # refused on its declared length


def test_the_bytes_are_counted_whatever_the_length_said():
    app = _app(lambda path, headers: 0)
    r = _post(app, content=_pieces(20))                                               # no length declared: 10 000 bytes
    assert r.status_code == 413 and max(app.state.read) <= 1000                       # the route never got past the ceiling
    known = _app(lambda path, headers: 4000)
    assert _post(known, content=_pieces(6)).json() == {"bytes": 3000}
    assert _post(known, content=_pieces(20)).status_code == 413


def test_an_endless_stream_of_a_known_sender_is_left_to_its_route():
    app = _app(lambda path, headers: None)
    assert _post(app, content=_pieces(40)).json() == {"bytes": 20000}


def test_the_api_holds_the_ceiling_for_strangers_and_known_callers(o):
    assert o["stranger_declared"] == 413 and o["stranger_counted"] == 413 and o["stranger_small"] == 401
    assert o["wrong_cookie"] == 413 and o["known_large"] == 200
    assert o["caps"] == [0, 0, True, True, 0] and o["camera_stream"] is None
    assert ANON < CAP


def test_caddy_holds_the_same_ceiling_in_front(cfg):
    text = net_https.render(cfg, AURORA_TLS_MODE="internal")
    assert f"max_size {CAP // 2**20}MiB" in text
    assert "@bounded not path /v1/aurora/astro/camera/push" in text                   # the camera's endless POST


def test_a_live_stream_ends_when_its_caller_s_right_is_over(o):
    assert o["stream_kept"] == 50                                                     # nothing changed: all of it
    assert o["stream_revoked"] == [1, 2]                                              # the device revoked at the second item
    assert o["inside_is"] == "guest" and o["stream_assist_ended"] == [1, 2]           # the assistance closed by the user


def test_the_assistance_changes_only_what_is_on_its_list(monkeypatch):
    for method, path in (("GET", "/v1/aurora/me/keys"), ("POST", "/v1/aurora/logout"), ("POST", "/v1/aurora/me/password")):
        assert not S.allowed(path, method), (method, path)                            # never, whatever the choice
    assert S.FULL and S.allowed("/v1/aurora/settings", "PUT")                         # the owner's choice: full access
    monkeypatch.setattr(S, "FULL", False)                                             # the narrower one, kept ready
    for method, path in (("PUT", "/v1/aurora/settings"), ("PUT", "/v1/aurora/me/prefs"), ("POST", "/v1/aurora/routines"),
                         ("POST", "/v1/aurora/push/subscribe"), ("POST", "/v1/aurora/accounts"), ("DELETE", "/v1/aurora/memory/conversation"),
                         ("POST", "/v1/aurora/a-route-made-tomorrow"), ("GET", "/v1/aurora/me/keys"), ("POST", "/v1/aurora/logout")):
        assert not S.allowed(path, method), (method, path)
    for method, path in (("GET", "/v1/aurora/settings"), ("GET", "/v1/aurora/routines"), ("POST", "/v1/aurora/ask"),
                         ("POST", "/v1/aurora/calendar/items"), ("DELETE", "/v1/aurora/documents/a.pdf"),
                         ("POST", "/v1/aurora/projects/p/talk"), ("POST", "/v1/aurora/assist/leave")):
        assert S.allowed(path, method), (method, path)
    assert not S.allowed("/v1/aurora/asking", "POST")                                 # a whole path, not its beginning


def test_the_admin_inside_an_account_leaves_no_setting_behind(o):
    # the owner's choice, 12 Nov: full access (sys_assist.FULL) — the settings are reached, only NEVER is not
    got = o["inside_refused"]                                  # (me/models answers by its own rule: the policy's 403)
    assert o["inside_reads"] == 200 and got["/v1/aurora/settings"] == got["/v1/aurora/me/prefs"] == 200, got
    assert o["inside_works"] != 403 and o["inside_leaves"] == {"left": True}


def test_a_changed_address_forgets_its_secret(o):
    assert o["address_and_secret"] == [200, None, "made-up-token"]                    # both given together: kept
    assert o["address_unchanged"] == [None, "made-up-token"]                          # the same address written again
    assert o["address_changed"] == [["AURORA_MASTODON_TOKEN"], "", "https://1.0.0.1"]


def test_a_user_s_own_address_is_not_one_of_the_house_s(o):
    assert o["user_house"] == 422 and o["user_this_machine"] == 422 and o["user_local_name"] == 422
    assert o["admin_house"] == 200 and o["user_same_as_admin"] == 200                 # the house's own, vouched by the admin
    assert o["user_other_port"] == 422 and o["user_public"] == 200
    assert o["names"] == [True, False, True]                                          # a name: by where it leads
