# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C735: a request's credentials (a token, a key, a cookie) follow a redirect on the same site only; to another site
they are dropped. C736: an approval is decided once — two taps at once run the action once. Made-up sites, no network."""
import threading

import httpx

from aurora import net_public as N
from aurora import sys_approvals as A


def _serve(monkeypatch):
    seen = []

    def routes(request):
        seen.append((request.headers.get("host"), request.url.path, request.headers.get("authorization"),
                     request.headers.get("x-api-key"), request.headers.get("accept")))
        if request.url.path == "/same":
            return httpx.Response(302, headers={"location": "/after"})
        if request.url.path == "/away":
            return httpx.Response(302, headers={"location": "https://other.example/landing"})
        return httpx.Response(200, text="ok")
    real = httpx.Client
    monkeypatch.setattr(N.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(routes), **kw))
    monkeypatch.setattr(N, "check", lambda url, lan=False: "93.184.216.34")
    return seen


def test_credentials_follow_a_redirect_on_the_same_site_only(monkeypatch):
    seen = _serve(monkeypatch)
    head = {"Authorization": "Bearer Made-Up-Token", "X-Api-Key": "made-up-key", "Accept": "application/json"}
    assert N.request("GET", "https://deposit.example/same", headers=dict(head)).text == "ok"
    assert seen[1][:4] == ("deposit.example", "/after", "Bearer Made-Up-Token", "made-up-key")
    seen.clear()
    assert N.request("GET", "https://deposit.example/away", headers=dict(head)).text == "ok"
    assert seen[1] == ("other.example", "/landing", None, None, "application/json")   # the rest of the headers kept


def test_an_approval_is_decided_once(cfg):
    store = A.Approvals(cfg)
    item = store.request("tool_call", "external", "a made-up post", "", {}, {"plugin": "x", "tool": "y"})
    wins, gate = [], threading.Barrier(4)

    def tap(decision):
        gate.wait()
        wins.append(store.claim(item["id"], status=decision, decided="now"))
    threads = [threading.Thread(target=tap, args=(d,)) for d in ("approved", "approved", "rejected", "approved")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(w is not None for w in wins) == 1
    assert store.claim(item["id"], status="approved") is None and store.get(item["id"])["status"] in ("approved", "rejected")
