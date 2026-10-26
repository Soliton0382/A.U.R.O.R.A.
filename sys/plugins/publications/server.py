# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "publications": the reach of the owner's public works (owner, 26 Oct: «un plugin dove mettiamo quello che
serve per creare statistiche… una routine che mi dice le visite e i download di tutti i miei papers»).

Source, public and with no key: the records on Zenodo whose creators carry AURORA_PUBLICATIONS_ORCID (unique views
and downloads, as Zenodo's page shows them). GitHub's numbers are on the projects page already (owner, 26 Oct), not
here. Zenodo keeps only the totals: one reading a day is kept in <AURORA_PUBLICATIONS_DIR>/history.jsonl,
so the change since yesterday and since a week ago can be told.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
from aurora import sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
server = MCPServer("publications", version="1.0")
logging.getLogger("httpx").setLevel(logging.WARNING)
UA = {"User-Agent": "Aurora/1.0 (https://github.com/Soliton0382/A.U.R.O.R.A.; personal assistant)"}
ORCID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
COUNTS = ("views", "downloads")
EVERY_S = 3600                                  # the sources asked at most once an hour
_cache: dict = {"at": 0.0, "day": "", "orcid": "", "works": None}   # one user's: keyed by the ORCID too


def tool(fn):
    import functools

    @functools.wraps(fn)
    def wrapped(*a, **k):
        try:
            return fn(*a, **k)
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"{type(e).__name__}: {e}") from e
    return server.tool()(wrapped)


def _zenodo(orcid: str) -> list[dict]:
    hits = []
    for page in range(1, 9):                          # 25 a page: more is refused without a login (400)
        r = httpx.get("https://zenodo.org/api/records", headers=UA, timeout=15,
                      params={"q": f'creators.orcid:"{orcid}"', "sort": "newest", "size": 25, "page": page})
        r.raise_for_status()
        got = r.json()["hits"]
        hits += got["hits"]
        if len(hits) >= got.get("total", 0) or not got["hits"]:
            break
    out = []
    for h in hits:
        m, st = h.get("metadata", {}), h.get("stats", {})
        out.append({"id": f"zenodo:{h['id']}", "source": "zenodo", "title": m.get("title", "")[:200],
                    "kind": (m.get("resource_type") or {}).get("title", ""), "published": m.get("publication_date", ""),
                    "url": f"https://doi.org/{h['doi']}" if h.get("doi") else h.get("links", {}).get("self_html", ""),
                    "views": int(st.get("unique_views") or 0), "downloads": int(st.get("unique_downloads") or 0)})
    return out


def _folder() -> Path:
    p = cfg.path("AURORA_PUBLICATIONS_DIR")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _history() -> list[dict]:
    f = _folder() / "history.jsonl"
    rows = []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def _keep(found: list[dict], today: str) -> list[dict]:
    """Today's numbers kept (one row a day, the last reading of the day wins); the history read back."""
    rows = [r for r in _history() if r.get("day") != today]
    rows.append({"day": today, "n": {w["id"]: {k: w[k] for k in COUNTS if k in w} for w in found}})
    rows.sort(key=lambda r: r["day"])
    (_folder() / "history.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return rows


def _before(rows: list[dict], day: str) -> dict:
    """The numbers of the last day kept before `day`; {} when none is older."""
    old = [r for r in rows if r["day"] < day]
    return old[-1]["n"] if old else {}


def works(today: date | None = None) -> list[dict]:
    """Every work with its numbers and their change since yesterday («day») and since a week ago («week»)."""
    today = today or date.today()
    orcid = str(cfg["AURORA_PUBLICATIONS_ORCID"] or "").strip()      # each user's own (scope user), with their folder
    if (_cache["works"] is not None and time.time() - _cache["at"] < EVERY_S and _cache["day"] == today.isoformat()
            and _cache["orcid"] == orcid):
        return _cache["works"]
    if not orcid:
        raise ToolError("set AURORA_PUBLICATIONS_ORCID: your ORCID iD")
    if not ORCID.match(orcid):
        raise ToolError("AURORA_PUBLICATIONS_ORCID: an ORCID iD looks like 0000-0002-1825-0097")
    found = _zenodo(orcid)
    rows = _keep(found, today.isoformat())
    yday, week = _before(rows, today.isoformat()), _before(rows, (today - timedelta(days=6)).isoformat())
    for w in found:
        for label, base in (("day", yday), ("week", week)):
            b = base.get(w["id"])
            w[label] = {k: w[k] - b.get(k, 0) for k in COUNTS if k in w} if b else None
    _cache.update(at=time.time(), day=today.isoformat(), orcid=orcid, works=found)
    return found


def _sign(n: int) -> str:
    return f"+{n}" if n > 0 else str(n)


def report(ws: list[dict]) -> str:
    papers = [w for w in ws if w["source"] == "zenodo"]
    lines = []
    if papers:
        v, d = sum(w["views"] for w in papers), sum(w["downloads"] for w in papers)
        dv = sum((w["day"] or {}).get("views", 0) for w in papers)
        dd = sum((w["day"] or {}).get("downloads", 0) for w in papers)
        lines.append(f"📚 {len(papers)} opere su Zenodo: {v} visite ({_sign(dv)} da ieri), {d} download ({_sign(dd)}).")
        for w in papers:
            ch = w["day"] or {}
            moved = (f" — da ieri {_sign(ch.get('views', 0))} visite, {_sign(ch.get('downloads', 0))} download"
                     if ch.get("views") or ch.get("downloads") else "")
            lines.append(f"- {w['title']} ({w['kind']}, {w['published']}): {w['views']} visite, "
                         f"{w['downloads']} download{moved}")
    if ws and not any(w["day"] for w in ws):
        lines.append("Prima lettura: da domani ti dico anche quanto sono cambiati.")
    return "\n".join(lines) or "Nessuna opera trovata su Zenodo con questo ORCID."


@tool
def publications_list() -> str:
    """Your public works as JSON: each with its views and downloads and
    their change since yesterday («day») and a week ago («week»); null where nothing older was kept."""
    return json.dumps(works(), ensure_ascii=False)


@tool
def publications_report() -> str:
    """The day's report on your works: the totals, the change since yesterday, one line per work."""
    return report(works())


if __name__ == "__main__":
    server.run()
