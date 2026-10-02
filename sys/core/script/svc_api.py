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

import asyncio
import base64
import binascii
import io
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from aurora import sys_config, sys_log  # noqa: E402
from aurora.sys_devices import COOKIE, Devices  # noqa: E402

cfg = sys_config.get()
devices = Devices(cfg)
log = sys_log.get_logger("api")
WEBUI = Path(__file__).resolve().parents[1] / "webui"
app = FastAPI(title="Aurora", docs_url=None, redoc_url=None)
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
    with _activity_cond:
        seq = (_activity[-1]["seq"] + 1) if _activity else 1
        item = {"seq": seq, "ts": time.time(), "source": source, "event": event, "payload": payload or {}}
        _activity.append(item)
        del _activity[:-MAX_ACTIVITY]
        _activity_cond.notify_all()
    _push(event, item["payload"])
    return item


def _push(event: str, payload: dict) -> None:
    """Events the owner chose (Notifications page) become a toast in the WebUI and/or a push to the devices."""
    from aurora import sys_push
    try:
        toast = sys_push.message(event, payload, cfg, "webui")
        msg = sys_push.message(event, payload, cfg, "push")
    except Exception:
        log.exception("notification for %s", event)
        return
    if toast and event != "test":
        note("notify", "notify", toast)              # the WebUI shows it (alerts widget); "notify" itself is not in TEXTS
    if msg and sys_push.count(cfg):
        threading.Thread(target=sys_push.send, args=(msg, cfg), name="push", daemon=True).start()


@app.exception_handler(httpx.HTTPError)
async def upstream_down(request: Request, exc: httpx.HTTPError) -> JSONResponse:
    """A service Aurora depends on (models, reasoner) is not reachable: 503, retry later."""
    log.warning("upstream unavailable on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": f"a service is not reachable: {exc}"})


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
        log.warning("audit: %d failed logins from %s: refused for %d s", n, ip, cfg["AURORA_AUTH_WINDOW_S"])
        note("security", "auth.lockout", {"title": f"{n} tentativi di accesso falliti da {ip}", "ip": ip})


def auth(request: Request) -> None:
    """The API key (third-party clients) or a registered device (WebUI cookie)."""
    _locked(request)
    bearer = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if _is_key(bearer):
        request.state.device = None
        return
    dev = devices.check(bearer) or devices.check(request.cookies.get(COOKIE, ""))
    if dev is None:
        if bearer or request.cookies.get(COOKIE):              # a wrong credential, not a page asking who we are
            _failed(request)
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    request.state.device = dev


def pipeline():
    if "pipeline" not in _state:
        from aurora.kno_answer import Pipeline
        from aurora.mdl_remote import RemoteEmbedder, RemoteReranker
        _state["pipeline"] = Pipeline(RemoteEmbedder(cfg), RemoteReranker(cfg), cfg, state_fn=self_facts)
    return _state["pipeline"]


SYS_CONFIRM = ("Aurora could not answer the owner's previous question from her vault and offered to search "
               "external sources. Does the owner's new message ask or agree to go and search (yes, search, go ahead, "
               "procedi, cerca, vai)? Reply YES or NO only.")


SYS_TOOLS = ("Decide whether the owner's last message asks Aurora to use one of her CONNECTED SERVICES (listed below) "
             "to read live data there or to do something there: e.g. look at his repositories, their issues or "
             "statistics, his e-mail, the house, the files of a project, take a photo, check an IP address. Reply TOOLS "
             "if so. Reply NO if it is small talk, a question about Aurora herself, or a question about knowledge of the "
             "world (science, law, medicine, history, definitions, how something works) that a knowledge base answers. "
             "Examples: 'controlla i miei repository su GitHub' TOOLS; 'quante stelle ha il mio progetto?' TOOLS; "
             "'ho nuove mail?' TOOLS; 'mostrami i file del progetto aurora-site' TOOLS; 'cos'è un repository git?' NO; "
             "'come funziona una pull request?' NO; 'cosa dice l'articolo 2043 del codice civile?' NO; 'come stai?' NO. "
             "Reply with exactly one word.\n\nCONNECTED SERVICES:\n{services}")
ROUTER_SKIP = {"web", "self"}          # web search is the knowledge path's job; "self" is Aurora's own maintenance


def connected_services() -> list[str]:
    """The plugins the owner has connected (enabled, configured, no error): what the chat may hand to the agent."""
    from aurora.plg_host import PluginHost
    return [f"- {p.name}: {(p.manifest.get('description') or {}).get('en', '')[:200]}"
            for p in PluginHost(cfg).plugins(with_tools=False) if p.available and p.name not in ROUTER_SKIP]


def wants_tools(question: str, recent: list, emit=None) -> bool:
    services = connected_services()
    if not services:
        return False
    prev = "\n".join(f"{'Owner' if t.extra.get('role') == 'user' else 'Aurora'}: {t.text[:300]}" for t in recent[-2:])
    out = pipeline()._for("route").complete(SYS_TOOLS.replace("{services}", "\n".join(services)),
                                  (f"PREVIOUS TURNS:\n{prev}\n\n" if prev else "") + f"LAST MESSAGE: {question}", 4)
    if emit:
        emit("route.tools", {"services": [x[2:].split(":")[0] for x in services], "reply": out.answer.strip()[:20]})
    return out.answer.strip().upper().startswith("TOOLS")


def picture_intent(question: str) -> str:
    """edit | look | other, for a message when a picture is in the conversation."""
    from aurora.img_edit import SYS_EDIT
    out = pipeline()._for("route").complete(SYS_EDIT, question, 3).answer.strip().upper()
    return "edit" if out.startswith("EDIT") else "look" if out.startswith("LOOK") else "other"


def last_picture(recent: list) -> tuple[str, bytes] | None:
    """The latest picture of the conversation (Aurora's last edit first, then the owner's): what "now make it
    brighter" refers to, without attaching it again."""
    from aurora import sys_uploads
    files = sys_uploads.by_run(cfg, {t.extra.get("run_id") for t in recent[-6:]} - {None})
    for t in reversed(recent[-6:]):
        for f in sorted(files.get(t.extra.get("run_id"), []), key=lambda f: f["role"] != "assistant"):
            found = sys_uploads.get(cfg, f["id"]) if f["inline"] and f["mime"].startswith("image/") else None
            if found:
                return f["name"], found[0].read_bytes()
    return None


def _run_picture_ops(data: bytes, ops: list[dict], emit, name: str, lang: str) -> tuple[bytes, str, dict]:
    """The planned operations in order: plain ones with Pillow (in runs), the others with an image model in its own
    process (mdl_image.gpu_job: FLUX.2 klein on the GPU, Swin2SR, SAM 2.1). A picture changed by FLUX.2 carries the
    AI disclosure (EU AI Act art. 50)."""
    from PIL import Image
    from aurora import img_edit, mdl_image, sys_disclosure
    cur, mime, plain, creative = data, None, [], False

    def flush():
        nonlocal cur, mime, plain
        if plain:
            cur, mime, _ = img_edit.apply(cur, plain)
            plain = []
    for o in ops:
        if o["op"] not in img_edit.AI_OPS:
            plain.append(o)
            continue
        flush()
        if o["op"] == "creative":
            cur, st = mdl_image.gpu_job("edit", cur, cfg, emit, need_gb=9, prompt=o["prompt"])
            creative = True
        elif o["op"] == "upscale":
            big = max(Image.open(io.BytesIO(cur)).size) > 400        # small pictures are quick on the CPU
            cur, st = mdl_image.gpu_job("upscale", cur, cfg, emit, need_gb=3 if big else 0, scale=o["scale"])
        else:
            cur, st = mdl_image.gpu_job("cutout", cur, cfg, emit)
        mime = "image/png"
        emit("image.model", {"op": o["op"], **st})
    flush()
    img = Image.open(io.BytesIO(cur))
    if creative:
        cur, mime = sys_disclosure.mark_image(img, name, lang, cfg), "image/png"
        img = Image.open(io.BytesIO(cur))
    return cur, mime or Image.MIME.get(img.format, "image/png"), {"width": img.width, "height": img.height}


def edit_pictures(question: str, pictures: list[tuple[str, bytes]], emit, run_id: str, remember: bool = True):
    """Each picture edited as asked (img_edit: a checked list of operations, Pillow); the results are new files of
    the conversation, shown in Aurora's bubble. The originals are never touched."""
    from pathlib import Path
    from aurora import img_edit, sys_uploads
    from aurora.kno_answer import Answer
    from aurora.sol_schema import now_iso
    asked_at, t0 = now_iso(), time.time()
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    from PIL import Image
    p, lines, images = pipeline(), [], []
    for name, data in pictures:
        w, h = Image.open(io.BytesIO(data)).size
        ops = img_edit.plan(p.llm, question, w, h)
        emit("image.plan", {"name": name, "ops": ops})
        if not ops:
            lines.append(f"{name}: " + ("non ho capito quale modifica fare." if lang == "it" else "I did not understand what to change."))
            continue
        out, mime, size = _run_picture_ops(data, ops, emit, name, lang)
        ext = mime.split("/")[1].replace("jpeg", "jpg")
        stem = re.sub(r"(-(modificata|edited))+$", "", Path(name).stem)          # not -modificata-modificata
        new = f"{stem}-{'modificata' if lang == 'it' else 'edited'}.{ext}"
        url = sys_uploads.public(sys_uploads.save(cfg, run_id, new, mime, out, role="assistant"))["url"] if remember else ""
        emit("image.edited", {"name": new, "url": url, "ops": ops, "width": size["width"], "height": size["height"]})
        images.append({"name": new, "url": url, "mime": mime, "inline": True})
        lines.append(f"{new}: {img_edit.describe(ops, lang)} ({size['width']}×{size['height']}).")
    ans = Answer(run_id, question, ("Ecco: " if lang == "it" else "Here it is: ") + " ".join(lines), False, mode="edit",
                 seconds=round(time.time() - t0, 1))
    emit("answer.final", {"text": ans.text, "abstained": False, "sources": [], "seconds": ans.seconds, "mode": "edit",
                          "images": images})
    if remember:
        p.remember(question, ans, run_id, emit, None, asked_at)
    emit("run.end", {"seconds": ans.seconds})
    return ans


