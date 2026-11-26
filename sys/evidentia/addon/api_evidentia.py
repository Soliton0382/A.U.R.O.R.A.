# The owner's own: the 🕵️ Evidentia page (never published: local/). Aurora only carries the requests to the
# own service of Evidentia on its unix socket (the add-on, sys/evidentia): nothing of it is kept here, nothing enters
# Aurora's memory, vault or shadows (owner, 9 Nov: «la mia aurora deve rimanere immacolata»). The admin's alone.
from __future__ import annotations

import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from aurora.api.users import admin_only, may_use

USE = may_use("addon:evidentia")   # who may: the admin, and the users or groups the admin opened it to (27 Nov)

router = APIRouter()
from .evd_worker import SOCK  # noqa: E402 — one address for the page and the worker
# only these paths of its API: a fixed list, never a path Aurora's page could make up
ALLOWED = re.compile(r"^(status|search|collections|health|agents|sources(/(browse|ingest))?|leads(/\d{1,9}(/reopen)?)?|network/(contacts|between|path|people|stats)|"
                     r"cases(/[0-9a-f]{12}(/(export\.md|search|leads|trace|trace/verify|members))?)?|doc/[A-Z]+:[A-Za-z0-9._-]+/page/\d{1,5})$")


async def _call(method: str, path: str, request: Request):
    if not ALLOWED.fullmatch(path):                     # fullmatch: «status\n» is not «status» (audit, 10 Nov)
        raise HTTPException(status_code=404, detail="not a path of Evidentia")
    if "/trace" in path and method != "GET":            # the case trail: read and verified from the page, written only
        raise HTTPException(status_code=404, detail="not a path of Evidentia")   # by the runs themselves (hand_over)
    if path == "sources/ingest" and method != "GET":    # R22: reading a folder in writes the archive: the admin's
        from aurora.api.core import _admin, me
        if me() != _admin():
            raise HTTPException(status_code=403, detail="only the admin reads a folder into the archive")
    body = await request.body() if method in ("POST", "PATCH", "DELETE", "PUT") else None
    if path.endswith("/members") and method == "PUT" and body:   # the admin among the members: Evidentia's owner («»)
        import json as _j
        from aurora.api.core import _admin
        try:
            d = _j.loads(body)
            d["members"] = ["" if m == _admin() else m for m in d.get("members") or []]
            body = _j.dumps(d).encode()
        except (ValueError, AttributeError):
            raise HTTPException(status_code=422, detail="members: a list of users") from None
    try:
        async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds=SOCK), timeout=120) as c:
            from aurora.api.core import _admin, me      # R15: the page's user's own archive
            u = me() or ""                              # the admin: Evidentia's owner (no user: the archive as it was)
            heads = {"X-Evidentia-User": "" if u == _admin() else u} | ({"content-type": "application/json"} if body else {})
            r = await c.request(method, f"http://evidentia/{path}", params=dict(request.query_params), content=body,
                                headers=heads)
    except (httpx.TransportError, OSError):
        raise HTTPException(status_code=503, detail="Evidentia is not running (its service is off)") from None
    if path.endswith("export.md"):
        return PlainTextResponse(r.text, status_code=r.status_code, media_type="text/markdown")
    try:
        return JSONResponse(r.json(), status_code=r.status_code)
    except ValueError:                                  # not JSON (a 405, a proxy error): said, never a 500 here
        return JSONResponse({"detail": f"Evidentia: HTTP {r.status_code}"}, status_code=r.status_code)


@router.api_route("/v1/aurora/evidentia/{path:path}", methods=["GET", "POST", "PATCH", "DELETE", "PUT"],
                  dependencies=[Depends(USE)])
async def evidentia(path: str, request: Request):
    return await _call(request.method, path, request)


