# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧾 C708 (ninth review, 20 Nov): a table the owner brings in, looked for wherever Aurora may have written it before.

prj_provenance's rule «an owner row is not enough when the agent's rows show the same content before it» held inside
one project only: a table the agent wrote in project A, brought by the owner into project B, became the owner's; a
plugin's table (circuits, cad, patent: they write in the projects' folder and keep no row) brought back by the owner
became the owner's too — and so did the plugin's original file, matched by content.

Now:
  * the agent's rows are read in EVERY ledger of the user (agent_rows), at the upload and at every verdict;
  * at an upload (or a chat attachment imported) every data table already in the user's projects is compared with it,
    bytes and numbers (tables_like): one with the same content that no owner's row of its own project covers — a
    plugin's, a command's, the terminal's — makes the new owner row an «echo», kept in the row for good: never
    claimable, and the upload's answer says so («this table was written in project A by …»);
  * past the time budget (BUDGET_S) some tables were not compared: the row says «unchecked», never claimable either
    (the provenance is positive: nothing claimable that was not checked).
"""
from __future__ import annotations

import hashlib
import os
import time

from . import prj_provenance as P
from . import prj_run, sys_config
from . import sys_users_layout as L

BUDGET_S = 20.0                  # seconds for comparing an upload with the tables already there


def ledgers(cfg: sys_config.Config) -> list[tuple[str, list[dict]]]:
    """(project, rows) of every provenance ledger of the user, projects removed since included."""
    base = L.place(cfg, "state", cfg.user) / "projects"
    try:
        names = sorted(d.name for d in base.iterdir() if d.is_dir())
    except OSError:
        return []
    return [(n, P._rows(cfg, n)) for n in names if prj_run.NAME.fullmatch(n)]


def _same(r: dict, sha256: str, canon: str | None) -> bool:
    return P._hashed(r) and (r.get("sha256") == sha256 or (canon is not None and r.get("canonical") == canon))


def agent_rows(cfg: sys_config.Config, sha256: str, canon: str | None,
               books: list[tuple[str, list[dict]]] | None = None) -> list[tuple[str, dict]]:
    """Every row not the owner's (a command, a write tool, a long run, a plugin's path) with this content, in every
    project's ledger: (project, row), oldest first."""
    out = [(n, r) for n, rows in (ledgers(cfg) if books is None else books) for r in rows
           if r.get("by") not in (P.OWNER, *P.MARKERS) and _same(r, sha256, canon)]
    return sorted(out, key=lambda x: P._t0(x[1]))


def _owner_covers(rows: list[dict], sha256: str, canon: str | None) -> bool:
    return any(r.get("by") == P.OWNER and not r.get("echo") and _same(r, sha256, canon) for r in rows)


def tables_like(cfg: sys_config.Config, raw: bytes, sha256: str, canon: str | None, skip: tuple[str, str] = ("", ""),
                books: list[tuple[str, list[dict]]] | None = None, budget: float = BUDGET_S) -> tuple[list, int]:
    """([(project, rel)] of the tables in the user's projects with the same bytes or numbers that no owner's row of
    their project covers, how many tables were left uncompared within `budget`). Same-sized files first (a byte
    match is one read); then the numbers of the others; sparse files never read (P.sparse: never claimable anyway)."""
    try:
        base = cfg.path("AURORA_PROJECTS_DIR")
        projects = sorted(d.name for d in base.iterdir() if d.is_dir() and prj_run.NAME.fullmatch(d.name))
    except (OSError, KeyError):
        return [], 0
    rows_of = dict(ledgers(cfg) if books is None else books)
    found, cand = [], []
    for n in projects:
        for rel in P.tables_in(base / n):
            if (n, rel) == skip:
                continue
            try:
                st = os.lstat(base / n / rel)
            except OSError:
                continue
            if P.sparse(st) or st.st_size > P.MAX_BYTES:
                continue
            cand.append((st.st_size != len(raw), n, rel))
    deadline, left = time.monotonic() + budget, 0
    for i, (other_size, n, rel) in enumerate(sorted(cand)):
        if other_size and canon is None:
            continue                                     # not a table the engine reads: bytes only
        if time.monotonic() > deadline:
            left = sum(1 for c in sorted(cand)[i:] if not c[0] or canon is not None)
            break
        got = P._read_in(base / n, rel, deadline)
        if not got or got[1] is None:
            if got and got[0] == "budget":
                left += 1
            continue
        data = got[1]
        same = hashlib.sha256(data).hexdigest() == sha256 or (other_size and P._canonical(data, rel) == canon)
        if same and not _owner_covers(rows_of.get(n, []), sha256, canon):
            found.append((n, rel))
    return found, left


