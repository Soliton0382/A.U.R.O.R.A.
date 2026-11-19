# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📏 A cage's disk measured (prj_run_box's guard, the long runs' DiskWatch): the project's size, every folder and no
link followed, and the files the cage deleted but still holds open or mapped (C662, C700). Only the standard library:
prj_run_box, run as a script in front of bwrap, loads this file by its path."""
from __future__ import annotations

import os
import stat
from pathlib import Path

MAX_ENTRIES = 1_000_000          # a project with more entries than this cannot be measured: stopped
CARRIERS = ("socket:", "anon_inode:[io_uring]")   # descriptors that can keep other files alive, out of sight
PIDFD_GETFD = 438                # the same number on every Linux architecture (the unified table, 5.6+)
PIDFD_THREAD = os.O_EXCL         # pidfd_open's flag for a thread, not its process (6.9+)


class Unmeasurable(OSError):
    """The project's size cannot be measured: a folder of it is unreadable, or it holds too many entries."""


def disk_bytes(root: Path, max_entries: int = MAX_ENTRIES) -> int:
    """The disk the project's files and folders take (blocks, like du), every folder counted and no link followed
    (C627). A folder that cannot be read, or more than max_entries entries, raises Unmeasurable (C645)."""
    total, stack, seen = 0, [str(root)], 0
    while stack:
        top = stack.pop()
        try:
            it = os.scandir(top)
        except FileNotFoundError:
            continue
        except OSError as e:
            raise Unmeasurable(f"{Path(top).name}: cannot be read ({e.strerror})") from None
        with it:
            for e in it:
                seen += 1
                if seen > max_entries:
                    raise Unmeasurable(f"more than {max_entries} entries")
                try:
                    st = e.stat(follow_symlinks=False)
                except FileNotFoundError:            # gone between the listing and the look: nothing to count
                    continue
                except OSError as err:               # C662: a folder r-- (listed, its files not looked at) hid them
                    raise Unmeasurable(f"{Path(e.path).name}: cannot be looked at ({err.strerror})") from None
                if stat.S_ISDIR(st.st_mode):
                    stack.append(e.path)
                    total += st.st_blocks * 512      # C688: a folder of millions of names takes the disk too
                elif stat.S_ISREG(st.st_mode):
                    total += st.st_blocks * 512
    return total


def _children(pid: int) -> list[int] | None:
    """The children of `pid` from /proc/<pid>/task/*/children (a few small reads), None where the kernel has none."""
    try:
        tasks = os.listdir(f"/proc/{pid}/task")
    except OSError:
        return []
    out: list[int] = []
    for t in tasks:
        try:
            out += [int(x) for x in Path(f"/proc/{pid}/task/{t}/children").read_text().split()]
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            continue
    return out


def tree(pid: int, each=None) -> list[int]:
    """`pid` and every process below it, from /proc (`each(p)` called on each as soon as it is found: the hold stops
    a parent before its children are looked for, so it forks no more meanwhile)."""
    out: list[int] = []
    seen, todo = set(), [pid]
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
        if each is not None:
            each(p)
        kids = _children(p)
        if kids is None:
            return _scan_tree(pid, each, seen)
        todo += kids
    return sorted(out)


def _scan_tree(pid: int, each, done: set) -> list[int]:
    """tree() where the kernel has no children files: every /proc/<pid>/stat read."""
    kids: dict[int, list[int]] = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            raw = Path(f"/proc/{d}/stat").read_text()
        except OSError:
            continue
        kids.setdefault(int(raw[raw.rfind(")") + 2:].split()[1]), []).append(int(d))
    out, todo = set(), [pid]
    while todo:
        p = todo.pop()
        if p not in out:
            out.add(p)
            if each is not None and p not in done:
                each(p)
            todo += kids.get(p, [])
    return sorted(out)


def cgroup_procs(cg: Path | None) -> list[int]:
    """The processes of the cage's cgroup and of any cgroup below it (C700: the tree from /proc misses none of them
    there, an orphan reparented away included)."""
    out: list[int] = []
    if cg is None:
        return out
    for f in [Path(cg) / "cgroup.procs", *Path(cg).glob("**/cgroup.procs")]:
        try:
            out += [int(x) for x in f.read_text().split()]
        except (OSError, ValueError):
            continue
    return out


def _getfd(pid: int, fd: int, thread: bool = False) -> int:
    """A copy of `pid`'s descriptor `fd` in this process (pidfd_getfd), -1 where it cannot be had (C710: `thread`, a
    thread's own table: its pidfd opened with PIDFD_THREAD, Linux 6.9+)."""
    import ctypes
    try:
        pfd = os.pidfd_open(pid, PIDFD_THREAD) if thread else os.pidfd_open(pid)
    except (OSError, AttributeError):
        return -1
    try:
        return int(ctypes.CDLL(None, use_errno=True).syscall(PIDFD_GETFD, pfd, fd, 0))
    except (OSError, AttributeError):
        return -1
    finally:
        os.close(pfd)


def carries(pid: int, fd: int, thread: bool = False) -> bool:
    """C707: whether this socket may hold a descriptor in flight (SCM_RIGHTS), the file it names kept out of sight.
    Only a unix socket can: one of another family never; a unix stream socket only with bytes queued, received or
    sent and unread (a descriptor travels with at least one byte: a stream's empty send carries nothing) — asyncio's
    self-pipe, multiprocessing.Pipe, zmq at rest are not carriers; a datagram or seqpacket socket (an empty
    datagram can carry one) or a listening one (its accept queue holds connections) always is. Read on a copy of the
    descriptor (pidfd_getfd: the cage is in a user namespace this account owns), the cage frozen meanwhile; a copy that
    cannot be had (an older kernel, another account): a carrier, as before (C700)."""
    import array
    import fcntl
    import socket
    import termios
    dup = _getfd(pid, fd, thread)
    if dup < 0:
        return True
    try:
        s = socket.socket(fileno=dup)                    # owns the copy from here: closed with it
    except OSError:
        os.close(dup)
        return True
    try:
        if s.family != socket.AF_UNIX:
            return False
        if s.type != socket.SOCK_STREAM or s.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN):
            return True
        n = array.array("i", [0])
        for req in (termios.FIONREAD, termios.TIOCOUTQ):     # unread received / sent and not yet read by its peer
            fcntl.ioctl(s.fileno(), req, n)
            if n[0] > 0:
                return True
        return False
    except OSError:
        return True
    finally:
        s.close()