def answer_or_acquire(question: str, emit, run_id: str, **kw):
    """The default job of a message. When Aurora's last answer in this session was an abstention and the
    message asks her to go and search, the arXiv agent works on the *previous* question (A11: the
    same for the WebUI and third-party clients, which have no button)."""
    from datetime import datetime, timezone
    p = pipeline()
    recent = p.reader.recent(6)
    pic = None if kw.get("attached") else last_picture(recent)
    intent = picture_intent(question) if pic else "other"
    if intent == "edit":                              # "ora rendila più luminosa": the latest picture, edited again
        return edit_pictures(question, [pic], emit, run_id)
    if intent == "look":                              # "cosa mostra?": the latest picture, looked at again
        from aurora.kno_attach import AttachmentHandler
        attached = AttachmentHandler(p, cfg).prepare([(pic[0], pic[1], "image/jpeg")], question, emit, run_id)
        return p.run(question, emit=emit, run_id=run_id, attached=attached)
    recent = recent[-4:]
    # a request about a connected service (GitHub, e-mail, the house...) goes to the agent, before anything else:
    # also right after an abstention, where "check my repositories" is not a "yes, search arXiv"
    if not kw.get("attached") and wants_tools(question, recent, emit):     # a connected service, not the vault
        emit("route", {"mode": "tools"})
        context = "\n".join(f"{'Owner' if t.extra.get('role') == 'user' else 'Aurora'}: {t.text[:500]}" for t in recent[-4:])
        return _agent_job(question, context, remember=True, label=question)(question, emit, run_id)
    last = recent[-1] if recent else None
    if (last is not None and last.extra.get("role") == "assistant" and last.extra.get("abstained")
            and last.extra.get("mode", "knowledge") == "knowledge" and len(question) < 200
            and (datetime.now(timezone.utc) - datetime.fromisoformat(last.created_at)).total_seconds()
            < cfg["AURORA_REM_SESSION_GAP_MIN"] * 60):
        asked = next((t for t in recent if t.extra.get("role") == "user"
                      and t.extra.get("run_id") == last.extra.get("run_id")), None)
        if asked and p._for("route").complete(SYS_CONFIRM, f"PREVIOUS QUESTION: {asked.text}\nNEW MESSAGE: {question}",
                                    3).answer.strip().upper().startswith("YES"):
            from aurora.kno_acquire import ArxivAgent
            prev = asked.text.split(" [")[0]
            emit("acquire.confirmed", {"question": prev})
            return ArxivAgent(p, cfg).run(prev, emit, run_id)
    return p.run(question, emit=emit, run_id=run_id, **kw)


def self_facts() -> dict:
    """Aurora's state as measured by the API now: services, uptime, GPU memory."""
    import subprocess
    import httpx
    facts = {"api_uptime_minutes": round((time.time() - STARTED) / 60), "runs_served": len(_runs)}
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
           "events": [], "done": False, "answer": None, "cond": threading.Condition()}
    _runs[run["id"]] = run
    while len(_runs) > MAX_RUNS:
        _runs.popitem(last=False)
    note(origin, "run.begin", {"run_id": run["id"], "question": question, "origin": origin})

    def emit(event: str, payload: dict) -> None:
        with run["cond"]:
            run["events"].append({"seq": len(run["events"]) + 1, "ts": time.time(), "event": event, "payload": payload})
            run["cond"].notify_all()

    def work() -> None:
        with _run_lock:
            try:
                work_fn = job or (lambda q, emit, run_id: pipeline().run(q, emit=emit, run_id=run_id))
                run["answer"] = work_fn(question, emit, run["id"])
            except Exception as e:                        # the run fails visibly, never silently
                log.exception("run %s failed", run["id"])
                emit("error", {"message": f"{type(e).__name__}: {e}"})
            finally:
                with run["cond"]:
                    run["done"] = True
                    run["cond"].notify_all()
                note(origin, "run.end", {"run_id": run["id"], "origin": origin,
                                         "seconds": round(time.time() - run["started"], 1)})

    threading.Thread(target=work, name=f"run-{run['id']}", daemon=True).start()
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


# ---- OpenAI-compatible -------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/models", dependencies=[Depends(auth)])
def models() -> dict:
    return {"object": "list", "data": [{"id": "aurora", "object": "model", "owned_by": "aurora"}]}


@app.post("/v1/chat/completions", dependencies=[Depends(auth)])
async def chat_completions(request: Request):
    body = await request.json()
    users = [m for m in body.get("messages", []) if m.get("role") == "user"]
    if not users:
        raise HTTPException(status_code=400, detail="no user message")
    question = text_of(users[-1].get("content"))            # every message is the first one
    run = start_run(question, origin="openai", job=lambda q, emit, run_id: answer_or_acquire(q, emit, run_id))
    cid, created = f"chatcmpl-{run['id']}", int(time.time())

    def chunk(delta: dict, finish: str | None = None) -> str:
        return "data: " + json.dumps({"id": cid, "object": "chat.completion.chunk", "created": created, "model": "aurora",
                                      "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]},
                                     ensure_ascii=False) + "\n\n"

    if not body.get("stream"):
        after, reasoning = 0, []
        while True:
            events, done = await asyncio.to_thread(wait_events, run, after)
            after += len(events)
            reasoning += [line for e in events if (line := trace_line(e))]
            if done and after >= len(run["events"]):
                break
        return JSONResponse({"id": cid, "object": "chat.completion", "created": created, "model": "aurora",
                             "choices": [{"index": 0, "finish_reason": "stop",
                                          "message": {"role": "assistant", "content": final_text(run["answer"]),
                                                      "reasoning_content": "".join(reasoning)}}]})

    async def gen():
        yield chunk({"role": "assistant"})
        after = 0
        while True:
            events, done = await asyncio.to_thread(wait_events, run, after)
            after += len(events)
            for e in events:
                line = trace_line(e)
                if line:
                    yield chunk({"reasoning_content": line})
            if done and after >= len(run["events"]):
                break
        yield chunk({"content": final_text(run["answer"])})
        yield chunk({}, "stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(quiet(gen()), media_type="text/event-stream")


# ---- native: runs and events -----------------------------------------------------------------
@app.post("/v1/aurora/ask", dependencies=[Depends(auth)])
async def ask(request: Request) -> dict:
    """{"question": str, "attachments": [{"name", "mime", "data": base64}], "remember": true} -> {"run_id"}.

    "remember": false leaves the memory untouched (checks and tests must not become memories)."""
    body = await request.json()
    question = body.get("question", "").strip()
    remember = body.get("remember", True) is not False
    files = []
    if body.get("attachments"):
        from aurora.kno_attach import AttachmentHandler, is_image
        handler = AttachmentHandler(pipeline(), cfg)
        for a in body["attachments"]:
            name = os.path.basename(a.get("name") or "file")
            try:
                data = base64.b64decode(a.get("data", ""), validate=True)
                handler.check(name, data, a.get("mime", ""))
            except (binascii.Error, ValueError) as e:
                raise HTTPException(status_code=422, detail=str(e))
            files.append((name, data, a.get("mime", "")))
        if not question:
            question = ("Descrivi l'immagine." if all(is_image(n, m) for n, _, m in files)
                        else "Di cosa parla questo documento?")
    if not question:
        raise HTTPException(status_code=400, detail="empty question")
    def job(q, emit, run_id):
        attached = []
        if files and remember:                         # kept to show them again in the conversation (sys_uploads)
            from aurora import sys_uploads
            for name, data, mime in files:
                sys_uploads.save(cfg, run_id, name, mime, data)
        from aurora.kno_attach import is_image
        pictures = [(n, d) for n, d, m in files if is_image(n, m)]
        if pictures and picture_intent(q) == "edit":    # "ritagliala", "in bianco e nero": an edit, not a question
            return edit_pictures(q, pictures, emit, run_id, remember)
        if files:
            from aurora.kno_attach import AttachmentHandler
            attached = AttachmentHandler(pipeline(), cfg).prepare(files, q, emit, run_id)
        if attached or not remember:
            return pipeline().run(q, emit=emit, run_id=run_id, attached=attached, remember=remember)
        return answer_or_acquire(q, emit, run_id)
    return {"run_id": start_run(question, origin="webui", job=job)["id"]}


@app.post("/v1/aurora/acquire", dependencies=[Depends(auth)])
async def acquire(request: Request) -> dict:
    """An external action: the WebUI calls it only on the owner's click (AURORA_CONFIRM_EXTERNAL_ACTIONS)."""
    question = (await request.json()).get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="empty question")

    def job(q, emit, run_id):
        from aurora.kno_acquire import ArxivAgent
        return ArxivAgent(pipeline(), cfg).run(q, emit, run_id)
    return {"run_id": start_run(question, origin="acquire", job=job)["id"]}


@app.get("/v1/aurora/runs", dependencies=[Depends(auth)])
def runs() -> list[dict]:
    return [{"id": r["id"], "question": r["question"], "origin": r["origin"], "started": r["started"],
             "done": r["done"], "events": len(r["events"])} for r in reversed(_runs.values())]


@app.get("/v1/aurora/runs/{run_id}/events", dependencies=[Depends(auth)])
async def run_events(run_id: str, after: int = 0):
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="unknown run")

    async def gen():
        seen = after
        while True:
            events, done = await asyncio.to_thread(wait_events, run, seen)
            for e in events:
                yield f"data: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"
            seen += len(events)
            if done and seen >= len(run["events"]):
                yield "event: end\ndata: {}\n\n"
                break
    return StreamingResponse(quiet(gen()), media_type="text/event-stream")


# ---- knowledge import -------------------------------------------------------------------------
@app.get("/v1/aurora/domains", dependencies=[Depends(auth)])
def domains() -> list[dict]:
    from aurora.sol_schema import load_taxonomy
    return [d for d in load_taxonomy().values() if not d.get("memory")]


def _import(name: str, data: bytes, domain: str, title: str, origin: str = "upload", meta: dict | None = None) -> dict:
    from aurora.kno_ingest import Importer
    p = pipeline()
    with _run_lock:                                   # vault and index have one writer: this process
        rep = Importer(p.writer, p.indexer, cfg, llm=p.llm).add(name, data, domain, title, origin=origin, meta=meta)
    return {"name": rep.name, "source_id": rep.source_id, "domain": rep.domain, "chunks": rep.chunks,
            "written": rep.written, "duplicates": rep.duplicates, "rejected": rep.rejected, "indexed": rep.indexed}


@app.post("/v1/aurora/import", dependencies=[Depends(auth)])
async def import_document(request: Request) -> dict:
    body = await request.json()
    from aurora.sol_schema import load_taxonomy
    taxonomy = load_taxonomy()
    domain = body.get("domain", "")
    if domain not in taxonomy or taxonomy[domain].get("memory"):
        raise HTTPException(status_code=422, detail=f"unknown knowledge domain {domain!r}")
    try:
        data = base64.b64decode(body.get("data", ""), validate=True)
    except binascii.Error:
        raise HTTPException(status_code=422, detail="data is not valid base64")
    if not data:
        raise HTTPException(status_code=422, detail="empty document")
    try:
        return await asyncio.to_thread(_import, os.path.basename(body.get("name", "document.txt")), data, domain,
                                       body.get("title", "").strip(), body.get("origin", "upload"),
                                       {"licence": body.get("licence", ""), "url": body.get("url", "")})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _add_solitons(items: list[dict]) -> dict:
    from aurora.sol_schema import Soliton
    p = pipeline()
    sols = [Soliton.new(x["text"], x["domain"], "knowledge", x.get("lang") or "en", x["source_id"], x.get("title", ""),
                        chunk_index=int(x.get("chunk_index", 0)), chunk_count=int(x.get("chunk_count", 1)),
                        extra=x.get("extra") or {}) for x in items]
    with _run_lock:                                   # vault and index have one writer: this process
        rep = p.writer.add_many(sols)
        indexed = {d: p.indexer.update(d) for d in sorted({s.domain for s in sols})} if rep.written else {}
    return {"received": len(items), "written": len(rep.written), "duplicates": len(rep.duplicates),
            "rejected": rep.rejected, "indexed": indexed}


