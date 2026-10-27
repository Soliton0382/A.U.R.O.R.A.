# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The Projects page, read side: the projects in AURORA_PROJECTS_DIR, their files, history and page previews.

Every path is resolved inside its project and never into .git. Previews are served under a short-lived token
(one project, read only) with a sandbox CSP: the previewed page runs in an opaque origin, without the WebUI's
cookies and without access to the API. Writing stays with the "projects" plugin (and the owner's approvals).
"""
from __future__ import annotations

import base64
import mimetypes
import re
import secrets
import subprocess
import time
from pathlib import Path

from . import prj_policy, sys_config
from .prj_run import GIT_SAFE

SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", ".libs", ".mypy_cache", ".pytest_cache", "dist", "build"}
NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
MAX_TEXT = 400_000
MAX_TREE = 3000
PREVIEW_S = 600
_previews: dict[str, tuple[Path, float]] = {}   # token -> the project's folder resolved for its owner, the expiry


def base(cfg: sys_config.Config) -> Path:
    b = cfg.path("AURORA_PROJECTS_DIR")
    b.mkdir(parents=True, exist_ok=True)
    return b


def project(cfg: sys_config.Config, name: str) -> Path:
    if not NAME.fullmatch(name):
        raise ValueError("bad project name")
    p = base(cfg) / name
    if not p.is_dir():
        raise FileNotFoundError(name)
    return p


def inside(proj: Path, path: str) -> Path:
    p = (proj / path).resolve()
    root = proj.resolve()
    if p != root and root not in p.parents:
        raise ValueError("outside the project")
    if ".git" in p.relative_to(root).parts:
        raise ValueError("the .git folder is git's own")
    return p


def _git(proj: Path, *args: str) -> str:
    # a project's own .git is not trusted (C420): no fsmonitor command, no hook runs here, outside the cage
    r = subprocess.run(["git", *GIT_SAFE, "-C", str(proj), *args], capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def summary(cfg: sys_config.Config, proj: Path) -> dict:
    readme = next((f for f in ("README.md", "readme.md", "README.rst", "README") if (proj / f).is_file()), None)
    first = ""
    if readme:
        for line in (proj / readme).read_text(encoding="utf-8", errors="replace").splitlines():
            raw, line = line.strip(), line.strip().lstrip("#").strip()
            # not the AI notice («> 🤖 …»), not a title that only repeats the folder's name: what it is about
            if line and not raw.startswith(("<", "!", "[", ">")) and line.lower() != proj.name.lower():
                first = line[:200]
                break
    last = _git(proj, "log", "-1", "--format=%h%x1f%cI%x1f%s").split("\x1f")
    return {"name": proj.name, "description": first, "readme": readme,
            "branch": _git(proj, "rev-parse", "--abbrev-ref", "HEAD"),
            "last_commit": dict(zip(("hash", "date", "subject"), last)) if len(last) == 3 else None,
            "changes": len([x for x in _git(proj, "status", "--porcelain").splitlines() if x.strip()]),
            "remote": re.sub(r"//[^@/]+@", "//", _git(proj, "remote", "get-url", "origin")),
            "has_index_html": any((proj / d / "index.html").is_file() for d in ("", "docs", "public", "site", "web")),
            "policy": prj_policy.load(cfg, proj.name)}


def list_projects(cfg: sys_config.Config) -> list[dict]:
    return [summary(cfg, p) for p in sorted(base(cfg).iterdir()) if p.is_dir() and NAME.fullmatch(p.name)]


def tree(cfg: sys_config.Config, name: str) -> list[dict]:
    proj = project(cfg, name)
    out: list[dict] = []

    def walk(d: Path, rel: str) -> None:
        for e in sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if len(out) >= MAX_TREE or e.name in SKIP or e.is_symlink():
                continue
            r = f"{rel}{e.name}"
            if e.is_dir():
                out.append({"path": r, "dir": True})
                walk(e, r + "/")
            else:
                out.append({"path": r, "dir": False, "size": e.stat().st_size})
    walk(proj, "")
    return out


def read_file(cfg: sys_config.Config, name: str, path: str) -> dict:
    p = inside(project(cfg, name), path)
    if not p.is_file():
        raise FileNotFoundError(path)
    data = p.read_bytes()
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    if mime.startswith("image/") and len(data) <= 3_000_000:
        return {"path": path, "size": len(data), "mime": mime, "image": base64.b64encode(data).decode("ascii")}
    if mime == "application/pdf":                       # its pages as pictures (doc_preview), on the project page
        from . import doc_preview
        try:
            return {"path": path, "size": len(data), "mime": mime, "pdf": True, "pages": doc_preview.pages(p)}
        except Exception:                                # noqa: BLE001 — a PDF it cannot read: shown as binary
            pass
    try:
        text = data[:MAX_TEXT].decode("utf-8")
    except UnicodeDecodeError:
        return {"path": path, "size": len(data), "mime": mime, "binary": True}
    return {"path": path, "size": len(data), "mime": mime, "text": text, "truncated": len(data) > MAX_TEXT}


def log(cfg: sys_config.Config, name: str, n: int = 20) -> list[dict]:
    raw = _git(project(cfg, name), "log", f"-{n}", "--format=%h%x1f%cI%x1f%an%x1f%s")
    return [dict(zip(("hash", "date", "author", "subject"), l.split("\x1f"))) for l in raw.splitlines() if l]


# ---- previews ---------------------------------------------------------------------------------------------

def preview_token(cfg: sys_config.Config, name: str) -> str:
    """The folder kept, resolved now for the asking user: the preview route has no login, so it must not resolve the
    name again (C424, 28 Oct: there it was the admin's view — a user's project named as the admin's served the admin's
    files)."""
    folder = project(cfg, name).resolve()
    now = time.time()
    for t in [t for t, (_, exp) in _previews.items() if exp < now]:
        _previews.pop(t, None)
    tok = secrets.token_urlsafe(24)
    _previews[tok] = (folder, now + PREVIEW_S)
    return tok


def preview_file(cfg: sys_config.Config, token: str, path: str) -> tuple[bytes, str]:
    folder, exp = _previews.get(token, (None, 0.0))
    if folder is None or exp < time.time():
        raise PermissionError("preview expired")
    p = inside(folder, path or "index.html")
    if p.is_dir():
        p = p / "index.html"
    if not p.is_file():
        raise FileNotFoundError(path)
    return p.read_bytes(), mimetypes.guess_type(p.name)[0] or "application/octet-stream"


def clone_name(full_name: str) -> str:
    n = re.sub(r"[^a-z0-9._-]+", "-", full_name.split("/")[-1].lower()).strip("-.") or "repo"
    return n[:64]
