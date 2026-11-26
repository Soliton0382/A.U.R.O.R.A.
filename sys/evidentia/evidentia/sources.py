# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The folders to read in, chosen from the WebUI (R22; owner, 27 Nov: «in evidentia manca la possibilità dalla web ui
di selezionare le cartelle dove si trovano i file da ingerire»).

Only under the roots this installation names — the originals' folder (EVD_SOURCES_DIR) and the NAS's (EVD_NAS_DIR,
mounted read only by aurora-root install evidentia --nas) — never a path typed: a root by its number and a folder
under it by its names, each one checked to stay inside (no «..», no link out). Browsing says the subfolders and what
the folder holds (PDFs, images); reading one in starts the inventory (script/evd_inventory.py, the same a terminal
runs) as a process of Evidentia's own, one at a time, its progress in <RUN_DIR>/ingest.json and its lines in
ingest.log: counts only are given to the page, never a file's name. A document already in the archive found in a new
folder only changes its path (inventory.plan)."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import archive, inventory

RUN = Path(os.environ.get("EVD_RUN_DIR") or "/var/lib/evidentia-api")
SCRIPT = Path(__file__).resolve().parents[1] / "script" / "evd_inventory.py"
WORKERS = 3                     # under the service's MemoryMax (6 GB): 3 × (1 GB pdftotext or 2 GB tesseract) and the API
MAX_LIST = 400                  # subfolders shown at once
_proc: list = []                # the running inventory's Popen: polled, so an ended one is reaped (never a zombie «alive»)


NAS_USER = "/mnt/evidentia-nas-{user}"          # N168: another user's own NAS folder, mounted by root for them


def roots(cfg) -> list[dict]:
    """This request's user's roots (R15, N168): the owner's originals and NAS; another user's own NAS folder only."""
    u = archive.who()
    pairs = (("EVD_SOURCES_DIR", "originals"), ("EVD_NAS_DIR", "nas")) if not u or u == archive.owner(cfg) else ()
    out = []
    for key, label in pairs:
        try:
            raw = str(cfg[key]).strip()
        except KeyError:
            raw = ""
        if raw:
            p = Path(raw)
            out.append({"id": len(out), "kind": label, "path": str(p), "reachable": _reachable(p)})
    if u and u != archive.owner(cfg) and archive.NAME.match(u):
        p = Path(NAS_USER.format(user=u))
        if p.exists():
            out.append({"id": len(out), "kind": "nas", "path": str(p), "reachable": _reachable(p)})
    return out


def _reachable(p: Path) -> bool:
    try:
        return p.is_dir() and os.access(p, os.R_OK | os.X_OK)
    except OSError:
        return False


def resolve(cfg, root: int, rel: str) -> Path:
    """A folder under a root, by names; ValueError for anything that would leave it."""
    rs = roots(cfg)
    if not isinstance(root, int) or not 0 <= root < len(rs):
        raise ValueError("no such root")
    base = Path(rs[root]["path"]).resolve()
    parts = [x for x in str(rel or "").split("/") if x]
    if any(x in (".", "..") or "\x00" in x for x in parts):
        raise ValueError("a folder's names only")
    p = base.joinpath(*parts)
    real = p.resolve()
    if real != base and base not in real.parents:
        raise ValueError("outside the root")
    return real


def browse(cfg, root: int, rel: str) -> dict:
    p = resolve(cfg, root, rel)
    dirs, pdfs, images, other = [], 0, 0, 0
    with os.scandir(p) as it:
        for e in it:
            try:
                if e.is_dir(follow_symlinks=False):
                    dirs.append(e.name)
                elif e.is_file(follow_symlinks=False):
                    n = e.name.lower()
                    if n.endswith(inventory.PDF):
                        pdfs += 1
                    elif n.endswith(inventory.IMAGES):
                        images += 1
                    else:
                        other += 1
            except OSError:
                continue
    dirs.sort(key=str.lower)
    return {"root": root, "path": "/".join(x for x in str(rel or "").split("/") if x), "dirs": dirs[:MAX_LIST],
            "more_dirs": max(0, len(dirs) - MAX_LIST), "pdfs": pdfs, "images": images, "other": other}


def _state_file() -> Path:
    u = archive.who()
    return RUN / (f"ingest-{u}.json" if u and archive.NAME.match(u) else "ingest.json")


def _log_file() -> Path:
    return _state_file().with_suffix(".log")


def _state() -> dict:
    try:
        return json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _alive(pid: int) -> bool:
    for pr in list(_proc):
        if pr.pid == pid:
            if pr.poll() is None:
                return True
            _proc.remove(pr)
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def status() -> dict:
    st = _state()
    if st.get("running") and not _alive(st.get("pid", 0)):
        st["running"] = False
    lines = []
    try:
        lines = [l for l in _log_file().read_text(encoding="utf-8", errors="replace").splitlines()
                 if l.strip() and not l.lstrip().startswith("conflict")][-8:]
    except OSError:
        pass
    return {**{k: st.get(k) for k in ("running", "started", "root", "path", "images", "by")}, "lines": lines}


def start(cfg, root: int, rel: str, images: bool, by: str = "") -> dict:
    """The inventory of that folder, in a process of its own; refused while one runs."""
    if any(_alive(pr.pid) for pr in list(_proc)):       # one inventory at a time on the machine, whoever asked
        raise RuntimeError("a folder is being read already: wait for it to end")
    p = resolve(cfg, root, rel)
    data = archive.folder(cfg)                          # into this user's own archive (R15)
    cmd = [sys.executable, "-I", "-B", str(SCRIPT), "--source", str(p), "--workers", str(WORKERS)] + (["--images"] if images else [])
    log = open(_log_file(), "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                            env={**os.environ, "PYTHONUNBUFFERED": "1", "EVD_DATA_OVERRIDE": str(data)},
                            start_new_session=True)
    log.close()
    _proc[:] = [proc]
    st = {"running": True, "pid": proc.pid, "started": time.time(), "root": root, "path": rel, "images": bool(images),
          "by": by[:64]}
    _state_file().write_text(json.dumps(st), encoding="utf-8")
    return status()


def stop() -> dict:
    st = _state()
    if st.get("running") and _alive(st.get("pid", 0)):
        os.killpg(st["pid"], signal.SIGTERM)
    st["running"] = False
    _state_file().write_text(json.dumps(st), encoding="utf-8")
    return status()
