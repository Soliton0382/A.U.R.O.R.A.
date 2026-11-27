# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Evidentia's own API for the dedicated chat in Aurora (owner, 9 Nov: «un Finder interattivo dentro aurora»):
on a unix socket only (no network port), read-only on the corpus and the findings, read-write on the case files.
Aurora's page reaches it through her own local route, the admin's only; nothing of it enters Aurora's memory."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse as _PlainJSON, PlainTextResponse
from starlette.middleware import Middleware
from starlette.routing import Route

from . import agents, archive, cases, config, health, leads, network, protect, search, shared, store

CFG = config.load()
DATA = CFG.path("EVD_DATA_DIR")                         # the owner's archive (R15: each request its user's, _data())
AGENTS = config.ROOT / "sys" / "evidentia" / "agents"               # the active cards: the project's own
PROPOSED = DATA / "agents" / "proposed"                  # a client's proposals: never active until the owner moves them


def _data() -> Path:
    """This request's archive (R15, evidentia/archive): the user's, the owner's when none is said."""
    return archive.folder(CFG)


def _ro(name: str):
    d = _data()
    if not (d / name).exists():                     # a user's new archive: its empty databases made first
        store.create(d)
    return store.connect(d, name, readonly=True)


_KEYS: dict[str, tuple[float, tuple[str, ...]]] = {}


def _protected() -> tuple[str, ...]:
    """The protected names (F5, B24) of this request's archive, read again at most every 5 s."""
    k = str(_data())
    hit = _KEYS.get(k)
    if hit is None or time.monotonic() - hit[0] > 5:
        try:
            ks = protect.keys(_ro("findings.db"))
        except Exception:  # noqa: BLE001 — no findings yet
            ks = ()
        hit = _KEYS[k] = (time.monotonic(), ks)
    return hit[1]


class JSONResponse(_PlainJSON):
    """Every answer of the server with the protected names masked, whatever handler made it (B24): passages, pages,
    quotes, subjects, the diary, the leads. The citations hold no name: they stay as they are."""
    def render(self, content) -> bytes:
        return protect.names(super().render(content).decode("utf-8"), _protected()).encode("utf-8")


def _cases():
    store.create(_data(), "cases.db")
    return store.connect(_data(), "cases.db")


def _err(code: int, why: str) -> JSONResponse:
    return JSONResponse({"detail": why}, status_code=code)


MAX_BODY = 1_000_000          # a request's body at most 1 MB: one service for every client (audit, 10 Nov)


class BadBody(Exception):
    pass


class BadValue(BadBody):
    """A field of the wrong type: 422 (a body too large or not JSON stays 400)."""


def _int(value, default: int, what: str) -> int:
    """A whole number from a query or a body, or BadBody → 422 (audit, 11 Nov, B27: «n=abc» was a 503, «offset» a 500)."""
    if value in (None, ""):
        return default
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).lstrip("-").isdigit():
        raise BadValue(f"{what}: a whole number")
    return int(value)


def _list(value, what: str) -> list:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise BadValue(f"{what}: a list")
    return value


async def _json(request: Request) -> dict:
    """The request's JSON object, or BadBody (too large, not JSON, not an object)."""
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        raise BadBody("the body is too large")
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_BODY:
            raise BadBody("the body is too large")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise BadBody("the body is not JSON") from None
    if not isinstance(body, dict):
        raise BadBody("the body is a JSON object")
    return body


async def status(_: Request):
    out = {"at": time.time()}
    try:
        c = _ro("corpus.db")
        out.update({r["status"]: r["n"] for r in c.execute("SELECT status, COUNT(*) AS n FROM documents GROUP BY status")})
        out["passages"] = c.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
    except Exception as e:  # noqa: BLE001 — no archive yet: said
        out["corpus"] = f"not built yet ({type(e).__name__})"
    return JSONResponse(out)


