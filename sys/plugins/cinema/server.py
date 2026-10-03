# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "cinema": films and series from TMDB (themoviedb.org): what is trending, search, details, and where a title
streams, rents or sells in the owner's country (watch providers, data by JustWatch).

Read only. The TMDB key (AURORA_TMDB_TOKEN) may be the short "API key" (v3, sent as a parameter) or the long "API
read access token" (sent as a Bearer header). Required attributions: "This product uses the TMDB API but is not
endorsed or certified by TMDB" and, for the providers, "data by JustWatch".
"""
from __future__ import annotations

import os

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

API = "https://api.themoviedb.org/3"
TOKEN = os.environ.get("AURORA_TMDB_TOKEN", "").strip()
REGION = (os.environ.get("AURORA_TMDB_REGION", "") or "IT").strip().upper()[:2]
LANG = "it-IT" if os.environ.get("AURORA_LANG_DEFAULT", "it").lower().startswith("it") else "en-US"
CREDIT = "Dati: TMDB (questo prodotto usa l'API di TMDB ma non è approvato né certificato da TMDB)"
KINDS = {"movie": "film", "tv": "serie"}
server = MCPServer("cinema", version="1.0")


def _get(path: str, **params) -> dict:
    if not TOKEN:
        raise ToolError("AURORA_TMDB_TOKEN is empty: a free key from themoviedb.org (Settings → API)")
    headers = {"Accept": "application/json"}
    if len(TOKEN) > 40:                                   # the long read access token (v4 style)
        headers["Authorization"] = f"Bearer {TOKEN}"
    else:
        params["api_key"] = TOKEN
    r = httpx.get(f"{API}{path}", params={"language": LANG, **params}, headers=headers, timeout=20)
    if r.status_code == 401:
        raise ToolError("TMDB refused the key (AURORA_TMDB_TOKEN)")
    if r.status_code == 404:
        raise ToolError("not found on TMDB")
    r.raise_for_status()
    return r.json()


def _kind(item: dict, default: str = "movie") -> str:
    return item.get("media_type") if item.get("media_type") in KINDS else default


def _line(item: dict, default: str = "movie") -> str:
    k = _kind(item, default)
    title = item.get("title") or item.get("name") or "?"
    date = (item.get("release_date") or item.get("first_air_date") or "")[:4]
    vote = item.get("vote_average")
    over = (item.get("overview") or "").replace("\n", " ")
    over = over if len(over) <= 220 else over[:217].rsplit(" ", 1)[0] + "…"
    return (f"- {title} ({KINDS[k]}{', ' + date if date else ''}{f', voto {vote:.1f}/10' if vote else ''}) "
            f"[id {k}:{item.get('id')}]\n  {over}")


def _ref(ref: str) -> tuple[str, int]:
    kind, _, num = str(ref).partition(":")
    if kind not in KINDS or not num.isdigit():
        raise ToolError("id like movie:603 or tv:1399 (from cinema_trending or cinema_search)")
    return kind, int(num)


def _providers(kind: str, num: int) -> str:
    res = _get(f"/{kind}/{num}/watch/providers").get("results", {}).get(REGION) or {}
    parts = []
    for key, label in (("flatrate", "in abbonamento"), ("free", "gratis"), ("ads", "gratis con pubblicità"),
                       ("rent", "a noleggio"), ("buy", "in vendita")):
        names = sorted({p["provider_name"] for p in res.get(key, [])})
        if names:
            parts.append(f"{label}: {', '.join(names)}")
    if not parts:
        return f"Dove vederlo ({REGION}): nessun servizio di streaming noto."
    return f"Dove vederlo ({REGION}, dati JustWatch): " + "; ".join(parts)


@server.tool()
def cinema_trending(kind: str = "all", window: str = "week", limit: int = 10) -> str:
    """Films and series in vogue now. kind: movie, tv or all; window: day or week."""
    kind = kind if kind in ("movie", "tv", "all") else "all"
    window = window if window in ("day", "week") else "week"
    items = _get(f"/trending/{kind}/{window}").get("results", [])
    if kind == "all":                                     # people (actors) are trending too: only titles here
        items = [i for i in items if i.get("media_type") in KINDS]
    items = items[:max(1, min(limit, 20))]
    return "\n".join([_line(i, kind if kind != "all" else "movie") for i in items] + [CREDIT])


@server.tool()
def cinema_now_playing(limit: int = 12) -> str:
    """Films in the cinemas of the owner's country now."""
    items = _get("/movie/now_playing", region=REGION).get("results", [])[:max(1, min(limit, 20))]
    return "\n".join([_line(i) for i in items] + [CREDIT])


@server.tool()
def cinema_search(query: str, limit: int = 8) -> str:
    """Find films, series by title (or a part of it)."""
    if not query.strip():
        raise ToolError("query: a title")
    items = [i for i in _get("/search/multi", query=query.strip(), include_adult="false").get("results", [])
             if i.get("media_type") in KINDS][:max(1, min(limit, 20))]
    return "\n".join([_line(i) for i in items] + [CREDIT]) if items else f"nothing found for «{query}»"


@server.tool()
def cinema_details(ref: str) -> str:
    """A title in full: plot, genres, length, director and cast, vote, and where to watch it. ref: movie:603 or tv:1399."""
    kind, num = _ref(ref)
    d = _get(f"/{kind}/{num}", append_to_response="credits")
    title = d.get("title") or d.get("name")
    crew = d.get("credits", {}).get("crew", [])
    lead = [c["name"] for c in crew if c.get("job") in ("Director", "Creator")][:2] or [c["name"] for c in d.get("created_by", [])][:2]
    cast = [c["name"] for c in d.get("credits", {}).get("cast", [])[:6]]
    length = (f"{d['runtime']} min" if d.get("runtime") else
              f"{d.get('number_of_seasons', '?')} stagioni, {d.get('number_of_episodes', '?')} episodi" if kind == "tv" else "")
    rows = [f"{title} ({KINDS[kind]}, {(d.get('release_date') or d.get('first_air_date') or '')[:4]})",
            f"Generi: {', '.join(g['name'] for g in d.get('genres', []))}" + (f" · {length}" if length else ""),
            f"Voto: {d.get('vote_average', 0):.1f}/10 ({d.get('vote_count', 0)} voti)",
            (f"Regia: {', '.join(lead)}" if kind == "movie" else f"Ideata da: {', '.join(lead)}") if lead else "",
            f"Con: {', '.join(cast)}" if cast else "",
            f"Trama: {d.get('overview') or '—'}",
            _providers(kind, num), CREDIT]
    return "\n".join(r for r in rows if r)


@server.tool()
def cinema_where(title: str) -> str:
    """Where to watch a title in the owner's country (subscription, rent, buy), found by its name."""
    items = [i for i in _get("/search/multi", query=title.strip()).get("results", []) if i.get("media_type") in KINDS]
    if not items:
        return f"nothing found for «{title}»"
    i = items[0]
    return f"{_line(i)}\n{_providers(i['media_type'], i['id'])}\n{CREDIT}"


if __name__ == "__main__":
    server.run("stdio")
