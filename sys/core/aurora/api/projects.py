# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Projects page: local projects, GitHub repositories, files, history, sandboxed preview."""
from __future__ import annotations

import base64
import json
import re
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from .core import auth, cfg, in_thread, log, plugin_host

router = APIRouter()


# ---- projects: the Projects page (prj_browse reads; the "projects" plugin writes) ---------------------------

def _prj(fn, *a):
    from aurora import prj_browse  # noqa: F401
    try:
        return fn(cfg, *a)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/v1/aurora/projects", dependencies=[Depends(auth)])
def projects_list() -> dict:
    from aurora import prj_browse
    return {"projects": _prj(prj_browse.list_projects), "base": cfg["AURORA_PROJECTS_DIR"]}


@router.get("/v1/aurora/projects/github", dependencies=[Depends(auth)])
async def projects_github() -> dict:
    """The owner's GitHub repositories through the github plugin (read): stars, forks, issues, pages."""
    def work():
        host = plugin_host()
        p = host.get("github")
        if p is None or not p.available:
            return {"connected": False, "repos": []}
        me = host.call("github", "get_me", {})
        login = json.loads(me["text"]).get("login", "") if me["ok"] else ""
        res = host.call("github", "search_repositories", {"query": f"user:{login}", "minimal_output": False})
        items = json.loads(res["text"]).get("items", []) if res["ok"] else []
        keep = ("full_name", "name", "private", "description", "stargazers_count", "forks_count", "open_issues_count",
                "language", "pushed_at", "html_url", "homepage", "has_pages", "default_branch", "archived")
        return {"connected": True, "login": login, "error": "" if res["ok"] else res["text"][:300],
                "repos": [{k: it.get(k) for k in keep} for it in items]}
    return await in_thread(work)


@router.get("/v1/aurora/projects/papers", dependencies=[Depends(auth)])
async def projects_papers(days: int = 90) -> dict:
    """The user's works through the publications plugin (read), each with its numbers day by day: «off» when the
    plugin is off or misses its settings, «error» with the plugin's words (a wrong ORCID, Zenodo not answering)."""
    def work():
        host = plugin_host()
        p = host.get("publications")
        if p is None or not (p.enabled and p.available):
            return {"state": "off", "items": [], "missing": list(p.missing) if p else []}
        r = host.call("publications", "publications_list", {"history_days": max(1, min(days, 365))})
        if not r.get("ok"):
            return {"state": "error", "items": [], "error": str(r.get("text", ""))[:300]}
        return {"state": "ok", "items": json.loads(r["text"])}
    return await in_thread(work)


_traffic: dict[tuple[str, str], tuple[float, dict]] = {}   # (user, repo): read with that user's token (C457)
TRAFFIC_S = 1800


@router.get("/v1/aurora/projects/github/{owner}/{repo}/traffic", dependencies=[Depends(auth)])
def projects_github_traffic(owner: str, repo: str) -> dict:
    """A repository's last 14 days on GitHub: views and clones, all and unique (GitHub keeps only 14 days; it needs
    the token's push access). Kept for 30 minutes."""
    import re as _re
    import time as _time

    import httpx
    full = f"{owner}/{repo}"
    if not _re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", full):
        raise HTTPException(status_code=400, detail="owner/repo")
    from .core import me
    hit = _traffic.get((me(), full))
    if hit and hit[0] > _time.time() - TRAFFIC_S:
        return hit[1]
    token = str(cfg["AURORA_GITHUB_TOKEN"] or "")
    out: dict = {"views": None, "clones": None}
    if token:
        h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        for k in ("views", "clones"):
            try:
                r = httpx.get(f"https://api.github.com/repos/{full}/traffic/{k}", headers=h, timeout=15)
                if r.status_code == 200:
                    d = r.json()
                    out[k] = {"count": d.get("count", 0), "uniques": d.get("uniques", 0)}
                elif r.status_code == 403:                 # the token lacks «Administration: Read» (GitHub's own rule)
                    out["why"] = "permission"
            except httpx.HTTPError:
                pass
    _traffic[(me(), full)] = (_time.time(), out)
    return out


