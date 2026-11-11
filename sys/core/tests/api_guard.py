# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Run by test_c570_accounts.py, test_c535_api.py and test_c568_loopback.py in its own process (the API keeps state
in its modules): a fake installation with `boss` (the admin) and `guest`, three failed logins before the lockout.
argv: the root, then the part to run (c570 | c535 | c568). Prints one JSON line of results. Made-up users."""
import asyncio
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "script"))

from aurora import sys_config as C  # noqa: E402

root, part = Path(sys.argv[1]), sys.argv[2]
base = C.load(root / ".env", check_root=False)
(base.path("AURORA_STATUS_DIR")).mkdir(parents=True, exist_ok=True)
(base.path("AURORA_STATUS_DIR") / "users_layout.json").write_text(json.dumps({"layout": 1, "admin": "boss"}))
from aurora.sys_users import Users, hotp  # noqa: E402
from aurora import sys_users_layout as L  # noqa: E402

PW = {"boss": "the boss's long password", "guest": "the guest's long password"}
users = Users(base)
for n, role in (("boss", "admin"), ("guest", "user")):
    users.add(n, role, PW[n])
    L.make_home(base, n)
C._cached = C._view(base)

import svc_api  # noqa: E402
from aurora import sec_hostfw, sys_assist, sys_user_config, sys_users_perm  # noqa: E402
from aurora.api import core, core_guard  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

sec_hostfw.block = lambda *a, **k: {"ok": False}        # a lockout here never reaches this machine's firewall
URL = "https://testserver"
client = lambda **k: TestClient(svc_api.app, base_url=URL, **k)       # noqa: E731
tok = {n: core.devices.register(f"{n} phone", "ua", user=n) for n in ("boss", "guest")}
H = {n: {"Authorization": f"Bearer {t[0]}"} for n, t in tok.items()}
K = {"Authorization": f"Bearer {base['AURORA_API_KEY']}"}
out = {}
code_now = lambda secret, ahead=0: hotp(secret, int(time.time() // 30) + ahead)      # noqa: E731


def c570() -> None:
    c = client()
    login = {"name": "guest", "password": PW["guest"]}
    # the login from another site's page: refused before the password is looked at; Aurora's own page passes
    out["csrf_elsewhere"] = c.post("/v1/aurora/login", json=login, headers={"Origin": "https://elsewhere.example"}).status_code
    out["csrf_cross"] = c.post("/v1/aurora/login", json=login, headers={"Sec-Fetch-Site": "cross-site"}).status_code
    r = c.post("/v1/aurora/login", json=login, headers={"Origin": URL})
    out["enrol_begins"] = [r.status_code, "enroll" in r.json(), "aurora_enrol" in r.headers.get("set-cookie", ""),
                           "HttpOnly" in r.headers.get("set-cookie", "")]
    secret = r.json()["enroll"]["secret"]
    # the right password and a right code from a browser that was not shown the QR: not confirmed
    other = client()
    r2 = other.post("/v1/aurora/login", json={**login, "code": code_now(secret)})
    out["enrol_other_browser"] = [r2.status_code, users.by_name("guest")["totp_on"]]
    r3 = c.post("/v1/aurora/login", json={**login, "code": code_now(secret)})
    out["enrol_same_browser"] = [r3.status_code, users.by_name("guest")["totp_on"], "aurora_device" in r3.headers.get("set-cookie", "")]
    core._fails.clear()
    # a wrong current password inside a session: counted, and refused after three
    g = client(headers=H["guest"])
    tries = [g.post("/v1/aurora/me/password", json={"old": "not this one", "new": "a new long password"}).status_code
             for _ in range(4)]
    out["password_guesses"] = tries
    out["session_still_good"] = g.get("/v1/aurora/me").status_code
    core._fails.clear()
    tries = [g.post("/v1/aurora/me/totp", json={"password": "not this one", "current": "000000"}).status_code for _ in range(4)]
    out["totp_guesses"] = tries
    core._fails.clear()
    # boss has a password and no authenticator: a first one asks the password
    b = client(headers=H["boss"])
    out["first_totp_no_password"] = b.post("/v1/aurora/me/totp", json={}).status_code
    out["first_totp_password"] = "secret" in b.post("/v1/aurora/me/totp", json={"password": PW["boss"]}).json()
    out["first_totp_with_the_key"] = "secret" in client(headers=K).post("/v1/aurora/me/totp", json={}).json()
    core._fails.clear()
    # an API key: the password again, and the code of whoever has an authenticator
    out["key_no_password"] = g.post("/v1/aurora/me/keys", json={"name": "a program"}).status_code
    out["key_password_only"] = g.post("/v1/aurora/me/keys", json={"name": "a program", "password": PW["guest"]}).status_code
    r = g.post("/v1/aurora/me/keys", json={"name": "a program", "password": PW["guest"], "code": code_now(secret, 1)})
    out["key_password_and_code"] = [r.status_code, bool(r.json().get("key"))]
    made = r.json().get("key", "")
    out["key_makes_no_key"] = client(headers={"Authorization": f"Bearer {made}"}).post(
        "/v1/aurora/me/keys", json={"name": "another"}).status_code
    out["installation_key_makes_one"] = client(headers=K).post("/v1/aurora/me/keys", json={"name": "a script"}).status_code
    core._fails.clear()
    # the replay cache: a login is never answered from it
    again = {"X-Aurora-Request": "login-0001-abcd"}
    a = client().post("/v1/aurora/login", json={"name": "guest", "password": "not this one"}, headers=again)
    b2 = client().post("/v1/aurora/login", json={"name": "guest", "password": "not this one"}, headers=again)
    out["login_replayed"] = [a.status_code, b2.status_code, b2.headers.get("x-aurora-replayed")]
    out["nothing_kept"] = len(svc_replay().done)
    core._fails.clear()
    # a service down: its address is not in the answer
    import httpx
    exc = httpx.ConnectError("All connection attempts failed for http://127.0.0.1:59999/health")
    scope = {"type": "http", "method": "GET", "path": "/v1/aurora/status", "headers": [], "query_string": b"",
             "server": ("testserver", 443), "scheme": "https"}
    from starlette.requests import Request
    resp = asyncio.run(svc_api.upstream_down(Request(scope), exc))
    out["upstream_handler"] = resp.body.decode()
    req = httpx.Request("GET", "https://provider.example/v1/models?key=made-up-value")
    out["upstream_said"] = [
        core_guard.upstream_error(httpx.HTTPStatusError("401 for url https://provider.example/v1/models?key=made-up-value",
                                                        request=req, response=httpx.Response(401, request=req))),
        core_guard.upstream_error(httpx.ConnectError("refused: http://10.20.30.40:8123/api")),
        core_guard.upstream_error(RuntimeError("no models at http://10.20.30.40:8123/api with madeupmadeupmadeupmadeup0000"))]
    # the call's socket from another site's page: closed before anything is looked at
    for name, headers in (("socket_elsewhere", {**H["guest"], "Origin": "https://elsewhere.example"}), ("socket_app", H["guest"])):
        try:
            with client().websocket_connect("/v1/aurora/call/nocall/audio", headers=headers):
                out[name] = "open"
        except WebSocketDisconnect as e:
            out[name] = e.code


def svc_replay():
    """The Replay layer of the running app."""
    from aurora.sys_replay import Replay
    layer = svc_api.app.middleware_stack
    while layer is not None and not isinstance(layer, Replay):
        layer = getattr(layer, "app", None)
    return layer


def c535() -> None:
    big = "x" * (2 * 2**20)
    # a stranger's large body: refused on its declared length, and on its bytes when none is declared
    out["stranger_declared"] = client().post("/v1/aurora/login", json={"name": big}).status_code

    def pieces():
        for _ in range(40):
            yield b"y" * 65536
    out["stranger_counted"] = client().post("/v1/aurora/login", content=pieces()).status_code
    out["stranger_small"] = client().post("/v1/aurora/login", json={"name": "guest", "password": "not this one"}).status_code
    out["wrong_cookie"] = client(cookies={"aurora_device": "not-a-device"}).put("/v1/aurora/me/prefs", json={"junk": big}).status_code
    core._fails.clear()
    out["known_large"] = client(headers=H["guest"]).put("/v1/aurora/me/prefs", json={"junk": big}).status_code
    # a live stream asks again who its caller is
    from starlette.requests import Request

    def request(name: str):
        r = Request({"type": "http", "method": "GET", "path": "/v1/aurora/activity/stream", "query_string": b"",
                     "headers": [(b"authorization", H[name]["Authorization"].encode())], "client": ("testclient", 1)})
        r.state.user = core_guard.who_now(r)
        return r

    async def follow(req, then) -> list:
        async def forever():
            n = 0
            while n < 50:
                n += 1
                yield n
        got = []
        async for item in core_guard.live(req, forever(), every=0):
            got.append(item)
            if item == 2:
                then()
        return got
    extra_tok, extra = core.devices.register("guest tablet", "ua", user="guest")
    H["tablet"] = {"Authorization": f"Bearer {extra_tok}"}
    out["stream_kept"] = len(asyncio.run(follow(request("guest"), lambda: None)))
    out["stream_revoked"] = asyncio.run(follow(request("tablet"), lambda: core.devices.revoke(extra["id"])))
    # 🛟 inside a user's account: reads, the person's work, and no lasting change
    sys_assist.grant(base, "guest", 8)
    sys_assist.enter(base, tok["boss"][1]["id"], "guest")
    b = client(headers=H["boss"])
    inside = request("boss")
    out["inside_is"] = inside.state.user
    out["stream_assist_ended"] = asyncio.run(follow(inside, lambda: sys_assist.revoke(base, "guest")))
    sys_assist.grant(base, "guest", 8)
    sys_assist.enter(base, tok["boss"][1]["id"], "guest")
    out["inside_reads"] = b.get("/v1/aurora/settings").status_code
    out["inside_refused"] = {p: b.request(m, p, json={}).status_code for m, p in (
        ("PUT", "/v1/aurora/settings"), ("PUT", "/v1/aurora/me/prefs"), ("POST", "/v1/aurora/push/subscribe"),
        ("POST", "/v1/aurora/routines"), ("POST", "/v1/aurora/accounts"), ("PUT", "/v1/aurora/notifications"),
        ("PUT", "/v1/aurora/me/models"), ("POST", "/v1/aurora/memory/reset"), ("POST", "/v1/aurora/astro/camera/key"))}
    out["inside_works"] = b.post("/v1/aurora/ideas", json={}).status_code
    out["inside_leaves"] = b.post("/v1/aurora/assist/leave", json={}).json()
    sys_assist.revoke(base, "guest")
    # a changed address forgets the secret that went with the old one
    sys_users_perm.set_(base, "guest", "settings", True)
    g = client(headers=H["guest"])
    mine = lambda k: str(sys_user_config.for_user(base, "guest")[k])     # noqa: E731
    r = g.put("/v1/aurora/settings", json={"AURORA_MASTODON_URL": "https://1.1.1.1", "AURORA_MASTODON_TOKEN": "made-up-token"})
    out["address_and_secret"] = [r.status_code, r.json().get("forgotten"), mine("AURORA_MASTODON_TOKEN")]
    r = g.put("/v1/aurora/settings", json={"AURORA_MASTODON_URL": "https://1.1.1.1/"})
    out["address_unchanged"] = [r.json().get("forgotten"), mine("AURORA_MASTODON_TOKEN")]
    r = g.put("/v1/aurora/settings", json={"AURORA_MASTODON_URL": "https://1.0.0.1"})
    out["address_changed"] = [r.json().get("forgotten"), mine("AURORA_MASTODON_TOKEN"), mine("AURORA_MASTODON_URL")]
    # a user's own address is not one of the house's, unless it is the admin's too
    put = lambda who, url: who.put("/v1/aurora/settings", json={"AURORA_HA_URL": url, "AURORA_HA_TOKEN": "made-up"}).status_code  # noqa: E731
    out["user_house"] = put(g, "http://10.20.30.40:8123")
    out["user_this_machine"] = put(g, "http://127.0.0.1:9700")
    out["user_local_name"] = put(g, "http://homeassistant.local:8123")
    out["admin_house"] = put(client(headers=K), "http://10.20.30.40:8123")
    out["user_same_as_admin"] = put(g, "http://10.20.30.40:8123")
    out["user_other_port"] = put(g, "http://10.20.30.40:22")
    out["user_public"] = put(g, "https://1.1.1.1")
    # a name is judged by where it leads (the resolver here is the test's own: nothing is asked of the network)
    leads = {"inside.example": ["10.0.0.8"], "outside.example": ["1.1.1.1"], "both.example": ["1.1.1.1", "127.0.0.1"]}
    out["names"] = [core_guard.private_host(n, lambda h: leads[h]) for n in ("inside.example", "outside.example", "both.example")]
    # and the cap of a body, read from the headers alone
    hdr = lambda **k: {a.replace("_", "-").encode(): b.encode() for a, b in k.items()}   # noqa: E731
    out["caps"] = [core_guard.body_cap("/v1/aurora/dj/tracks", hdr()),
                   core_guard.body_cap("/v1/aurora/dj/tracks", hdr(authorization="Bearer not-the-key")),
                   core_guard.body_cap("/v1/aurora/dj/tracks", hdr(authorization=H["guest"]["Authorization"])) > 100 * 2**20,
                   core_guard.body_cap("/v1/aurora/dj/tracks", hdr(cookie=f"other=1; aurora_device={tok['guest'][0]}")) > 100 * 2**20,
                   core_guard.body_cap("/v1/aurora/astro/camera/push", hdr(x_aurora_camera="not-a-camera-key"))]
    from aurora.api.astro_cam import relay
    cam = relay().new_key("guest")
    out["camera_stream"] = core_guard.body_cap("/v1/aurora/astro/camera/push", hdr(x_aurora_camera=cam))


def c568() -> None:
    here = client(client=("127.0.0.1", 40000))
    wrong = {"Authorization": "Bearer not-the-key"}
    codes = [here.get("/v1/aurora/me", headers=wrong).status_code for _ in range(31)]
    out["local_counted"] = [codes.count(401), codes[-1]]
    out["local_login_refused"] = here.post("/v1/aurora/login", json={"name": "guest", "password": PW["guest"]}).status_code
    out["local_key_passes"] = here.get("/v1/aurora/me", headers=K).status_code
    out["elsewhere_not_locked"] = client().get("/v1/aurora/me", headers=wrong).status_code
    out["told"] = [a["payload"].get("ip") for a in core._activity if a["event"] == "auth.lockout"]
    core._fails.clear()
    # behind the proxy an address keeps its own, lower ceiling
    proxied = [here.get("/v1/aurora/me", headers={**wrong, "X-Forwarded-For": "198.51.100.7"}).status_code for _ in range(4)]
    out["proxied"] = proxied


{"c570": c570, "c535": c535, "c568": c568}[part]()
print(json.dumps(out))
