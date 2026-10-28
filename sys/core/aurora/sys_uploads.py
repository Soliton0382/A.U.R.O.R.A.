# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Files the owner attached in the chat, kept so that the conversation shows them again after a reload.

Saved in AURORA_UPLOADS_DIR/<yyyy-mm>/<id>-<name> with an index (index.json, 0600 like the files). A file lives as
long as the conversation turn it belongs to (memory turns are never rotated away, only reset), or until the owner
deletes it from the Files page; AURORA_UPLOADS_KEEP_DAYS > 0 also removes it after that many days. Checks and tests
(remember: false) keep nothing.

Served safely: images (but SVG), videos and audio inline; anything else only as a download, never rendered by the
WebUI's origin (an uploaded HTML or SVG must not run there).

Sealed with the user's key (N64): the index (names, turns) and every stored file, bound to its id (the trash may move
it), opened only for its owner by read(); a program that needs a file (pdfinfo, pdftoppm) gets plain_copy(), a copy
in this process's memory folder. Not sealed: Aurora's own pictures and videos (role «assistant»), which the social
plugins publish by file name from their cage, where no key is — but a picture or video a user asked for in their
chat is theirs (private=True: sealed; owner, 29 Oct: «la parte social è solo di aurora, gli utenti non devono
condividere»). A file or index of before reads as it is.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

from . import sys_config, sys_seal

GRACE_S = 3600
INLINE = re.compile(r"^(image/(jpeg|png|webp|gif|bmp|avif)|video/[\w.+-]+|audio/[\w.+-]+)$")


