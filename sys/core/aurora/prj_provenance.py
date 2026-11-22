# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧾 Where a project's data tables came from (C632, second review of N147, 20 Nov: the «table written in this phase»
check read the file's mtime, which a `touch -d` in the cage sets back, and a table made in one phase passed in the next).

Aurora keeps, in the user's state (out of every cage's reach), the SHA-256 of each data table (.csv, .npz) that her
agents wrote — and the SHA-256 of its numbers (prj_discover_data.canonical: C686, the same numbers with one byte more
are the same table) — with who wrote it: a command in the cage (prj_run.run, «run»), a write tool («write»), or a long
run (prj_longrun, «longrun», with its frozen entry and whether its code stayed intact). The discovery engine asks it
(origin): a table written by a command or a write tool is never evidence of a discovery, whatever its date says; the
output of a long run is the output of the agent's own simulation (C686), named as such and never «discovered»; a table
with no record is NOT one no agent wrote (C697, below): it is a table nobody vouched for, never evidence.

The ledger is never trimmed by count (C685, seventh review: 22,000 tiny writes pushed the agent's own table, and C649's
«capped» row, out of a 20,000-row window): appended rows are compacted into one row per table and author once the file
passes LEDGER_BYTES; only when the compacted index is still larger than KEEP_BYTES are its oldest rows cut, and then a
permanent «trimmed» row says when: no table without a record, nor one recorded only before the cut, is claimable again.
The «capped» and «trimmed» rows are never dropped.

C697/C698 (eighth review, 20 Nov): the provenance is POSITIVE. A table «no record attributes to the agent» was claimable,
so every way of writing that kept no record (a path typed «./t.csv», a plugin writing tables, a new command) was a
hole. Now a table is claimable as the owner's or outside data only when its bytes or its numbers match an «owner» row
made when the data came in: an upload from the project's page, a chat attachment imported into the project, a clone
of a repository from the page (record_owner, called by api/projects.py only — never by a tool an agent can call).
No row, the agent's, a plugin's, a simulation's, an unknown one: never DISCOVERED. Decided and declared: what the user
writes in their own cages (terminal, package) is not recorded as the owner's — those cages run the project's code,
which the agent may have written; data meant as evidence are brought in by an upload. An owner row is not enough when
the agent's rows show the same content before it (the owner brought back a table the agent made) — C708: in every
ledger of the user, and an upload repeating a table already in the projects that no owner's row covers (a plugin's)
is kept as an «echo», never claimable (prj_provenance_seen).

C703: every hash has a time budget (BUDGET_S per record(), bytes and numbers); a sparse file (allocated blocks under
1/SPARSE_RATIO of its size) is never read — «skipped», so never claimable.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import time
from pathlib import Path

try:
    import fcntl                 # one ledger, several processes (the API, the long runs' supervisor)
except ImportError:              # pragma: no cover - Windows port: threads only
    fcntl = None

from . import prj_run, sys_config
from . import sys_users_layout as L

SUFFIXES = (".csv", ".npz")
MAX_BYTES = 64 * 1024 * 1024     # the discovery engine's own limit: a larger table is never one of its inputs
LEDGER_BYTES = 32 * 1024 * 1024  # appended rows compacted past this size (C685; 64 MB: 470 MB peak, measured)
KEEP_BYTES = 16 * 1024 * 1024    # the compacted index cut to this size, oldest first, with a permanent «trimmed» row
OLD_MAX_ROWS = 20000             # the window of the ledger before C685: a file without a header that long was cut
BUDGET_S = 20.0                  # seconds per record() for every hash, bytes and numbers; past it «skipped» (C686, C703)
CANON_BUDGET_S = BUDGET_S        # the name before C703
SPARSE_MIN = 1 << 20             # a file this large or more ...
SPARSE_RATIO = 16                # ... with allocated blocks under 1/16 of its size is sparse: never read (C703)
CHUNK = 1 << 20
HEADER = {"by": "ledger", "v": 2}
MARKERS = ("capped", "trimmed")
OWNER = "owner"                  # the only author whose tables are claimable as outside data (C697/C698)
HOW = {"upload": "uploaded from the project's page", "chat": "a chat attachment imported into the project",
       "clone": "a repository cloned from the page"}
_lock = threading.Lock()


def _file(cfg: sys_config.Config, project: str) -> Path:
    if not prj_run.NAME.fullmatch(project or ""):
        raise ValueError("a project name")
    return L.place(cfg, "state", cfg.user) / "projects" / project / "provenance.jsonl"


