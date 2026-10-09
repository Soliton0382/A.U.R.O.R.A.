# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-api: OpenAI-compatible API, live event stream, settings, and the WebUI.

    GET  /health                                   liveness (no key)
    GET  /                      /static/...        the WebUI (static files)
    GET  /v1/models                                OpenAI: the model list ("aurora")
    POST /v1/chat/completions                      OpenAI: stream or not; only the last user message is used
    POST /v1/aurora/ask                            start a run, returns its id (WebUI)
    POST /v1/aurora/acquire                        search arXiv for a question, import, answer again (a run)
    GET  /v1/aurora/runs                           recent runs
    GET  /v1/aurora/runs/{id}/events?after=N       the run's events, streamed as they happen (SSE)
    GET  /v1/aurora/status                         vault, index, models, reasoner
    GET  /v1/aurora/domains                        knowledge domains of the taxonomy (IT/EN names)
    POST /v1/aurora/import                         a document (base64) into a domain: chunked, written, indexed
    POST /v1/aurora/solitons                       ready knowledge solitons in bulk (migration, harvester): written, indexed
    DELETE /v1/aurora/sources?domain=&source_id=   remove a source from vault and index (no re-encoding)
    POST /v1/aurora/memory/reset {"confirm": true} delete all memory (conversations, reflections) and its index
    GET  /v1/aurora/history?n=8                    the latest conversation turns (the WebUI shows them on load)
    GET  /v1/aurora/uploads[/{id}]; DELETE /v1/aurora/uploads/{id}; POST /v1/aurora/uploads/purge  files attached in the chat
    GET  /v1/aurora/metrics                        CPU, RAM, GPUs now
    GET  /v1/aurora/rem/state                      what the autonomic cycle needs: idle time, open sessions, weather
    POST /v1/aurora/rem/{consolidate|reflect|dream|introspect} one autonomic task, as a run (aurora-rem)
    GET  /v1/aurora/activity[/stream]              what is happening: runs begin/end, service notes (SSE)
    POST /v1/aurora/activity                       a service reports what it is doing
    GET  /v1/aurora/logs[/{component}]             log inventory with recent problems; the tail of one log
    GET  /v1/aurora/health                         every service, disk, GPUs: ok / warn / down, with the reasons
    GET  /v1/aurora/reflections?type=&n=           Aurora's inner life: session memories, thoughts, dreams, reviews
    GET  /v1/aurora/images/{name}                  an image Aurora painted (a dream), with its AI disclosure
    GET  /v1/aurora/push; POST /v1/aurora/push/{subscribe|unsubscribe|test}  Web Push to this browser
    GET|PUT /v1/aurora/notifications                which events notify, on which channel (push, WebUI)
    GET  /v1/aurora/harvester; POST /v1/aurora/harvester/{now|batch}  the owner steers aurora-harvester
    PUT  /v1/aurora/harvester/domains {domain: off|round|exhaust}   which domains it harvests, and how
    GET|POST /v1/aurora/routines; PUT|DELETE /v1/aurora/routines/{id}; POST /v1/aurora/routines/{id}/run
    POST /v1/aurora/routines/tick                  aurora-rem: start the due routines, welcome newly ready plugins
    GET  /v1/aurora/forge; POST /v1/aurora/forge/tick  the capability forge: requests, and aurora-rem builds them
    GET  /v1/aurora/models[/stats|/{provider}/list]; PUT /v1/aurora/models/roles  which model does each step
    GET  /v1/aurora/projects[/github]; GET /v1/aurora/projects/{name}/{tree|file|log}; POST .../preview
    POST /v1/aurora/projects {name,...} (create); POST /v1/aurora/projects/clone {full_name}
    GET  /v1/preview/{token}/{path}                a project's page, sandboxed, under a 10-minute token (no cookie)
    GET  /v1/aurora/update; POST /v1/aurora/update/{check|apply}  updates from GitHub: changelog, approval or auto
    GET  /v1/aurora/senses/devices; POST /v1/aurora/senses/{photo|listen}  camera and microphone of this machine
    POST /v1/aurora/sentinel/incident              aurora-sentinel reports a firewall incident (stored, investigated)
    GET  /v1/aurora/incidents[?status=open]; POST /v1/aurora/incidents/{id}/close
    GET  /v1/aurora/social; POST /v1/aurora/social/draft; POST /v1/aurora/social/publish
    GET  /v1/aurora/runs/{id}/record               a past run's events, from the trace files
    POST /v1/aurora/agent {"goal"}                  an agent run with the plugins' tools (a run)
    GET  /v1/aurora/plugins                        plugins, their tools and effects, what they miss
    POST /v1/aurora/plugins/{name}/{enable|disable}
    GET  /v1/aurora/approvals[?status=pending]     actions waiting for the owner, and past decisions
    POST /v1/aurora/approvals/{id}/{approve|reject} the owner decides; an approved action runs (a run)
    POST /v1/aurora/rem/repair                     self-repair from the last self-review (aurora-rem)
    GET  /v1/aurora/settings                       every .env variable with its explanation (secrets masked)
    PUT  /v1/aurora/settings                       change values: validated, written atomically, services to restart