@app.post("/v1/aurora/solitons", dependencies=[Depends(auth)])
async def add_solitons(request: Request) -> dict:
    items = (await request.json()).get("items", [])
    from aurora.sol_schema import load_taxonomy
    taxonomy = load_taxonomy()
    bad = sorted({x.get("domain") for x in items if x.get("domain") not in taxonomy or taxonomy[x["domain"]].get("memory")})
    if bad:
        raise HTTPException(status_code=422, detail=f"not knowledge domains: {bad}")
    if any(not x.get("source_id") for x in items):
        raise HTTPException(status_code=422, detail="every item needs a source_id")
    # an empty or invalid text is not an error of the batch: the writer rejects that soliton and reports it
    return await asyncio.to_thread(_add_solitons, items)


@app.delete("/v1/aurora/sources", dependencies=[Depends(auth)])
async def remove_source(domain: str, source_id: str) -> dict:
    from aurora.sol_schema import load_taxonomy
    if domain not in load_taxonomy():
        raise HTTPException(status_code=422, detail=f"unknown domain {domain!r}")

    def work():
        p = pipeline()
        with _run_lock:
            sids = p.writer.remove_source(domain, source_id)
            return {"domain": domain, "source_id": source_id, "removed": len(sids),
                    "index_rows_removed": p.indexer.drop(domain, sids)}
    out = await asyncio.to_thread(work)
    if not out["removed"]:
        raise HTTPException(status_code=404, detail="no solitons of that source in that domain")
    return out


@app.post("/v1/aurora/memory/reset", dependencies=[Depends(auth)])
async def reset_memory(request: Request) -> dict:
    if (await request.json()).get("confirm") is not True:
        raise HTTPException(status_code=400, detail='send {"confirm": true}: this deletes every conversation')

    def work():
        with _run_lock:
            files = pipeline().writer.reset_memory(confirm=True)
            _state.pop("pipeline", None)          # readers and indexes start again from the new state
            from aurora import sys_uploads
            uploads = sys_uploads.purge(cfg, set(), grace=0)     # no turn left: no attached file either
            return {"files_removed": files, "uploads_removed": len(uploads)}
    return await asyncio.to_thread(work)


@app.get("/v1/aurora/history", dependencies=[Depends(auth)])
def history(n: int = 8) -> list[dict]:
    turns = pipeline().reader.recent(max(0, min(n, 100)))
    items = [{"sid": t.sid, "role": t.extra.get("role"), "text": t.text, "created_at": t.created_at,
             "run_id": t.extra.get("run_id"), "abstained": t.extra.get("abstained", False),
             "mode": t.extra.get("mode"), "seconds": t.extra.get("seconds"), "speed": t.extra.get("speed"),
             "sources": t.extra.get("source_list", []), "trace": t.extra.get("trace", []),
             "thought": t.extra.get("thought", ""), "long_term": t.consolidated} for t in turns]
    from aurora import sys_uploads
    files = sys_uploads.by_run(cfg, {i["run_id"] for i in items if i["run_id"]})
    for i in items:                                   # the owner's files with his turn, Aurora's (edits) with hers
        i["attachments"] = [f for f in files.get(i["run_id"], []) if f["role"] == ("user" if i["role"] == "user" else "assistant")]
    return sorted(items + recent_dreams(), key=lambda x: x["created_at"])          # same UTC ISO format


@app.get("/v1/aurora/uploads", dependencies=[Depends(auth)])
def uploads_list() -> dict:
    from aurora import sys_uploads
    return {"files": sys_uploads.all_uploads(cfg), "total_bytes": sys_uploads.total_bytes(cfg),
            "keep_days": cfg["AURORA_UPLOADS_KEEP_DAYS"]}


@app.get("/v1/aurora/uploads/{uid}", dependencies=[Depends(auth)])
def upload_get(uid: str):
    """Images, videos and audio inline; anything else only as a download (an HTML or SVG never runs here)."""
    from fastapi.responses import FileResponse
    from aurora import sys_uploads
    found = sys_uploads.get(cfg, uid) if re.fullmatch(r"[0-9a-f]{16}", uid) else None
    if found is None:
        raise HTTPException(status_code=404, detail="no such file")
    path, item = found
    inline = bool(sys_uploads.INLINE.match(item["mime"]))
    return FileResponse(path, media_type=item["mime"] if inline else "application/octet-stream",
                        filename=item["name"], content_disposition_type="inline" if inline else "attachment",
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox",
                                 "Cache-Control": "private, max-age=86400"})


@app.delete("/v1/aurora/uploads/{uid}", dependencies=[Depends(auth)])
def upload_delete(uid: str) -> dict:
    from aurora import sys_uploads
    if not sys_uploads.delete(cfg, uid):
        raise HTTPException(status_code=404, detail="no such file")
    log.info("audit: owner deleted an attached file (%s)", uid)
    return {"deleted": uid}


@app.post("/v1/aurora/uploads/purge", dependencies=[Depends(auth)])
def uploads_purge() -> dict:
    """aurora-rem, daily: files whose conversation turn is gone, and those older than AURORA_UPLOADS_KEEP_DAYS."""
    from aurora import sys_uploads
    live = {t.extra.get("run_id") for t in pipeline().reader.recent(1_000_000)} - {None}
    removed = sys_uploads.purge(cfg, live)
    if removed:
        log.info("uploads purge: %d files removed", len(removed))
    return {"removed": len(removed)}


def recent_dreams() -> list[dict]:
    """Last nights' dreams, shown in the chat among the turns (AURORA_CHAT_DREAM_HOURS; 0 = never)."""
    from datetime import datetime, timedelta, timezone
    hours = cfg["AURORA_CHAT_DREAM_HOURS"]
    if not hours:
        return []
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    dreams = [d for d in pipeline().reader.recent(100, domain="reflection")
              if d.extra.get("type") == "dream" and datetime.fromisoformat(d.created_at) >= since]
    return [{"sid": d.sid, "role": "dream", "text": d.text, "created_at": d.created_at,
             "image": f"/v1/aurora/images/{d.extra['image']}" if d.extra.get("image") else None,
             "image_prompt": d.extra.get("image_prompt", "")} for d in dreams[-2:]]


@app.get("/v1/aurora/senses/devices", dependencies=[Depends(auth)])
def senses_devices() -> dict:
    from aurora import sns_av
    return {**sns_av.devices(), "camera": cfg["AURORA_SENSES_CAMERA"], "microphone": cfg["AURORA_SENSES_MIC"]}


@app.post("/v1/aurora/senses/{action}", dependencies=[Depends(auth)])
async def senses_action(action: str, request: Request) -> dict:
    """The owner's own click in the WebUI (📷, 🎙️): consent is the click itself, no approval needed."""
    from aurora import sns_av
    try:
        if action == "photo":
            jpeg = await asyncio.to_thread(sns_av.photo, cfg)
            log.info("audit: owner took a photo from the camera (%d bytes)", len(jpeg))
            return {"name": time.strftime("camera-%Y%m%d-%H%M%S.jpg"), "mime": "image/jpeg",
                    "data": base64.b64encode(jpeg).decode("ascii")}
        if action == "listen":
            seconds = float((await request.json()).get("seconds", 6))
            audio = await asyncio.to_thread(sns_av.record, seconds, cfg)
            out = await asyncio.to_thread(sns_av.transcribe, audio, str(cfg["AURORA_LANG_DEFAULT"])[:2], cfg)
            log.info("audit: owner dictated %.1f s (clear: %s)", out["audio_s"], out["clear"])
            return out
        if action == "transcribe":                       # the owner's own device (phone, PC browser) recorded it
            body = await request.json()
            try:
                data = base64.b64decode(str(body.get("data", "")), validate=True)
            except binascii.Error:
                raise HTTPException(status_code=422, detail="data is not valid base64")
            if not data or len(data) > 20 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="audio missing or larger than 20 MB")
            try:
                audio = await asyncio.to_thread(sns_av.decode, data, cfg)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            out = await asyncio.to_thread(sns_av.transcribe, audio, str(cfg["AURORA_LANG_DEFAULT"])[:2], cfg)
            log.info("audit: owner dictated %.1f s from a device (%s, %d bytes; clear: %s)", out["audio_s"],
                     str(body.get("mime", "?"))[:40], len(data), out["clear"])
            return out
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    raise HTTPException(status_code=404, detail="unknown action")


@app.get("/v1/aurora/update", dependencies=[Depends(auth)])
def update_info() -> dict:
    from aurora import sys_update
    return {**sys_update.last(cfg), "mode": cfg["AURORA_UPDATE_MODE"]}


@app.post("/v1/aurora/update/check", dependencies=[Depends(auth)])
async def update_check() -> dict:
    """Fetch and compare; new commits become a notification and an approval (notify), or are applied (auto, when safe)."""
    from aurora import sys_update
    from aurora.sys_approvals import Approvals
    info = await asyncio.to_thread(sys_update.check, cfg)
    if info.get("error") or not info.get("commits"):
        return info
    pending = [a for a in Approvals(cfg).list("pending") if a["kind"] == "update"]
    if pending and pending[-1]["action"].get("to") == info["there"]:
        return {**info, "approval": pending[-1]["id"]}           # already asked for this version
    text = sys_update.changelog(info, "it")
    note("update", "update.available", {"text": f"{info['behind']} novità: " + "; ".join(c["subject"] for c in info["commits"])[:300],
                                         "to": info["there"]})
    if cfg["AURORA_UPDATE_MODE"] == "auto" and info["safe"]:
        return {**info, "run_id": _start_update(info["there"])}
    item = Approvals(cfg).request("update", "code_change", f"Aggiornamento: {info['behind']} commit fino a {info['there']}",
                                  text, {"commits": info["commits"], "files": info["files"], "protected": info["protected"]},
                                  {"to": info["there"]})
    return {**info, "approval": item["id"]}


