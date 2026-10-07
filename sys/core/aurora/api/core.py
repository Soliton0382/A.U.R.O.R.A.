# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What every part of aurora-api shares: configuration, logs, the activity feed and notifications,
authentication (key, devices, lockout), the answer pipeline, runs (one at a time) and the facts Aurora knows about
herself. The chat's routing (tools, pictures, videos) is in core_route, re-exported here."""
from __future__ import annotations

import asyncio
import httpx
import secrets
import subprocess
import threading
import time
import uuid

from collections import OrderedDict
from pathlib import Path
from aurora import sol_reader, sys_config, sys_context, sys_features, sys_log
from aurora.sys_devices import COOKIE, Devices
from fastapi import HTTPException, Request

BASE = sys_config.get()                         # the admin's view (or the single owner's, before the migration)


class _UserConfig:
    """The `cfg` every module of the API shares: the configuration of the user whose request is being served
    (sys_context, set by `auth`: their settings, folders, state); the admin's for work without a user (U3)."""

    __slots__ = ()

    @staticmethod
    def now() -> sys_config.Config:
        return sys_config.get()                       # context-aware: the request's user, else the admin's view

    def __getattr__(self, name):
        return getattr(self.now(), name)

    def __getitem__(self, key):
        return self.now()[key]


cfg = _UserConfig()
devices = Devices(BASE)
log = sys_log.get_logger("api")
WEBUI = Path(__file__).resolve().parents[2] / "webui"     # sys/core/webui
_run_lock = threading.Lock()                    # one run at a time: one reasoner slot
_runs: "OrderedDict[str, dict]" = OrderedDict()
_state: dict = {}
MAX_RUNS = 200
STARTED = time.time()
# Activity feed: every run that starts or ends, and notes from the services (harvester...).
# The WebUI follows it, so what Aurora does on her own is visible live in the chat.
_activity: list[dict] = []
_activity_cond = threading.Condition()
MAX_ACTIVITY = 1000


def note(source: str, event: str, payload: dict | None = None) -> dict:
    """An item of the activity feed, the user's whose work it is (none given: the admin's); each user sees theirs."""
    with _activity_cond:
        seq = (_activity[-1]["seq"] + 1) if _activity else 1
        item = {"seq": seq, "ts": time.time(), "source": source, "event": event, "payload": payload or {},
                "user": sys_context.user() or _admin()}
        _activity.append(item)
        del _activity[:-MAX_ACTIVITY]
        _activity_cond.notify_all()
    _push(event, item["payload"])
    return item


_TOLD = {"cloud.budget": "provider", "cloud.fallback": "provider", "plugin.refused": "plugin"}
_told_at: dict = {}


def _from_trace(component: str, event: str, payload: dict) -> None:
    """Trace events nobody was told of (the cloud ceiling, a failing provider, a plugin stopped): a notification,
    once an hour per event and provider/plugin (owner, 2026-10-04)."""
    if event not in _TOLD:
        return
    key = (event, str(payload.get(_TOLD[event], "")))
    if time.time() - _told_at.get(key, 0) < 3600:
        return
    _told_at[key] = time.time()
    text = {"cloud.budget": lambda p: f"{p.get('provider')}: {p.get('spent')} / {p.get('cap')} token",
            "cloud.fallback": lambda p: f"{p.get('provider')} ({p.get('role')}): {str(p.get('error', ''))[:120]}",
            "plugin.refused": lambda p: f"{p.get('plugin')}.{p.get('tool')}"}[event](payload)
    with sys_context.acting_as(_admin()):            # the machine's news: the admin's, whoever's call it was
        note(component, event, {**payload, "text": text})


sys_log.on_trace(_from_trace)


def _push(event: str, payload: dict) -> None:
    """Events the owner chose (Notifications page) become a toast in the WebUI and/or a push to the devices."""
    from aurora import sys_push
    try:
        toast = sys_push.message(event, payload, cfg, "webui")
        msg = sys_push.message(event, payload, cfg, "push")
    except Exception:
        log.exception("notification for %s", event)
        return
    if (toast or msg) and event != "test":           # kept for the Notifications page's history
        try:
            sys_push.remember(toast or msg, event, [c for c, m in (("webui", toast), ("push", msg)) if m], cfg)
        except OSError:
            log.exception("notification history")
    if toast and event != "test":
        note("notify", "notify", toast)              # the WebUI shows it (alerts widget); "notify" itself is not in TEXTS
    if msg and sys_push.count(cfg):
        sys_context.start(sys_push.send, msg, cfg.now(), name="push")     # to the devices of the event's user