async def case_list(_: Request):
    own = cases.listing(_cases())
    who = archive.who() or archive.owner(CFG)
    for c in own:                                       # mine, with whom I share them
        c["members"] = shared.members(CFG, c["id"]) if isinstance(c, dict) and "id" in c else []
    theirs = []
    for cid, maker in shared.shared_with(CFG, who):     # the cases shared with me, from their makers' archives
        try:
            d = archive.folder(CFG, maker)
            theirs.append({**cases.get(store.connect(d, "cases.db"), cid), "shared_by": maker or "owner"})
        except (KeyError, ValueError, OSError):
            continue
    return JSONResponse({"cases": own + theirs})


async def case_members(request: Request):
    """👥 Who works on this case with its maker (GET; PUT {"members": [...]}): the maker's own cases only."""
    cid = request.path_params["cid"]
    try:
        cases.get(_cases(), cid)
    except KeyError:
        return _err(404, "no such case")
    if request.method == "PUT":
        body = await _json(request)
        who = archive.who() or archive.owner(CFG)
        names = [archive.owner(CFG) if str(m) == "" else str(m) for m in _list(body.get("members"), "members")]
        return JSONResponse(shared.set_members(CFG, cid, who, names))
    return JSONResponse({"members": shared.members(CFG, cid)})


async def case_new(request: Request):
    body = await _json(request)
    try:
        return JSONResponse(cases.create(_cases(), str(body.get("title", ""))))
    except ValueError as e:
        return _err(422, str(e))


async def case_one(request: Request):
    con, cid = _cases(), request.path_params["cid"]
    try:
        if request.method == "DELETE":
            return JSONResponse({"deleted": cases.delete(con, cid)})
        if request.method == "PATCH":
            body = await _json(request)
            if "group" in body:
                cases.move(con, cid, str(body.get("group") or ""))
            if "title" in body:
                cases.rename(con, cid, str(body.get("title", "")))
            return JSONResponse(cases.get(con, cid))
        return JSONResponse({**cases.get(con, cid), "table": cases.table(con, cid), "diary": cases.diary(con, cid)})
    except KeyError:
        return _err(404, "no such case")
    except ValueError as e:
        return _err(422, str(e))


async def case_export(request: Request):
    try:
        return PlainTextResponse(protect.answer(cases.markdown(_cases(), request.path_params["cid"]), _protected()),
                                 media_type="text/markdown")
    except KeyError:
        return _err(404, "no such case")


def find(request: Request):                   # sync: a count over millions of passages runs in a thread
    q, p = request.query_params.get("q", ""), request.query_params
    try:
        corpus = _ro("corpus.db")
        n, offset = _int(p.get("n"), 20, "n"), _int(p.get("offset"), 0, "offset")
        out = {"hits": search.search(corpus, q, n, offset)}
        if p.get("total"):
            out["total"], out["cap"] = search.total(corpus, q), search.COUNT_CAP
        return JSONResponse(out)
    except BadBody as e:
        return _err(422, str(e))
    except Exception as e:  # noqa: BLE001
        return _err(503, f"the archive is not ready: {type(e).__name__}")


async def case_search(request: Request):
    """A search made inside a case: its hits returned and the step written in the case's diary (with the documents)."""
    con, cid = _cases(), request.path_params["cid"]
    body = await _json(request)
    q, offset = str(body.get("q", ""))[:300], _int(body.get("offset"), 0, "offset")
    try:
        cases.get(con, cid)
        out = await run_in_threadpool(search.ask, _ro("corpus.db"), q, 20, offset)   # never on the event loop (B21)
    except KeyError:
        return _err(404, "no such case")
    except Exception as e:  # noqa: BLE001
        return _err(503, f"the archive is not ready: {type(e).__name__}")
    if not offset:                                       # the next pages of the same search are not new steps
        ks = _protected()                                # kept masked, not only shown masked (B24)
        cases.step(con, cid, "search", {"q": protect.names(q, ks), "hits": len(out["hits"]),
                                        "used": protect.names(out["used"], ks), "total": out["total"]},
                   sorted({h["doc"] for h in out["hits"]}))
    return JSONResponse(out)