def sparse(st: os.stat_result) -> bool:
    """C703: a file whose blocks on disk are far fewer than its size (truncate -s 64M): costs the cage no disk, would
    cost Aurora a full read. Not a table anyone measured."""
    blocks = getattr(st, "st_blocks", None)
    return blocks is not None and st.st_size >= SPARSE_MIN and blocks * 512 * SPARSE_RATIO < st.st_size


def _read_in(root: Path, rel: str, deadline: float | None = None) -> tuple[str, bytes | None] | None:
    """(«ok», bytes) of the table read from the project without following a link (C643), or («sparse» | «budget»,
    None) when it is not read (C703); None when it is no table of the engine (not a file, past MAX_BYTES)."""
    from . import prj_safeio
    try:
        fd = prj_safeio.open_in(root, rel, os.O_RDONLY | os.O_NONBLOCK)
    except (OSError, ValueError):
        return None
    with os.fdopen(fd, "rb") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
            return None
        if sparse(st):
            return ("sparse", None)
        buf = bytearray()
        while len(buf) <= MAX_BYTES:
            if deadline is not None and time.monotonic() > deadline:
                return ("budget", None)
            b = fh.read(CHUNK)
            if not b:
                break
            buf += b
    return ("ok", bytes(buf)) if len(buf) <= MAX_BYTES else None


def _canonical(raw: bytes, rel: str) -> str:
    """The numbers' SHA-256 as the discovery engine computes it, or «invalid» (not a table it would read)."""
    from . import prj_discover_data as DD
    try:
        return DD.canonical(DD.load(raw, Path(rel).suffix))
    except Exception:                                # any table it cannot read: not one it would read either
        return "invalid"


# ---- writing: append under a lock, compact past LEDGER_BYTES -----------------------------------------------------
class _Locked:
    """The ledger's lock: this process's threads and, where flock exists, the other processes."""

    def __init__(self, f: Path):
        self.f = f

    def __enter__(self):
        _lock.acquire()
        self.fh = None
        try:
            self.f.parent.mkdir(parents=True, exist_ok=True)
            if fcntl is not None:
                self.fh = open(self.f.with_name(self.f.name + ".lock"), "a")
                fcntl.flock(self.fh, fcntl.LOCK_EX)
        except BaseException:
            _lock.release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            if self.fh is not None:
                fcntl.flock(self.fh, fcntl.LOCK_UN)
                self.fh.close()
        finally:
            _lock.release()


def _parse(text: str) -> list[dict]:
    out = []
    for ln in text.splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def _write(f: Path, rows: list[dict]) -> None:
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in [HEADER, *rows]), encoding="utf-8")
    os.replace(tmp, f)


def _legacy_cut(rows: list[dict]) -> dict | None:
    """A ledger written before C685 (no header) that reached the old window may have lost its oldest rows."""
    if len(rows) >= OLD_MAX_ROWS:
        return {"t": max((float(r.get("t") or 0) for r in rows), default=time.time()), "rel": "*", "sha256": None,
                "by": "trimmed", "why": f"a ledger of {len(rows)} rows from before C685 (kept {OLD_MAX_ROWS})"}
    return None


def _ensure_header(f: Path) -> None:
    """A ledger without the v2 header (written before C685) rewritten with it, and its old cut marked."""
    try:
        with open(f, encoding="utf-8") as fh:
            first = fh.readline()
    except FileNotFoundError:
        _write(f, [])
        return
    try:
        if json.loads(first).get("by") == "ledger":
            return
    except (ValueError, AttributeError):
        pass
    rows = _parse(f.read_text(encoding="utf-8"))
    cut = _legacy_cut(rows)
    _write(f, rows + ([cut] if cut else []))


def _key(r: dict) -> tuple:
    by = r.get("by")
    if by in MARKERS:
        return (by,)
    if not _hashed(r):                               # a path row, or a table not hashed (C703)
        return ("path", by, r.get("rel"), r.get("sha256"))
    good = by == "longrun" and bool(r.get("frozen")) and bool(r.get("intact"))
    return ("sha", r.get("sha256"), by, good, r.get("run") if good else None)


