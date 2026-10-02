# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What every part of aurora-api shares: configuration, logs, the activity feed and notifications,
authentication (key, devices, lockout), the answer pipeline, runs (one at a time), the chat's routing
(tools, pictures, videos) and the facts Aurora knows about herself."""
from __future__ import annotations

import asyncio
import httpx
import io
import re
import secrets
import subprocess
import threading
import time
import uuid

from collections import OrderedDict
from pathlib import Path
from aurora import sys_config, sys_features, sys_log
from aurora.sys_devices import COOKIE, Devices
from fastapi import HTTPException, Request

cfg = sys_config.get()
devices = Devices(cfg)
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


def plugin_host():
    """One plugin host for the whole API: its cache of tool lists (by plugin.json) lasts as long as the service,
    so listing the plugins does not start every plugin again at each request (the Plugins page took 3.8 s)."""
    if "plugins" not in _state:
        from aurora.plg_host import PluginHost
        _state["plugins"] = PluginHost(cfg)
    return _state["plugins"]


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
             "statistics, his e-mail, the house, the files of a project, take a photo, check an IP address, today's NEWS "
             "and current events (what is happening now, the latest news of a topic: a news service reads them). Reply TOOLS "
             "if so. Reply NO if it is small talk, a question about Aurora herself, or a question about knowledge of the "
             "world (science, law, medicine, history, definitions, how something works) that a knowledge base answers. "
             "Examples: 'controlla i miei repository su GitHub' TOOLS; 'quante stelle ha il mio progetto?' TOOLS; "
             "'ho nuove mail?' TOOLS; 'che novità ci sono oggi nello spazio?' TOOLS; 'ultime notizie di tecnologia' TOOLS; 'mostrami i file del progetto aurora-site' TOOLS; 'cos'è un repository git?' NO; "
             "'come funziona una pull request?' NO; 'cosa dice l'articolo 2043 del codice civile?' NO; 'come stai?' NO. "
             "Reply with exactly one word.\n\nCONNECTED SERVICES:\n{services}")
ROUTER_SKIP = {"web", "self"}          # web search is the knowledge path's job; "self" is Aurora's own maintenance


def connected_services() -> list[str]:
    """The plugins the owner has connected (enabled, configured, no error): what the chat may hand to the agent."""
    return [f"- {p.name}: {(p.manifest.get('description') or {}).get('en', '')[:200]}"
            for p in plugin_host().plugins(with_tools=False) if p.available and p.name not in ROUTER_SKIP]


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


AI_FEATURE = {"creative": "edit_ai", "upscale": "upscale", "remove_background": "cutout"}


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
        for o in ops:
            if o["op"] in AI_FEATURE:
                sys_features.need(cfg, AI_FEATURE[o["op"]], lang)
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


_video = {"busy": False, "title": "", "ready_at": 0.0}


def _say(question: str, text: str, emit, run_id: str, mode: str, remember: bool = True):
    """A short answer that needs no reasoner (it may be off for a GPU job)."""
    from aurora.kno_answer import Answer
    from aurora.sol_schema import now_iso
    asked_at = now_iso()
    ans = Answer(run_id, question, text, False, mode=mode, seconds=0.0)
    emit("answer.final", {"text": text, "abstained": False, "sources": [], "seconds": 0.0, "mode": mode})
    if remember:
        pipeline().remember(question, ans, run_id, emit, None, asked_at)
    emit("run.end", {"seconds": 0.0})
    return ans


def video_busy_answer(question: str, emit, run_id: str):
    """While a video is being made the reasoner is off: say so, and when the video should be ready."""
    if not _video["busy"]:
        return None
    it = str(cfg["AURORA_LANG_DEFAULT"]).startswith("it")
    at = time.strftime("%H:%M", time.localtime(_video["ready_at"]))
    text = (f"🎬 Sto creando il video «{_video['title']}»: finché non ho finito il mio ragionatore è spento. "
            f"Dovrebbe essere pronto verso le {at}, ti avviso io." if it else
            f"🎬 I am making the video \"{_video['title']}\": until it is done my reasoner is off. "
            f"It should be ready around {at}; I will let you know.")
    return _say(question, text, emit, run_id, "video", remember=False)


def make_video(question: str, vp: dict, picture: tuple[str, bytes] | None, emit, run_id: str, remember: bool = True):
    """A short video (mdl_video): Aurora answers at once with the time it will take, makes it in the background
    (the reasoner is off meanwhile) and notifies the owner; the video is kept with this turn of the conversation."""
    from aurora import mdl_video, sys_uploads
    it = str(cfg["AURORA_LANG_DEFAULT"]).startswith("it")
    sys_features.need(cfg, "video_make", "it" if it else "en")
    if _video["busy"]:
        return video_busy_answer(question, emit, run_id)
    minutes = mdl_video.estimate_minutes(cfg)
    secs, title = cfg["AURORA_VIDEO_SECONDS"], vp["title"]
    _video.update(busy=True, title=title, ready_at=time.time() + minutes * 60)
    src = "dalla tua foto, " if it and picture else "from your picture, " if picture else ""
    text = (f"🎬 Creo il video «{title}» ({src}{secs:g} secondi): ci vorranno circa {minutes} minuti. Mentre lo creo "
            f"il ragionatore è spento, quindi non posso risponderti; ti avviso appena è pronto e lo trovi qui." if it else
            f"🎬 Making the video \"{title}\" ({src}{secs:g} seconds): about {minutes} minutes. Meanwhile my reasoner "
            f"is off, so I cannot answer; I will notify you when it is ready, and it will be here.")
    emit("video.plan", {"title": title, "prompt": vp["prompt"], "from_picture": bool(picture), "minutes": minutes})
    lang = "it" if it else "en"

    def work():
        try:
            data, st = mdl_video.generate(vp["prompt"], cfg, image=picture[1] if picture else None, title=title, lang=lang)
            name = re.sub(r"[^\w-]+", "-", title.lower()).strip("-")[:40] or "video"
            url = sys_uploads.public(sys_uploads.save(cfg, run_id, f"{name}.mp4", "video/mp4", data, role="assistant"))["url"] \
                if remember else ""
            note("video", "video.done", {"text": f"{title}: {st['seconds_video']} s, {st['width']}×{st['height']}, "
                                         f"{round(st['total_seconds'] / 60)} min", "run_id": run_id, "url": url, **st})
        except Exception as e:                        # the owner is told, never silence
            log.exception("video %s failed", run_id)
            note("video", "video.failed", {"text": f"{title}: {type(e).__name__}: {str(e)[:120]}", "run_id": run_id})
        finally:
            _video["busy"] = False

    ans = _say(question, text, emit, run_id, "video", remember)
    threading.Thread(target=work, name=f"video-{run_id}", daemon=True).start()
    return ans


def answer_or_acquire(question: str, emit, run_id: str, **kw):
    """The default job of a message. When Aurora's last answer in this session was an abstention and the
    message asks her to go and search, the arXiv agent works on the *previous* question (A11: the
    same for the WebUI and third-party clients, which have no button)."""
    from datetime import datetime, timezone
    busy = video_busy_answer(question, emit, run_id)
    if busy:
        return busy
    p = pipeline()
    recent = p.reader.recent(6)
    pic = None if kw.get("attached") else last_picture(recent)
    from aurora import mdl_video
    vp = None if kw.get("attached") else mdl_video.plan(p._for("route"), question, pic is not None)
    if vp:                                            # "fammi un video di...", "anima questa foto"
        return make_video(question, vp, pic if vp["from_picture"] else None, emit, run_id)
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


# names of sibling modules, looked up only when called: imported last, so that modules that use each
# other (routines, forge, agents) load in any order
from .activity import health_all  # noqa: E402
from .agents import _agent_job  # noqa: E402
