# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The firewall's official documentation, kept and searched on this machine (owner, 2026-10-07: "the security plugin
can index the whole manual and use it to carry out the operations").

Three sources, each a setting (Sophos Firewall 22.0 by default; a new version is a new number in the three links):
  manual   AURORA_FIREWALL_MANUAL_URL — the administrator's help (MkDocs: every page listed in its sitemap.xml)
  api      AURORA_FIREWALL_API_DOC_URL — the XML API reference (list.html → entity pages → operation pages; the
           operation's sample request, inside <xmp>, is kept verbatim: it is what the writer copies)
  syslog   AURORA_SECURITY_SYSLOG_DOC — the syslog reference (one page, cut at its headings)
Kept in <STATUS>/security/fwdocs.sqlite with a full-text index (FTS5, no GPU, no model): search() gives the passages,
sample() the API's sample of an entity. The documentation is copyrighted («no part may be stored in a retrieval
system unless you are a valid licensee»): the owner of the firewall is; the index stays on this machine, never in the
repository, never sent anywhere.
"""
from __future__ import annotations

import html
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote, urljoin

import httpx

from . import sys_config, sys_log

UA = {"User-Agent": "Aurora/1.0 (https://github.com/Soliton0382/A.U.R.O.R.A.; security plugin, owner's licensed firewall)"}
CHUNK = 1800                                         # characters of a passage: a section of a page, or a part of it


def path(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "security" / "fwdocs.sqlite"


def _db(cfg: sys_config.Config) -> sqlite3.Connection:
    p = path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE IF NOT EXISTS pages (url TEXT PRIMARY KEY, kind TEXT, title TEXT, fetched REAL)")
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(kind, title, url UNINDEXED, text, "
                "tokenize='porter unicode61')")
    con.execute("CREATE TABLE IF NOT EXISTS samples (entity TEXT, operation TEXT, url TEXT, xml TEXT)")
    return con


# ---- text out of a page --------------------------------------------------------------------------------------------
def _plain(fragment: str) -> str:
    fragment = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", fragment, flags=re.S | re.I)
    fragment = re.sub(r"<(h[1-4])[^>]*>", "\n\n## ", fragment, flags=re.I)
    fragment = re.sub(r"<(br|p|li|tr|div)[^>]*>", "\n", fragment, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n\s*(\n\s*)+", "\n\n", text).strip()


def page_text(raw: str) -> tuple[str, str, list[str]]:
    """(title, text, samples): the article of a MkDocs page or the body of any other; an <xmp> sample stays as XML."""
    title = html.unescape(re.sub(r"\s+", " ", (re.search(r"<title>(.*?)</title>", raw, re.S | re.I) or [None, ""])[1])).strip()
    samples = [s.strip() for s in re.findall(r"<xmp[^>]*>(.*?)</xmp>", raw, re.S | re.I)]
    raw = re.sub(r"<xmp[^>]*>(.*?)</xmp>", lambda m: "\n[[SAMPLE]]\n", raw, flags=re.S | re.I)
    body = re.search(r"<article[^>]*>(.*?)</article>", raw, re.S | re.I) or re.search(r"<body[^>]*>(.*)</body>", raw, re.S | re.I)
    text = _plain(body.group(1) if body else raw)
    text = re.sub(r"©\s*Copyright.*$", "", text, flags=re.S)          # the footer, the same on every API page
    for s in samples:
        text = text.replace("[[SAMPLE]]", "\n" + s + "\n", 1)
    if not title:
        title = (re.search(r"Operation:\s*([^\n]+)", text) or re.search(r"Entity:\s*([^\n]+)", text) or [None, ""])[1].strip()
    return title, text, samples


def chunks(text: str, size: int = CHUNK) -> list[str]:
    """Sections at the headings, each cut to `size` at a paragraph when longer."""
    out = []
    for sec in re.split(r"\n(?=## )", text):
        sec = sec.strip()
        while len(sec) > size:
            cut = sec.rfind("\n", 0, size)
            cut = cut if cut > size // 3 else size
            out.append(sec[:cut].strip())
            sec = sec[cut:].strip()
        if len(sec) > 40:
            out.append(sec)
    return out


# ---- which pages --------------------------------------------------------------------------------------------------
def manual_pages(client: httpx.Client, base: str) -> list[str]:
    root = base.rsplit("/", 1)[0] + "/" if base.endswith(".html") else base.rstrip("/") + "/"
    r = client.get(root + "sitemap.xml")
    r.raise_for_status()
    return [u.strip() for u in re.findall(r"<loc>([^<]+)</loc>", r.text)]


def api_pages(client: httpx.Client, base: str) -> list[str]:
    """The entity pages named in list.html, then each entity's operation pages (names with spaces and «&»)."""
    root = base.rsplit("/", 1)[0] + "/"
    r = client.get(root + "list.html")
    r.raise_for_status()
    entities = sorted({p for p in re.findall(r"[A-Za-z0-9_./-]+\.html", r.text) if "/operations/" not in p and "/" in p})
    out = []
    for e in entities:
        url = urljoin(root, e)
        out.append(url)
        try:
            page = client.get(url).text
        except httpx.HTTPError:
            continue
        out += [urljoin(url, quote(h, safe="/&")) for h in re.findall(r"href='(operations/[^']+)'", page)]
    return out


