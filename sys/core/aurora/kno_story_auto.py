# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's videos on a schedule (owner, 2026-10-08: «una routine per la generazione dei video almeno un paio di volte
al giorno intervallata da quella dei post… anche per i video facciamo il post automatico»).

A routine of kind "story" does one of two things ("action"):
 make     at night: Aurora picks a topic (the science news of the day as a hint, never one of her last videos), makes
          the narrated video (kno_story) and keeps it ready. The topic must be answered by PUBLIC knowledge only: every
          source of the answer comes from a public origin (arXiv, Wikipedia, Normattiva…, a web page) — the owner's own documents,
          papers and patents never become a video, nor their titles a post (checked before any picture is painted).
 publish  by day: the oldest ready video goes on the page with its post, through the same gates as every post: the
          privacy check (sure findings → it waits for the owner in Approvals), a repeat of the last 7 days (skipped),
          the daily number of posts Aurora may publish by herself (beyond it → Approvals).
State: <the video's folder>/auto.json {"made", "published", "result"}.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import kno_story, sys_config, sys_log

PUBLIC = frozenset({"arxiv", "wikipedia", "wiki", "normattiva", "biorxiv", "medrxiv", "europepmc", "pmc", "docs", "github"})
NEWS = ("astronomia", "fisica", "biologia", "spazio")
SYS_TOPIC = (
    "You choose the topics of short narrated science videos (about one minute) for Aurora's Facebook page: astronomy, "
    "astrophotography, physics, biology, the sky, nature. Reply ONLY with a JSON list of {n} topics, each a short "
    "question in Italian that an encyclopedia answers well (e.g. \"Perché il cielo è blu?\", \"Cos'è un buco nero?\"). "
    "Use the news below only as a hint of what people talk about today: the question is about the general idea behind "
    "a news item, never the news itself. Never a topic close to one already made (listed below). No people, no "
    "politics, nothing about the owner or about Aurora.")


def _origin(extra: dict) -> str:
    return re.split(r"[:/]", str(extra.get("origin") or ""), maxsplit=1)[0].lower()


def private_sources(reader, sources: list[dict]) -> list[str]:
    """The titles of the answer's sources that do not come from a public origin (empty: all public)."""
    found = reader.get_many([s["sid"] for s in sources if s.get("sid")])
    out = []
    for s in sources:
        if str(s.get("source") or s.get("url") or "").startswith(("http://", "https://")):
            continue                                       # a page of the web the answer read: public by nature
        sol = found.get(s.get("sid"))
        if sol is None or _origin(sol.extra) not in PUBLIC:
            out.append(s.get("title") or s.get("source") or "?")
    return list(dict.fromkeys(out))


