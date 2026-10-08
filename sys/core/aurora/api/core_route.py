# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The chat's routing (moved from api/core, 7 October 2026: one module per part): a connected service goes to the
agent, a picture is edited or looked at again, a video is made (or the GPU's job said), an abstention offers the
search outside, a shadow answers at once — else the answer pipeline. Shared, no routes of its own (api/core_*)."""
from __future__ import annotations

import io
import re
import time
from pathlib import Path

from aurora import sol_reader, sys_context, sys_features

from .core import cfg, log, note, pipeline, plugin_host


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
             "'come funziona una pull request?' NO; 'cosa dice l'articolo 2043 del codice civile?' NO; 'come stai?' NO; "
             "'fammi un grafico interattivo della funzione seno' TOOLS; 'crea una foto di un gatto astronauta' TOOLS; "
             "'cos'è la funzione seno?' NO; 'che tempo farà domani a Lodi?' TOOLS; 'previsioni per il weekend a "
             "Milano' TOOLS; 'ci sono allerte meteo?' TOOLS (a weather service forecasts; the weather NOW at Aurora's "
             "home is hers: 'piove lì da te?' NO); "
             "'ricordami domani alle 9 di chiamare Marco' TOOLS; 'cosa ho in agenda venerdì?' TOOLS; 'fissa il "
             "dentista giovedì alle 15' TOOLS; 'sposta la riunione a lunedì' TOOLS (her calendar). "
             "Reply with exactly one word.\n\nCONNECTED SERVICES:\n{services}")
ROUTER_SKIP = {"web", "self"}          # web search is the knowledge path's job; "self" is Aurora's own maintenance


def connected_services() -> list[str]:
    """The plugins the owner has connected (enabled, configured, no error): what the chat may hand to the agent."""
    built_in = ["- pictures: paint a new picture on request (a photo, an illustration)",
                "- artifacts: make an interactive page shown live in the chat (a chart, a plot of a function, a "
                "calculator, a simulation, a small game or app)"]
    return built_in + [f"- {p.name}: {(p.manifest.get('description') or {}).get('en', '')[:200]}"
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


_video = {"busy": False, "title": "", "ready_at": 0.0, "started": 0.0}


def gpu_busy() -> dict | None:
    """A job on the GPU with the reasoner stopped for it (a local video, a painting, an edit) — also one this API did
    not start as such (6 October: a cloud video fell back to the local model and the chat answered with an error)."""
    from aurora import mdl_video, sys_health
    if _video["busy"]:
        return {**_video}
    job = sys_health.gpu_job(cfg)
    if not job or sys_health._unit("aurora-llm") == "active":
        return None
    title, _, since = job.partition(" since ")
    try:
        h, m, s_ = (int(x) for x in since.split(":"))
        t = time.localtime()
        started = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, h, m, s_, 0, 0, -1))
    except ValueError:
        started = time.time()
    minutes = mdl_video.estimate_minutes(cfg) if title.startswith("video") else 2
    return {"busy": True, "title": title.split(" ", 1)[-1], "started": started, "ready_at": started + minutes * 60}


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
    v = gpu_busy()
    if not v:
        return None
    it = str(cfg["AURORA_LANG_DEFAULT"]).startswith("it")
    at = time.strftime("%H:%M", time.localtime(max(v["ready_at"], time.time() + 60)))
    text = (f"🎬 Sto creando il video «{v['title']}»: finché non ho finito il mio ragionatore è spento. "
            f"Dovrebbe essere pronto verso le {at}, ti avviso io." if it else
            f"🎬 I am making the video \"{v['title']}\": until it is done my reasoner is off. "
            f"It should be ready around {at}; I will let you know.")
    return _say(question, text, emit, run_id, "video", remember=False)


def make_video(question: str, vp: dict, picture: tuple[str, bytes] | None, emit, run_id: str, remember: bool = True):
    """A short video (mdl_video): Aurora answers at once with the time it will take, makes it in the background
    (the reasoner is off meanwhile) and notifies the owner; the video is kept with this turn of the conversation."""
    from aurora import mdl_media, mdl_video, sys_uploads
    it = str(cfg["AURORA_LANG_DEFAULT"]).startswith("it")
    cloud = mdl_media.provider(cfg, "video")[0] != "local"      # a cloud provider (Models page): the reasoner stays on
    if not cloud:
        sys_features.need(cfg, "video_make", "it" if it else "en")
    if _video["busy"]:
        return video_busy_answer(question, emit, run_id)
    minutes = 3 if cloud else mdl_video.estimate_minutes(cfg)
    secs, title = cfg["AURORA_VIDEO_SECONDS"], vp["title"]
    if not cloud:
        _video.update(busy=True, title=title, ready_at=time.time() + minutes * 60, started=time.time())
    src = "dalla tua foto, " if it and picture else "from your picture, " if picture else ""
    text = (f"🎬 Creo il video «{title}» ({src}con {mdl_media.provider(cfg, 'video')[1]}): qualche minuto; intanto puoi "
            f"continuare a scrivermi, ti avviso quando è pronto." if it else
            f"🎬 Making the video \"{title}\" ({src}with {mdl_media.provider(cfg, 'video')[1]}): a few minutes; you can "
            f"keep writing to me meanwhile, I will tell you when it is ready.") if cloud else (
            f"🎬 Creo il video «{title}» ({src}{secs:g} secondi): ci vorranno circa {minutes} minuti. Mentre lo creo "
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
            sol_reader.release()

    ans = _say(question, text, emit, run_id, "video", remember)
    sys_context.start(work, name=f"video-{run_id}")
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
    from aurora import kno_followup
    recent = kno_followup.with_quote(p.reader.recent(6), kw.get("quote"))      # a reply: the quoted message is the last
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
    if cfg["AURORA_SHADOW"] and not kw.get("attached") and not kw.get("focus") and not kw.get("quote"):
        hit = shadow_answer(p, question, emit, run_id)
        if hit is not None:
            return hit
    ans = p.run(question, emit=emit, run_id=run_id, **kw)
    if cfg["AURORA_SHADOW"] and not ans.abstained and ans.mode == "knowledge" and ans.sources:
        from aurora import kno_shadow                     # a verified answer casts its shadow
        kno_shadow.add(cfg, p.search.embedder, question, ans.text, ans.sources, follow=ans.suggestions)
    if (cfg["AURORA_ACQUIRE_AUTO"] and ans.abstained and ans.mode == "knowledge" and not kw.get("attached")
            and len(question) < 400):                 # Autonomy panel, knowledge at 🚀: she searches by herself
        from aurora.kno_acquire import ArxivAgent
        emit("acquire.confirmed", {"question": question, "auto": True})
        from aurora import sys_autonomy
        sys_autonomy.log(cfg, "knowledge", f"searched the sources by herself: {question[:180]}")
        return ArxivAgent(p, cfg).run(question, emit, run_id)
    return ans


def shadow_answer(p, question: str, emit, run_id: str):
    """A question in the shadow of an answer already given (kno_shadow): that answer, written again for this question
    from the same passages and verified (kno_shadow.adapt), saying for which question and when. Two bands (owner,
    2026-10-06): at cosine ≥ AURORA_SHADOW_SURE nothing more; below it the whole pipeline again in the background — its
    verified answer casts a shadow of its own, a different one is told in the chat."""
    from aurora import kno_shadow
    from aurora.kno_answer import Answer, Trail
    from aurora.sol_schema import now_iso
    t0 = time.time()
    hit = kno_shadow.find(cfg, p.search.embedder, p.search.reranker, question)
    if hit is None:
        return None
    emit("route", {"mode": "shadow"})
    text, sources, adapted = hit["text"], hit["sources"], False
    if cfg["AURORA_SHADOW_ADAPT"]:
        try:
            new = kno_shadow.adapt(p, question, hit, emit)
        except Exception as e:                            # noqa: BLE001 — the verified answer as it was
            log.warning("shadow adapt failed: %s", e)
            new = ""
        if new:
            cited = {int(x) for x in re.findall(r"\[(\d+)\]", new)}
            text, sources, adapted = new, [s for s in hit["sources"] if s.get("n") in cited] or hit["sources"], True
    again = not hit["sure"]
    ans = Answer(run_id, question, text, False, sources, [], round(time.time() - t0, 2), suggestions=hit["follow"])
    emit("answer.final", {"text": ans.text, "abstained": False, "sources": ans.sources, "dropped": [], "mode": "knowledge",
                          "seconds": ans.seconds, "shadow": {**{k: hit[k] for k in ("question", "made", "cos", "score",
                                                                                    "overlap")},
                                                             "adapted": adapted, "recheck": again},
                          **({"suggestions": ans.suggestions} if ans.suggestions else {})})
    p.remember(question, ans, run_id, emit, Trail(), now_iso())
    emit("run.end", {"seconds": ans.seconds})

    def recheck():
        try:
            new = p.run(question, emit=lambda e, d: None, run_id=run_id + "-recheck", remember=False, suggest=True)
        except Exception as e:                            # noqa: BLE001 — the answer given stands
            log.warning("shadow recheck failed: %s", e)
            return
        if new.abstained or not new.sources:
            return
        kno_shadow.add(cfg, p.search.embedder, question, new.text, new.sources, follow=new.suggestions)
        if {s["source"] for s in new.sources} != {s["source"] for s in hit["sources"]}:
            note("api", "answer.refined", {"run_id": run_id, "title": f"🔁 {question[:80]}", "text": new.text[:1500]})
    if again:
        sys_context.start(recheck, name="shadow-recheck")
    log.info("shadow: answered in %.1f s (cosine %.3f, re-rank %.3f, %d overlapping, adapted %s, recheck %s) from «%s»",
             ans.seconds, hit["cos"], hit["score"], hit["overlap"], adapted, again, hit["question"][:80])
    return ans


# a sibling module, looked up only when called: imported last (agents imports from core)
from .agents import _agent_job  # noqa: E402