async def in_thread(fn, *args):
    """asyncio.to_thread for a job that may read the vault: the pooled thread lives on, its connections are
    closed at the end of the job (C103)."""
    def job():
        try:
            return fn(*args)
        finally:
            sol_reader.release()
    return await asyncio.to_thread(job)


async def quiet(stream):
    """An SSE generator that ends silently when cancelled (client gone, service stopping)."""
    try:
        async for item in stream:
            yield item
    except asyncio.CancelledError:
        return


# ---- helpers ---------------------------------------------------------------------------
def _is_key(token: str) -> bool:
    return bool(token) and secrets.compare_digest(token.encode(), str(cfg["AURORA_API_KEY"]).encode())


# Failed logins per client address: after AURORA_AUTH_MAX_FAILS in AURORA_AUTH_WINDOW_S the address is refused
# for the same window (429), and the owner is told (a security incident notification). A direct loopback
# caller (no proxy header) is never counted nor locked: Aurora's own services live there, and a 256-bit key
# cannot be guessed by trying; remote clients always come through Caddy and keep the lockout.
_fails: dict[str, list[float]] = {}
_fails_lock = threading.Lock()


def _client(request: Request) -> str:
    """The caller's address; behind Caddy (a local proxy) the first X-Forwarded-For is the real one."""
    peer = request.client.host if request.client else "?"
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if peer in ("127.0.0.1", "::1") and fwd else peer


def via_tunnel(ip: str) -> bool:
    """A caller that reached Caddy from one of this machine's own non-loopback addresses: a Cloudflare tunnel
    (cloudflared connects from here, every remote device the same address) or a browser on this computer."""
    from aurora import sec_fwapi
    return not ip.startswith("127.") and ip != "::1" and ip in sec_fwapi._own_addresses()


def _local(request: Request) -> bool:
    peer = request.client.host if request.client else "?"
    return peer in ("127.0.0.1", "::1") and not request.headers.get("x-forwarded-for")


def _locked(request: Request) -> None:
    if _local(request):
        return
    now, ip = time.time(), _client(request)
    with _fails_lock:
        recent = [t for t in _fails.get(ip, []) if now - t < cfg["AURORA_AUTH_WINDOW_S"]]
        _fails[ip] = recent
    if len(recent) >= cfg["AURORA_AUTH_MAX_FAILS"]:
        raise HTTPException(status_code=429, detail="too many failed attempts: try again later")


def _failed(request: Request) -> None:
    if _local(request):
        log.warning("audit: wrong credential from a local process (not counted for the lockout)")
        return
    ip = _client(request)
    with _fails_lock:
        _fails.setdefault(ip, []).append(time.time())
        n = len(_fails[ip])
    if n == cfg["AURORA_AUTH_MAX_FAILS"]:
        tunnel = via_tunnel(ip)                           # every remote device shares it: said, and never firewalled
        log.warning("audit: %d failed logins from %s%s: refused for %d s", n, ip, " (tunnel or this machine)" if tunnel
                    else "", cfg["AURORA_AUTH_WINDOW_S"])
        note("security", "auth.lockout", {"title": f"{n} tentativi di accesso falliti da {ip}" + (
            " — dal tunnel Cloudflare o da questo computer: chi è fuori casa resta fuori per qualche minuto" if tunnel else ""),
            "ip": ip})
        if tunnel:
            return

        def keep_out():                                   # and off this machine for hours (sec_hostfw), if installed
            from aurora import sec_hostfw
            r = sec_hostfw.block(cfg, ip, f"{n} credenziali sbagliate")
            if r.get("ok"):
                note("security", "hostfw.block", {"title": f"🧱 {ip} bloccato sul computer di Aurora", "text": "login falliti"})
        threading.Thread(target=keep_out, name="hostfw", daemon=True).start()


async def auth(request: Request) -> None:
    """The API key (third-party clients) or a registered device (WebUI cookie). Async on purpose: the user it sets
    (sys_context) stays in the request's context, where the route runs (a sync dependency runs in another thread)."""
    _locked(request)
    bearer = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if _is_key(bearer):
        request.state.device = None
        request.state.user = _admin()                    # the API key is the admin's (third-party clients)
        sys_context.CURRENT.set(request.state.user)
        return
    dev = devices.check(bearer) or devices.check(request.cookies.get(COOKIE, ""))
    if dev is None:
        if bearer or request.cookies.get(COOKIE):              # a wrong credential, not a page asking who we are
            _failed(request)
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    request.state.device = dev
    request.state.user = dev.get("user") or _admin()   # a device made before multi-user is the admin's
    sys_context.CURRENT.set(request.state.user)


def _admin() -> str | None:
    """The admin's name; None while the installation has no users (today's layout: every path as before)."""
    from aurora.sys_users import Users
    return Users(BASE.base or BASE).admin_name()


