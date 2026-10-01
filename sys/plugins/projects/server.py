# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "projects": Aurora starts and keeps software projects, ready for GitHub.

Each project is a git repository in AURORA_PROJECTS_DIR/<name>. Scaffolding uses GitHub's own
licence and .gitignore templates; the README says the project was made with Aurora (EU AI Act).
Local work (files, commits) is automatic; creating the GitHub repository and pushing are external
actions (the owner approves). The token is passed to git only for the push, never stored.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import time
from pathlib import Path

import httpx
from aurora import sys_config, sys_disclosure
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
BASE = cfg.path("AURORA_PROJECTS_DIR")
TOKEN = os.environ.get("AURORA_GITHUB_TOKEN", "")
server = MCPServer("projects", version="1.0")


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


def _project(name: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", name):
        raise ValueError("project names: lowercase letters, digits, . _ - (max 64)")
    return BASE / name


def _inside(project: Path, path: str) -> Path:
    p = (project / path).resolve()
    if project.resolve() not in p.parents and p != project.resolve():
        raise ValueError(f"outside the project: {path}")
    if ".git" in p.relative_to(project.resolve()).parts:
        raise ValueError("the .git folder is git's own")
    return p


def _git(project: Path, *args: str, extra_env: dict | None = None) -> str:
    author = cfg["AURORA_GIT_AUTHOR_NAME"] or "Aurora"
    email = cfg["AURORA_GIT_AUTHOR_EMAIL"] or "aurora@localhost"
    env = dict(os.environ, GIT_AUTHOR_NAME=author, GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_NAME=author,
               GIT_COMMITTER_EMAIL=email, GIT_TERMINAL_PROMPT="0", **(extra_env or {}))
    r = subprocess.run(["git", *args], cwd=project, env=env, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise ToolError(f"git {args[0]}: {(r.stderr or r.stdout).strip()[:1500]}")
    return (r.stdout + r.stderr).strip()


def _github(method: str, path: str, **kw) -> dict:
    if not TOKEN:
        raise ToolError("AURORA_GITHUB_TOKEN is empty")
    r = httpx.request(method, f"https://api.github.com{path}", timeout=30, headers={
        "Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}, **kw)
    if r.status_code >= 400:
        raise ToolError(f"GitHub {r.status_code}: {r.json().get('message', r.text[:200])}")
    return r.json() if r.content else {}


@tool
def project_list() -> str:
    """The projects, with their last commit."""
    BASE.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in sorted(x for x in BASE.iterdir() if (x / ".git").is_dir()):
        last = subprocess.run(["git", "log", "-1", "--format=%cs %s"], cwd=p, capture_output=True, text=True).stdout.strip()
        rows.append(f"{p.name}: {last or 'no commits'}")
    return "\n".join(rows) or "no projects"


@tool
def project_create(name: str, description: str, license: str = "MIT", language: str = "Python",
                   holder: str = "") -> str:
    """Create a project ready for GitHub: README, LICENSE (GitHub template, e.g. MIT, Apache-2.0, GPL-3.0),
    .gitignore for the language, CHANGELOG, src/; git repository with a first commit on 'main'."""
    p = _project(name)
    if p.exists():
        raise ValueError(f"project {name} exists")
    lic = httpx.get(f"https://api.github.com/licenses/{license.lower()}", timeout=30)
    if lic.status_code != 200:
        raise ValueError(f"unknown licence {license!r} (GitHub has e.g. mit, apache-2.0, gpl-3.0, bsd-3-clause)")
    who = holder or cfg["AURORA_GITHUB_OWNER"] or cfg["AURORA_GIT_AUTHOR_NAME"]
    body = lic.json()["body"].replace("[year]", time.strftime("%Y")).replace("[fullname]", who)
    gi = httpx.get(f"https://api.github.com/gitignore/templates/{language}", timeout=30)
    ignore = gi.json()["source"] if gi.status_code == 200 else ""
    (p / "src").mkdir(parents=True)
    (p / "src" / ".gitkeep").write_text("")
    readme = f"# {name}\n\n{description}\n\n## License\n\n{lic.json()['name']} — see [LICENSE](LICENSE).\n"
    (p / "README.md").write_text(sys_disclosure.mark_document(readme, "en", cfg))
    (p / "LICENSE").write_text(body)
    (p / ".gitignore").write_text(ignore)
    (p / "CHANGELOG.md").write_text(f"# Changelog\n\n## [0.1.0] - {time.strftime('%Y-%m-%d')}\n\n- Project created.\n")
    _git(p, "init", "-b", "main")
    _git(p, "add", "-A")
    _git(p, "commit", "-m", "Initial scaffold")
    return f"project {name} created in {p} ({lic.json()['spdx_id']}, .gitignore {language if ignore else 'none'})"


@tool
def project_tree(name: str) -> str:
    """The files of a project."""
    p = _project(name)
    return _git(p, "ls-files", "--others", "--cached", "--exclude-standard") or "empty"


@tool
def project_read_file(name: str, path: str) -> str:
    """Read a file of a project."""
    return _inside(_project(name), path).read_text(encoding="utf-8", errors="replace")[:20000]


@tool
def project_write_file(name: str, path: str, content: str) -> str:
    """Write a file of a project (new or whole)."""
    f = _inside(_project(name), path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return f"written {path} ({len(content.splitlines())} lines)"


@tool
def project_status(name: str) -> str:
    """git status and the last commits."""
    p = _project(name)
    return _git(p, "status", "--short", "--branch") + "\n\n" + _git(p, "log", "-5", "--format=%h %cs %s")


@tool
def project_commit(name: str, message: str) -> str:
    """Commit every change of a project locally."""
    p = _project(name)
    _git(p, "add", "-A")
    if not _git(p, "status", "--porcelain"):
        return "nothing to commit"
    return _git(p, "commit", "-m", message)


def _push(p: Path, url: str) -> str:
    auth = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()
    return _git(p, "-c", f"http.extraHeader=Authorization: Basic {auth}", "push", "-u", url, "main")


@tool
def project_publish(name: str, private: bool = True) -> str:
    """Create the GitHub repository (under AURORA_GITHUB_OWNER or the token's user) and push 'main'."""
    p = _project(name)
    owner = cfg["AURORA_GITHUB_OWNER"]
    me = _github("GET", "/user")["login"]
    desc = (p / "README.md").read_text().splitlines()
    payload = {"name": name, "private": private, "description": next((l for l in desc[3:] if l.strip()), "")[:300]}
    repo = _github("POST", f"/orgs/{owner}/repos" if owner and owner != me else "/user/repos", json=payload)
    url = repo["clone_url"]
    _git(p, "remote", "add", "origin", url)
    out = _push(p, url)
    return f"published {repo['html_url']} ({'private' if private else 'public'})\n{out[-500:]}"


@tool
def project_push(name: str) -> str:
    """Push 'main' to the project's GitHub repository."""
    p = _project(name)
    url = _git(p, "remote", "get-url", "origin")
    return _push(p, url)


if __name__ == "__main__":
    server.run("stdio")
