# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C570 (area audit of 10 Nov), the smaller gaps of the accounts, one by one: the login from another site's page, the
first authenticator confirmed by another browser, guesses of the password and of the code inside a session, an API
key made with the session alone, the login's answer kept by the replay cache, a failed service's text given as it
came, the call's socket opened by another site. Made-up users (api_guard.py)."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Response

from aurora.sys_csrf import foreign, foreign_socket
from aurora.sys_replay import Replay

HERE = Path(__file__).resolve().parent
WINDOWS = {k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ}


def guard(tmp_path, part: str) -> dict:
    """api_guard.py in its own process, on an installation of its own: multi-user, three failed logins allowed."""
    from conftest import write_env
    env = write_env(tmp_path, AURORA_USER_MODE="multi", AURORA_AUTH_MAX_FAILS="3")
    r = subprocess.run([sys.executable, str(HERE / "api_guard.py"), str(tmp_path), part], capture_output=True, text=True,
                       timeout=300, env={**WINDOWS, "PATH": "/usr/bin:/bin", "AURORA_ENV_FILE": str(env)})
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def o(tmp_path_factory):
    return guard(tmp_path_factory.mktemp("c570"), "c570")


def test_the_login_is_checked_for_its_origin_with_no_cookie_yet():
    host = {"host": "aurora.example:8443"}
    assert foreign("POST", {**host, "origin": "https://elsewhere.example"}, {}, "/v1/aurora/login")
    assert foreign("POST", {**host, "sec-fetch-site": "cross-site"}, {}, "/v1/aurora/login")
    assert foreign("POST", {**host, "origin": "null"}, {}, "/v1/aurora/login")
    assert not foreign("POST", {**host, "origin": "https://aurora.example:8443"}, {}, "/v1/aurora/login")
    assert not foreign("POST", host, {}, "/v1/aurora/login")                         # the app, a program: no browser
    assert not foreign("POST", {**host, "origin": "https://elsewhere.example"}, {}, "/v1/aurora/push-ack")   # no session made


def test_the_login_from_another_site_is_refused_by_the_api(o):
    assert o["csrf_elsewhere"] == 403 and o["csrf_cross"] == 403


def test_the_first_authenticator_is_confirmed_only_by_the_browser_shown_its_qr(o):
    assert o["enrol_begins"] == [200, True, True, True]                   # the ticket: an HttpOnly cookie
    assert o["enrol_other_browser"] == [401, False]                       # the password and a right code: not enough
    assert o["enrol_same_browser"] == [200, True, True]


def test_a_first_authenticator_from_a_session_asks_the_password(o):
    assert o["first_totp_no_password"] == 401 and o["first_totp_password"] and o["first_totp_with_the_key"]


def test_guesses_inside_a_session_are_failed_logins(o):
    assert o["password_guesses"] == [401, 401, 401, 429] and o["totp_guesses"] == [401, 401, 401, 429]
    assert o["session_still_good"] == 200                                 # the lockout refuses guesses, not the session


def test_an_api_key_asks_the_password_and_the_code_again(o):
    assert o["key_no_password"] == 401 and o["key_password_only"] == 401
    assert o["key_password_and_code"] == [200, True]
    assert o["key_makes_no_key"] == 401                                   # a key never makes another by itself
    assert o["installation_key_makes_one"] == 200                         # the installation's own key: nothing stronger to ask


def test_a_login_is_never_answered_from_the_replay_cache(o):
    assert o["login_replayed"] == [401, 401, None] and o["nothing_kept"] == 0


def test_an_answer_that_sets_a_cookie_is_not_kept():
    app = FastAPI()
    app.state.n = 0

    @app.post("/session")
    async def session(response: Response):
        app.state.n += 1
        response.set_cookie("made_up_session", f"value-{app.state.n}")
        return {"n": app.state.n}

    @app.post("/plain")
    async def plain():
        app.state.n += 1
        return {"n": app.state.n}

    app.add_middleware(Replay)

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://a") as c:
            h = {"X-Aurora-Request": "key-0003-abcd", "Cookie": "aurora_device=one"}
            a, b = await c.post("/session", headers=h), await c.post("/session", headers=h)
            p, q = await c.post("/plain", headers=h), await c.post("/plain", headers=h)
            return a, b, p, q
    a, b, p, q = asyncio.run(go())
    assert (a.json(), b.json()) == ({"n": 1}, {"n": 2}) and "x-aurora-replayed" not in b.headers
    assert "value-1" in a.headers["set-cookie"]                           # given once, to the one who asked
    assert p.json() == q.json() == {"n": 3} and q.headers["x-aurora-replayed"] == "1"     # the others as before (C199)


def test_a_failed_service_is_named_without_its_text(o):
    assert "127.0.0.1" not in o["upstream_handler"] and "ConnectError" in o["upstream_handler"]
    assert o["upstream_said"][:2] == ["HTTP 401", "not reachable (ConnectError)"]
    assert "10.20" not in o["upstream_said"][2] and "madeup" not in o["upstream_said"][2]


def test_the_call_s_socket_is_not_opened_by_another_site(o):
    assert foreign_socket({"origin": "https://elsewhere.example", "host": "aurora.example"})
    assert not foreign_socket({"host": "aurora.example"})                 # the phone app sends no Origin
    assert not foreign_socket({"origin": "https://aurora.example", "host": "aurora.example"})
    assert o["socket_elsewhere"] == 4403 and o["socket_app"] == 4404      # 4404: let in, and no such call