def user_of(request: Request) -> str | None:
    return getattr(request.state, "user", None)


_NOBODY = object()


def plugin_host(user=_NOBODY):
    """One plugin host per user for the whole API: the plugins are everyone's, their settings and folders the
    user's (sys_user_config.for_user; before the migration the same for all). Its cache of tool lists lasts as long
    as the service, so listing the plugins does not start every plugin again (the Plugins page took 3.8 s)."""
    user = (sys_context.user() or _admin()) if user is _NOBODY else user
    hosts = _state.setdefault("plugin_hosts", {})
    if user not in hosts:
        from aurora import sys_user_config
        from aurora.plg_access import UserPluginHost
        from aurora.plg_host import PluginHost
        cls = UserPluginHost if user and user != _admin() else PluginHost    # the admin's plugins: not for users
        hosts[user] = cls(sys_user_config.for_user(BASE, user) if user else BASE)
    return hosts[user]


def pipeline(user=_NOBODY):
    """The answer pipeline of a user (their memory and conversations); every user's shares the models and the
    knowledge index of the first. No user: today's single owner (multi-user, U3)."""
    user = (sys_context.user() or _admin()) if user is _NOBODY else user
    pipes = _state.setdefault("pipelines", {})
    if user not in pipes:
        from aurora import sys_user_config
        from aurora.kno_answer import Pipeline
        from aurora.mdl_remote import RemoteEmbedder, RemoteReranker
        first = next(iter(pipes.values()), None)
        ucfg = sys_user_config.for_user(BASE, user) if user else BASE    # fixed: also used outside a request
        pipes[user] = Pipeline(RemoteEmbedder(ucfg), RemoteReranker(ucfg), ucfg, state_fn=self_facts, user=user,
                               index=first.search.index if first else None)
    return pipes[user]


def self_facts() -> dict:
    """Aurora's state as measured by the API now: services, uptime, GPU memory."""
    import subprocess
    import httpx
    facts = {"api_uptime_minutes": round((time.time() - STARTED) / 60), "runs_served": len(_runs)}
    from aurora import kno_mood                        # 💗 how she feels, measured at the REM's last look (roadmap 52)
    facts["my_emotions_measured"] = kno_mood.compact(kno_mood.last(cfg))
    try:
        from aurora import sys_health
        h = health_all()
        facts["health"] = {"level": h["level"], "problems": h["problems"] or "none"}
    except Exception as e:                            # never break an answer for a health check
        facts["health"] = f"not measured ({type(e).__name__})"
    for name, url in (("models_service", f"http://{cfg['AURORA_MODELS_HOST']}:{cfg['AURORA_MODELS_PORT']}/health"),
                      ("reasoner_service", f"http://{cfg['AURORA_LLM_HOST']}:{cfg['AURORA_LLM_PORT']}/health")):
        try:
            facts[name] = httpx.get(url, timeout=2).json().get("status", "?")
        except httpx.HTTPError:
            facts[name] = "down"
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout
        facts["gpu_memory_mib"] = {f"gpu{i.strip()}": f"{u.strip()}/{t.strip()}" for i, u, t in
                                   (l.split(",") for l in out.strip().splitlines())}
    except (OSError, subprocess.SubprocessError, ValueError):
        facts["gpu_memory_mib"] = "not measured"
    return facts


def text_of(content) -> str:
    """OpenAI message content: a string or a list of parts; only text parts are read for now."""
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text", "") for p in content or [] if isinstance(p, dict) and p.get("type") == "text")


def start_run(question: str, origin: str, job=None) -> dict:
    """Run `job(question, emit, run_id)` (default: the answer pipeline) in the background, one at a time."""
    run = {"id": uuid.uuid4().hex[:12], "question": question, "origin": origin, "started": time.time(),
           "events": [], "done": False, "answer": None, "cond": threading.Condition(),
           "user": sys_context.user() or _admin()}                   # whose run: only they follow it
    _runs[run["id"]] = run
    while len(_runs) > MAX_RUNS:
        _runs.popitem(last=False)
    from aurora import mdl_tts                            # the answer first: the natural voice leaves the GPU (C173)
    if not mdl_tts.BUSY:
        mdl_tts.BUSY.append(lambda: any(not r["done"] for r in list(_runs.values())))
    threading.Thread(target=mdl_tts.release, daemon=True, name="tts-release").start()
    note(origin, "run.begin", {"run_id": run["id"], "question": question, "origin": origin})

    from aurora import sys_runs

    def emit(event: str, payload: dict) -> None:          # only the run's own end ends it (C166, sys_runs)
        sys_runs.emit(run, event, payload)

    def work() -> None:
        with _run_lock:
            try:
                work_fn = job or (lambda q, emit, run_id: pipeline().run(q, emit=emit, run_id=run_id))
                run["answer"] = work_fn(question, emit, run["id"])
            except sys_features.Missing as e:             # a model or setting this installation lacks: say what to do
                log.info("run %s: %s", run["id"], e)
                emit("feature.missing", {"feature": e.feature})
                emit("answer.final", {"text": f"⚠️ {e}", "abstained": False, "sources": [], "seconds": 0.0, "mode": "missing"})
                emit("run.end", {"seconds": round(time.time() - run["started"], 1)})
            except Exception as e:                        # the run fails visibly, never silently
                log.exception("run %s failed", run["id"])
                emit("error", {"message": f"{type(e).__name__}: {e}"})
                from .agents import react                    # a request of the owner failed: diagnosed now
                react(origin, question, f"{type(e).__name__}: {e}", run["id"])
            finally:
                sol_reader.release()                      # this thread's vault connections, now (C103)
                sys_runs.end(run)
                note(origin, "run.end", {"run_id": run["id"], "origin": origin,
                                         "seconds": round(time.time() - run["started"], 1)})

    sys_context.start(work, name=f"run-{run['id']}")                 # the run works for the request's user
    return run


