# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Projects page: local projects, GitHub repositories, files, history, sandboxed preview."""
from __future__ import annotations

import asyncio
import base64
import json
import re
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from .core import auth, cfg, log, plugin_host

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
    return await asyncio.to_thread(work)


@router.get("/v1/aurora/projects/{name}/tree", dependencies=[Depends(auth)])
def project_tree_api(name: str) -> dict:
    from aurora import prj_browse
    return {"name": name, "files": _prj(prj_browse.tree, name)}


@router.get("/v1/aurora/projects/{name}/file", dependencies=[Depends(auth)])
def project_file_api(name: str, path: str) -> dict:
    from aurora import prj_browse
    return _prj(prj_browse.read_file, name, path)


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
    from aurora import prj_browse
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
    out = await asyncio.to_thread(work)
    log.info("audit: project created from the page: %s (%s)", args.get("name"), "ok" if out["ok"] else "failed")
    if not out["ok"]:
        raise HTTPException(status_code=422, detail=out["text"][:400])
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
    r = await asyncio.to_thread(work)
    log.info("audit: cloned %s into %s: %s", full, dest.name, "ok" if r.returncode == 0 else "failed")
    if r.returncode != 0:
        raise HTTPException(status_code=502, detail=(r.stderr or "git clone failed").replace(token, "***")[-400:])
    return {"name": dest.name}