def echo(cfg: sys_config.Config, project: str, rel: str, raw: bytes, sha256: str, canon: str | None) -> dict | None:
    """What an owner's upload repeats, kept in its row: {"project", "rel", "author"} or {"unchecked": n}; None when it
    repeats nothing Aurora, a plugin or a cage wrote."""
    canon = canon if canon and len(canon) == 64 else None
    books = ledgers(cfg)
    rows = agent_rows(cfg, sha256, canon, books)
    if rows:
        n, r = rows[0]
        return {"project": n, "rel": r.get("rel"), "author": P._author(r), "t": P._t0(r)}
    files, left = tables_like(cfg, raw, sha256, canon, (project, rel), books)
    if files:
        n, other = files[0]
        return {"project": n, "rel": other, "author": "a plugin, a command or a cage (no owner's row)"}
    if left:
        return {"unchecked": left}
    return None


def echoes(cfg: sys_config.Config, project: str, items: list[tuple[str, int, str, str | None]],
           deadline: float) -> dict[str, dict]:
    """C712: echo() for many tables at once — a clone's, recorded as the owner's: {rel: echo} for those among `items`
    ((rel, size, sha256, canonical)) that repeat what Aurora, a plugin or a cage wrote — the agent's rows of every
    ledger, then every table already in the user's projects that no owner's row covers, each read once and compared
    with all of them. Past `deadline` (monotonic) the tables not yet cleared are «unchecked» (never claimable)."""
    books = ledgers(cfg)
    out: dict[str, dict] = {}
    todo: dict[str, tuple[str, str | None]] = {}
    for rel, _size, sha, canon in items:
        canon = canon if canon and len(canon) == 64 else None
        if time.monotonic() > deadline:
            out[rel] = {"unchecked": "all"}
            continue
        if (rows := agent_rows(cfg, sha, canon, books)):
            n, r = rows[0]
            out[rel] = {"project": n, "rel": r.get("rel"), "author": P._author(r), "t": P._t0(r)}
        else:
            todo[rel] = (sha, canon)
    if not todo:
        return out
    by_sha: dict[str, list[str]] = {}
    by_canon: dict[str, list[str]] = {}
    for rel, (sha, canon) in todo.items():
        by_sha.setdefault(sha, []).append(rel)
        if canon is not None:
            by_canon.setdefault(canon, []).append(rel)
    sizes = {size for rel, size, _s, _c in items if rel in todo}
    rows_of, mine_rels = dict(books), {it[0] for it in items}
    try:
        base = cfg.path("AURORA_PROJECTS_DIR")
        projects = sorted(d.name for d in base.iterdir() if d.is_dir() and prj_run.NAME.fullmatch(d.name))
    except (OSError, KeyError):
        projects, base = [], None
    cand = []
    for n in projects:
        if time.monotonic() > deadline:
            break
        for rel in P.tables_in(base / n):
            if n == project and rel in mine_rels:      # the table being recorded itself
                continue
            try:
                st = os.lstat(base / n / rel)
            except OSError:
                continue
            if not P.sparse(st) and st.st_size <= P.MAX_BYTES:
                cand.append((st.st_size not in sizes, n, rel))
    late = time.monotonic() > deadline
    for other_size, n, rel in sorted(cand):
        if not todo:
            break
        if other_size and not by_canon:
            continue                                     # no table here the engine reads: bytes only
        got = None if late else P._read_in(base / n, rel, deadline)
        if late or (got and got[0] == "budget"):
            late = True
            break
        if not got or got[1] is None:
            continue
        data = got[1]
        hit = list(by_sha.get(hashlib.sha256(data).hexdigest(), []))
        if by_canon and time.monotonic() < deadline:
            hit += by_canon.get(P._canonical(data, rel), [])
        for mine in hit:
            if mine in todo and not _owner_covers(rows_of.get(n, []), *todo[mine]):
                out[mine] = {"project": n, "rel": rel, "author": "a plugin, a command or a cage (no owner's row)"}
                del todo[mine]
    if late:
        for mine in todo:
            out[mine] = {"unchecked": "all"}
    return out


def said(e: dict) -> str:
    """The echo in words: the upload's answer and the verdict's reason."""
    if e.get("unchecked"):
        n = "some" if e["unchecked"] == "all" else e["unchecked"]   # C712: a clone's, past its time
        return (f"{n} tables already in the projects could not be compared with it within the time "
                "budget: it is kept, but never evidence of a discovery")
    return (f"this table was written in project {e.get('project')} by {e.get('author')} ({e.get('rel')}): brought "
            "back by the owner it stays that data, never evidence of a discovery")