def _env_add_missing() -> list[str]:
    """Keys a new schema declares and .env lacks get their recommended value (an update must not stop Aurora)."""
    specs = sys_config.load_schema()["settings"]
    env = sys_config.env_file_path()
    current = sys_config.parse_env(env.read_text(encoding="utf-8"))
    missing = [s for s in specs if s["key"] not in current and not s.get("optional")]
    if missing:
        lines = env.read_text(encoding="utf-8").rstrip("\n").splitlines() + [f"{s['key']}={s['recommended']}" for s in missing]
        fd = os.open(env.with_name(env.name + ".tmp"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        os.replace(env.with_name(env.name + ".tmp"), env)
        log.info("audit: update added settings with their recommended value: %s", ", ".join(s["key"] for s in missing))
    return [s["key"] for s in missing]


def _start_update(to: str) -> str:
    def job(q, emit, run_id):
        from aurora import sys_update
        from aurora.kno_answer import Answer
        out = sys_update.apply(cfg, emit)
        if out.get("applied"):
            out["settings_added"] = _env_add_missing()
            threading.Timer(2.0, lambda: subprocess.run(["systemctl", "restart", "--no-block", *[u for u in UNITS if u != "aurora-api"]],
                                                        capture_output=True)).start()
            threading.Timer(4.0, lambda: subprocess.run(["systemctl", "restart", "--no-block", "aurora-api"],
                                                        capture_output=True)).start()
        note("update", "update.done", {"ok": out.get("applied", False), "text": out.get("reason", f"aggiornata a {to}")})
        return Answer(run_id, q, json.dumps(out, ensure_ascii=False), False, mode="agent")
    return start_run(f"[update] {to}", origin="update", job=job)["id"]


def _harvest_domains() -> list[dict]:
    from aurora import kno_sources
    from aurora.sol_schema import load_taxonomy
    tax = load_taxonomy()
    return [{"id": d, "it": tax.get(d, {}).get("it", d), "en": tax.get(d, {}).get("en", d), "mode": m,
             **kno_sources.progress(cfg, d)} for d, m in kno_sources.modes(cfg).items()]


@app.put("/v1/aurora/harvester/domains", dependencies=[Depends(auth)])
async def harvester_domains(request: Request) -> dict:
    from aurora import kno_harvest, kno_sources
    changes = {str(k): str(v) for k, v in (await request.json()).items()}
    try:
        kno_sources.set_modes(cfg, changes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if any(v != "off" for v in changes.values()):
        kno_harvest.send(cfg, "wake")                   # the harvester re-reads the choice within seconds
    log.info("audit: harvester domains: %s", ", ".join(f"{k}={v}" for k, v in sorted(changes.items())))
    return {"domains": _harvest_domains()}


@app.get("/v1/aurora/harvester", dependencies=[Depends(auth)])
def harvester() -> dict:
    from aurora import kno_harvest
    env = sys_config.parse_env(sys_config.env_file_path().read_text(encoding="utf-8"))
    seen = cfg.path("AURORA_STATUS_DIR") / "harvest" / "seen.json"
    return {**kno_harvest.status(cfg), "pending": kno_harvest.pending(cfg),
            "enabled_setting": env.get("AURORA_HARVEST_ENABLED", "0").lower() in sys_config.TRUE_WORDS,
            "categories": cfg["AURORA_HARVEST_CATEGORIES"], "per_category": cfg["AURORA_HARVEST_PER_CATEGORY"],
            "interval_h": cfg["AURORA_HARVEST_INTERVAL_H"],
            "papers_seen": len(json.loads(seen.read_text())) if seen.exists() else 0,
            "domains": _harvest_domains()}


@app.post("/v1/aurora/harvester/{action}", dependencies=[Depends(auth)])
async def harvester_action(action: str, request: Request) -> dict:
    from aurora import kno_harvest
    if action == "now":
        item = kno_harvest.send(cfg, "now")
        log.info("audit: owner asked the harvester for a round now")
        return {"queued": item["id"]}
    if action == "batch":
        ids, unsupported = kno_harvest.parse_items(str((await request.json()).get("items", ""))[:50000])
        if not ids:
            raise HTTPException(status_code=422, detail={"message": "no arXiv id or link found", "unsupported": unsupported})
        item = kno_harvest.send(cfg, "batch", ids=ids)
        log.info("audit: owner sent the harvester a batch of %d papers", len(ids))
        return {"queued": item["id"], "ids": ids, "unsupported": unsupported}
    raise HTTPException(status_code=404, detail="unknown action")


# ---- projects: the Projects page (prj_browse reads; the "projects" plugin writes) ---------------------------

def _prj(fn, *a):
    from aurora import prj_browse  # noqa: F401
    try:
        return fn(cfg, *a)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/v1/aurora/projects", dependencies=[Depends(auth)])
def projects_list() -> dict:
    from aurora import prj_browse
    return {"projects": _prj(prj_browse.list_projects), "base": cfg["AURORA_PROJECTS_DIR"]}


@app.get("/v1/aurora/projects/github", dependencies=[Depends(auth)])
async def projects_github() -> dict:
    """The owner's GitHub repositories through the github plugin (read): stars, forks, issues, pages."""
    def work():
        from aurora.plg_host import PluginHost
        host = PluginHost(cfg)
        p = host.get("github")
        if p is None or not p.available:
            return {"connected": False, "repos": []}
        me = host.call("github", "get_me", {})
        login = json.loads(me["text"]).get("login", "") if me["ok"] else ""
        res = host.call("github", "search_repositories", {"query": f"user:{login}", "minimal_output": False})
        items = json.loads(res["text"]).get("items", []) if res["ok"] else []
        keep = ("full_name", "name", "private", "description", "stargazers_count", "forks_count", "open_issues_count",
                "language", "pushed_at", "html_url", "homepage", "has_pages", "default_branch", "archived")
        return {"connected": True, "login": login, "error": "" if res["ok"] else res["text"][:300],
                "repos": [{k: it.get(k) for k in keep} for it in items]}
    return await asyncio.to_thread(work)


@app.get("/v1/aurora/projects/{name}/tree", dependencies=[Depends(auth)])
def project_tree_api(name: str) -> dict:
    from aurora import prj_browse
    return {"name": name, "files": _prj(prj_browse.tree, name)}


@app.get("/v1/aurora/projects/{name}/file", dependencies=[Depends(auth)])
def project_file_api(name: str, path: str) -> dict:
    from aurora import prj_browse
    return _prj(prj_browse.read_file, name, path)


@app.get("/v1/aurora/projects/{name}/log", dependencies=[Depends(auth)])
def project_log_api(name: str) -> dict:
    from aurora import prj_browse
    return {"name": name, "commits": _prj(prj_browse.log, name)}


@app.post("/v1/aurora/projects/{name}/preview", dependencies=[Depends(auth)])
def project_preview(name: str) -> dict:
    from aurora import prj_browse
    return {"url": f"/v1/preview/{_prj(prj_browse.preview_token, name)}/", "seconds": prj_browse.PREVIEW_S}


@app.get("/v1/preview/{token}/{path:path}")
def preview(token: str, path: str = ""):
    """No login: the token is the key (one project, 10 minutes). The page runs sandboxed (opaque origin, no cookie)."""
    from fastapi import Response
    from aurora import prj_browse
    try:
        data, mime = prj_browse.preview_file(cfg, token, path)
    except PermissionError:
        raise HTTPException(status_code=403, detail="preview expired: open it again from the Projects page")
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="not found")
    return Response(data, media_type=mime, headers={
        "Content-Security-Policy": "sandbox allow-scripts allow-forms allow-popups; frame-ancestors 'self'",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@app.post("/v1/aurora/projects", dependencies=[Depends(auth)])
async def project_new(request: Request) -> dict:
    """A new project from the page (a local write, like the plugin does for the agent)."""
    body = await request.json()
    args = {k: str(body[k]) for k in ("name", "description", "license", "language") if body.get(k)}

    def work():
        from aurora.plg_host import PluginHost
        return PluginHost(cfg).call("projects", "project_create", args)
    out = await asyncio.to_thread(work)
    log.info("audit: project created from the page: %s (%s)", args.get("name"), "ok" if out["ok"] else "failed")
    if not out["ok"]:
        raise HTTPException(status_code=422, detail=out["text"][:400])
    return out


@app.post("/v1/aurora/projects/clone", dependencies=[Depends(auth)])
async def project_clone(request: Request) -> dict:
    """One of the owner's GitHub repositories, cloned into the projects folder to browse and preview it.
    The token goes to git as a request header, never into the repository's config."""
    from aurora import prj_browse
    full = str((await request.json()).get("full_name", ""))
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", full):
        raise HTTPException(status_code=400, detail="owner/repository expected")
    dest = prj_browse.base(cfg) / prj_browse.clone_name(full)
    if dest.exists():
        raise HTTPException(status_code=409, detail=f"{dest.name} already exists")
    token = str(cfg["AURORA_GITHUB_TOKEN"] or "")
    extra = ["-c", "http.extraHeader=Authorization: Basic "
             + base64.b64encode(f"x-access-token:{token}".encode()).decode()] if token else []

    def work():
        import subprocess
        return subprocess.run(["git", *extra, "clone", "--quiet", f"https://github.com/{full}.git", str(dest)],
                              capture_output=True, text=True, timeout=900)
    r = await asyncio.to_thread(work)
    log.info("audit: cloned %s into %s: %s", full, dest.name, "ok" if r.returncode == 0 else "failed")
    if r.returncode != 0:
        raise HTTPException(status_code=502, detail=(r.stderr or "git clone failed").replace(token, "***")[-400:])
    return {"name": dest.name}


# ---- models: which model does each step (mdl_router) ----------------------------------------------------------

@app.get("/v1/aurora/models", dependencies=[Depends(auth)])
def models_overview() -> dict:
    from aurora import mdl_router, sys_ethics
    a = mdl_router.assignments(cfg)
    return {"exempt": sys_ethics.exempt(cfg), "mask": bool(cfg["AURORA_CLOUD_MASK"]),
            "mask_words": cfg["AURORA_CLOUD_MASK_WORDS"],
            "providers": [{"id": k, "label": v["label"], "kind": v["kind"], "key": v.get("key"),
                           "configured": v["kind"] in ("local", "claude_code") or bool(cfg.values.get(v.get("key", "")))}
                          for k, v in mdl_router.PROVIDERS.items()],
            "roles": [{"id": r, "it": it, "en": en, "sees": sees, **a[r]} for r, (it, en, sees) in mdl_router.ROLES.items()]}


@app.put("/v1/aurora/models/roles", dependencies=[Depends(auth)])
async def models_roles(request: Request) -> dict:
    from aurora import mdl_router
    try:
        out = mdl_router.set_assignments(cfg, await request.json())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    log.info("audit: model assignments changed: %s", ", ".join(f"{k}={v['provider']}:{v['model']}" for k, v in out.items()
                                                                  if v["provider"] != "local"))
    return out


@app.get("/v1/aurora/models/{provider}/list", dependencies=[Depends(auth)])
async def models_list(provider: str) -> dict:
    from aurora import mdl_router
    if provider not in mdl_router.PROVIDERS:
        raise HTTPException(status_code=404, detail="unknown provider")
    try:
        return {"provider": provider, "models": await asyncio.to_thread(mdl_router.list_models, provider, cfg)}
    except Exception as e:                               # a wrong key, a provider down: said, not hidden
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {str(e)[:300]}")


@app.get("/v1/aurora/models/stats", dependencies=[Depends(auth)])
async def models_stats(days: float = 7) -> dict:
    from aurora import mdl_router
    return await asyncio.to_thread(mdl_router.stats, cfg, max(1.0, min(days, 90)))


# ---- the capability forge (agt_forge): Aurora builds the plugin she is missing -----------------------------

def _forge_done(req_id: str, name: str) -> None:
    """A forged plugin is live: tell the owner, and run again the routine that asked for it."""
    from aurora import agt_forge, sys_routines
    req = agt_forge.update(cfg, req_id, status="installed", plugin=name, installed=time.time())
    note("forge", "forge.installed", {"id": req_id, "plugin": name,
                                      "text": f"Mi sono costruita il plugin «{name}»: {req['need'][:160]}"})
    r = sys_routines.get(cfg, req["routine"]) if req.get("routine") else None
    if r:
        _start_routine(r)


def _forge_job(req: dict, cloud: bool = False):
    def job(q, emit, run_id):
        from aurora import agt_forge
        from aurora.kno_answer import Answer
        from aurora.plg_host import PluginHost
        agt_forge.update(cfg, req["id"], status="building", started=time.time(), attempts=req.get("attempts", 0) + 1)
        emit("forge.start", {"id": req["id"], "need": req["need"], "cloud": cloud})
        host = PluginHost(cfg)
        if cloud:                                       # the owner allowed it for this request: masked samples only
            from aurora.mdl_cloud import ClaudeCodeLLM
            res = agt_forge.build(cfg, ClaudeCodeLLM(cfg), host, req, emit, masker=agt_forge.Masker(cfg))
        else:
            res = agt_forge.build(cfg, pipeline()._for("forge_write"), host, req, emit,     # as assigned (local by default)
                                  judge=pipeline()._for("forge_judge"))
        if not res["ok"] and not cloud:                 # ask once whether the cloud may try, showing what would leave
            from aurora.sys_approvals import Approvals
            m = agt_forge.Masker(cfg)
            sample = m(agt_forge.peek(cfg, re.findall(r"[\w./-]+/[\w./-]+", req["need"])[:3] or ["sys/logs"]))
            item = Approvals(cfg).request("forge_cloud", "external", f"Posso farmi aiutare dal cloud per «{req['need'][:80]}»?",
                                          "La forgia locale non ci è riuscita. Il ragionatore cloud (Claude) vedrebbe la "
                                          "richiesta e questi campioni, mascherati (IP, email, token, nomi di dispositivi, "
                                          "i tuoi dati personali). Il plugin girerebbe comunque solo qui, nella gabbia.",
                                          {"need": req["need"], "campioni mascherati": sample[:4000],
                                           "errori locali": res["errors"][:3]}, {"request": req["id"]}, run_id)
            agt_forge.update(cfg, req["id"], status="awaiting_cloud", errors=res["errors"][:5], approval=item["id"])
            note("forge", "approval.pending", {"id": item["id"], "kind": "forge_cloud", "title": item["title"]})
            return Answer(run_id, q, "Forgia locale non riuscita: chiedo il permesso per il cloud.", False, mode="agent")
        if not res["ok"]:
            agt_forge.update(cfg, req["id"], status="failed", errors=res["errors"][:5])
            note("forge", "forge.failed", {"id": req["id"], "text": f"Non sono riuscita a costruire: {req['need'][:120]}"})
            return Answer(run_id, q, "Forgia non riuscita: " + "; ".join(res["errors"])[:1500], False, mode="agent")
        m = res["manifest"]
        if agt_forge.read_only(m):
            agt_forge.install(cfg, res["stage"])
            log.info("audit: forged plugin %s installed (read only, no network)", m["name"])
            _forge_done(req["id"], m["name"])
            text = f"Plugin «{m['name']}» costruito, provato nella gabbia e acceso (sola lettura, senza rete)."
        else:
            from aurora.sys_approvals import Approvals
            code = (Path(res["stage"]) / "server.py").read_text(encoding="utf-8")
            item = Approvals(cfg).request("plugin_install", "external", f"Installare il plugin «{m['name']}»?",
                                          f"{req['need']}\n\nMotivo: {req['why']}",
                                          {"manifest": m, "server.py": code[:6000]},
                                          {"request": req["id"], "stage": res["stage"], "name": m["name"]}, run_id)
            agt_forge.update(cfg, req["id"], status="proposed", plugin=m["name"], approval=item["id"])
            note("forge", "approval.pending", {"id": item["id"], "kind": "plugin_install", "title": item["title"]})
            text = f"Plugin «{m['name']}» costruito e provato: scrive, invia o usa la rete, quindi aspetta la tua approvazione."
        return Answer(run_id, q, text, False, mode="agent")
    return job


@app.get("/v1/aurora/forge", dependencies=[Depends(auth)])
def forge_list() -> dict:
    from aurora import agt_forge
    return {"requests": list(reversed(agt_forge.requests(cfg)))}


@app.post("/v1/aurora/forge/tick", dependencies=[Depends(auth)])
def forge_tick() -> dict:
    """aurora-rem, every tick: the oldest pending request is built (one at a time)."""
    from aurora import agt_forge
    req = agt_forge.next_pending(cfg)
    if req is None:
        return {"started": None}
    agt_forge.update(cfg, req["id"], status="building", started=time.time())
    return {"started": start_run(f"[forge] {req['need'][:120]}", origin="forge", job=_forge_job(req))["id"]}


# ---- routines: periodic checks the owner switched on (sys_routines) -------------------------------------

def _routine_job(r: dict):
    from aurora import sys_routines
    from aurora.kno_answer import Answer

    def job(q, emit, run_id):
        ok, text, files = True, "", []
        if r["kind"] == "tool":
            from aurora.plg_host import PluginHost
            host = PluginHost(cfg)
            p = host.get(r["plugin"])
            if p is None or not p.available:
                ok, text = False, f"plugin {r['plugin']} not available"
            elif p.effect(r["tool"]) != "read":                  # a routine by itself only reads
                ok, text = False, f"{r['plugin']}.{r['tool']} is not read-only: a routine cannot call it"
            else:
                res = host.call(r["plugin"], r["tool"], r.get("args") or {}, run_id=run_id)
                ok, text = res["ok"], res["text"].strip()
            emit("routine.result", {"routine": r["id"], "ok": ok, "text": text[:2000]})
            ans = Answer(run_id, q, text or "Niente da segnalare.", False, mode="agent")
        else:
            from aurora.agt_loop import Agent
            # the owner's words may carry the schedule ("ogni mattina..."): the schedule exists, the task is now (C68)
            goal = (f"Do this task now, once, and report the result: {r['goal']}\n(It is one run of a periodic check the "
                    "owner already scheduled: do not create or change routines, do not study Aurora's code to do it; use "
                    "the tools that read the data. If no tool can read what is needed, say so in one line.)")
            try:
                agent = Agent(pipeline(), cfg, notify=lambda e, p: note("agent", e, p))
                agent.routine = r["id"]                     # a capability it requests runs this routine again
                ans = agent.run(goal, emit, run_id, f"Routine: {r.get('title', '')}. Read only.")
                text, files = ans.text.strip(), agent.produced
                _gap_check(agent, r["goal"], text, emit, run_id, r["id"])
            except Exception as e:                       # a failed routine is recorded and said, never left pending
                log.exception("routine %s failed", r["id"])
                ok, text = False, f"{type(e).__name__}: {str(e)[:300]}"
                ans = Answer(run_id, q, f"Routine non riuscita: {text}", False, mode="agent")
        routine, notify = sys_routines.record(cfg, r["id"], text, ok, run_id, files)
        if notify:
            note("routine", r.get("event", "routine.done") if ok else "routine.failed",
                 {"routine": r["id"], "title": routine.get("title", ""), "run_id": run_id,
                  "text": (f"{routine.get('title', '')}: " if r.get("event", "routine.done") == "routine.done" else "") + text})
        return ans
    return job


def _start_routine(r: dict) -> str:
    from aurora import sys_routines
    sys_routines.mark_started(cfg, r["id"])
    return start_run(f"[routine] {r.get('title', r['id'])}", origin="routine", job=_routine_job(r))["id"]


@app.get("/v1/aurora/routines", dependencies=[Depends(auth)])
def routines() -> dict:
    from aurora import sys_routines
    from aurora.plg_host import PluginHost
    plugins = PluginHost(cfg).plugins(with_tools=False)
    rs = sys_routines.all_routines(cfg)
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    return {"routines": rs, "suggestions": sys_routines.suggestions(plugins, rs),
            "welcome": [{"plugin": p.name, "text": (p.manifest.get("welcome") or {}).get(lang, "")}
                        for p in plugins if p.available and p.manifest.get("welcome")]}


@app.post("/v1/aurora/routines", dependencies=[Depends(auth)])
async def routine_create(request: Request) -> dict:
    from aurora import sys_routines
    from aurora.plg_host import PluginHost
    body = await request.json()
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    try:
        if body.get("suggestion"):
            r = sys_routines.from_suggestion(cfg, PluginHost(cfg).plugins(with_tools=False), str(body["suggestion"]), lang)
        else:
            r = sys_routines.create(cfg, body)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown suggestion")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    log.info("audit: routine %s switched on: %s", r["id"], r.get("title"))
    return r


@app.put("/v1/aurora/routines/{rid}", dependencies=[Depends(auth)])
async def routine_update(rid: str, request: Request) -> dict:
    from aurora import sys_routines
    try:
        r = sys_routines.update(cfg, rid, await request.json())
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown routine")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    log.info("audit: routine %s changed", rid)
    return r


@app.delete("/v1/aurora/routines/{rid}", dependencies=[Depends(auth)])
def routine_delete(rid: str) -> dict:
    from aurora import sys_routines
    if not sys_routines.delete(cfg, rid):
        raise HTTPException(status_code=404, detail="unknown routine")
    log.info("audit: routine %s removed", rid)
    return {"deleted": rid}


@app.post("/v1/aurora/routines/{rid}/run", dependencies=[Depends(auth)])
def routine_run(rid: str) -> dict:
    from aurora import sys_routines
    r = sys_routines.get(cfg, rid)
    if r is None:
        raise HTTPException(status_code=404, detail="unknown routine")
    return {"run_id": _start_routine(r)}


@app.post("/v1/aurora/routines/tick", dependencies=[Depends(auth)])
def routine_tick() -> dict:
    """aurora-rem, every tick: start what is due; tell the owner, once, what a newly ready plugin can do."""
    from aurora import sys_routines
    from aurora.plg_host import PluginHost
    started = [_start_routine(r) for r in sys_routines.due(cfg)]
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    new = sys_routines.newly_ready(cfg, PluginHost(cfg).plugins(with_tools=False))
    if new:
        n = sum(len(p.manifest.get("routines", [])) for p in new)
        note("plugins", "plugin.ready", {"plugins": [p.name for p in new], "text": " ".join(
            (p.manifest.get("welcome") or {}).get(lang, "") for p in new)
            + (f" Ti propongo {n} controlli periodici nella pagina 🔁 Routine." if n and lang == "it"
               else f" I suggest {n} periodic checks in the 🔁 Routines page." if n else "")})
    return {"started": started, "welcomed": [p.name for p in new]}


@app.get("/v1/aurora/notifications", dependencies=[Depends(auth)])
def notifications() -> dict:
    from aurora import sys_push
    lang = "it" if str(cfg["AURORA_LANG_DEFAULT"]).startswith("it") else "en"
    return {"prefs": sys_push.prefs(cfg), "presets": sys_push.PRESETS, "subscriptions": sys_push.count(cfg),
            "kinds": [{"id": k, "label": v[lang], "it": v["it"], "en": v["en"]} for k, v in sys_push.KINDS.items()]}


@app.put("/v1/aurora/notifications", dependencies=[Depends(auth)])
async def notifications_set(request: Request) -> dict:
    from aurora import sys_push
    p = sys_push.set_prefs(cfg, await request.json())
    log.info("audit: notifications: push %s, webui %s", ",".join(p["push"]) or "-", ",".join(p["webui"]) or "-")
    return {"prefs": p}


@app.post("/v1/aurora/update/apply", dependencies=[Depends(auth)])
def update_apply() -> dict:
    """The owner's click on "update now" in the Updates page: the same path as an approved update."""
    from aurora import sys_update
    info = sys_update.check(cfg)
    if info.get("error") or not info.get("commits"):
        raise HTTPException(status_code=409, detail=info.get("error") or "already up to date")
    if info["protected"]:
        raise HTTPException(status_code=409, detail=f"protected files change: {', '.join(info['protected'])}")
    return {"run_id": _start_update(info["there"])}


@app.get("/v1/aurora/push", dependencies=[Depends(auth)])
def push_info() -> dict:
    from aurora import sys_push
    return {"public_key": sys_push.public_key(cfg), "subscriptions": sys_push.count(cfg),
            "events": [e.strip() for e in cfg["AURORA_PUSH_EVENTS"].split(",") if e.strip()]}


@app.post("/v1/aurora/push/{action}", dependencies=[Depends(auth)])
async def push_action(action: str, request: Request) -> dict:
    from aurora import sys_push
    body = await request.json() if action != "test" else {}
    if action == "subscribe":
        dev = getattr(request.state, "device", None)
        try:
            n = sys_push.subscribe(body.get("subscription"), (dev or {}).get("name") if isinstance(dev, dict) else None, cfg)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        log.info("audit: push subscription added (%d in all)", n)
        return {"subscriptions": n}
    if action == "unsubscribe":
        n = sys_push.unsubscribe(str(body.get("endpoint", "")), cfg)
        log.info("audit: push subscription removed (%d left)", n)
        return {"subscriptions": n}
    if action == "test":
        msg = sys_push.message("test", {"text": "Aurora"}, cfg)
        return await asyncio.to_thread(sys_push.send, msg, cfg)
    raise HTTPException(status_code=404, detail="unknown action")


@app.get("/v1/aurora/images/{name}", dependencies=[Depends(auth)])
def image(name: str):
    import re
    if not re.fullmatch(r"[a-z0-9-]+\.png", name):
        raise HTTPException(status_code=404, detail="no such image")
    f = cfg.path("AURORA_IMAGE_DIR") / name
    if not f.is_file():
        raise HTTPException(status_code=404, detail="no such image")
    return FileResponse(f, media_type="image/png")


@app.get("/v1/aurora/metrics", dependencies=[Depends(auth)])
def metrics() -> dict:
    from aurora import sys_metrics
    m = sys_metrics.sample()
    m["busy"] = _run_lock.locked()
    return m


@app.get("/v1/aurora/rem/state", dependencies=[Depends(auth)])
def rem_state() -> dict:
    from aurora.kno_rem import Rem
    from aurora.kno_social import platforms
    from aurora.plg_host import PluginHost
    rem_running = any(r["origin"] == "rem" and not r["done"] for r in list(_runs.values()))
    social = sum(1 for t in platforms(PluginHost(cfg)) if t["available"] and t["stats"])
    return {**Rem(pipeline(), cfg).state(), "busy": _run_lock.locked(), "rem_running": rem_running,
            "social_platforms": social}


@app.post("/v1/aurora/rem/{task}", dependencies=[Depends(auth)])
def rem_task(task: str) -> dict:
    if task == "repair":                              # registered earlier than /rem/repair: hand over
        return rem_repair()
    if task not in ("consolidate", "reflect", "dream", "introspect", "social"):
        raise HTTPException(status_code=404, detail="unknown task")

    def job(q, emit, run_id):
        from aurora.kno_rem import Rem

        def tell(event, payload):                         # what Aurora wrote tonight reaches the owner too
            emit(event, payload)
            if event in ("rem.dream", "rem.thought", "rem.self_review"):
                note("rem", event, {"sid": payload.get("sid"), "text": payload.get("text", "")})
        emit("rem.start", {"task": task})
        out = getattr(Rem(pipeline(), cfg), task)(tell)
        emit("rem.end", {"task": task, **out})
        return None
    return {"run_id": start_run(f"[{task}]", origin="rem", job=job)["id"]}


# ---- activity, logs ----------------------------------------------------------------------------
@app.post("/v1/aurora/activity", dependencies=[Depends(auth)])
async def post_activity(request: Request) -> dict:
    """A service reports what it is doing: {"source", "event", "payload"} (shown in the WebUI)."""
    body = await request.json()
    item = note(str(body.get("source", "service"))[:40], str(body.get("event", "note"))[:60], body.get("payload") or {})
    sys_log.trace("activity", item["event"], item["payload"])
    return {"seq": item["seq"]}


@app.get("/v1/aurora/activity", dependencies=[Depends(auth)])
def get_activity(after: int = 0, limit: int = 200) -> list[dict]:
    with _activity_cond:
        return [a for a in _activity if a["seq"] > after][-max(1, min(limit, MAX_ACTIVITY)):]


@app.get("/v1/aurora/activity/stream", dependencies=[Depends(auth)])
async def activity_stream(after: int | None = None):
    """SSE of the activity feed from `after` (default: from now)."""
    def wait(seen: int) -> list[dict]:
        with _activity_cond:
            if not any(a["seq"] > seen for a in _activity):
                _activity_cond.wait(15)
            return [a for a in _activity if a["seq"] > seen]

    async def gen():
        with _activity_cond:
            seen = after if after is not None else (_activity[-1]["seq"] if _activity else 0)
        while True:
            items = await asyncio.to_thread(wait, seen)
            for a in items:
                yield f"data: {json.dumps(a, ensure_ascii=False, default=str)}\n\n"
                seen = a["seq"]
            if not items:
                yield ": keep-alive\n\n"
    return StreamingResponse(quiet(gen()), media_type="text/event-stream")


@app.get("/v1/aurora/logs", dependencies=[Depends(auth)])
def logs(hours: float = 24) -> dict:
    from aurora import sys_logread
    return {**sys_logread.inventory(cfg, hours), "answers": sys_logread.answer_stats(hours, cfg)}


@app.get("/v1/aurora/logs/{component}", dependencies=[Depends(auth)])
def log_tail(component: str, lines: int = 100, level: str | None = None) -> dict:
    from aurora import sys_logread
    try:
        return {"component": component, "lines": sys_logread.tail(component, lines, level, cfg)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/v1/aurora/runs/{run_id}/record", dependencies=[Depends(auth)])
def run_record(run_id: str) -> list[dict]:
    """A past run's events from the trace files (also after a restart of the API)."""
    from aurora import sys_logread
    return sys_logread.run_events(run_id, cfg)


_health_cache: dict = {"at": 0.0, "value": None}


@app.get("/v1/aurora/health", dependencies=[Depends(auth)])
def health_all() -> dict:
    from aurora import sys_health
    if time.time() - _health_cache["at"] > 10:
        _health_cache.update(at=time.time(), value=sys_health.check(cfg))
    return _health_cache["value"]


@app.get("/v1/aurora/reflections", dependencies=[Depends(auth)])
def reflections(type: str | None = None, n: int = 30) -> list[dict]:
    p = pipeline()
    if not p.reader.layout.shards("memory", "reflection"):
        return []
    items = [s for s in p.reader.recent(500, domain="reflection") if type is None or s.extra.get("type") == type]
    return [{"sid": s.sid, "type": s.extra.get("type"), "text": s.text, "created_at": s.created_at,
             "extra": {k: v for k, v in s.extra.items() if k not in ("turns", "fragments")}}
            for s in reversed(items[-max(1, min(n, 200)):])]


# ---- documents ----------------------------------------------------------------------------------
@app.post("/v1/aurora/documents/pdf", dependencies=[Depends(auth)])
async def create_pdf(request: Request) -> dict:
    """{"title", "text" (Markdown)} -> a PDF in AURORA_DOCUMENTS_DIR, marked as AI-generated."""
    from aurora import doc_pdf, txt_lang
    body = await request.json()
    text, title = str(body.get("text", "")).strip(), str(body.get("title", "")).strip() or "Documento di Aurora"
    if not text:
        raise HTTPException(status_code=400, detail="empty document")
    try:
        p = await asyncio.to_thread(doc_pdf.create, title[:120], text, txt_lang.detect(text), cfg)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"name": p.name, "url": f"/v1/aurora/documents/{p.name}", "bytes": p.stat().st_size}


@app.get("/v1/aurora/documents", dependencies=[Depends(auth)])
def documents() -> list[dict]:
    d = cfg.path("AURORA_DOCUMENTS_DIR")
    files = sorted(d.glob("*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True) if d.is_dir() else []
    return [{"name": f.name, "bytes": f.stat().st_size, "url": f"/v1/aurora/documents/{f.name}"} for f in files[:200]]


@app.get("/v1/aurora/documents/{name}", dependencies=[Depends(auth)])
def document(name: str):
    import re
    if not re.fullmatch(r"[a-z0-9-]+\.pdf", name):
        raise HTTPException(status_code=404, detail="no such document")
    f = cfg.path("AURORA_DOCUMENTS_DIR") / name
    if not f.is_file():
        raise HTTPException(status_code=404, detail="no such document")
    return FileResponse(f, media_type="application/pdf", filename=name)


# ---- firewall incidents -------------------------------------------------------------------------
@app.post("/v1/aurora/sentinel/incident", dependencies=[Depends(auth)])
async def sentinel_incident(request: Request) -> dict:
    """aurora-sentinel reports an incident: kept, shown, investigated at once if the .env says so."""
    from aurora.sec_incidents import Incidents
    item = Incidents(cfg).add(await request.json())
    note("sentinel", "incident", {"id": item["id"], "kind": item["kind"], "source": item["source"],
                                  "severity": item["severity"], "title": f"{item['kind']} · {item['source']}"})
    if cfg["AURORA_SENTINEL_INVESTIGATE"]:
        def job(q, emit, run_id):
            from aurora.kno_answer import Answer
            from aurora.plg_host import PluginHost
            from aurora.sec_incidents import investigate
            text = investigate(pipeline(), PluginHost(cfg), item, emit, cfg)
            return Answer(run_id, q, text, False, mode="agent")
        start_run(f"[incident] {item['kind']} {item['source']}", origin="sentinel", job=job)
    return {"id": item["id"], "severity": item["severity"]}


@app.get("/v1/aurora/incidents", dependencies=[Depends(auth)])
def incidents(status: str | None = None) -> list[dict]:
    from aurora.sec_incidents import Incidents
    return Incidents(cfg).list(status)[:200]


@app.post("/v1/aurora/incidents/{incident_id}/close", dependencies=[Depends(auth)])
def close_incident(incident_id: str) -> dict:
    from aurora.sec_incidents import Incidents
    try:
        Incidents(cfg).update(incident_id, status="closed", closed=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    except StopIteration:
        raise HTTPException(status_code=404, detail="unknown incident")
    log.info("audit: incident %s closed by the owner", incident_id)
    return {"id": incident_id, "status": "closed"}


# ---- social -------------------------------------------------------------------------------------
@app.get("/v1/aurora/social", dependencies=[Depends(auth)])
def social() -> dict:
    from aurora.kno_social import platforms
    from aurora.plg_host import PluginHost
    reports = reflections(type="social_report", n=1)
    return {"platforms": platforms(PluginHost(cfg)), "last_report": reports[0] if reports else None}


@app.post("/v1/aurora/social/draft", dependencies=[Depends(auth)])
async def social_draft(request: Request) -> dict:
    """{"text": content to share, "plugins": [optional subset]} -> a draft per connected platform."""
    from aurora.kno_social import draft, platforms
    from aurora.plg_host import PluginHost
    body = await request.json()
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="nothing to share")
    found = await asyncio.to_thread(lambda: platforms(PluginHost(cfg)))    # the host runs its own event loop
    targets = [t for t in found if t["available"] and t["publish"]
               and (not body.get("plugins") or t["plugin"] in body["plugins"])]
    if not targets:
        raise HTTPException(status_code=409, detail="no social platform connected (tokens in Settings)")
    drafts = await asyncio.to_thread(draft, pipeline().llm, text, targets, cfg)
    return {"drafts": [{"plugin": t["plugin"], "label": t["label"], "max_chars": t["max_chars"], "text": drafts[t["plugin"]]}
                       for t in targets]}


@app.post("/v1/aurora/social/publish", dependencies=[Depends(auth)])
async def social_publish(request: Request) -> dict:
    """The owner clicked "Publish" on a draft he read: that click is the confirmation (recorded as an
    approval, executed at once). The AI disclosure is added if the text lost it while editing."""
    from aurora import sys_disclosure, txt_lang
    from aurora.kno_social import platforms
    from aurora.plg_host import PluginHost
    from aurora.sys_approvals import Approvals
    body = await request.json()
    plugin, text = str(body.get("plugin", "")), str(body.get("text", "")).strip()
    found = await asyncio.to_thread(lambda: platforms(PluginHost(cfg)))
    target = next((t for t in found if t["plugin"] == plugin and t["available"]), None)
    if target is None or not text:
        raise HTTPException(status_code=409, detail="platform not connected or empty text")
    text = sys_disclosure.mark_text(text, txt_lang.detect(text), cfg)
    args = {target["publish"]["field"]: text}
    req = Approvals(cfg).request("tool_call", "external", f"{plugin}.{target['publish']['tool']}",
                                 "post shared by the owner from the chat", {"plugin": plugin, "tool": target["publish"]["tool"],
                                                                            "arguments": args},
                                 {"plugin": plugin, "tool": target["publish"]["tool"], "arguments": args})
    return decide(req["id"], "approve")


# ---- agents, plugins, approvals ------------------------------------------------------------------
def _gap_check(agent, goal: str, report: str, emit, run_id: str, routine: str | None = None) -> None:
    """After an agent run, by code: a report saying a tool is missing becomes a forge request (agt_forge.detect_gap)."""
    from aurora import agt_forge
    try:
        need = agt_forge.detect_gap(pipeline()._for("route"), goal, report, getattr(agent, "requested", False))
    except Exception:                                    # the check never breaks the run
        log.exception("gap check")
        return
    if need:
        req = agt_forge.request(cfg, need, f"rilevato dopo il run: {goal[:300]}", run_id, routine)
        emit("forge.request", {"id": req["id"], "need": req["need"], "status": req["status"], "by": "code"})
        note("forge", "forge.request", {"id": req["id"], "title": req["need"][:160]})
        log.info("gap found after run %s: forge request %s (%s)", run_id, req["id"], need[:120])


def _agent_job(goal: str, context: str = "", after=None, remember: bool = False, label: str | None = None):
    """An agent run. `remember`: the owner asked for it, so goal and report become conversation turns
    (with the whole path), like any other answer; the autonomic ones become reflections (`after`)."""
    def job(q, emit, run_id):
        from aurora.agt_loop import Agent
        from aurora.sol_schema import now_iso
        asked_at = now_iso()
        agent = Agent(pipeline(), cfg, notify=lambda e, p: note("agent", e, p))
        ans = agent.run(goal, emit, run_id, context)
        _gap_check(agent, goal, ans.text, emit, run_id)
        if agent.produced:                             # the documents it wrote stay with its turn (downloadable)
            from aurora import sys_uploads
            for f in agent.produced:
                sys_uploads.link(cfg, run_id, f["name"], f["url"], f["mime"])
        if remember:
            pipeline().remember(label or f"/agente {goal}", ans, run_id, emit, agent.trail, asked_at)
        if after:
            after(ans, emit)
        return ans
    return job


@app.post("/v1/aurora/agent", dependencies=[Depends(auth)])
async def agent(request: Request) -> dict:
    body = await request.json()
    goal = str(body.get("goal", "")).strip()
    if not goal:
        raise HTTPException(status_code=400, detail="empty goal")
    job = _agent_job(goal, str(body.get("context", "")), remember=body.get("remember", True) is not False)
    return {"run_id": start_run(goal, origin="agent", job=job)["id"]}


@app.get("/v1/aurora/plugins", dependencies=[Depends(auth)])
def plugins() -> list[dict]:
    from aurora.plg_host import PluginHost
    return [{"name": p.name, "version": p.manifest.get("version"), "kind": p.manifest.get("kind"),
             "description": p.manifest.get("description", {}), "enabled": p.enabled, "available": p.available,
             "missing": p.missing, "error": p.error, "setup": p.manifest.get("setup", {}),
             "settings": [k for k in dict.fromkeys(p.manifest.get("env", []) + p.manifest.get("requires", [])
                                                   + list(p.manifest.get("env_as", {})) + p.manifest.get("settings", []))],
             "icon": f"/v1/aurora/plugins/{p.name}/icon",
             "tools": [{"name": t["name"], "effect": t["effect"], "description": t["description"],
                        "required": (t.get("input_schema") or {}).get("required", [])} for t in p.tools]}
            for p in PluginHost(cfg).plugins()]


@app.post("/v1/aurora/plugins/{name}/{action}", dependencies=[Depends(auth)])
def plugin_switch(name: str, action: str) -> dict:
    from aurora.plg_host import PluginHost
    if action not in ("enable", "disable"):
        raise HTTPException(status_code=404, detail="unknown action")
    host = PluginHost(cfg)
    if name not in {p.name for p in host.plugins(with_tools=False)}:
        raise HTTPException(status_code=404, detail="unknown plugin")
    host.set_enabled(name, action == "enable")
    return {"name": name, "enabled": action == "enable"}


ICON_DEFAULT = {"tool": "🛠️", "connector": "🔌", "service": "🛰️", "trigger": "⚡"}


@app.get("/v1/aurora/plugins/{name}/icon", dependencies=[Depends(auth)])
def plugin_icon(name: str):
    """The owner's icon (user data, AURORA_STATUS_DIR/plugins/icons), else the plugin's own icon.png, else one for its kind."""
    from aurora.plg_host import PluginHost
    p = next((x for x in PluginHost(cfg).plugins(with_tools=False) if x.name == name), None)
    if p is None:
        raise HTTPException(status_code=404, detail="unknown plugin")
    for f in (cfg.path("AURORA_STATUS_DIR") / "plugins" / "icons" / f"{name}.png", p.folder / "icon.png"):
        if f.is_file():
            return FileResponse(f, media_type="image/png", headers={"Cache-Control": "no-cache"})
    glyph = ICON_DEFAULT.get(p.manifest.get("kind", "tool"), "🧩")
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect width='64' height='64' rx='14' "
           f"fill='#2a3350'/><text x='32' y='44' font-size='32' text-anchor='middle'>{glyph}</text></svg>")
    return Response(svg, media_type="image/svg+xml")


@app.post("/v1/aurora/plugins/{name}/icon", dependencies=[Depends(auth)])
async def plugin_icon_set(name: str, request: Request) -> dict:
    """The owner changes a plugin's icon: {"data": base64 image} or {"url": "https://..."} (checked,
    made a 64x64 PNG)."""
    import io
    from PIL import Image
    from aurora.plg_host import PluginHost
    p = next((x for x in PluginHost(cfg).plugins(with_tools=False) if x.name == name), None)
    if p is None:
        raise HTTPException(status_code=404, detail="unknown plugin")
    body = await request.json()
    try:
        if body.get("url"):
            url = str(body["url"])
            if not url.startswith("https://"):
                raise ValueError("only https:// links")
            raw = httpx.get(url, timeout=20, follow_redirects=True).content
        else:
            raw = base64.b64decode(body.get("data", ""), validate=True)
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("image larger than 5 MB")
        img = Image.open(io.BytesIO(raw))
        img.load()
        img = img.convert("RGBA")
        img.thumbnail((64, 64))
        canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        canvas.paste(img, ((64 - img.width) // 2, (64 - img.height) // 2))
        mine = cfg.path("AURORA_STATUS_DIR") / "plugins" / "icons"       # user data: the plugin's own icon stays
        mine.mkdir(parents=True, exist_ok=True)
        canvas.save(mine / f"{name}.png")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"not a usable image: {e}")
    log.info("audit: icon of plugin %s changed", name)
    return {"name": name, "icon": f"/v1/aurora/plugins/{name}/icon"}


UNITS = ("aurora-llm", "aurora-models", "aurora-api", "aurora-rem", "aurora-harvester", "aurora-sentinel", "aurora-https")


@app.post("/v1/aurora/services/restart", dependencies=[Depends(auth)])
async def restart_services(request: Request) -> dict:
    """Restart services from the WebUI (after a settings change). aurora-api restarts last, after this
    answer has left: the page reconnects by itself."""
    import subprocess
    wanted = [u for u in (await request.json()).get("services", []) if u in UNITS]
    if not wanted:
        raise HTTPException(status_code=400, detail="no known service")
    others = [u for u in wanted if u != "aurora-api"]
    if others:
        r = await asyncio.to_thread(subprocess.run, ["systemctl", "restart", "--no-block", *others],
                                    capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise HTTPException(status_code=500, detail=r.stderr.strip()[:300] or "systemctl failed")
    if "aurora-api" in wanted:
        threading.Timer(1.5, lambda: subprocess.run(["systemctl", "restart", "--no-block", "aurora-api"],
                                                    capture_output=True, timeout=30)).start()
    log.info("audit: restart requested from the WebUI: %s", ", ".join(wanted))
    return {"restarting": wanted}


@app.post("/v1/aurora/plugins/{name}/try/{tool}", dependencies=[Depends(auth)])
async def plugin_try(name: str, tool: str, request: Request) -> dict:
    """The owner tries a read-only tool from the Plugins page (e.g. is the token right?). Read only."""
    from aurora.plg_host import PluginHost
    args = await request.json() if request.headers.get("content-length", "0") != "0" else {}

    def work():                                   # the host runs its own event loop: not inside this one
        host = PluginHost(cfg)
        p = host.get(name)
        if p is None or not p.available:
            raise HTTPException(status_code=409, detail="plugin not available")
        if p.effect(tool) != "read":
            raise HTTPException(status_code=403, detail="only read-only tools can be tried here")
        return host.call(name, tool, args or {})
    return await asyncio.to_thread(work)


@app.get("/v1/aurora/approvals", dependencies=[Depends(auth)])
def approvals(status: str | None = None) -> list[dict]:
    from aurora.sys_approvals import Approvals
    return Approvals(cfg).list(status)


@app.post("/v1/aurora/approvals/{approval_id}/{decision}", dependencies=[Depends(auth)])
def decide(approval_id: str, decision: str) -> dict:
    from aurora.sys_approvals import Approvals
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=404, detail="unknown decision")
    store = Approvals(cfg)
    item = store.get(approval_id)
    if item is None:
        raise HTTPException(status_code=404, detail="unknown request")
    if item["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"already {item['status']}")
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if decision == "reject":
        store.update(approval_id, status="rejected", decided=now)
        if item["kind"] in ("forge_cloud", "plugin_install"):      # the forge request ends with the owner's no
            from aurora import agt_forge
            try:
                agt_forge.update(cfg, item["action"]["request"], status="declined", decided=time.time())
            except StopIteration:
                pass
        note("owner", "approval.rejected", {"id": approval_id, "title": item["title"]})
        return {"id": approval_id, "status": "rejected"}
    store.update(approval_id, status="approved", decided=now)

    def job(q, emit, run_id):
        emit("approval.execute", {"id": approval_id, "kind": item["kind"], "title": item["title"]})
        try:
            if item["kind"] == "code_change":
                from aurora import agt_change
                out = agt_change.apply(item["action"]["sandbox_id"], emit, cfg)
                ok = out.get("applied", False)
            elif item["kind"] == "forge_cloud":             # the owner allowed the cloud for this request
                from aurora import agt_forge
                req = next(r for r in agt_forge.requests(cfg) if r["id"] == item["action"]["request"])
                rid = start_run(f"[forge, cloud] {req['need'][:100]}", origin="forge", job=_forge_job(req, cloud=True))["id"]
                out, ok = {"forge_run": rid}, True
            elif item["kind"] == "plugin_install":          # a forged plugin the owner approved
                from aurora import agt_forge
                a = item["action"]
                dest = agt_forge.install(cfg, a["stage"])
                _forge_done(a["request"], a["name"])
                out, ok = {"installed": str(dest)}, True
            elif item["kind"] == "update":
                from aurora import sys_update
                out = sys_update.apply(cfg, emit)
                ok = out.get("applied", False)
                if ok:
                    out["settings_added"] = _env_add_missing()
                    threading.Timer(3.0, lambda: subprocess.run(["systemctl", "restart", "--no-block", *UNITS],
                                                                capture_output=True)).start()
            else:
                from aurora.plg_host import PluginHost
                a = item["action"]
                out = PluginHost(cfg).call(a["plugin"], a["tool"], a.get("arguments") or {}, run_id)
                ok = out["ok"]
        except Exception as e:                                # recorded, never lost
            out, ok = {"error": f"{type(e).__name__}: {e}"}, False
        store.update(approval_id, status="executed" if ok else "failed", result=out)
        emit("approval.done", {"id": approval_id, "ok": ok, "result": json.dumps(out, ensure_ascii=False)[:1500]})
        note("owner", "approval.done", {"id": approval_id, "ok": ok, "title": item["title"]})
        from aurora.kno_answer import Answer
        return Answer(run_id, q, ("Fatto: " if ok else "Non riuscito: ") + json.dumps(out, ensure_ascii=False)[:1500],
                      False, mode="agent")
    return {"id": approval_id, "status": "approved", "run_id": start_run(f"[approval] {item['title']}",
                                                                          origin="approval", job=job)["id"]}


@app.post("/v1/aurora/rem/repair", dependencies=[Depends(auth)])
def rem_repair() -> dict:
    """Self-repair: an agent works on the problems of the last self-review; its report becomes a memory."""
    p = pipeline()
    reviews = [s for s in p.reader.recent(40, domain="reflection") if s.extra.get("type") == "self_review"] \
        if p.reader.layout.shards("memory", "reflection") else []
    if not reviews:
        raise HTTPException(status_code=409, detail="no self-review yet")
    review = reviews[-1]
    goal = ("Autoriparazione: esamina i problemi della tua ultima autodiagnosi. Per ognuno verifica prima se è ancora "
            "presente (ultimo orario nei log, riavvii dei servizi, codice attuale): se la causa non c'è più, riportalo "
            "come risolto con la prova. Per ciò che resta, trova la causa nei log e nel codice, correggi nella sandbox "
            "ciò che ha una causa chiara e proponi la modifica; per il resto riporta cosa manca.")

    def after(ans, emit):
        from aurora.kno_rem import Rem
        Rem(p, cfg)._write(ans.text, "repair", f"repair:{int(time.time())}",
                           {"review": review.sid, "run_id": ans.run_id}, emit)
    from aurora import sys_logread
    evidence = sys_logread.problem_evidence(cfg)
    line = lambda e: (f"- {e['component']}: {e['count']} × {e['kind'][:140]} [{e['first'][11:]} → {e['last'][11:]}]; "
                      f"{e['host_service']} last start {(e['host_last_start'] or '-')[11:]}")
    alive = [e for e in evidence if e["seen_after_last_start"]]
    gone = [e for e in evidence if not e["seen_after_last_start"]]
    # Only problems seen again after their service last restarted go to the agent: the others are, by
    # measurement, not recurring (a fix or a restart already happened); the code decides this, not the model.
    if not alive:
        text = ("Autoriparazione: nessun problema dell'ultima autodiagnosi si è ripresentato dopo l'ultimo riavvio del "
                "servizio che lo ospita, quindi non c'è nulla da correggere adesso. Non ricomparsi:\n"
                + "\n".join(line(e) for e in gone[:30]))

        def quick(q, emit, run_id):
            from aurora.kno_answer import Answer
            emit("agent.finish", {"summary": text, "steps": 0, "seconds": 0})
            ans = Answer(run_id, q, text, False, mode="agent")
            after(ans, emit)
            return ans
        return {"run_id": start_run("[repair]", origin="rem", job=quick)["id"]}
    context = (f"SELF-REVIEW:\n{review.text}\n\nPROBLEMS STILL OCCURRING (seen again after their service last "
               f"started; work on these only):\n" + "\n".join(line(e) for e in alive)
               + "\n\nNOT RECURRING (not seen since the restart: do not work on them):\n"
               + "\n".join(line(e) for e in gone[:20]))
    return {"run_id": start_run("[repair]", origin="rem", job=_agent_job(goal, context, after))["id"]}


# ---- devices -----------------------------------------------------------------------------------
@app.post("/v1/aurora/devices")
async def register_device(request: Request) -> Response:
    """Only the API key can register a device: a device cannot make more devices."""
    bearer = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    _locked(request)
    if not _is_key(bearer):
        _failed(request)
        raise HTTPException(status_code=401, detail="the API key is required to register a device")
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    token, rec = devices.register(body.get("name", ""), request.headers.get("user-agent", ""))
    log.info("audit: device registered: %s (%s)", rec["name"], rec["id"])
    sys_log.trace("api", "device.register", {"id": rec["id"], "name": rec["name"]})
    resp = JSONResponse(rec)
    resp.set_cookie(COOKIE, token, max_age=cfg["AURORA_DEVICE_DAYS"] * 86400, httponly=True, secure=True,
                    samesite="strict", path="/")
    return resp


@app.get("/v1/aurora/devices", dependencies=[Depends(auth)])
def list_devices(request: Request) -> list[dict]:
    me = getattr(request.state, "device", None)
    return [{**d, "current": bool(me and me["id"] == d["id"])} for d in devices.list()]


@app.delete("/v1/aurora/devices/{device_id}", dependencies=[Depends(auth)])
def revoke_device(device_id: str) -> dict:
    if not devices.revoke(device_id):
        raise HTTPException(status_code=404, detail="unknown device")
    log.info("audit: device revoked: %s", device_id)
    sys_log.trace("api", "device.revoke", {"id": device_id})
    return {"revoked": device_id}


@app.post("/v1/aurora/logout", dependencies=[Depends(auth)])
def logout(request: Request) -> Response:
    me = getattr(request.state, "device", None)
    if me:
        devices.revoke(me["id"])
    resp = JSONResponse({"logged_out": bool(me)})
    resp.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return resp


# ---- status and settings -------------------------------------------------------------------
@app.get("/v1/aurora/status", dependencies=[Depends(auth)])
def status() -> dict:
    import httpx
    from aurora.sol_reader import VaultReader
    out = {"vault": VaultReader(cfg).count()}
    for name, url in (("models", f"http://{cfg['AURORA_MODELS_HOST']}:{cfg['AURORA_MODELS_PORT']}/health"),
                      ("llm", f"http://{cfg['AURORA_LLM_HOST']}:{cfg['AURORA_LLM_PORT']}/health")):
        try:
            out[name] = httpx.get(url, timeout=3).json()
        except httpx.HTTPError as e:
            out[name] = {"status": "down", "error": str(e)}
    return out


@app.get("/v1/aurora/settings", dependencies=[Depends(auth)])
def settings() -> dict:
    schema = sys_config.load_schema()
    current = sys_config.parse_env(sys_config.env_file_path().read_text(encoding="utf-8"))
    items = []
    for s in schema["settings"]:
        value = current.get(s["key"], "")
        items.append({**s, "value": ("••••••" if s.get("secret") and value else value)})
    return {"categories": schema["categories"], "settings": items}


@app.put("/v1/aurora/settings", dependencies=[Depends(auth)])
async def update_settings(request: Request) -> dict:
    changes: dict = await request.json()
    specs = {s["key"]: s for s in sys_config.load_schema()["settings"]}
    problems = []
    for key, value in changes.items():
        if key not in specs:
            problems.append(f"{key}: not in the settings schema")
            continue
        try:
            sys_config.convert(specs[key], str(value))
        except ValueError as e:
            problems.append(f"{key}: {e}")
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    env = sys_config.env_file_path()
    lines = env.read_text(encoding="utf-8").splitlines()
    done = set()
    for i, line in enumerate(lines):
        k = line.split("=", 1)[0].strip()
        if k in changes and not line.lstrip().startswith("#"):
            lines[i] = f"{k}={changes[k]}"
            done.add(k)
    lines += [f"{k}={v}" for k, v in changes.items() if k not in done]
    tmp = env.with_name(env.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)     # secrets inside: owner only
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, env)
    restart = sorted({svc for k in changes for svc in specs[k]["services"]})
    log.info("audit: settings changed: %s; services to restart: %s", ", ".join(sorted(changes)), ", ".join(restart))
    sys_log.trace("api", "settings.change", {"keys": sorted(changes), "restart": restart})
    return {"changed": sorted(changes), "restart": restart}


# ---- WebUI -------------------------------------------------------------------------------------
if WEBUI.is_dir():
    app.mount("/static", StaticFiles(directory=WEBUI), name="static")


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
    uvicorn.run(app, host=cfg["AURORA_API_HOST"], port=cfg["AURORA_API_PORT"], log_level="warning", timeout_graceful_shutdown=5)