@router.api_route("/v1/aurora/evidentia-worker", methods=["GET", "POST"], dependencies=[Depends(admin_only)])
async def worker(request: Request):
    """🔁 Evidentia's lead worker (local/evd_worker): on or off, and its last runs."""
    from . import evd_worker
    st = evd_worker.state()
    if request.method == "POST":
        body = await request.json()
        st["on"] = bool(body.get("on"))
        evd_worker.save(st)
    return {"on": st["on"], "last": st.get("last", []), "every_minutes": evd_worker.EVERY_S // 60,
            "steps": evd_worker.STEPS, "minutes": evd_worker.MINUTES}


@router.post("/v1/aurora/evidentia-ask", dependencies=[Depends(USE)])
async def ask(request: Request):
    """💬 A question of Evidentia's chat: one of Aurora's agents with Evidentia's tools answers it, the page follows the
    run live (GET /v1/aurora/runs/{id}/events, as Aurora's chat); question and answer go into the case's diary."""
    from aurora.api.core import start_run
    from . import evd_chat
    body = await request.json()
    case, question = str(body.get("case", "")), " ".join(str(body.get("question", "")).split())[:2000]
    if not re.fullmatch(r"[0-9a-f]{12}", case) or not question:
        raise HTTPException(status_code=422, detail="a case and a question")
    lang = str(body.get("lang") or "it_IT")[:8]
    return {"id": start_run(question, origin="evidentia", job=evd_chat.job(case, question, lang))["id"]}


@router.post("/v1/aurora/evidentia-translate", dependencies=[Depends(USE)])
async def translate(request: Request):
    """🌐 A report, a summary or a line of evidence in the reader's language (owner, 10 Nov: «almeno un tasto traduci»):
    Aurora's model, nothing remembered; quotes kept in their own words with the meaning beside them."""
    from aurora.api.core import in_thread, pipeline
    from . import evd_chat
    body = await request.json()
    text = str(body.get("text", ""))[:12000]
    if not text.strip():
        raise HTTPException(status_code=422, detail="a text to translate")
    name = evd_chat.LANGS.get(str(body.get("lang") or "it")[:2].lower(), "Italian")
    system = (f"Translate the text into {name}, except the quotes. A quote is any text between « and »: it is evidence, "
              f"so copy it EXACTLY as it is, in its original language, with its « », and right after it add its meaning "
              f"in {name} in square brackets. Example: «sold on January 19, 2001» [venduto il 19 gennaio 2001]. Keep every "
              "document number (as the collection writes it), page and person's name as it is, and the structure (headings, lists). Output "
              "the translation only.")
    out = await in_thread(lambda: pipeline().llm.complete(system, text, 3000))
    return {"text": str(getattr(out, "answer", out)).strip()}


def _case_markdown(case: str) -> tuple[str, str]:
    """The case's title and its export (Evidentia's own markdown: every step, every quote with its source)."""
    from .evd_chat import _ask
    with httpx.Client(transport=httpx.HTTPTransport(uds=SOCK), base_url="http://evidentia", timeout=60) as c:
        md = c.get(f"/cases/{case}/export.md").text
    return str(_ask("GET", f"/cases/{case}").get("title") or "Fascicolo"), md


@router.post("/v1/aurora/evidentia-pdf", dependencies=[Depends(USE)])
async def pdf(request: Request):
    """📄 The case, its summary or its investigative document as a PDF laid out by Aurora's own printer (doc_pdf),
    made in a folder of its own and given to the reader — never kept among Aurora's documents (owner, 10 Nov:
    «esportazione… PDF ben formattato»)."""
    import copy
    import shutil
    import tempfile
    from pathlib import Path
    from fastapi.responses import Response
    from aurora import doc_pdf, sys_config
    from aurora.api.core import in_thread
    body = await request.json()
    case = str(body.get("case", ""))
    if not re.fullmatch(r"[0-9a-f]{12}", case):
        raise HTTPException(status_code=422, detail="a case")
    title, md = await in_thread(lambda: _case_markdown(case))
    what = str(body.get("what") or "case")
    if what != "case":                                   # a summary or a document the page already has
        md = str(body.get("text") or "")[:200000]
        title = f"{title} — {'Riassunto' if what == 'summary' else 'Documento investigativo'}"
    lang = "it" if str(body.get("lang") or "it").startswith("it") else "en"
    tmp = Path(tempfile.mkdtemp(prefix="evidentia-pdf-"))
    try:
        cfg = copy.copy(sys_config.get())
        cfg.values = {**cfg.values, "AURORA_DOCUMENTS_DIR": str(tmp)}
        out = await in_thread(lambda: doc_pdf.create(title, md, lang, cfg))
        data = out.read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    name = re.sub(r"[^\w\- ]+", "", title).strip()[:80] or "fascicolo"
    if body.get("ticket"):                               # C726: the Android app saves only a GET of Aurora's address
        return {"url": f"/v1/aurora/evidentia-pdf/{_ticket(name, data)}"}
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})


