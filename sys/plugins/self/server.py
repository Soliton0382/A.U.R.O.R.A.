# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "self": Aurora's hands on her own code, with walls.

Reads: code, docs and plugins of the installation; never .env, the vault, the models, the TLS keys.
Writes: only inside a sandbox, <AURORA_SANDBOX_DIR>/<id>/, a copy of sys/core (+ pyproject.toml).
A replacement needs an anchor that occurs exactly once (the owner's rule 3: otherwise abort).
Tests run with Aurora's own virtual environment, in the sandbox or on the live code.
"""
from __future__ import annotations

import difflib
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path

from aurora import sys_config, sys_logread, sys_tests
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
ROOT = cfg.root
SANDBOX = cfg.path("AURORA_SANDBOX_DIR")
READABLE = ("sys/core", "sys/plugins", "docs", "README.md", "pyproject.toml", "requirements.txt")
FORBIDDEN = re.compile(r"(^|/)\.env|(^|/)sys/(vault|models|https|status)(/|$)|(^|/)\.venv(/|$)|__pycache__")
MAX_LINES = 400
server = MCPServer("self", version="1.0")


def tool(fn):
    """A tool whose refusals and failures reach the agent with their reason."""
    import functools

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"{type(e).__name__}: {e}") from e
    return server.tool()(wrapped)


def _rel(path: str) -> str:
    p = os.path.normpath(path.strip().lstrip("/"))
    if p.startswith("..") or FORBIDDEN.search(p):
        raise ValueError(f"not allowed: {path}")
    return p


def _readable(path: str) -> Path:
    rel = _rel(path)
    if not any(rel == r or rel.startswith(r + "/") for r in READABLE):
        raise ValueError(f"outside the readable parts ({', '.join(READABLE)}): {path}")
    return ROOT / rel


def _box(sandbox_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]{4,40}", sandbox_id):
        raise ValueError("bad sandbox id")
    box = SANDBOX / sandbox_id
    if not box.is_dir():
        raise ValueError(f"no sandbox {sandbox_id}")
    return box


def _in_box(sandbox_id: str, path: str) -> Path:
    rel = _rel(path)
    if not rel.startswith("sys/core/"):
        raise ValueError("a sandbox holds sys/core only: paths start with sys/core/")
    return _box(sandbox_id) / rel


def _numbered(text: str, start: int, lines: int) -> str:
    rows = text.splitlines()
    start = max(1, start)
    end = min(len(rows), start - 1 + min(lines, MAX_LINES))
    body = "\n".join(f"{i:5}  {rows[i - 1]}" for i in range(start, end + 1))
    return f"lines {start}-{end} of {len(rows)}\n{body}"


@tool
def list_files(path: str = "sys/core", pattern: str = "*.py") -> str:
    """List files under a readable folder (sys/core, sys/plugins, docs), with their size in lines."""
    base = _readable(path)
    out = []
    for f in sorted(base.rglob(pattern)):
        rel = f.relative_to(ROOT).as_posix()
        if f.is_file() and not FORBIDDEN.search(rel):
            out.append(f"{rel}  ({sum(1 for _ in open(f, encoding='utf-8', errors='replace'))} lines)")
    return "\n".join(out[:500]) or "no files"


@tool
def read_file(path: str, start: int = 1, lines: int = 200) -> str:
    """Read a file of the installation (code, docs, plugins), with line numbers, at most 400 lines at a time."""
    return _numbered(_readable(path).read_text(encoding="utf-8", errors="replace"), start, lines)


@tool
def search_code(pattern: str, path: str = "sys/core", max_results: int = 60) -> str:
    """Search a regular expression in the code under a readable folder; returns file:line: text."""
    rx, base, out = re.compile(pattern), _readable(path), []
    for f in sorted(base.rglob("*")):
        rel = f.relative_to(ROOT).as_posix()
        if not f.is_file() or FORBIDDEN.search(rel) or f.suffix not in (".py", ".js", ".css", ".json", ".md", ".html"):
            continue
        for i, line in enumerate(open(f, encoding="utf-8", errors="replace"), 1):
            if rx.search(line):
                out.append(f"{rel}:{i}: {line.rstrip()[:200]}")
                if len(out) >= max_results:
                    return "\n".join(out) + "\n(more results not shown)"
    return "\n".join(out) or "no match"


@tool
def logs_inventory(hours: float = 24) -> str:
    """Every component's log: files, warnings and errors of the last hours grouped by kind, with first/last time."""
    inv = sys_logread.inventory(cfg, hours)
    lines = [f"log folder: {inv['log_dir']}  format: {inv['format']}"]
    for name, c in inv["components"].items():
        lines.append(f"- {name}: {c['warnings']} warnings, {c['errors']} errors ({c['about']})")
        for kind, k in sorted(c["kinds"].items(), key=lambda kv: -kv[1]["count"])[:8]:
            lines.append(f"    {k['count']:4} × {kind}  [{k['first'][11:]} → {k['last'][11:]}]")
        if c["lifecycle"]:
            lines.append("    service starts/stops: " + " | ".join(x[11:] for x in c["lifecycle"]))
    return "\n".join(lines)


@tool
def read_log(component: str, lines: int = 100, level: str = "") -> str:
    """The last lines of a component's log; level="WARNING" keeps only warnings and errors."""
    return "\n".join(sys_logread.tail(component, lines, level or None, cfg)) or "empty"


@tool
def sandbox_create(label: str = "change") -> str:
    """Create a sandbox: a copy of sys/core (and pyproject.toml) where code can be changed and tested safely."""
    sid = f"{re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')[:20] or 'change'}-{uuid.uuid4().hex[:6]}"
    box = SANDBOX / sid
    shutil.copytree(ROOT / "sys" / "core", box / "sys" / "core", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "pyproject.toml", box / "pyproject.toml")
    (box / "SANDBOX.txt").write_text(f"created {time.strftime('%Y-%m-%d %H:%M:%S')} from {ROOT}/sys/core\n")
    return f"sandbox {sid} created: edit files as sys/core/..."


@tool
def sandbox_read(sandbox_id: str, path: str, start: int = 1, lines: int = 200) -> str:
    """Read a file inside a sandbox (path starts with sys/core/)."""
    return _numbered(_in_box(sandbox_id, path).read_text(encoding="utf-8", errors="replace"), start, lines)


@tool
def sandbox_replace(sandbox_id: str, path: str, old: str, new: str) -> str:
    """Replace a piece of text in a sandbox file. `old` must occur exactly once, otherwise nothing is changed."""
    f = _in_box(sandbox_id, path)
    text = f.read_text(encoding="utf-8")
    n = text.count(old)
    if n != 1:
        raise ValueError(f"the anchor occurs {n} times in {path}: it must occur exactly once (nothing changed)")
    f.write_text(text.replace(old, new), encoding="utf-8")
    return f"replaced in {path}"


@tool
def sandbox_write(sandbox_id: str, path: str, content: str) -> str:
    """Write a whole file inside a sandbox (for a new file; to change an existing one prefer sandbox_replace)."""
    f = _in_box(sandbox_id, path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return f"written {path} ({len(content.splitlines())} lines)"


@tool
def sandbox_diff(sandbox_id: str) -> str:
    """The unified diff between the sandbox and the live code."""
    box, out = _box(sandbox_id), []
    for f in sorted((box / "sys" / "core").rglob("*")):
        if not f.is_file() or "__pycache__" in f.parts or f.suffix == ".pyc":
            continue
        rel = f.relative_to(box).as_posix()
        live = ROOT / rel
        a = live.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if live.exists() else []
        b = f.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        if a != b:
            out += difflib.unified_diff(a, b, f"live/{rel}", f"sandbox/{rel}")
    return "".join(out) or "no differences"


@tool
def run_tests(sandbox_id: str = "", select: str = "") -> str:
    """Run the test suite (without the GPU tests) with Aurora's own environment: in a sandbox, or on the live
    code when sandbox_id is empty. `select` is a pytest -k expression. Returns the outcome and the failures."""
    t = sys_tests.run_suite(_box(sandbox_id) if sandbox_id else ROOT, select)
    where = f"sandbox {sandbox_id}" if sandbox_id else "live code"
    return f"{'PASSED' if t['ok'] else 'FAILED'} on {where} in {t['seconds']} s: {t['summary']}\n" + (
        "" if t["ok"] else t["output"])

if __name__ == "__main__":
    server.run("stdio")