Every /v1 call needs `Authorization: Bearer <AURORA_API_KEY>`, or a registered device: the WebUI
logs in once with the key (POST /v1/aurora/devices) and then uses an HttpOnly cookie.

    POST   /v1/aurora/devices                      register this browser (key required), sets the cookie
    GET    /v1/aurora/devices                      registered devices
    DELETE /v1/aurora/devices/{id}                 revoke a device
    POST   /v1/aurora/logout                       revoke this device and clear its cookie

Every message is treated as the first (ECOSYSTEM 2.3): the history a client sends
is discarded, Aurora's memory supplies the context. For third-party clients the
live trace travels in `delta.reasoning_content`, the verified answer in
`delta.content`. Runs are served one at a time: the reasoner has one slot.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from aurora.api import MODULES  # noqa: E402
from aurora.api.core import WEBUI, cfg, log  # noqa: E402

app = FastAPI(title="Aurora", docs_url=None, redoc_url=None, openapi_url=None)   # no public map of the API (C79)


@app.exception_handler(httpx.HTTPError)
async def upstream_down(request: Request, exc: httpx.HTTPError) -> JSONResponse:
    """A service Aurora depends on (models, reasoner) is not reachable: 503, retry later."""
    log.warning("upstream unavailable on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": f"a service is not reachable: {exc}"})


from aurora.sys_replay import Replay  # noqa: E402

app.add_middleware(Replay)                          # a request repeated after a lost connection: answered once (C199)

for _name in MODULES:                               # each area of the API is its own module (aurora/api)
    app.include_router(__import__(f"aurora.api.{_name}", fromlist=["router"]).router)


# ---- WebUI -------------------------------------------------------------------------------------
class WebUIFiles(StaticFiles):
    """The WebUI's files are checked again at every load (ETag: an unchanged file is a 304): without a Cache-Control
    the browser kept modules by its own heuristics, and an old social.js lost the dream's picture of a share (C107)."""

    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        r.headers["Cache-Control"] = "no-cache"
        return r


if WEBUI.is_dir():
    app.mount("/static", WebUIFiles(directory=WEBUI), name="static")


@app.get("/")
def index():
    return FileResponse(WEBUI / "index.html", headers={"Cache-Control": "no-cache"})