def everyone() -> list:
    """Every user's name (the admin first); [None] while the installation has no users: today's single owner."""
    from aurora.sys_users import Users
    base = BASE.base or BASE
    if not base.path("AURORA_STATUS_DIR").joinpath("users.db").exists():
        return [None]
    admin = _admin()
    names = [u["name"] for u in Users(base).list()]
    return sorted(names, key=lambda n: n != admin) or [None]


def me() -> str | None:
    """The user of the request being served (the admin for the API key and for work without a user)."""
    return sys_context.user() or _admin()


def mine(item: dict, who: str | None = None) -> bool:
    """An activity item or a run of this user's: nobody follows another user's questions, answers or notes."""
    return item.get("user") == (who if who is not None else me())


def own_run(run_id: str) -> dict:
    run = _runs.get(run_id)
    if not run or not mine(run):
        raise HTTPException(status_code=404, detail="unknown run")
    return run


def wait_events(run: dict, after: int, timeout: float = 15.0) -> tuple[list[dict], bool]:
    with run["cond"]:
        if len(run["events"]) <= after and not run["done"]:
            run["cond"].wait(timeout)
        return run["events"][after:], run["done"]


LABELS = {"acquire.confirmed": "🛰️", "acquire.round": "🛰️", "acquire.paper": "📥", "route": "🧭", "self.state": "🩺", "attach.image": "🖼️", "attach.document": "📄", "translate": "🌐", "retrieval.hits": "🔎", "retrieval.filter": "🧹", "memory.recent": "🧠", "gate": "🚪",
          "synthesis.domain": "🧩", "verify.keep": "✅", "verify.drop": "✂️", "memory.write": "💾", "error": "⛔"}


def trace_line(e: dict) -> str | None:
    """One readable line per event, for the reasoning panel of third-party clients."""
    p, name = e["payload"], e["event"]
    icon = LABELS.get(name)
    if name == "synthesis.delta":
        return p["text"] if p["kind"] == "thought" else None
    if name == "route":
        return f"{icon} {'domanda su di me' if p['mode'] == 'self' else 'domanda di conoscenza'}\n"
    if name == "translate":
        return f"{icon} traduzione: {p['translation']}\n"
    if name == "retrieval.hits":
        return f"{icon} {len(p['hits'])} passaggi: " + ", ".join(f"[{h['n']}] {h['domain']}" for h in p["hits"]) + "\n"
    if name == "gate":
        return f"{icon} cancello {'aperto: ' + str(p['passages']) if p['open'] else 'chiuso: nessun passaggio risponde'}\n"
    if name == "synthesis.domain":
        return f"{icon} {p['domain']}: {'estratto' if p['kept'] else 'niente di rilevante'}\n"
    if name in ("verify.drop",):
        return f"{icon} tolta: {p['sentence'][:120]} ({p['reason']})\n"
    if icon:
        return f"{icon} {name}\n"
    return None


def final_text(ans) -> str:
    if ans is None:
        return "Si è verificato un errore: vedi la traccia."
    text = ans.text
    if ans.sources:
        text += "\n\nFonti:\n" + "\n".join(f"[{s['n']}] {s['title'] or s['source']} ({s['domain']})" for s in ans.sources)
    return text


# names of sibling modules, looked up only when called: imported last, so that modules that use each
# other (routines, forge, agents) load in any order
from .activity import health_all  # noqa: E402
from .core_route import (answer_or_acquire, edit_pictures, gpu_busy, make_video, picture_intent,  # noqa: E402,F401
                         shadow_answer, video_busy_answer, wants_tools)