async def case_step(request: Request):
    """A question, an answer or a note of the chat, written into the case's diary (Aurora's investigating agent)."""
    body = await _json(request)
    kind = str(body.get("kind", ""))
    if kind not in ("question", "answer", "note"):
        return _err(422, "kind: question, answer or note")
    text = protect.answer(str(body.get("text", "")).strip()[:20000], _protected())    # names and accounts (B24)
    if not text:
        return _err(422, "text: what was asked or answered")
    try:
        sid = cases.step(_cases(), request.path_params["cid"], kind, {"text": text},
                         [str(d) for d in _list(body.get("docs"), "docs")][:200])
    except KeyError:
        return _err(404, "no such case")
    except ValueError as e:
        return _err(422, str(e))
    return JSONResponse({"step": sid})


async def case_trace(request: Request):
    """🧾 The case's audit trail (audit.py): POST appends the steps an agent took (Aurora hands them over at the end of a
    run, keeping none), GET reads the last ones with the whole chain verified."""
    from . import audit
    cid = request.path_params["cid"]
    try:
        cases.get(_cases(), cid)
    except KeyError:
        return _err(404, "no such case")
    try:
        if request.method == "POST":
            body = await _json(request)
            who = str(body.get("who", "agent"))
            if shared.ACTOR.get():                      # a member's step in a shared case: their name in the trail
                who = f"{shared.ACTOR.get()} · {who}"
            n = audit.append(_data(), cid, _list(body.get("entries"), "entries"), who,
                             mask=lambda t: protect.answer(t, _protected()))
            return JSONResponse({"written": n})
        limit = max(1, min(int(request.query_params.get("limit", "200")), 2000))
        return JSONResponse({"verify": audit.verify(_data(), cid), "steps": audit.read(_data(), cid, limit)})
    except (ValueError, BadBody) as e:
        return _err(422, str(e))


async def case_trace_verify(request: Request):
    """The chain of the case's trail recomputed from its first line: ok, or where it breaks and why."""
    from . import audit
    try:
        return JSONResponse(audit.verify(_data(), request.path_params["cid"]))
    except ValueError as e:
        return _err(422, str(e))


async def page(request: Request):
    r = search.page(_ro("corpus.db"), request.path_params["doc"], int(request.path_params["n"]))
    return JSONResponse(r) if r else _err(404, "no such page")


async def document(request: Request):
    r = search.document(_ro("corpus.db"), request.path_params["doc"])
    return JSONResponse(r) if r else _err(404, "no such document")


async def identifier(request: Request):
    """Every page where this very identifier appears, with whether it passed its check (the MCP server's tool)."""
    kind, value = request.path_params["kind"], request.query_params.get("value", "")
    return JSONResponse({"pages": search.same_identifier(_ro("findings.db"), kind, value)})


async def agent_list(_: Request):
    """The active agents (with their instructions: the MCP server serves them as prompts) and the proposals."""
    try:
        active, proposed = agents.load(AGENTS), agents.load(PROPOSED)
    except ValueError as e:
        return _err(500, f"an agent card is broken: {e}")
    return JSONResponse({"agents": active, "proposed": [{k: c[k] for k in agents.HEADER} for c in proposed]})


async def agent_propose(request: Request):
    """A new agent proposed by a client (Aurora, when she thinks one is missing): written to the proposals, waiting for
    the owner (script/evd_agents.py approve <name>). Never over an active one or another proposal."""
    body = await _json(request)
    card = {k: str(body.get(k, "")).strip() for k in (*agents.HEADER, "instructions")}
    if any(c in card[k] for k in agents.HEADER for c in "\r\n"):
        return _err(422, "the header's fields are one line each")
    try:
        if agents.parse(agents.card_text(card), "proposal")["name"] != card["name"]:
            return _err(422, "the card names another agent")
    except ValueError as e:
        return _err(422, str(e))
    if (AGENTS / f"{card['name']}.md").exists() or (PROPOSED / f"{card['name']}.md").exists():
        return _err(409, f"an agent named {card['name']} exists or is already proposed")
    if len(card["instructions"]) > 6000:
        return _err(422, "instructions: at most 6,000 characters")
    if _proposals() >= MAX_PROPOSED:                     # an agent in a loop never fills the disk (audit, 11 Nov, B26)
        return _err(429, f"{MAX_PROPOSED} proposals wait for the owner already: let them be looked at first")
    PROPOSED.mkdir(parents=True, exist_ok=True)
    (PROPOSED / f"{card['name']}.md").write_text(agents.card_text(card), encoding="utf-8")
    return JSONResponse({"proposed": card["name"], "active": False, "approve": "evd_agents.py approve " + card["name"]})


