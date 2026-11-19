# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📂 A project's files opened from Aurora's side without ever following a link (C625, C643).

Every path is walked from the project's folder one component at a time with openat(O_NOFOLLOW): a component that is
a link, «..» or a device fails, and nothing is resolved first and opened later by name. That closes the
check-then-open race (C643, third review, 20 Nov: a long run swapped a folder of its project with a link to the host
with renameat2 RENAME_EXCHANGE between Aurora's check and Aurora's open; 24,399 writes of 51,313 landed outside).
Files are opened non-blocking and must be regular files (a pipe planted under a name hung the caller: C644).

Systems without dir_fd (Windows) fall back to a lexical check of the path (no cage runs there, so no writer races).
"""
from __future__ import annotations

import errno
import hashlib
import os
import stat
from pathlib import Path

_FD = os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW")
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIR = getattr(os, "O_DIRECTORY", 0)


def _relative(rel: str, root: Path | str | None) -> str:
    """C663: an absolute path is the project's only when it is lexically inside its folder (the prefix taken off);
    any other absolute path is refused — it was made relative and written inside the project («/etc/x» → etc/x)."""
    s = str(rel).replace("\\", "/")
    if not s.startswith("/") and not (len(s) > 1 and s[1] == ":"):
        return s
    if root is None:
        raise ValueError(f"{rel!r}: a path relative to the project")
    base = os.path.normpath(str(root)).replace("\\", "/").rstrip("/")
    full = os.path.normpath(s).replace("\\", "/")
    if full == base:
        return "."
    if not full.startswith(base + "/"):
        raise ValueError(f"{rel!r}: outside the project")
    return full[len(base) + 1:]


def parts(rel: str, root: Path | str | None = None) -> list[str]:
    """The components of a project path: no «..», no empty name, no newline or NUL; ValueError otherwise. An absolute
    path: see _relative (C663)."""
    rel = _relative(rel, root)
    ps = [p for p in str(rel).replace("\\", "/").split("/") if p not in ("", ".")]
    if not ps or any(p == ".." for p in ps) or any(c in p for p in ps for c in "\n\r\0"):
        raise ValueError(f"{rel!r}: a plain path inside the project")
    return ps


def norm(rel: str, root: Path | str | None = None) -> str:
    """The project path as the project sees it, lexically ('.' for the folder itself); `root`: the project's folder,
    for an absolute path inside it (C663)."""
    rel = _relative(rel, root)
    try:
        return "/".join(parts(rel))
    except ValueError:
        if str(rel).strip().replace("\\", "/").strip("/.") == "":
            return "."
        raise


def _dir_fd(root: Path, ps: list[str], mkdirs: bool) -> int:
    fd = os.open(str(root), os.O_RDONLY | _DIR | _CLOEXEC)
    try:
        for p in ps:
            try:
                nfd = os.open(p, os.O_RDONLY | _DIR | _NOFOLLOW | _CLOEXEC, dir_fd=fd)
            except FileNotFoundError:
                if not mkdirs:
                    raise
                os.mkdir(p, 0o755, dir_fd=fd)
                nfd = os.open(p, os.O_RDONLY | _DIR | _NOFOLLOW | _CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = nfd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _lexical(root: Path, rel: str) -> Path:
    p = (Path(root) / norm(rel, root)).resolve()
    r = Path(root).resolve()
    if p != r and r not in p.parents:
        raise ValueError(f"{rel}: outside the project")
    return p


def open_in(root: Path, rel: str, flags: int, mode: int = 0o644, mkdirs: bool = False) -> int:
    """A file descriptor for root/rel opened step by step, no component a link. OSError when a link is met."""
    ps = parts(rel, root)
    if not _FD:
        return os.open(str(_lexical(root, rel)), flags, mode)
    fd = _dir_fd(root, ps[:-1], mkdirs)
    try:
        return os.open(ps[-1], flags | _NOFOLLOW | _CLOEXEC, mode, dir_fd=fd)
    finally:
        os.close(fd)


def _regular(fd: int, rel: str) -> None:
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError(f"{rel}: not a regular file")


def read_bytes(root: Path, rel: str, limit: int | None = None) -> bytes:
    """The bytes of a regular file of the project (at most `limit`); ValueError for a link, a pipe, a folder."""
    try:
        fd = open_in(root, rel, os.O_RDONLY | _NONBLOCK)
    except OSError as e:
        raise ValueError(f"{rel}: not a readable plain file of the project ({errno.errorcode.get(e.errno, e.errno)})") from None
    _regular(fd, rel)
    with os.fdopen(fd, "rb") as fh:
        return fh.read() if limit is None else fh.read(limit)


def read_text(root: Path, rel: str) -> str:
    return read_bytes(root, rel).decode("utf-8", errors="replace")


def write_bytes(root: Path, rel: str, data: bytes, append: bool = False) -> None:
    """Create or replace (or append to) a regular file of the project, never through a link, the folders on the way
    created as folders. ValueError when the target is a link, a pipe or a folder."""
    flags = os.O_WRONLY | os.O_CREAT | _NONBLOCK | (os.O_APPEND if append else 0)
    try:
        fd = open_in(root, rel, flags, 0o644, mkdirs=True)
    except OSError as e:
        raise ValueError(f"{rel}: not a writable plain file of the project ({errno.errorcode.get(e.errno, e.errno)})") from None
    _regular(fd, rel)
    if not append:
        os.ftruncate(fd, 0)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def write_text(root: Path, rel: str, text: str, append: bool = False) -> None:
    write_bytes(root, rel, text.encode("utf-8"), append=append)


def is_file(root: Path, rel: str) -> bool:
    try:
        fd = open_in(root, rel, os.O_RDONLY | _NONBLOCK)
    except (OSError, ValueError):
        return False
    try:
        return stat.S_ISREG(os.fstat(fd).st_mode)
    finally:
        os.close(fd)


def walk(root: Path, rel: str = ".", skip: frozenset = frozenset(), limit: int = 10000):
    """(path, is_dir, size) of what is under root/rel, sorted, links listed as themselves and never entered."""
    base = norm(rel, root)
    if not _FD:
        top = _lexical(root, base)
        out = []
        for p in sorted(top.rglob("*")):
            r = p.relative_to(Path(root).resolve())
            if skip & set(r.parts):
                continue
            out.append((r.as_posix(), p.is_dir() and not p.is_symlink(), p.lstat().st_size))
            if len(out) >= limit:
                break
        return out
    out: list[tuple[str, bool, int]] = []

    def rec(fd: int, prefix: str) -> None:
        with os.scandir(fd) as it:
            ents = sorted(it, key=lambda e: e.name)
        for e in ents:
            if len(out) >= limit:
                return
            if e.name in skip:
                continue
            path = f"{prefix}{e.name}" if prefix else e.name
            st = e.stat(follow_symlinks=False)
            d = stat.S_ISDIR(st.st_mode)
            out.append((path, d, st.st_size))
            if d:
                try:
                    nfd = os.open(e.name, os.O_RDONLY | _DIR | _NOFOLLOW | _CLOEXEC, dir_fd=fd)
                except OSError:
                    continue
                try:
                    rec(nfd, path + "/")
                finally:
                    os.close(nfd)

    fd = _dir_fd(root, [] if base == "." else parts(base), False)
    try:
        rec(fd, "" if base == "." else base + "/")
    finally:
        os.close(fd)
    return out


def read_small(root: Path, rel: str, limit: int) -> str:
    """At most `limit` bytes of a regular file of the project ('' when it is missing, a link, a pipe or a folder)."""
    try:
        return read_bytes(root, rel, limit).decode("utf-8", errors="replace")
    except ValueError:
        return ""


def sha_in(root: Path, rel: str) -> str:
    """The SHA-256 of a regular file of the project, opened without links; ValueError when it is not one."""
    try:
        fd = open_in(root, rel, os.O_RDONLY | _NONBLOCK)
    except OSError as e:
        raise ValueError(f"{rel}: not a plain file of the project ({errno.errorcode.get(e.errno, e.errno)})") from None
    _regular(fd, rel)
    with os.fdopen(fd, "rb") as fh:
        h = hashlib.sha256()
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
        return h.hexdigest()


def write_new(root: Path, rel: str, data: bytes) -> str:
    """root/rel created exclusively, never through a link (C625); a name taken gives rel with .2, .3… before the
    suffix. The path written."""
    stem, dot, suf = rel.rpartition(".")
    for n in range(1, 100):
        cand = rel if n == 1 else f"{stem}.{n}{dot}{suf}" if dot else f"{rel}.{n}"
        try:
            fd = open_in(root, cand, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NONBLOCK, 0o644, mkdirs=True)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return cand
    raise ValueError(f"{rel}: no free name")


def create_exclusive(root: Path, rel: str) -> None:
    """An empty regular file made exclusively, never through a link nor on a pipe (C644: a FIFO planted under the
    next run's .keep hung start() under the global lock)."""
    fd = open_in(root, rel, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NONBLOCK, 0o644, mkdirs=True)
    _regular(fd, rel)
    os.close(fd)
