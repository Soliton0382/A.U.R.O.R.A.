# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "news": what is happening in the world, from the official RSS feeds of established newsrooms (feeds.json).

Read only: titles, a short summary, the source, the time and the link of each item — never the whole article (that
stays with its publisher: a post links to it). Feeds are read at most every 15 minutes (a small cache in memory).
XML is parsed by expat (protected against entity expansion since 2.4) with no external entities.
"""
from __future__ import annotations

import html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

FEEDS = json.loads((Path(__file__).parent / "feeds.json").read_text(encoding="utf-8"))["topics"]
UA = {"User-Agent": "Aurora/1.0 (+https://github.com/Soliton0382/A.U.R.O.R.A.)"}
TTL, _cache = 900, {}
server = MCPServer("news", version="1.0")


def _text(node, *names) -> str:
    for n in names:
        el = node.find(n)
        if el is not None and (el.text or el.get("href")):
            return (el.text or el.get("href") or "").strip()
    return ""


def _when(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _clean(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def _read(source: str, url: str) -> list[dict]:
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    r = httpx.get(url, headers=UA, timeout=20, follow_redirects=True)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    atom = "{http://www.w3.org/2005/Atom}"
    nodes = root.findall(".//item") or root.findall(f".//{atom}entry")
    items = []
    for it in nodes[:60]:
        title = _clean(_text(it, "title", f"{atom}title"), 200)
        link = _text(it, "link", f"{atom}link")
        if not title or not link.startswith("http"):
            continue
        items.append({"source": source, "title": title, "link": link,
                      "summary": _clean(_text(it, "description", f"{atom}summary", f"{atom}content"), 280),
                      "when": _when(_text(it, "pubDate", f"{atom}updated", f"{atom}published",
                                          "{http://purl.org/dc/elements/1.1/}date"))})
    _cache[url] = (time.time(), items)
    return items


@server.tool()
def news_topics() -> str:
    """The topics and the sources of each."""
    return "\n".join(f"{t}: " + ", ".join(s for s, _ in feeds) for t, feeds in FEEDS.items())


@server.tool()
def news_headlines(topic: str = "mondo", hours: int = 24, limit: int = 12) -> str:
    """The latest news of a topic (italia, mondo, scienza, tecnologia, spazio, astronomia, astrofotografia, fisica,
    biologia, or "tutto"): title, source, time,
    a short summary and the link. Newest first; items without a date at the end."""
    topic = topic.strip().lower()
    if topic in ("tutto", "all", "*"):
        feeds = [f for fs in FEEDS.values() for f in fs]
    elif topic in FEEDS:
        feeds = FEEDS[topic]
    else:
        raise ToolError(f"unknown topic {topic!r}: {', '.join(FEEDS)} or tutto")
    since = datetime.now(timezone.utc) - timedelta(hours=max(1, min(hours, 168)))
    items, failed = [], []
    for source, url in feeds:
        try:
            items += [i for i in _read(source, url) if i["when"] is None or i["when"] >= since]
        except (httpx.HTTPError, ET.ParseError) as e:
            failed.append(f"{source} ({type(e).__name__})")
    items.sort(key=lambda i: i["when"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    seen, rows = set(), []
    for i in items:
        key = re.sub(r"\W+", "", i["title"].lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        when = i["when"].astimezone().strftime("%d/%m %H:%M") if i["when"] else "?"
        rows.append(f"- [{when}] {i['title']} — {i['source']}\n  {i['summary']}\n  {i['link']}")
        if len(rows) >= max(1, min(limit, 40)):
            break
    head = f"Notizie: {topic}, ultime {hours} ore ({len(rows)})"
    tail = f"\n(non raggiungibili: {', '.join(failed)})" if failed else ""
    return head + "\n" + ("\n".join(rows) or "nessuna notizia nel periodo") + tail


if __name__ == "__main__":
    server.run("stdio")