def _tables(pid: int, unread: set) -> list[tuple[str, int]]:
    """C710: every descriptor table of `pid` as (its /proc folder, the task to copy a descriptor from): the process's
    own and each thread's — a thread that called unshare(CLONE_FILES) has a table /proc/<pid>/fd does not show (measured:
    480 MB held on a 100 MB budget). Threads sharing the process's table list the same descriptors again (counted
    once: by inode, by socket). A task list that cannot be read (not gone) is added to `unread`."""
    out = [(f"/proc/{pid}/fd", pid)]
    try:
        tids = os.listdir(f"/proc/{pid}/task")
    except FileNotFoundError:
        return out
    except OSError:
        unread.add(pid)
        return out
    for t in tids:
        if t.isdigit() and int(t) != pid:
            out.append((f"/proc/{pid}/task/{t}/fd", int(t)))
    return out


def held(pids, root=None) -> tuple[int, int]:
    """(bytes, hidden) of the files the run deleted but still holds — they take the disk and no folder lists them.
    C662: those it holds open (/proc/<pid>/fd: their size read). C700: those it holds mapped with the descriptor
    closed (/proc/<pid>/maps «(deleted)»): /proc/<pid>/map_files, the only way to their size, needs CAP_SYS_ADMIN in
    the first user namespace — so their mapped extents are counted (a lower bound) and `hidden` says how many of them
    lie on the project's filesystem (its device, or a path under `root`); a socket or an io_uring it holds is counted
    in `hidden` too (a descriptor sent with SCM_RIGHTS and closed keeps its file in the socket's queue, seen by no
    /proc file: measured, 480 MB on a 100 MB budget; C707: only a socket that may carry one, see carries). C710: every
    thread's table is read too (_tables), and a process whose table or mappings cannot be read (EACCES: made
    non-dumpable with prctl; anything but «gone») is counted in `hidden` like a carrier. With
    `hidden` the guard counts the free space the disk lost since
    its last measure without any, whole (Guard.check)."""
    total, seen, hidden, extents, carriers, unread, judged = 0, set(), set(), {}, set(), set(), set()
    pids = sorted(set(pids))
    for p in pids:
        for table, tid in _tables(p, unread):
            try:
                fds = os.listdir(table)
            except FileNotFoundError:                    # gone meanwhile: nothing it holds
                continue
            except OSError:                              # C710: unreadable (made non-dumpable): what it holds unseen
                unread.add(tid)
                continue
            for fd in fds:
                try:
                    link = os.readlink(f"{table}/{fd}")
                    if link.startswith(CARRIERS):        # C700: may hold descriptors no /proc file shows
                        if link not in judged:           # a socket judged once, whichever table lists it
                            judged.add(link)
                            if not link.startswith("socket:") or carries(tid, int(fd), tid != p):
                                carriers.add(link)
                        continue
                    if not link.endswith(" (deleted)"):
                        continue
                    st = os.stat(f"{table}/{fd}")
                except FileNotFoundError:
                    continue
                except OSError:                          # C710: a descriptor of it that cannot be looked at
                    unread.add(tid)
                    continue
                key = (os.major(st.st_dev), os.minor(st.st_dev), st.st_ino)
                if stat.S_ISREG(st.st_mode) and key not in seen:
                    seen.add(key)
                    total += st.st_blocks * 512
    dev, prefix = None, ""
    if root is not None:
        try:
            d = os.stat(root).st_dev
            dev, prefix = (os.major(d), os.minor(d)), str(root).rstrip("/") + "/"
        except OSError:
            pass
    for p in pids:
        try:
            with open(f"/proc/{p}/maps", encoding="utf-8", errors="replace") as fh:
                lines = [ln for ln in fh if ln.endswith(" (deleted)\n")]
        except FileNotFoundError:
            continue
        except OSError:                                  # C710: its mappings unreadable (non-dumpable)
            unread.add(p)
            continue
        for ln in lines:
            f = ln.split(None, 5)
            if len(f) < 6:
                continue
            try:
                lo, hi = (int(x, 16) for x in f[0].split("-"))
                off = int(f[2], 16)
                mj, mn = (int(x, 16) for x in f[3].split(":"))
                ino = int(f[4])
            except ValueError:
                continue
            key = (mj, mn, ino)
            if ino == 0 or key in seen:
                continue
            ours = (dev is not None and (mj, mn) == dev) or (prefix and f[5].startswith(prefix))
            if root is not None and not ours:
                continue                                 # memfd, SysV, the cage's RAM disks: its cgroup's memory
            extents.setdefault(key, set()).add((off, off + hi - lo))   # the file's bytes, not the address
            if ours:
                hidden.add(key)
    for spans in extents.values():                       # the union of the file's mapped ranges
        end = 0
        for lo, hi in sorted(spans):
            total += max(0, hi - max(lo, end))
            end = max(end, hi)
    return total, len(hidden) + len(carriers) + len(unread)


def deleted_open_bytes(pids, root=None) -> int:
    """The bytes of held(): the files the run deleted but still holds open or mapped."""
    return held(pids, root)[0]