# ---- the index ----------------------------------------------------------------------------------------------------
def _entity(url: str) -> tuple[str, str]:
    parts = url.split("/")
    if "operations" in parts:
        i = parts.index("operations")
        return parts[i - 1], re.sub(r"\.html$", "", parts[-1]).replace("%20", " ")
    return re.sub(r"\.html$", "", parts[-1]), ""


def add_page(con: sqlite3.Connection, kind: str, url: str, raw: str) -> int:
    title, text, samples = page_text(raw)
    con.execute("DELETE FROM passages WHERE url = ?", (url,))
    con.execute("DELETE FROM samples WHERE url = ?", (url,))
    parts = chunks(text) if kind != "syslog" else chunks(text, 2400)
    con.executemany("INSERT INTO passages (kind, title, url, text) VALUES (?, ?, ?, ?)",
                    [(kind, title, url, p) for p in parts])
    if kind == "api":
        entity, op = _entity(url)
        con.executemany("INSERT INTO samples VALUES (?, ?, ?, ?)", [(entity, op, url, s) for s in samples])
    con.execute("INSERT OR REPLACE INTO pages VALUES (?, ?, ?, ?)", (url, kind, title, time.time()))
    return len(parts)


def refresh(cfg: sys_config.Config, kinds: tuple[str, ...] = ("syslog", "api", "manual"), pause: float = 0.2,
            limit: int | None = None, progress=None) -> dict:
    """Download and index the three sources (a few minutes: about 1,200 pages at `pause` seconds). A page that fails
    is counted, not fatal. Returns {kind: {"pages", "passages", "failed"}}."""
    log = sys_log.get_logger("security")
    out = {}
    with httpx.Client(timeout=60, follow_redirects=True, headers=UA) as client:
        for kind in kinds:
            if kind == "syslog":
                urls = [str(cfg["AURORA_SECURITY_SYSLOG_DOC"])]
            elif kind == "api":
                urls = api_pages(client, str(cfg["AURORA_FIREWALL_API_DOC_URL"]))
            else:
                urls = manual_pages(client, str(cfg["AURORA_FIREWALL_MANUAL_URL"]))
            urls = list(dict.fromkeys(urls))[:limit] if limit else list(dict.fromkeys(urls))
            done = {"pages": 0, "passages": 0, "failed": 0}
            con = _db(cfg)
            try:
                for n, url in enumerate(urls, 1):
                    try:
                        r = client.get(url)
                        r.raise_for_status()
                        done["passages"] += add_page(con, kind, url, r.text)
                        done["pages"] += 1
                    except (httpx.HTTPError, sqlite3.Error) as e:
                        done["failed"] += 1
                        log.warning("fwdocs: %s not indexed: %s", url, e)
                    if n % 50 == 0:
                        con.commit()
                        if progress:
                            progress(kind, n, len(urls))
                    time.sleep(pause)
                con.commit()
            finally:
                con.close()
            out[kind] = done
            log.info("fwdocs: %s indexed: %s", kind, done)
    return out


def _match(query: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9]+", query) if len(w) > 1][:12]
    return " OR ".join(f'"{w}"' for w in words)


def search(cfg: sys_config.Config, query: str, k: int = 5, kind: str | None = None) -> list[dict]:
    """The best passages for `query` (BM25; the words of the query, any of them): [{"kind", "title", "url", "text"}]."""
    if not path(cfg).exists() or not _match(query):
        return []
    con = _db(cfg)
    try:
        sql = "SELECT kind, title, url, text FROM passages WHERE passages MATCH ?"
        args: list = [_match(query)]
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        rows = con.execute(sql + " ORDER BY bm25(passages, 0, 4.0, 0, 1.0) LIMIT ?", (*args, k)).fetchall()
    finally:
        con.close()
    return [{"kind": r[0], "title": r[1], "url": r[2], "text": r[3]} for r in rows]


def sample(cfg: sys_config.Config, entity: str) -> list[dict]:
    """The API's sample requests of an entity (e.g. "NATRule", "FirewallRule"): [{"operation", "url", "xml"}]."""
    if not path(cfg).exists():
        return []
    con = _db(cfg)
    try:
        rows = con.execute("SELECT operation, url, xml FROM samples WHERE lower(entity) = lower(?) OR xml LIKE ?",
                           (entity, f"%<{entity}>%")).fetchall()
    finally:
        con.close()
    return [{"operation": r[0], "url": r[1], "xml": r[2]} for r in rows]


def stats(cfg: sys_config.Config) -> dict:
    if not path(cfg).exists():
        return {"pages": {}, "passages": 0, "samples": 0, "when": None}
    con = _db(cfg)
    try:
        pages = dict(con.execute("SELECT kind, count(*) FROM pages GROUP BY kind").fetchall())
        when = con.execute("SELECT max(fetched) FROM pages").fetchone()[0]
        return {"pages": pages, "passages": con.execute("SELECT count(*) FROM passages").fetchone()[0],
                "samples": con.execute("SELECT count(*) FROM samples").fetchone()[0], "when": when}
    finally:
        con.close()