@router.get("/v1/aurora/projects/{name}/tree", dependencies=[Depends(auth)])
def project_tree_api(name: str) -> dict:
    from aurora import prj_browse
    return {"name": name, "files": _prj(prj_browse.tree, name)}


@router.get("/v1/aurora/projects/{name}/file", dependencies=[Depends(auth)])
def project_file_api(name: str, path: str) -> dict:
    from aurora import prj_browse
    return _prj(prj_browse.read_file, name, path)


@router.get("/v1/aurora/projects/{name}/reports", dependencies=[Depends(auth)])
def project_reports(name: str) -> list[dict]:
    """Aurora's reports on this project, newest first."""
    from aurora import prj_reports
    try:
        return prj_reports.all_of(cfg, name)
    except ValueError:
        raise HTTPException(status_code=404, detail="no such project") from None


@router.get("/v1/aurora/projects/{name}/log", dependencies=[Depends(auth)])
def project_log_api(name: str) -> dict:
    from aurora import prj_browse
    return {"name": name, "commits": _prj(prj_browse.log, name)}


@router.post("/v1/aurora/projects/{name}/preview", dependencies=[Depends(auth)])
def project_preview(name: str) -> dict:
    from aurora import prj_browse
    return {"url": f"/v1/preview/{_prj(prj_browse.preview_token, name)}/", "seconds": prj_browse.PREVIEW_S}