_TICKETS: dict[str, tuple[float, str, bytes]] = {}       # in memory only, never on disk (the case is never kept)
TICKET_S, TICKETS_MAX = 120, 8


def _ticket(name: str, data: bytes) -> str:
    import secrets
    import time
    now = time.time()
    for k in [k for k, v in _TICKETS.items() if now - v[0] > TICKET_S]:
        _TICKETS.pop(k, None)
    while len(_TICKETS) >= TICKETS_MAX:                  # the oldest goes first
        _TICKETS.pop(min(_TICKETS, key=lambda k: _TICKETS[k][0]), None)
    tok = secrets.token_hex(16)
    _TICKETS[tok] = (now, name, data)
    return tok


@router.get("/v1/aurora/evidentia-pdf/{tok}", dependencies=[Depends(USE)])
def pdf_ticket(tok: str):
    """The PDF made a moment ago, once, within two minutes: what the app's download manager fetches (C726)."""
    import time
    from fastapi.responses import Response
    got = _TICKETS.pop(tok, None) if re.fullmatch(r"[0-9a-f]{32}", tok) else None
    if got is None or time.time() - got[0] > TICKET_S:
        raise HTTPException(status_code=404, detail="no such file")
    return Response(got[2], media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{got[1]}.pdf"', "Cache-Control": "no-store"})


@router.post("/v1/aurora/evidentia-summary", dependencies=[Depends(USE)])
async def summary(request: Request):
    """🧾 The case in a page, in the reader's language: what was asked, what the evidence shows (with its sources), what
    is still open; written into the case's diary as a note. Aurora's model, nothing remembered."""
    from aurora.api.core import in_thread, pipeline
    from . import evd_chat
    body = await request.json()
    case = str(body.get("case", ""))
    if not re.fullmatch(r"[0-9a-f]{12}", case):
        raise HTTPException(status_code=422, detail="a case")
    title, md = await in_thread(lambda: _case_markdown(case))
    name = evd_chat.LANGS.get(str(body.get("lang") or "it")[:2].lower(), "Italian")
    system = (f"You summarise an investigation's case file for its owner, in {name}. Use only what the file says. "
              "Structure: a title; «La domanda» (what was asked); «Cosa mostrano i documenti» — points, each with its "
              "source as «<document number> p. N» and the kind of source (record, testimony, allegation, press); «Cosa resta aperto» "
              "(cold leads, missing links, what to look for next). Quotes stay in their original words between « », with "
              f"their meaning in {name} in square brackets. Never name victims or private persons the file does not name "
              "as public. Markdown, at most about 600 words.")
    out = await in_thread(lambda: pipeline().llm.complete(system, f"CASE: {title}\n\n{md[-60000:]}", 2500))
    text = str(getattr(out, "answer", out)).strip()
    try:
        evd_chat._ask("POST", f"/cases/{case}/steps", {"kind": "note", "text": f"🧾 {text}"})
    except (httpx.HTTPError, ValueError):
        pass
    return {"text": text}


@router.post("/v1/aurora/evidentia-dossier", dependencies=[Depends(USE)])
async def dossier(request: Request):
    """📑 The investigative document: Evidentia's «reporter» agent writes it from the case's evidence, followed live
    like any question (a run); then it can be printed."""
    from aurora.api.core import start_run
    from . import evd_chat
    body = await request.json()
    case, lang = str(body.get("case", "")), str(body.get("lang") or "it_IT")[:8]
    if not re.fullmatch(r"[0-9a-f]{12}", case):
        raise HTTPException(status_code=422, detail="a case")
    q = evd_chat.DOSSIER
    return {"id": start_run(q, origin="evidentia", job=evd_chat.job(case, q, lang))["id"]}


# ---- N168: a user's own NAS folder (owner, 27 Nov: «è importante che ognuno possa collegare il percorso che vuole») ----
@router.get("/v1/aurora/evidentia-nas", dependencies=[Depends(USE)])
def evidentia_nas_state() -> dict:
    """This user's NAS folder for Evidentia: what root said the last time (mounted, how many folders, the error)."""
    import json as _j
    from aurora.api.core import me
    u = me() or ""
    try:
        return _j.loads(Path(f"/var/lib/evidentia-api/nas-{u}.json").read_text(encoding="utf-8")) if u else {}
    except (OSError, ValueError):
        return {}


@router.post("/v1/aurora/evidentia-nas", dependencies=[Depends(USE)])
async def evidentia_nas_ask(request: Request) -> dict:
    """{url: smb://host/share/folder, nas_user, password} — or {remove: true}: one request for root
    (aurora-evidentia-nas), for the user asking only. The admin's own folder is the install's (--nas)."""
    import json as _j
    import os as _os
    import subprocess as _sp
    import time as _t
    from aurora.api.core import _admin, cfg, log, me
    from aurora.sys_users_groups import NAME
    u = me() or ""
    if not NAME.match(u) or u == _admin():
        raise HTTPException(status_code=422, detail="the admin's NAS folder is set at install (aurora-root install evidentia --nas)")
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="a JSON object")
    req = {"at": _t.time(), "remove": bool(body.get("remove"))}
    if not req["remove"]:
        url, nas_user, pw = str(body.get("url", "")).strip(), str(body.get("nas_user", "")), str(body.get("password", ""))
        if not re.fullmatch(r"smb://[^/\s]+/[^/\s]+/\S+", url) or not nas_user or "\n" in nas_user + pw or len(url + nas_user + pw) > 1500:
            raise HTTPException(status_code=422, detail="smb://address/share/folder, the NAS user and its password")
        req |= {"url": url, "nas_user": nas_user, "password": pw}
    folder = cfg.path("AURORA_STATUS_DIR") / "evidentia"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = folder / f"nas-{u}.tmp"
    fd = _os.open(tmp, _os.O_WRONLY | _os.O_CREAT | _os.O_TRUNC | _os.O_NOFOLLOW, 0o600)
    with _os.fdopen(fd, "w") as f:
        _j.dump(req, f)
    tmp.replace(folder / f"nas-{u}.json")
    r = _sp.run(["systemctl", "start", "--no-block", "aurora-evidentia-nas.service"], capture_output=True, text=True)
    if r.returncode != 0:
        (folder / f"nas-{u}.json").unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="the NAS unit is not installed yet: run ./install.sh (or the services' install) once")
    log.info("audit: %s asked their own NAS folder for Evidentia (%s)", u, "removed" if req["remove"] else "set")
    return {"started": True}


@router.get("/v1/aurora/evidentia-people", dependencies=[Depends(USE)])
def evidentia_people() -> dict:
    """Owner, 27 Nov: the people a case file can be shared with — the users who may use Evidentia (👥 Accessi), names
    only, the one asking left out."""
    from aurora import sys_users_groups as G
    from aurora.api.core import BASE, _admin, me
    from aurora.sys_users import Users
    base = BASE.base or BASE
    admin, mine = _admin(), me() or ""
    names = [u["name"] for u in Users(base).list()]
    return {"people": sorted(n for n in names if n != mine and G.may_use(base, n, "evidentia", admin))}
