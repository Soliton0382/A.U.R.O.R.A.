#!/opt/aurora/.venv/bin/python
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's plugins in a container of their own (owner, 2026-10-09: «per i plugi invece si crea un docker apposito che
farà parte della stessa rete del docker aurora così saranno separati e comunicheranno internamente tra di loro»).

The same image as Aurora, another first process: this gateway. Each plugin runs here as on Linux, inside bubblewrap
(its own secrets only, Aurora's folder read-only, the other users' folders hidden, no network unless its manifest asks
for it). Bubblewrap needs user namespaces, which Docker's default seccomp profile forbids: this container — and only
this one — runs with that profile relaxed (docker/compose.yaml); Aurora's own container keeps the strict one.

    POST /tools {"plugin", "user"}                                   -> {"tools": [...]}
    POST /call  {"plugin", "user", "tool", "args", "run_id"}         -> {"ok", "text", "seconds"}
    GET  /health

Reachable only on Docker's internal network (no port published), and only with Aurora's API key. The checks are
Aurora's (plg_host in the API container: the secrets in the arguments, the approvals of external tools): here a tool
is run as asked.
"""
# no «from __future__ import annotations»: FastAPI must read Request and Body as types, not as names it cannot find
# (they are imported inside main(), after the data is linked — a 422 «query: request» otherwise)
import hmac
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "sys" / "core"))


def main() -> int:
    import entrypoint                                   # the same links into /data as Aurora's container
    entrypoint.data()
    env = Path("/data/.env")
    for _ in range(300):                                # Aurora's container writes the settings at its first start
        if env.exists():
            break
        time.sleep(2)
    import uvicorn
    from fastapi import Body, Depends, FastAPI, HTTPException, Request
    from aurora import plg_host, plg_sandbox, sys_config, sys_user_config

    cfg = sys_config.get()
    base = cfg.base or cfg
    app = FastAPI(title="aurora-plugins", docs_url=None, redoc_url=None, openapi_url=None)

    def auth(request: Request) -> None:
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given.encode(), str(sys_config.get()["AURORA_API_KEY"]).encode()):
            raise HTTPException(status_code=401, detail="unauthorized")

    def host_for(user: str | None) -> plg_host.PluginHost:
        return plg_host.PluginHost(sys_user_config.for_user(base, user) if user else base)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "cage": plg_sandbox.available()}

    # plain (not async) endpoints: run in a thread, where the host's own asyncio.run may start its loop
    @app.post("/tools", dependencies=[Depends(auth)])
    def tools(body: dict = Body(...)) -> dict:
        host = host_for(body.get("user"))
        p = next((x for x in host.plugins(with_tools=False) if x.name == body.get("plugin")), None)
        if p is None:
            raise HTTPException(status_code=404, detail="no such plugin")
        return {"tools": host._tools(p, (p.folder / "plugin.json").stat().st_mtime)}

    @app.post("/call", dependencies=[Depends(auth)])
    def call(body: dict = Body(...)) -> dict:
        return host_for(body.get("user")).call(str(body.get("plugin")), str(body.get("tool")), body.get("args") or {},
                                              body.get("run_id"))

    print(f"[aurora-plugins] cage: {'bubblewrap' if plg_sandbox.available() else 'MISSING — no plugin will run'}",
          flush=True)
    uvicorn.run(app, host="0.0.0.0", port=9790, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