def _dir(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_UPLOADS_DIR")
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def _index(cfg: sys_config.Config) -> list[dict]:
    try:
        return json.loads(sys_seal.read_any(cfg, _dir(cfg) / "index.json", cfg.user))
    except (OSError, ValueError):
        return []


def _write_index(cfg: sys_config.Config, items: list[dict]) -> None:
    sys_seal.write(cfg, _dir(cfg) / "index.json", json.dumps(items, ensure_ascii=False, indent=1).encode("utf-8"),
                   cfg.user, "state")                   # 0600, through a temporary file


def _label(uid: str) -> str:
    return f"upload:{uid}"


def sealed(role: str, mime: str) -> bool:
    """Whether a stored file is sealed: all but Aurora's own pictures and videos (the cage's social plugins post them)."""
    return not (role == "assistant" and str(mime).startswith(("image/", "video/")))


class _Stored(type(Path())):
    """A stored file's path whose read_bytes() gives the plain data (a reader of before calls it on get()'s path)."""
    _open = None

    def read_bytes(self) -> bytes:
        blob = super().read_bytes()
        return self._open(blob) if self._open and sys_seal.is_sealed(blob) else blob


def safe_name(name: str) -> str:
    base = re.sub(r"[^\w.\- ]+", "_", Path(name).name).strip(" .") or "file"
    return base[-120:]


def save(cfg: sys_config.Config, run_id: str, name: str, mime: str, data: bytes, role: str = "user",
         private: bool = False) -> dict:
    uid = uuid.uuid4().hex[:16]
    rel = Path(time.strftime("%Y-%m")) / f"{uid}-{safe_name(name)}"
    path = _dir(cfg) / rel
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    mime = mime or mimetypes.guess_type(name)[0] or "application/octet-stream"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as h:
        h.write(sys_seal.seal(cfg, data, _label(uid), cfg.user, "state") if private or sealed(role, mime) else data)
    item = {"id": uid, "name": Path(name).name[:200], "mime": mime,
            "size": len(data), "run_id": run_id, "created": time.time(), "path": str(rel), "role": role}
    items = _index(cfg)
    items.append(item)
    _write_index(cfg, items)
    return item


def link(cfg: sys_config.Config, run_id: str, name: str, url: str, mime: str, role: str = "assistant") -> dict:
    """A file kept elsewhere (a document Aurora wrote) shown with its turn: only the link is indexed."""
    item = {"id": uuid.uuid4().hex[:16], "name": name[:200], "mime": mime or "application/octet-stream", "size": 0,
            "run_id": run_id, "created": time.time(), "link": url, "role": role}
    items = _index(cfg)
    items.append(item)
    _write_index(cfg, items)
    return item


def public(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("path", "link")} | {"role": item.get("role", "user"),
                                                                         "url": item.get("link") or f"/v1/aurora/uploads/{item['id']}",
                                                             "inline": bool(INLINE.match(item["mime"]))}


def all_uploads(cfg: sys_config.Config) -> list[dict]:
    return [public(i) for i in sorted(_index(cfg), key=lambda i: -i["created"])]


def by_run(cfg: sys_config.Config, run_ids: set[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for i in _index(cfg):
        if i["run_id"] in run_ids:
            out.setdefault(i["run_id"], []).append(public(i))
    return out


def get(cfg: sys_config.Config, uid: str) -> tuple[Path, dict] | None:
    item = next((i for i in _index(cfg) if i["id"] == uid), None)
    if item is None or "path" not in item:            # a link is served by its own endpoint
        return None
    path = (_dir(cfg) / item["path"]).resolve()
    if _dir(cfg).resolve() not in path.parents or not path.is_file():
        return None
    p = _Stored(path)
    p._open = lambda blob, u=item["id"]: sys_seal.unseal(cfg, blob, _label(u), cfg.user, "state")
    return p, item


def read(cfg: sys_config.Config, uid: str) -> tuple[bytes, dict] | None:
    """A stored file's plain data and its line, for its owner only (ValueError: not this user's, or changed)."""
    found = get(cfg, uid)
    return (found[0].read_bytes(), found[1]) if found else None


def plain_copy(cfg: sys_config.Config, uid: str) -> Path | None:
    """A file for a program that reads paths (pdfinfo, pdftoppm): the stored file itself when never sealed, else a
    copy opened into this process's memory folder (/dev/shm, 0700; the system's temporary folder without one), made
    once per file and process — never beside the sealed one."""
    found = get(cfg, uid)
    if not found:
        return None
    path, item = found
    with open(path, "rb") as f:
        if f.read(len(sys_seal.MAGIC)) != sys_seal.MAGIC:
            return path
    out = memory_dir() / f"{item['id']}-{path.name}"
    if not out.is_file():
        tmp = out.with_name(out.name + f".{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as h:
            h.write(path.read_bytes())
        os.replace(tmp, out)
    return out


def memory_dir() -> Path:
    """This process's folder for opened copies (plain_copy) and what is drawn from them (doc_preview's pages)."""
    base = Path("/dev/shm") if Path("/dev/shm").is_dir() and os.access("/dev/shm", os.W_OK) else Path(tempfile.gettempdir())
    import getpass                                    # every system has it (os.getuid: not on Windows)
    d = base / f"aurora-{getpass.getuser()}-{os.getpid()}" / "uploads"
    if not d.is_dir():
        import atexit
        import shutil
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(d.parent, 0o700)
        atexit.register(shutil.rmtree, d.parent, True)  # the opened copies end with the process
    return d


def delete(cfg: sys_config.Config, uid: str) -> bool:
    """The owner's delete: the file goes to the trash (sys_trash), its line kept there to take it back."""
    from . import sys_trash
    items = _index(cfg)
    keep = [i for i in items if i["id"] != uid]
    for i in items:
        if i["id"] == uid and "path" in i and (_dir(cfg) / i["path"]).is_file():
            sys_trash.discard(cfg, _dir(cfg) / i["path"], "upload", i["name"], record=i)
        elif i["id"] == uid and str(i.get("url", "")).startswith("/v1/aurora/documents/"):
            # a PDF Aurora wrote, shown with its turn: the 🗑️ sends the document itself to the trash (6 October: only
            # the link went, the file stayed) — never one the owner put in the folder himself
            from . import doc_pdf
            f = cfg.path("AURORA_DOCUMENTS_DIR") / str(i["url"]).rsplit("/", 1)[-1]
            if f.is_file() and doc_pdf.made_by_aurora(f):
                sys_trash.discard(cfg, f, "document", i["name"])
    _write_index(cfg, keep)
    return len(keep) != len(items)


def reindex(cfg: sys_config.Config, record: dict, path: Path) -> None:
    """An upload back from the trash: its line again (at the path it came back to)."""
    items = [i for i in _index(cfg) if i["id"] != record["id"]]
    items.append({**record, "path": str(path.relative_to(_dir(cfg)))})
    _write_index(cfg, items)


def purge(cfg: sys_config.Config, live_runs: set[str] | None, now: float | None = None, grace: float = GRACE_S) -> list[str]:
    """Remove the files whose conversation turn is gone (live_runs: the run ids still in memory; None = do not check)
    and, with AURORA_UPLOADS_KEEP_DAYS > 0, the older ones. Returns the removed ids."""
    now = now or time.time()
    days = cfg["AURORA_UPLOADS_KEEP_DAYS"]
    # a file is saved when the question arrives, its turn only when the answer is written: an hour of grace
    gone = [i for i in _index(cfg)
            if (live_runs is not None and i["run_id"] not in live_runs and now - i["created"] > grace)
            or (days > 0 and now - i["created"] > days * 86400)]
    for i in gone:
        delete(cfg, i["id"])
    return [i["id"] for i in gone]


def total_bytes(cfg: sys_config.Config) -> int:
    return sum(i["size"] for i in _index(cfg))