# The service worker must be served from the root to control the whole site (PWA).
@app.get("/sw.js")
def service_worker():
    return FileResponse(WEBUI / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(WEBUI / "manifest.webmanifest", media_type="application/manifest+json")


if __name__ == "__main__":
    # Lifecycle in the component's own log: a start without a clean stop before it means a crash or a kill.
    from aurora import sys_ethics
    sys_ethics.require_intact(log)
    log.info("started: pid %d on %s:%s (systemd invocation %s)", os.getpid(), cfg["AURORA_API_HOST"], cfg["AURORA_API_PORT"],
             os.environ.get("INVOCATION_ID", "-"))
    # A crash between a shard write and its registry entry leaves a row the registry does not
    # know (BUGS A1): check at every start, repair when needed (~0.2 s on 36k solitons).
    from aurora import sol_vault
    _t = time.time()
    _layout = sol_vault.Layout.from_config(cfg)
    _found = {sec: {k: len(v) for k, v in r.items() if isinstance(v, list) and v}
              for sec, r in sol_vault.check(_layout).items()}
    if any(_found.values()):
        sol_vault.repair(_layout)
        log.warning("vault check found %s: repaired", _found)
    log.info("vault check: %s in %.1f s", "clean" if not any(_found.values()) else "repaired", time.time() - _t)
    # Open streams (the WebUI's activity feed never ends by itself) would hold the shutdown until
    # systemd kills the process: close them after 5 s so that a stop is clean (BUGS C23).
    # uvicorn re-raises SIGTERM after a graceful shutdown, so a line after run() would never be
    # written: the clean stop is logged by the application's shutdown hook instead.
    app.router.add_event_handler("shutdown", lambda: log.info("stopped cleanly: pid %d", os.getpid()))

    def _settings_in_place() -> None:
        """Every setting written where it lives, before the first page asks for them (C224)."""
        from aurora import sys_user_config
        try:
            added = sys_user_config.reconcile(cfg)
        except (OSError, RuntimeError, ValueError) as e:        # a start never fails on it: said, and left as it was
            log.warning("settings not put in place: %s", e)
            return
        for where, keys in added.items():
            log.info("audit: settings written (%s): %s", where, ", ".join(keys))

    def _seed_shadows() -> None:
        """Every user starts with the published seed of answers (owner, 9 Oct: «i git clone partano già con un set di
        ombre già presenti»): config/shadow_seed.json into the shadow of each user who has none of it yet, once the
        encoder answers. Each seed answer is checked again like any other when it is first served."""
        import json as _json
        from aurora import kno_shadow, sys_user_config, sys_users_layout as L
        f = Path(__file__).resolve().parents[1] / "config" / "shadow_seed.json"
        if not cfg["AURORA_SHADOW"] or not f.is_file():
            return
        rows = _json.loads(f.read_text(encoding="utf-8"))
        base = cfg.base or cfg
        users = sorted(L._registered(base)) if L.migrated(base) else [None]
        for _ in range(60):                                  # the encoder may still be loading (aurora-models)
            try:
                from aurora.api.core import pipeline
                embedder = pipeline().search.embedder
                embedder.dim
                break
            except Exception:                                # noqa: BLE001 - not ready yet: wait, never fail the start
                time.sleep(10)
        else:
            log.warning("shadow seed not loaded: the encoder did not answer")
            return
        for name in users:
            mine = sys_user_config.for_user(base, name)
            try:
                if kno_shadow.stats(mine)["seed"]:
                    continue
                out = kno_shadow.import_seed(mine, embedder, rows)
                log.info("audit: shadow seed for %s: %d answers added, %d skipped", name or "the owner", out["added"],
                         out["skipped"])
            except Exception as e:                           # noqa: BLE001 - a user without it, said
                log.warning("shadow seed for %s not loaded: %s", name, e)

    def _warm_plugins() -> None:
        """List the plugins' tools once in the background: the first Plugins page or agent run does not wait ~4 s."""
        from aurora.api.core import plugin_host
        t0 = time.time()
        try:
            n = sum(len(p.tools) for p in plugin_host().plugins())
            log.info("plugin tools listed in the background: %d tools in %.1f s", n, time.time() - t0)
        except Exception as e:                        # a slow page later, never a failed start
            log.warning("plugin tools not listed at start: %s", e)
    import threading
    app.router.add_event_handler("startup", _settings_in_place)
    app.router.add_event_handler("startup", lambda: threading.Thread(target=_seed_shadows, name="seed-shadows",
                                                                      daemon=True).start())
    app.router.add_event_handler("startup", lambda: threading.Thread(target=_warm_plugins, name="warm-plugins",
                                                                      daemon=True).start())
    from aurora.api.security import watch_defence     # automatic blocks lifted when their time is over
    app.router.add_event_handler("startup", lambda: threading.Thread(target=watch_defence, name="watch-defence",
                                                                      daemon=True).start())
    from aurora.api.activity import watch_health      # a service down or the disk full becomes an alert
    app.router.add_event_handler("startup", lambda: threading.Thread(target=watch_health, name="watch-health",
                                                                      daemon=True).start())
    from aurora.api.tunnel import at_start as tunnel_at_start   # the Cloudflare tunnel up again after a reboot
    app.router.add_event_handler("startup", lambda: threading.Timer(20, tunnel_at_start).start())
    from aurora.api.diet import watch_diet           # the meal of this minute, for each user with reminders on
    app.router.add_event_handler("startup", lambda: threading.Thread(target=watch_diet, name="watch-diet",
                                                                      daemon=True).start())
    from aurora.api.calendar import watch_calendar   # the calendar's alerts, for each user
    app.router.add_event_handler("startup", lambda: threading.Thread(target=watch_calendar, name="watch-calendar",
                                                                      daemon=True).start())
    uvicorn.run(app, host=cfg["AURORA_API_HOST"], port=cfg["AURORA_API_PORT"], log_level="warning", timeout_graceful_shutdown=5)