MAX_PROPOSED = 50


def _proposals() -> int:
    """How many proposals wait, counted without reading them."""
    return sum(1 for _ in PROPOSED.glob("*.md")) if PROPOSED.is_dir() else 0


def _known() -> dict[str, dict]:
    return {a["name"]: a for a in agents.load(AGENTS)}


async def lead_open(request: Request):
    """A lead opened in a case: chased once by its agent; the same work already done comes back with its evidence."""
    body = await _json(request)
    try:
        parent = body.get("parent")
        ks = _protected()
        out = leads.open_lead(_cases(), request.path_params["cid"], protect.names(str(body.get("what", "")), ks),
                              str(body.get("agent", "")), set(_known()), protect.names(str(body.get("why", "")), ks), _list(body.get("docs"), "docs"),
                              _int(parent, None, "parent"))
        return JSONResponse(out)
    except KeyError:
        return _err(404, "no such case or lead")
    except (ValueError, TypeError) as e:
        return _err(422, str(e))


async def lead_list(request: Request):
    q = request.query_params
    return JSONResponse({"leads": leads.listing(_cases(), q.get("status", ""), q.get("case", ""))})


async def lead_one(request: Request):
    try:
        lid = int(request.path_params["lid"])
        if request.method == "DELETE":
            return JSONResponse(leads.drop(_cases(), lid, (await _json(request)).get("why", "")))
        return JSONResponse(leads.get(_cases(), lid))
    except KeyError:
        return _err(404, "no such lead")
    except ValueError as e:
        return _err(422, str(e))


async def lead_reopen(request: Request):
    """↩️ The owner's page opens a cold or dropped lead again (B20); not a tool of the MCP server."""
    try:
        return JSONResponse(leads.reopen(_cases(), int(request.path_params["lid"]), (await _json(request)).get("why", "")))
    except KeyError:
        return _err(404, "no such lead")
    except ValueError as e:
        return _err(422, str(e))


async def lead_claim(request: Request):
    """The next lead for a worker (Aurora's routine, or any client), with its agent's prompt ready to run."""
    body = await _json(request)
    try:
        lead = leads.claim(_cases(), str(body.get("worker", "")), str(body.get("agent", "")))
    except ValueError as e:
        return _err(422, str(e))
    if lead is None:
        return JSONResponse({"lead": None})
    card = _known().get(lead["agent"])
    goal = f"{lead['what']}\n\nWhy: {lead['why']}" + (f"\nStart from: {', '.join(lead['docs'])}" if lead["docs"] else "")
    return JSONResponse({"lead": lead, "prompt": agents.prompt(card, goal) + leads.REPORT if card else None})


async def lead_report(request: Request):
    body = await _json(request)
    try:
        out = leads.report(_cases(), _ro("corpus.db"), int(request.path_params["lid"]), str(body.get("token", "")),
                           str(body.get("status", "")), protect.answer(str(body.get("summary", "")), _protected()),
                           body.get("evidence") or [], mask=lambda t: protect.names(t, _protected()))
        return JSONResponse(out)
    except KeyError:
        return _err(404, "no such lead")
    except PermissionError as e:
        return _err(409, str(e))
    except LookupError as e:
        return JSONResponse(json.loads(str(e.args[0])), status_code=422)
    except ValueError as e:
        return _err(422, str(e))


def collections(_: Request):                    # sync: Starlette runs it in a thread (a 2 s scan, I6)
    """🗄️ The archive's collections with their numbers, and the vectors (Aurora's Evidentia menu)."""
    try:
        return JSONResponse(health.collections(_ro("corpus.db"), _data() / "vectors"))
    except Exception as e:  # noqa: BLE001 — no archive yet: said
        return _err(503, f"the archive is not ready: {type(e).__name__}")