def compact(rows: list[dict], keep_bytes: int | None = None) -> list[dict]:
    """One row per table, author and frozen run: the last one's fields, the first and last time, how many; the markers
    kept (the latest cut); past keep_bytes the oldest rows cut and a «trimmed» row added (C685)."""
    keep_bytes = KEEP_BYTES if keep_bytes is None else keep_bytes
    groups: dict[tuple, dict] = {}
    for r in rows:
        if r.get("by") == "ledger":
            continue
        k = _key(r)
        t = float(r.get("t") or 0)
        g = groups.get(k)
        if g is None:
            groups[k] = {**r, "t": t, "t0": float(r.get("t0", t) or t), "n": int(r.get("n", 1) or 1)}
            continue
        canon = g.get("canonical")
        n, t0, t1 = g["n"] + int(r.get("n", 1) or 1), min(g["t0"], float(r.get("t0", t) or t)), max(g["t"], t)
        if r.get("by") == "capped":
            continue
        g.clear()
        g.update({**r, "t": t1, "t0": t0, "n": n})
        if canon and len(str(canon)) == 64 and len(str(g.get("canonical") or "")) != 64:
            g["canonical"] = canon                         # a computed hash never replaced by «skipped»
    marks = [g for g in groups.values() if g.get("by") in MARKERS]
    body = sorted((g for g in groups.values() if g.get("by") not in MARKERS), key=lambda g: g["t"])
    size = [len(json.dumps(g, ensure_ascii=False)) + 1 for g in body]
    total, cut = sum(size), 0
    while total > keep_bytes and cut < len(body):
        total -= size[cut]
        cut += 1
    if cut:
        last = max(g["t"] for g in body[:cut])
        old = next((m for m in marks if m.get("by") == "trimmed"), None)
        mark = {"t": max(last, float(old["t"]) if old else last), "rel": "*", "sha256": None, "by": "trimmed",
                "why": f"{cut} oldest rows of the provenance index cut (more distinct tables than it keeps)"}
        marks = [m for m in marks if m.get("by") != "trimmed"] + [mark]
    return marks + body[cut:]