@router.get("/v1/preview/{token}/{path:path}")
def preview(token: str, path: str = ""):
    """No login: the token is the key (one project, 10 minutes). The page runs sandboxed (opaque origin, no cookie)."""
    from fastapi import Response
    from aurora import doc_artifact, prj_browse
    if token.startswith(doc_artifact.PREFIX):             # an artifact of Aurora's: inline only, no network (doc_artifact)
        try:
            data = doc_artifact.page(token)
        except PermissionError:
            raise HTTPException(status_code=403, detail="artifact expired: open it again from the chat")
        return Response(data, media_type="text/html; charset=utf-8", headers={
            "Content-Security-Policy": doc_artifact.CSP, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer"})
    try:
        data, mime = prj_browse.preview_file(cfg, token, path)
    except PermissionError:
        raise HTTPException(status_code=403, detail="preview expired: open it again from the Projects page")
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="not found")
    return Response(data, media_type=mime, headers={
        "Content-Security-Policy": "sandbox allow-scripts allow-forms allow-popups; frame-ancestors 'self'",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.post("/v1/aurora/projects", dependencies=[Depends(auth)])
async def project_new(request: Request) -> dict:
    """A new project from the page (a local write, like the plugin does for the agent)."""
    body = await request.json()
    args = {k: str(body[k]) for k in ("name", "description", "license", "language") if body.get(k)}

    def work():
        return plugin_host().call("projects", "project_create", args)
    out = await in_thread(work)
    log.info("audit: project created from the page: %s (%s)", args.get("name"), "ok" if out["ok"] else "failed")
    if not out["ok"]:
        raise HTTPException(status_code=422, detail=out["text"][:400])
    from aurora import prj_policy                     # how Aurora handles it, chosen in the same form
    out["policy"] = prj_policy.save(cfg, args["name"], {"models": body.get("models"),
                                                         "publish": body.get("publish") not in (False, "no")})
    return out


@router.post("/v1/aurora/projects/{name}/save", dependencies=[Depends(auth)])
async def project_save(name: str, request: Request) -> dict:
    """💾 Every change of the project kept in its history (a local commit, never a push): the page's «Salva»."""
    body = await request.json()
    message = str(body.get("message") or "").strip()[:200] or "Salvato dalla pagina del progetto"

    def work():
        return plugin_host().call("projects", "project_commit", {"name": name, "message": message})
    out = await in_thread(work)
    if not out["ok"]:
        raise HTTPException(status_code=422, detail=out["text"][:400])
    log.info("audit: project %s saved from the page", name)
    return {"saved": "nothing to commit" not in out["text"], "text": out["text"][:300]}


@router.get("/v1/aurora/projects/{name}/policy", dependencies=[Depends(auth)])
def project_policy(name: str) -> dict:
    from aurora import prj_policy
    return prj_policy.load(cfg, name)


@router.put("/v1/aurora/projects/{name}/policy", dependencies=[Depends(auth)])
async def project_policy_set(name: str, request: Request) -> dict:
    """🔒 local only or ☁️ the cloud (masked); 🚫 never published (prj_policy)."""
    from aurora import prj_policy
    try:
        out = prj_policy.save(cfg, name, await request.json())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    log.info("audit: project %s handled: %s", name, out)
    return out


@router.post("/v1/aurora/projects/clone", dependencies=[Depends(auth)])
async def project_clone(request: Request) -> dict:
    """One of the owner's GitHub repositories, cloned into the projects folder to browse and preview it.
    The token goes to git as a request header, never into the repository's config."""
    from aurora import prj_browse
    full = str((await request.json()).get("full_name", ""))
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", full):
        raise HTTPException(status_code=400, detail="owner/repository expected")
    dest = prj_browse.base(cfg) / prj_browse.clone_name(full)
    if dest.exists():
        raise HTTPException(status_code=409, detail=f"{dest.name} already exists")
    token = str(cfg["AURORA_GITHUB_TOKEN"] or "")
    extra = ["-c", "http.extraHeader=Authorization: Basic "
             + base64.b64encode(f"x-access-token:{token}".encode()).decode()] if token else []

    def work():
        import subprocess
        return subprocess.run(["git", *extra, "clone", "--quiet", f"https://github.com/{full}.git", str(dest)],
                              capture_output=True, text=True, timeout=900)
    r = await in_thread(work)
    log.info("audit: cloned %s into %s: %s", full, dest.name, "ok" if r.returncode == 0 else "failed")
    if r.returncode != 0:
        raise HTTPException(status_code=502, detail=(r.stderr or "git clone failed").replace(token, "***")[-400:])
    return {"name": dest.name}


# ---- a terminal in a project's cage (prj_term, roadmap 75): output as SSE, input as POST -----------------------------
def _term(fn, *a):
    from aurora import prj_term
    try:
        return fn(*a)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such terminal (closed?)")
    except (prj_term.TermError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/v1/aurora/projects/{name}/terminal", dependencies=[Depends(auth)])
def terminal_open(name: str) -> dict:
    from aurora import prj_term
    from .core import me
    out = _term(prj_term.start, cfg, name, me())
    log.info("audit: terminal opened in project %s (cage, no network)", name)
    return out


@router.get("/v1/aurora/projects/{name}/terminal/{sid}/stream", dependencies=[Depends(auth)])
async def terminal_stream(name: str, sid: str, after: int = 0):
    """The terminal's output as Server-Sent Events: {"n", "text"} chunks, then {"ended": true}."""
    import asyncio
    from fastapi.responses import StreamingResponse
    from aurora import prj_term
    from .core import me, quiet
    who = me()
    _term(prj_term.get, sid, who)

    async def gen():
        seen = after
        while True:
            try:
                items, ended = await asyncio.to_thread(prj_term.chunks, sid, who, seen, 15)
            except KeyError:
                yield f"data: {json.dumps({'ended': True})}\n\n"
                return
            for n, text in items:
                seen = n
                yield f"data: {json.dumps({'n': n, 'text': text}, ensure_ascii=False)}\n\n"
            if ended and not items:
                yield f"data: {json.dumps({'ended': True})}\n\n"
                return
            if not items:
                yield ": keep-alive\n\n"
    return StreamingResponse(quiet(gen()), media_type="text/event-stream")


@router.post("/v1/aurora/projects/{name}/terminal/{sid}/input", dependencies=[Depends(auth)])
async def terminal_input(name: str, sid: str, request: Request) -> dict:
    from aurora import prj_term
    from .core import me
    body = await request.json()
    _term(prj_term.write, sid, me(), str(body.get("data", "")))
    return {"ok": True}


@router.delete("/v1/aurora/projects/{name}/terminal/{sid}", dependencies=[Depends(auth)])
def terminal_close(name: str, sid: str) -> dict:
    from aurora import prj_term
    from .core import me
    _term(prj_term.stop, sid, me())
    return {"closed": True}