def topics(llm, news: str, done: list[str], n: int = 3) -> list[str]:
    user = (f"ALREADY MADE (never again, nor close to them):\n" + "\n".join(f"- {d}" for d in done[:40])
            + f"\n\nTODAY'S SCIENCE NEWS (hints only):\n{news[:4000] or '(none)'}")
    raw = llm.complete(SYS_TOPIC.format(n=n), user, 400, think=False)
    raw = getattr(raw, "answer", raw)
    m = re.search(r"\[.*\]", str(raw), re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        items = []
    seen = {d.strip().lower() for d in done}
    return [str(x).strip() for x in items if isinstance(x, str) and 3 <= len(x.strip()) <= 200
            and x.strip().lower() not in seen][:n]


def _news(host) -> str:
    out = []
    for topic in NEWS:
        try:
            r = host.call("news", "news_headlines", {"topic": topic, "hours": 48, "limit": 6})
        except Exception:                               # noqa: BLE001 - no news: the topic is chosen without hints
            continue
        if r.get("ok"):
            out.append(r["text"][:1200])
    return "\n\n".join(out)


def make(pipeline, cfg: sys_config.Config, host, emit) -> dict:
    """A video ready for the next "publish": {"topic", "video", "length_s", "tried"}. ValueError when no topic works."""
    done = [s["topic"] for s in kno_story.stories(cfg, 60) if s.get("topic")]
    tried = []
    for topic in topics(pipeline.llm, _news(host), done):
        def accept(ans, topic=topic):
            private = private_sources(pipeline.reader, ans.sources)
            return f"fonti non pubbliche ({', '.join(private[:3])}): nessun video" if private else ""
        try:
            out = kno_story.make(pipeline, cfg, topic, emit, accept=accept)
        except ValueError as e:
            tried.append(f"{topic}: {e}")
            emit("story.skip", {"topic": topic, "why": str(e)[:200]})
            continue
        (Path(out["folder"]) / "auto.json").write_text(json.dumps({"made": time.time(), "published": None}), encoding="utf-8")
        return {"topic": topic, "video": Path(out["video"]).name, "length_s": out["length_s"], "tried": tried}
    raise ValueError("nessun argomento adatto: " + " · ".join(tried) if tried else "il modello non ha proposto argomenti")


def ready(cfg: sys_config.Config) -> list[dict]:
    """The videos made by the routine and not published yet, oldest first."""
    root = cfg.path("AURORA_IMAGE_DIR") / "stories"
    out = []
    for s in reversed(kno_story.stories(cfg, 60)):
        f = root / s["stamp"] / "auto.json"
        try:
            state = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not state.get("published"):
            out.append({**s, "state": state, "file": f})
    return out


def _mark(item: dict, **fields) -> None:
    item["file"].write_text(json.dumps({**item["state"], **fields}), encoding="utf-8")


def publish(cfg: sys_config.Config, host, emit, run_id: str | None = None, fmt: str = "", llm=None) -> str:
    """The oldest ready video on the first platform that takes videos; the text says what happened."""
    from . import sec_privacy, sys_approvals, sys_social_guard, txt_lang
    from .kno_social import platforms
    target = next((p for p in platforms(host) if p["available"] and p.get("video")), None)
    if target is None:
        return "NOTHING: no connected platform publishes videos"
    log = sys_log.get_logger("social")
    for item in ready(cfg):
        text = item["post"]
        if (again := sys_social_guard.check(cfg, text)):
            _mark(item, published="skipped", result=again[:300])
            continue
        how = target["video"]
        args = {how["field"]: text, how["video"]: item["video"]}
        if how.get("format") and (fmt or cfg.values.get(how.get("default", ""))):
            args[how["format"]] = fmt or str(cfg.values.get(how["default"]))
        title = f"{target['plugin']}.{how['tool']}"
        action = {"plugin": target["plugin"], "tool": how["tool"], "arguments": args}
        approvals = sys_approvals.Approvals(cfg)
        private = [f["value"] for f in sec_privacy.findings(text, cfg, txt_lang.detect(text), llm) if f["sure"]]
        if private or not sys_approvals.social_auto(cfg, title):
            why = (f"privacy: {len(private)} dati da controllare" if private
                   else "oltre il numero di post che Aurora pubblica da sola oggi")
            req = approvals.request("tool_call", "external", title, f"video «{item['topic']}» — {why}", action, action, run_id)
            _mark(item, published="waiting", result=req["id"])
            emit("approval.request", {"id": req["id"], "kind": "tool_call", "title": req["title"]})
            return f"Il video «{item['topic']}» aspetta la tua approvazione ({why})."
        r = host.call(target["plugin"], how["tool"], args, run_id)
        if not r["ok"] and how.get("format") and "lasts" in r["text"]:      # too long for a Reel: a video post
            args[how["format"]] = "post"
            r = host.call(target["plugin"], how["tool"], args, run_id)
        approvals.record_auto(title, f"video «{item['topic']}»", action, r["text"], run_id)
        _mark(item, published=time.time() if r["ok"] else None, result=r["text"][:300])
        log.info("audit: scheduled video %s %s: %s", item["video"], "published" if r["ok"] else "NOT published", r["text"][:200])
        return (f"Pubblicato il video «{item['topic']}» su {target['label']}: {r['text']}" if r["ok"]
                else f"Video «{item['topic']}» non pubblicato: {r['text']}")
    return "NOTHING: no video ready"