def _append(cfg: sys_config.Config, project: str, rows: list[dict]) -> None:
    try:
        f = _file(cfg, project)
    except ValueError:
        return
    with _Locked(f):
        _ensure_header(f)
        with open(f, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        try:
            if f.stat().st_size > LEDGER_BYTES:
                _write(f, compact(_parse(f.read_text(encoding="utf-8"))))
        except OSError:
            pass                                     # the rows stay appended; compacted next time


def record(cfg: sys_config.Config, project: str, root: Path, rels: list, by: str, budget: float | None = None,
           echo: bool = False, **extra) -> int:
    """The data tables among `rels` (paths in the project) hashed — bytes and numbers — and kept with who wrote them;
    how many. Within `budget` seconds (BUDGET_S) in all: past it, and for a sparse file, the row says «skipped» and
    the file is not read (C703) — such a table is never claimable. `echo` (C712, an owner's clone): each table also
    looked for wherever Aurora or a plugin wrote it (prj_provenance_seen.echoes), within the same time; past it
    «unchecked»."""
    from . import prj_safeio
    rows, t0, items = [], time.monotonic(), []
    deadline = t0 + (BUDGET_S if budget is None else float(budget))
    for rel in rels or []:
        rel = str(rel)
        if not rel.lower().endswith(SUFFIXES):
            continue
        try:
            rel = prj_safeio.norm(rel, root)          # C697: the path as the project sees it
        except ValueError:
            continue
        row = {"t": time.time(), "rel": rel, "by": by, **extra}
        got = ("budget", None) if time.monotonic() > deadline else _read_in(root, rel, deadline)
        if got is None:
            continue
        why, raw = got
        if raw is None:
            rows.append({**row, "sha256": "skipped", "canonical": "skipped", "skipped": why})
            continue
        canon = _canonical(raw, rel) if time.monotonic() < deadline else "skipped"
        rows.append({**row, "sha256": hashlib.sha256(raw).hexdigest(), "canonical": canon})
        items.append((rel, len(raw), rows[-1]["sha256"], canon))
    if echo and items:                               # C712: C708's check for a clone's tables too
        from . import prj_provenance_seen as S
        found = S.echoes(cfg, project, items, deadline)
        for r in rows:
            if (e := found.get(r["rel"])) and _hashed(r):
                r["echo"] = e
    if rows:
        _append(cfg, project, rows)
    return len(rows)


# C715: folders of installed packages and caches — no table in them is the owner's evidence or Aurora's output
NOT_DATA_DIRS = frozenset({".git", ".venv", "venv", "site-packages", "node_modules", "__pycache__", ".ipynb_checkpoints"})


def tables_in(root: Path, sub: str = ".", limit: int = 20000) -> list[str]:
    """The data tables under root/sub, links never followed, .git and the package folders skipped (a clone's
    tables; C715: a .venv's datasets are the packages', never evidence nor an echo)."""
    from . import prj_safeio
    try:
        found = prj_safeio.walk(root, sub, skip=NOT_DATA_DIRS, limit=limit)
    except (OSError, ValueError):
        return []
    return [p for p, is_dir, _ in found if not is_dir and p.lower().endswith(SUFFIXES)]


def record_owner(cfg: sys_config.Config, project: str, root: Path, rels: list, how: str, who: str = "",
                 note: str = "", budget: float | None = None) -> int:
    """C697/C698: tables that came in by the owner's hand — `how` one of HOW — kept as the owner's, the only ones a
    discovery can be claimed on. Called by the owner's own requests (api/projects.py), never by an agent's tool."""
    if how not in HOW:
        raise ValueError(f"how a table came in: one of {', '.join(HOW)}")
    return record(cfg, project, root, rels, OWNER, budget=budget, echo=True, how=how, who=str(who)[:64],
                  note=str(note)[:200])


def record_owner_bytes(cfg: sys_config.Config, project: str, rel: str, raw: bytes, how: str, who: str = "",
                       note: str = "") -> dict:
    """C697/C698: a table the owner hands in (an upload, a chat attachment), hashed from the bytes received — not read
    back from the project, where a cage of the project could change it between the write and the read. The row."""
    from . import prj_safeio
    if how not in HOW:
        raise ValueError(f"how a table came in: one of {', '.join(HOW)}")
    rel = prj_safeio.norm(str(rel))
    if not rel.lower().endswith(SUFFIXES) or len(raw) > MAX_BYTES:
        raise ValueError(f"a data table ({', '.join(SUFFIXES)}) of at most {MAX_BYTES >> 20} MB")
    row = {"t": time.time(), "rel": rel, "by": OWNER, "sha256": hashlib.sha256(raw).hexdigest(),
           "canonical": _canonical(raw, rel), "how": how, "who": str(who)[:64], "note": str(note)[:200]}
    from . import prj_provenance_seen as S          # C708: a table Aurora or a plugin wrote, brought back
    if (e := S.echo(cfg, project, rel, raw, row["sha256"], row["canonical"])):
        row["echo"] = e
    _append(cfg, project, [row])
    return row


def record_path(cfg: sys_config.Config, project: str, rel: str, by: str = "write", root: Path | None = None) -> None:
    """A write tool about to write a data table (prj_policy.guard, before the plugin's call): its path kept, so that
    whatever the tool then writes there is said to be the agent's (the hash is not known yet). Since C697 only the
    message depends on it: a table without an owner's row is never claimable anyway."""
    from . import prj_safeio
    try:
        rel = prj_safeio.norm(str(rel or "").replace("\\", "/"), root)
    except ValueError:
        return
    if rel.lower().endswith(SUFFIXES):
        _append(cfg, project, [{"t": time.time(), "rel": rel, "sha256": None, "by": by}])


def record_capped(cfg: sys_config.Config, project: str) -> None:
    """The project held more files than a snapshot lists (prj_run.MAX_FILES): some tables the agent wrote were not
    hashed (C649). Kept, never compacted away (C685); since C697 it changes no verdict — a table is claimable only by
    an owner's row, which no unrecorded write can make."""
    _append(cfg, project, [{"t": time.time(), "rel": "*", "sha256": None, "by": "capped"}])


# ---- reading -----------------------------------------------------------------------------------------------------
def _rows(cfg: sys_config.Config, project: str) -> list[dict]:
    try:
        rows = _parse(_file(cfg, project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if rows and rows[0].get("by") == "ledger":
        return rows[1:]
    cut = _legacy_cut(rows)                          # not yet rewritten by record(): read as it will be
    return rows + ([cut] if cut else [])


def of(cfg: sys_config.Config, project: str, sha256: str) -> list[dict]:
    """Every record of a table with this SHA-256 in the project (oldest first)."""
    return [r for r in _rows(cfg, project) if r.get("sha256") == sha256]


def _when(t: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(t))


def _hashed(r: dict) -> bool:
    v = r.get("sha256")
    return isinstance(v, str) and len(v) == 64


def _t0(r: dict) -> float:
    return float(r.get("t0", r.get("t")) or 0)


def _author(r: dict) -> str:
    if r.get("by") == "longrun":
        return (f"its simulation, the frozen long run {r.get('run')}" if r.get("frozen") and r.get("intact")
                else "a long run without frozen, intact code")
    return {"run": "a command in the cage", "write": "a write tool", OWNER: "the owner"}.get(r.get("by"),
                                                                                         f"«{r.get('by')}»")


NO_OWNER = ("no record that the owner brought this table in (an upload from the project's page, a chat attachment "
            "imported into the project, a clone from the page): whoever wrote it — a command, a plugin, a tool, a path "
            "written another way — it is not evidence of a discovery")


def origin(cfg: sys_config.Config, project: str, rel: str, sha256: str, canonical: str | None = None) -> dict:
    """Where the table at `rel` with this content came from: {"kind", "claimable", "why", "run"?, "how"?}. kind:
      «owner»      its bytes or its numbers match a row the owner's own request made when it came in (record_owner),
                   and no row of the agent shows the same content before it — the only kind claimable as outside data;
      «simulation» made by a long run with its code frozen and intact — the output of the agent's simulation (C686);
      «agent»      written by a command, a write tool, a plugin, a long run (its bytes or its numbers) — never evidence;
      «unknown»    the ledger cannot say (the content not hashed, capped, cut) — never evidence;
      «none»       no record of the owner's: never evidence (C697/C698 — the provenance is positive)."""
    from . import prj_safeio
    rows = _rows(cfg, project)
    canon = canonical if canonical and len(canonical) == 64 else None
    same = [r for r in rows if r.get("by") not in MARKERS and _hashed(r)
            and (r.get("sha256") == sha256 or (canon is not None and r.get("canonical") == canon))]
    echoes = [r for r in same if r.get("by") == OWNER and r.get("echo")]
    owner = [r for r in same if r.get("by") == OWNER and not r.get("echo")]
    others = [r for r in same if r.get("by") != OWNER]
    if echoes and not owner:                         # C708: an upload repeating a table Aurora or a plugin wrote
        from . import prj_provenance_seen as S
        return {"kind": "agent", "claimable": False, "why": "the owner brought it in, but " + S.said(echoes[0]["echo"])}
    if owner:
        first = min(_t0(r) for r in owner)
        from . import prj_provenance_seen as S      # C708: the agent's rows of every project, not this one only
        before = [(project, r) for r in others if _t0(r) < first] + [
            (n, r) for n, r in S.agent_rows(cfg, sha256, canon) if n != project and _t0(r) < first]
        if before:
            n, r = before[0]
            where = "" if n == project else f" in project {n}"
            return {"kind": "agent", "claimable": False,
                    "why": f"the owner brought in on {_when(first)} a table Aurora's agent had written before{where} "
                           f"({_author(r)}, {r.get('rel')}, {_when(_t0(r))}): the agent's data, never evidence"}
        r = min(owner, key=_t0)
        note = f": {r['note']}" if r.get("note") else ""
        return {"kind": "owner", "claimable": True, "how": r.get("how"),
                "why": f"brought in by the owner on {_when(first)} ({HOW.get(r.get('how'), r.get('how'))}{note}, "
                       f"{r.get('rel')})"}
    good = [r for r in others if r.get("by") == "longrun" and r.get("frozen") and r.get("intact")]
    bad = [r for r in others if r not in good]
    if bad:
        r = bad[-1]
        same_bytes = r.get("sha256") == sha256
        return {"kind": "agent", "claimable": False,
                "why": f"the table was written by Aurora's agent ({_author(r)}, {r.get('rel')}"
                       f"{'' if same_bytes else ', the same numbers in other bytes'}): never evidence of a discovery"}
    if good:
        r = max(good, key=lambda g: float(g.get("t") or 0))
        return {"kind": "simulation", "claimable": True, "run": r.get("run"),
                "why": f"output of the agent's own simulation: the frozen long run {r.get('run')} (entry "
                       f"{r.get('frozen')}, code intact) — a law found in it describes that code, not outside data"}
    try:
        key = prj_safeio.norm(rel)
    except ValueError:
        key = str(rel)
    if any(r.get("rel") == key and r.get("sha256") == "skipped" for r in rows):
        return {"kind": "unknown", "claimable": False,
                "why": "the table was not hashed when it was written (a sparse file, or past the time budget: "
                       "prj_provenance.BUDGET_S): " + NO_OWNER}
    if any(r.get("rel") == key and r.get("by") == "write" and r.get("sha256") is None for r in rows):
        return {"kind": "agent", "claimable": False,
                "why": f"a write tool of Aurora's agent wrote {key}: never evidence of a discovery"}
    return {"kind": "none", "claimable": False, "why": NO_OWNER}


def verdict(cfg: sys_config.Config, project: str, rel: str, sha256: str, canonical: str | None = None) -> tuple[bool, str]:
    """(claimable, why): origin() in two values; claimable only as the owner's data or as the agent's simulation."""
    o = origin(cfg, project, rel, sha256, canonical)
    return o["claimable"], o["why"]
