# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C199: a request the page repeats after a lost connection is answered once, never done twice (owner, 2026-10-08)."""
import asyncio

import httpx
from fastapi import FastAPI, Request

from aurora.sys_replay import Replay


def _app():
    app = FastAPI()
    app.state.n = 0

    @app.post("/work")
    async def work(request: Request):
        body = await request.json()
        app.state.n += 1
        await asyncio.sleep(0.2)
        return {"n": app.state.n, "echo": body["x"]}

    app.add_middleware(Replay)
    return app


def _run(coro):
    return asyncio.run(coro)


def test_the_same_key_is_done_once_and_answered_to_both():
    app = _app()

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://a") as c:
            h = {"X-Aurora-Request": "key-0001-abcd", "Cookie": "aurora_device=one"}
            a, b = await asyncio.gather(c.post("/work", json={"x": 1}, headers=h), c.post("/work", json={"x": 1}, headers=h))
            later = await c.post("/work", json={"x": 1}, headers=h)
            return a, b, later
    a, b, later = _run(go())
    assert a.json() == b.json() == later.json() == {"n": 1, "echo": 1}
    assert later.headers.get("x-aurora-replayed") == "1" and app.state.n == 1


def test_another_caller_or_no_key_is_never_given_someone_else_s_answer():
    app = _app()

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://a") as c:
            await c.post("/work", json={"x": 1}, headers={"X-Aurora-Request": "key-0001-abcd", "Cookie": "aurora_device=one"})
            other = await c.post("/work", json={"x": 2}, headers={"X-Aurora-Request": "key-0001-abcd", "Cookie": "aurora_device=two"})
            plain = await c.post("/work", json={"x": 3})
            return other, plain
    other, plain = _run(go())
    assert other.json() == {"n": 2, "echo": 2} and plain.json() == {"n": 3, "echo": 3}


def test_a_caller_that_goes_away_does_not_stop_the_work_and_the_retry_gets_its_answer():
    app = _app()
    mw = app.build_middleware_stack()
    scope = {"type": "http", "method": "POST", "path": "/work", "raw_path": b"/work", "query_string": b"", "root_path": "",
             "scheme": "http", "server": ("a", 80), "client": ("c", 1), "http_version": "1.1",
             "headers": [(b"x-aurora-request", b"key-0002-abcd"), (b"cookie", b"d=1"), (b"content-type", b"application/json"),
                         (b"content-length", b"7")]}

    async def go():
        sent = []
        msgs = [{"type": "http.request", "body": b'{"x":5}', "more_body": False}]

        async def receive():
            return msgs.pop(0) if msgs else {"type": "http.disconnect"}

        async def gone(msg):                                    # the phone went to sleep: nothing can be sent
            raise OSError("connection lost")

        await mw(scope, receive, gone)
        msgs2 = [{"type": "http.request", "body": b'{"x":5}', "more_body": False}]

        async def receive2():
            return msgs2.pop(0) if msgs2 else {"type": "http.disconnect"}

        async def keep(msg):
            sent.append(msg)
        await mw(scope, receive2, keep)
        return sent
    sent = _run(go())
    assert b'"n":1' in sent[-1]["body"] and app.state.n == 1


def test_no_page_follows_a_run_or_calls_the_api_without_taking_up_a_lost_connection():
    """C199: every run is followed with followRun (from the last event, waiting while the page is away) and every API
    call goes through call() (sent again with its key): a raw stream of a run or a raw fetch of the API is a page that
    shows «network error» when the phone wakes up."""
    import re
    from pathlib import Path
    js = Path(__file__).resolve().parents[1] / "webui" / "js"
    for f in [*js.glob("*.js"), *(js / "modules").glob("*.js")]:
        src = f.read_text()
        if f.name == "api.js":
            assert "X-Aurora-Request" in src and "export async function followRun" in src
            continue
        assert not re.search(r"stream\(`/v1/aurora/runs/", src), f.name
        raw = re.findall(r'fetch\("(/v1/aurora/[^"]+)"', src)
        assert set(raw) <= {"/v1/aurora/tts"}, (f.name, raw)          # speech: a tap again is the retry
