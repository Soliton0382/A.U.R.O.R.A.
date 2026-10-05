# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Synapses (owner, 2026-10-05: "neurons make new synapses when needed; Aurora has what it takes to make the links in
her knowledge"): lasting, weighted links between passages of DIFFERENT domains, that grow, get stronger with use and
fade without it.

- grow where there is activity (each question): the passages it brought up get their links at once, in the
  background — synapses form where knowledge is used (a night round covers ~400 passages of 344k: too slow alone);
- grow (at night, aurora-rem): for passages not yet looked at, their nearest passages in other domains; a link when
  the similarity reaches AURORA_SYNAPSE_MIN (0.72: the top ~5% of every passage's best match in another domain, M107);
- spread (each question): the linked passages of the best candidates join the candidates — the re-ranker still
  decides, a link never puts a passage in the answer by itself;
- strengthen (Hebb: what fires together wires together): passages cited together in one answer, a link made or made
  stronger;
- fade (daily): a link unused for a week loses a little weight each day; below FADE_FLOOR it is gone.
State: <AURORA_STATUS_DIR>/synapses.db (SQLite): the knowledge is shared, so are its links.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from contextlib import closing

import numpy as np

from . import sys_config

_lock = threading.Lock()
HEBB_NEW, HEBB_STEP, FADE_DAY, FADE_FLOOR, FADE_AFTER = 0.6, 0.05, 0.01, 0.5, 7 * 86400


def _db(cfg: sys_config.Config) -> sqlite3.Connection:
    f = (cfg.base or cfg).path("AURORA_STATUS_DIR") / "synapses.db"
    f.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f, timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS links (a TEXT, b TEXT, da TEXT, db TEXT, w REAL, kind TEXT, made REAL,"
                " last REAL, uses INTEGER DEFAULT 0, PRIMARY KEY (a, b))")
    con.execute("CREATE INDEX IF NOT EXISTS links_b ON links (b)")
    con.execute("CREATE TABLE IF NOT EXISTS cursor (domain TEXT PRIMARY KEY, shard TEXT, row INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS looked (sid TEXT PRIMARY KEY, at REAL)")
    have = {r[1] for r in con.execute("PRAGMA table_info(links)")}
    for col, decl in (("pinned", "INTEGER DEFAULT 0"), ("level", "INTEGER DEFAULT 1"), ("active", "INTEGER DEFAULT 1"),
                      ("note", "TEXT DEFAULT ''")):
        if col not in have:                           # an older synapses.db: the columns of 2026-10-05 evening
            con.execute(f"ALTER TABLE links ADD COLUMN {col} {decl}")
    con.execute("CREATE TABLE IF NOT EXISTS concepts (id INTEGER PRIMARY KEY, members TEXT, domains TEXT, name TEXT,"
                " made REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    return con


REFS = re.compile(r"\[\d{1,3}\]\s*[A-Z]|et al\.|doi:|arXiv:\d")


def references(text: str) -> bool:
    """A bibliography's passage: lists of references look alike by their form, not by what they say (M107 bis)."""
    return len(REFS.findall(text)) >= 4


def same_source(x, y) -> bool:
    """Two passages of one document — the same source, or the same title (an article that came twice: from the
    previous installation in literature, from the harvester in religion, M108): a link would teach nothing."""
    sx, sy = getattr(x, "source_id", None), getattr(y, "source_id", None)
    if sx and sx == sy:
        return True
    tx, ty = (re.sub(r"\W+", " ", str(getattr(o, "title", "") or "")).strip().lower() for o in (x, y))
    return len(tx) >= 6 and tx == ty


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def link(cfg: sys_config.Config, a: tuple[str, str], b: tuple[str, str], w: float, kind: str = "grow") -> None:
    """(sid, domain) a and b linked with weight w (the stronger of the old and the new)."""
    (x, dx), (y, dy) = sorted([a, b])
    now = time.time()
    with _lock, closing(_db(cfg)) as con, con:
        con.execute("INSERT INTO links (a, b, da, db, w, kind, made, last) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT (a, b) DO UPDATE SET w = max(w, excluded.w)", (x, y, dx, dy, float(w), kind, now, now))


def grow(cfg: sys_config.Config, reader, index, embedder, limit: int) -> dict:
    """Look at up to `limit` passages not looked at yet (a round over the domains, each from where it stopped)."""
    t0, seen, made = time.time(), 0, 0
    domains = list(reader.layout.domains("knowledge"))
    if not domains:
        return {"seen": 0, "made": 0, "seconds": 0}
    per = max(1, limit // len(domains))
    with closing(_db(cfg)) as con:
        cur = {d: (s, r) for d, s, r in con.execute("SELECT domain, shard, row FROM cursor")}
    for d in domains:
        batch, last = [], cur.get(d)
        for key, row, s in reader.iter_domain(d, after=last):
            batch.append(s)
            last = (key, row)
            if len(batch) >= per:
                break
        if not batch:
            continue
        seen += len(batch)                                # looked at, bibliographies included (they get no link)
        useful = [s for s in batch if not references(s.text)]
        vecs = embedder.encode_queries([s.text[:1500] for s in useful]) if useful else []
        for s, found in zip(useful, index.search(np.asarray(vecs), 30, {"knowledge"}, None) if useful else []):
            near = [(sid, sc) for sid, sc, _, _ in found if sid != s.sid and sc >= cfg["AURORA_SYNAPSE_MIN"]]
            got = reader.get_many({sid: 0 for sid, _ in near})
            for sid, sc in [(sid, sc) for sid, sc in near if sid in got and got[sid].domain != d
                            and not references(got[sid].text) and not same_source(s, got[sid])][:3]:
                link(cfg, (s.sid, d), (sid, got[sid].domain), sc)
                made += 1
        with _lock, closing(_db(cfg)) as con, con:
            con.execute("INSERT OR REPLACE INTO cursor VALUES (?, ?, ?)", (d, last[0], last[1]))
        if seen >= limit:
            break
    return {"seen": seen, "made": made, "seconds": round(time.time() - t0, 1)}


def grow_for(cfg: sys_config.Config, reader, index, embedder, sids: list[str]) -> int:
    """Activity makes synapses (as in a brain): the passages a question just brought up, not looked at yet, get their
    links to other domains now. Returns the links made."""
    with closing(_db(cfg)) as con:
        q = ",".join("?" * len(sids))
        done = {r[0] for r in con.execute(f"SELECT sid FROM looked WHERE sid IN ({q})", sids)} if sids else set()
    todo = [s for s in reader.get_many({sid: 0 for sid in sids if sid not in done}).values()]
    todo = [s for s in todo if s.kind not in ("conversation", "reflection") and not references(s.text)]
    if not todo:
        return 0
    made = 0
    vecs = embedder.encode_queries([s.text[:1500] for s in todo])
    for s, found in zip(todo, index.search(np.asarray(vecs), 30, {"knowledge"}, None)):
        near = [(sid, sc) for sid, sc, _, _ in found if sid != s.sid and sc >= cfg["AURORA_SYNAPSE_MIN"]]
        got = reader.get_many({sid: 0 for sid, _ in near})
        for sid, sc in [(sid, sc) for sid, sc in near if sid in got and got[sid].domain != s.domain
                        and not references(got[sid].text) and not same_source(s, got[sid])][:3]:
            link(cfg, (s.sid, s.domain), (sid, got[sid].domain), sc, kind="activity")
            made += 1
    with _lock, closing(_db(cfg)) as con, con:
        con.executemany("INSERT OR IGNORE INTO looked VALUES (?, ?)", [(s.sid, time.time()) for s in todo])
    return made


def neighbours(cfg: sys_config.Config, sids: list[str], limit: int) -> list[tuple[str, float, str]]:
    """(linked sid, weight, from sid) of the given passages, strongest first, at most `limit`, none of the given."""
    if not sids or limit <= 0:
        return []
    given = set(sids)
    q = ",".join("?" * len(sids))
    with closing(_db(cfg)) as con:
        rows = con.execute(f"SELECT a, b, w FROM links WHERE active = 1 AND (a IN ({q}) OR b IN ({q}))", sids + sids).fetchall()
    out: dict[str, tuple[float, str]] = {}
    for a, b, w in rows:
        for src, dst in ((a, b), (b, a)):
            if src in given and dst not in given and w > out.get(dst, (0, ""))[0]:
                out[dst] = (w, src)
    return sorted(((s, w, src) for s, (w, src) in out.items()), key=lambda x: -x[1])[:limit]


def used(cfg: sys_config.Config, sids: list[str]) -> None:
    """The links that brought these passages into an answer were useful: their clock and count."""
    if not sids:
        return
    q = ",".join("?" * len(sids))
    with _lock, closing(_db(cfg)) as con, con:
        con.execute(f"UPDATE links SET last = ?, uses = uses + 1 WHERE active = 1 AND (a IN ({q}) OR b IN ({q}))",
                    [time.time()] + sids + sids)


def strengthen(cfg: sys_config.Config, cited: list[tuple]) -> int:
    """Passages (sid, domain[, source]) cited together in one answer: each cross-domain pair of different documents
    linked, or its link stronger."""
    n, now = 0, time.time()
    for i, x in enumerate(cited):
        for y in cited[i + 1:]:
            (a, da), (b, db) = x[:2], y[:2]
            if da == db or a == b or (len(x) > 2 and len(y) > 2 and x[2] and x[2] == y[2]):
                continue
            lo, hi = _pair(a, b)
            dlo, dhi = (da, db) if lo == a else (db, da)
            with _lock, closing(_db(cfg)) as con, con:
                con.execute("INSERT INTO links (a, b, da, db, w, kind, made, last, uses) VALUES (?, ?, ?, ?, ?, 'hebb', ?, ?, 1) "
                            "ON CONFLICT (a, b) DO UPDATE SET w = min(1.0, w + ?), last = ?, uses = uses + 1, active = 1",
                            (lo, hi, dlo, dhi, HEBB_NEW, now, now, HEBB_STEP, now))
            n += 1
    return n


def fade(cfg: sys_config.Config, now: float | None = None) -> dict:
    """Once a day: links unused for a week lose FADE_DAY, except those the owner pinned; below FADE_FLOOR a link is
    put to sleep, not deleted (owner, 2026-10-05: he may want a faded concept back) — it no longer spreads."""
    now = now or time.time()
    with _lock, closing(_db(cfg)) as con, con:
        weaker = con.execute("UPDATE links SET w = w - ? WHERE last < ? AND pinned = 0 AND active = 1",
                             (FADE_DAY, now - FADE_AFTER)).rowcount
        gone = con.execute("UPDATE links SET active = 0 WHERE w < ? AND pinned = 0 AND active = 1", (FADE_FLOOR,)).rowcount
    return {"weaker": weaker, "gone": gone}


def edit(cfg: sys_config.Config, a: str, b: str, w: float | None = None, pinned: bool | None = None,
         active: bool | None = None, delete: bool = False) -> dict | None:
    """The owner's hand on a link: its weight, pinned (never fades), awake again, or deleted."""
    x, y = _pair(a, b)
    with _lock, closing(_db(cfg)) as con, con:
        if delete:
            con.execute("DELETE FROM links WHERE a = ? AND b = ?", (x, y))
            return None
        if w is not None:
            con.execute("UPDATE links SET w = ?, active = CASE WHEN ? >= ? THEN 1 ELSE active END, last = ? "
                        "WHERE a = ? AND b = ?", (max(0.0, min(1.0, float(w))), float(w), FADE_FLOOR, time.time(), x, y))
        if pinned is not None:
            con.execute("UPDATE links SET pinned = ? WHERE a = ? AND b = ?", (int(bool(pinned)), x, y))
        if active is not None:
            con.execute("UPDATE links SET active = ?, w = CASE WHEN ? = 1 AND w < ? THEN ? ELSE w END, last = ? "
                        "WHERE a = ? AND b = ?", (int(bool(active)), int(bool(active)), FADE_FLOOR, HEBB_NEW, time.time(), x, y))
        row = con.execute("SELECT a, b, da, db, w, kind, made, last, uses, pinned, level, active, note FROM links "
                          "WHERE a = ? AND b = ?", (x, y)).fetchone()
    return _row(row) if row else None


def _row(r) -> dict:
    keys = ("a", "b", "da", "db", "w", "kind", "made", "last", "uses", "pinned", "level", "active", "note")
    return dict(zip(keys, r))


def listing(cfg: sys_config.Config, active: bool = True, domain: str = "", level: int = 0, limit: int = 100,
            offset: int = 0) -> list[dict]:
    """The links for the Synapses page: awake or asleep, of a domain, of a level; strongest first."""
    where, args = ["active = ?"], [int(active)]
    if domain:
        where.append("(da = ? OR db = ?)")
        args += [domain, domain]
    if level:
        where.append("level = ?")
        args.append(int(level))
    with closing(_db(cfg)) as con:
        rows = con.execute(f"SELECT a, b, da, db, w, kind, made, last, uses, pinned, level, active, note FROM links "
                           f"WHERE {' AND '.join(where)} ORDER BY pinned DESC, w DESC LIMIT ? OFFSET ?",
                           args + [int(limit), int(offset)]).fetchall()
    return [_row(r) for r in rows]


def stats(cfg: sys_config.Config) -> dict:
    with closing(_db(cfg)) as con:
        total, used_ = con.execute("SELECT count(*), sum(uses > 0) FROM links WHERE active = 1").fetchone()
        asleep, pinned = con.execute("SELECT sum(active = 0), sum(pinned = 1) FROM links").fetchone()
        levels = dict(con.execute("SELECT level, count(*) FROM links WHERE active = 1 GROUP BY level").fetchall())
        concepts = con.execute("SELECT count(*) FROM concepts").fetchone()[0]
        kinds = dict(con.execute("SELECT kind, count(*) FROM links WHERE active = 1 GROUP BY kind").fetchall())
        pairs = con.execute("SELECT min(da, db), max(da, db), count(*) n FROM links WHERE active = 1 "
                            "GROUP BY min(da, db), max(da, db) "
                            "ORDER BY n DESC LIMIT 8").fetchall()      # a pair of domains once, whatever the order
        day = con.execute("SELECT count(*) FROM links WHERE active = 1 AND made > ?", (time.time() - 86400,)).fetchone()[0]
    return {"links": total or 0, "used": used_ or 0, "kinds": kinds, "today": day, "asleep": asleep or 0,
            "pinned": pinned or 0, "levels": levels, "concepts": concepts,
            "pairs": [{"a": a, "b": b, "n": n} for a, b, n in pairs]}