async def doc_rules(_: Request):
    """The configured collections' number rules (docids): a client finds the document numbers in an answer with them,
    never with a release's scheme written in its own code."""
    from . import docids
    return JSONResponse({"collections": [{"name": n, "pattern": rx.pattern, "upper": up}
                                         for n, rx, up in docids._collections()]})


async def server_health(_: Request):
    """🩺 The server's health: its files, the originals' folder, the leads' queue, the agents."""
    try:
        _ro("corpus.db").execute("SELECT 1 FROM documents LIMIT 1")
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    con = _cases()
    queue = {r[0]: r[1] for r in con.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")}
    try:
        n_agents = (len(agents.load(AGENTS)), _proposals())        # the proposals counted, never read (B26)
    except ValueError:
        n_agents = (-1, -1)
    try:
        sources = CFG.path("EVD_SOURCES_DIR")
    except config.ConfigError:                           # not set in the .env: said, not a 500
        sources = None
    return JSONResponse(health.health(_data(), sources, ok, queue, n_agents))


def net(request: Request):                       # sync: the network's queries run in a thread
    """R20: the lateral moves — contacts of a person, the messages between two, the chain from one to another."""
    q, what = request.query_params, request.path_params["what"]
    try:
        f = _ro("findings.db")
        if what == "contacts":
            return JSONResponse(network.contacts(f, q.get("name", ""), _int(q.get("n"), 30, "n")))
        if what == "between":
            return JSONResponse(network.between(f, q.get("a", ""), q.get("b", "")))
        if what == "path":
            return JSONResponse(network.path(f, q.get("a", ""), q.get("b", ""), _int(q.get("depth"), 3, "depth")))
        if what == "stats":
            return JSONResponse(network.stats(f))
        if what == "people":
            return JSONResponse({"people": network.people(f, q.get("q", ""), _int(q.get("n"), 20, "n"))})
        return _err(404, "contacts, between, path, people or stats")
    except BadBody as e:
        return _err(422, str(e))
    except PermissionError as e:
        return _err(403, str(e))
    except network.Ambiguous as e:
        return JSONResponse({"detail": "several people fit: choose one", "candidates": e.candidates}, status_code=300)
    except ValueError as e:
        return _err(422, str(e))
    except Exception as e:  # noqa: BLE001 — not built yet: said
        return _err(503, f"the network is not built yet: {type(e).__name__}")



# ---- 💰 follow the money (evidentia/money): the report of this request's archive, and a run asked from the page ----
_money_proc: list = []


def money_report(_: Request):
    f = _data() / "money_report.json"
    try:
        rep = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rep = {}
    running = any(p.poll() is None for p in _money_proc)
    return JSONResponse({**rep, "at": f.stat().st_mtime if f.exists() else None, "running": running})


async def money_run(_: Request):
    import subprocess
    import sys as _sys
    if any(p.poll() is None for p in _money_proc):
        return _err(409, "the money is being followed already")
    script = config.ROOT / "sys" / "evidentia" / "script" / "evd_money.py"
    import os as _os
    _money_proc[:] = [subprocess.Popen([_sys.executable, "-I", "-B", str(script)], stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, env={**_os.environ, "EVD_DATA_OVERRIDE": str(_data())},
                                       start_new_session=True)]
    return JSONResponse({"running": True})


# ---- R22: the folders to read in, chosen from the WebUI (evidentia/sources) ---------------------------------------
from . import sources as _src  # noqa: E402


def source_roots(_: Request):
    return JSONResponse({"roots": _src.roots(CFG), "ingest": _src.status()})


def source_browse(request: Request):            # sync: a folder of 500,000 files on the NAS is listed in a thread
    try:
        return JSONResponse(_src.browse(CFG, _int(request.query_params.get("root"), 0, "root"),
                                        str(request.query_params.get("path", ""))[:1000]))
    except (ValueError, OSError) as e:
        return _err(422, f"{type(e).__name__}: {e}"[:300])


async def source_ingest(request: Request):
    if request.method == "GET":
        return JSONResponse(_src.status())
    body = await _json(request)
    if body.get("stop"):
        return JSONResponse(_src.stop())
    try:
        return JSONResponse(_src.start(CFG, _int(body.get("root"), -1, "root"), str(body.get("path", ""))[:1000],
                                       bool(body.get("images")), str(body.get("by", ""))))
    except (ValueError, RuntimeError, OSError) as e:
        return _err(409 if isinstance(e, RuntimeError) else 422, str(e)[:300])

class WhoseRequest:
    """R15: the archive is the request's user's (X-Evidentia-User, Aurora's side sets it); a name that is not a name
    is refused before any route runs. Plain ASGI: the user stays in the context of the route and of its thread."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        raw = dict(scope.get("headers") or []).get(b"x-evidentia-user", b"").decode("latin-1").strip()
        if raw and not archive.NAME.match(raw):
            return await _err(400, "X-Evidentia-User: a user's name")(scope, receive, send)
        who = raw or archive.owner(CFG)
        user, actor = raw, ""
        m = re.match(r"^/cases/([0-9a-f]{12})(/[^?]*)?$", scope.get("path", ""))
        if not m and scope.get("path") == "/leads":       # a shared case's leads: asked as /leads?case=<id>
            q = re.search(rb"(?:^|&)case=([0-9a-f]{12})(?:&|$)", scope.get("query_string", b""))
            m = re.match(r"^/cases/([0-9a-f]{12})()$", f"/cases/{q.group(1).decode()}") if q else None
        if m:                                             # a case shared with this user: the maker's archive (shared.py)
            maker = shared.whose(CFG, m.group(1), who)
            if maker is not None:
                sub, method = m.group(2) or "", scope.get("method", "GET")
                if sub == "/members" or (not sub and method in ("PATCH", "DELETE")):
                    return await _err(403, "only its maker changes a shared case's members, name or existence")(scope, receive, send)
                user, actor = maker, who
        token, tok2 = archive.USER.set(user), shared.ACTOR.set(actor)
        try:
            await self.app(scope, receive, send)
        finally:
            archive.USER.reset(token)
            shared.ACTOR.reset(tok2)


app = Starlette(routes=[
    Route("/status", status),
    Route("/collections", collections),
    Route("/docids", doc_rules),
    Route("/health", server_health),
    Route("/money", money_report),
    Route("/money/run", money_run, methods=["POST"]),
    Route("/sources", source_roots),
    Route("/sources/browse", source_browse),
    Route("/sources/ingest", source_ingest, methods=["GET", "POST"]),
    Route("/network/{what:str}", net),
    Route("/cases", case_list, methods=["GET"]),
    Route("/cases", case_new, methods=["POST"]),
    Route("/cases/{cid:str}", case_one, methods=["GET", "PATCH", "DELETE"]),
    Route("/cases/{cid:str}/export.md", case_export),
    Route("/cases/{cid:str}/search", case_search, methods=["POST"]),
    Route("/cases/{cid:str}/steps", case_step, methods=["POST"]),
    Route("/cases/{cid:str}/trace", case_trace, methods=["GET", "POST"]),
    Route("/cases/{cid:str}/trace/verify", case_trace_verify),
    Route("/cases/{cid:str}/members", case_members, methods=["GET", "PUT"]),
    Route("/search", find),
    Route("/doc/{doc:str}/page/{n:int}", page),
    Route("/doc/{doc:str}", document),
    Route("/identifier/{kind:str}", identifier),
    Route("/agents", agent_list, methods=["GET"]),
    Route("/agents/proposed", agent_propose, methods=["POST"]),
    Route("/cases/{cid:str}/leads", lead_open, methods=["POST"]),
    Route("/leads", lead_list, methods=["GET"]),
    Route("/leads/claim", lead_claim, methods=["POST"]),
    Route("/leads/{lid:int}", lead_one, methods=["GET", "DELETE"]),
    Route("/leads/{lid:int}/report", lead_report, methods=["POST"]),
    Route("/leads/{lid:int}/reopen", lead_reopen, methods=["POST"]),
], exception_handlers={BadBody: lambda _r, e: _err(400, str(e)), BadValue: lambda _r, e: _err(422, str(e))},
   middleware=[Middleware(WhoseRequest)])
