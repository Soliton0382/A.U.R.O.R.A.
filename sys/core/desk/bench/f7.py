# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""F7: SO_PEERPIDFD (77) and the PID of the unreaped child, kernel 7.0, without root.

The phase-1 verifier runs as root; here the «parent» is a test process of the owner's uid (declared difference).
    server   : the parent P. Listens on a unix socket in the bench runtime dir, spawns its child C (posix_spawn:
               nothing reaps it behind our back), checks every peer: SO_PEERCRED pid == C, and the pidfd from
               getsockopt(SOL_SOCKET, 77) has the same pidfs inode as pidfd_open(C). Then 100 cycles of
               «child dead, not reaped»: a stranger forks and tries clone3(set_tid = that PID).
    child    : C. N connections labelled «child»; M connections handed to a forked grandchild that writes «grand».
    stranger : same uid, not a descendant of P: N connections labelled «stranger»; in «reuse» mode it tries to obtain
               a given PID (fork K times, clone3 with set_tid) and connects once.
The label each client writes is the oracle of who really sent the bytes (the programs are ours).
"""
import ctypes
import json
import os
import socket
import struct
import sys
import time

SO_PEERPIDFD = 77                                     # asm-generic/socket.h:136; the system Python has no constant
SYS_CLONE3 = 435
HERE = os.path.abspath(__file__)


def peer(conn: socket.socket) -> dict:
    pid, uid, gid = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    out = {"pid": pid, "uid": uid, "pidfd_ino": None, "pidfd_err": None}
    try:
        raw = conn.getsockopt(socket.SOL_SOCKET, SO_PEERPIDFD, 4)
        fd = int.from_bytes(raw, "little", signed=True)
        try:
            out["pidfd_ino"] = os.fstat(fd).st_ino
        finally:
            os.close(fd)
    except OSError as e:
        out["pidfd_err"] = e.errno
    return out


def spawn(args: list) -> int:
    return os.posix_spawn(sys.executable, [sys.executable, "-I", "-B", HERE] + args, {"PATH": "/usr/bin:/bin"})


def server(sock_path: str, out_path: str, n_child: int, n_grand: int, n_stranger: int, cycles: int,
           stranger_ready: str) -> int:
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
    srv.bind(sock_path)
    srv.listen(64)
    cpid = spawn(["child", sock_path, str(n_child), str(n_grand)])
    cfd = os.pidfd_open(cpid)
    c_ino = os.fstat(cfd).st_ino
    open(stranger_ready, "w").write(str(os.getpid()))   # the harness starts the stranger now
    want = n_child + n_grand + n_stranger
    conns = []
    srv.settimeout(60)
    while len(conns) < want:
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            break
        with conn:
            p = peer(conn)
            conn.settimeout(10)
            label = b""
            try:
                while not label.endswith(b"\n"):
                    chunk = conn.recv(64)
                    if not chunk:
                        break
                    label += chunk
            except socket.timeout:
                pass
            p["label"] = label.decode(errors="replace").strip()
            p["by_pid"] = p["pid"] == cpid
            p["by_pidfd"] = p["pidfd_ino"] == c_ino
            conns.append(p)
    os.waitpid(cpid, 0)
    os.close(cfd)
    # child dead, not reaped: does anyone else get its PID?
    zres = []
    for i in range(cycles):
        zpid = spawn(["exit"])
        zfd = os.pidfd_open(zpid)                      # works on a zombie too: it is not reaped yet
        z_ino = os.fstat(zfd).st_ino
        t0 = time.monotonic()
        state = "?"
        while time.monotonic() - t0 < 5:
            try:
                state = open(f"/proc/{zpid}/stat").read().rsplit(")", 1)[1].split()[0]
            except OSError:
                state = "gone"
            if state == "Z":
                break
            time.sleep(0.005)
        rp = spawn(["reuse", sock_path, str(zpid), out_path + f".reuse{i}"])
        conn, _ = srv.accept()
        with conn:
            p = peer(conn)
        os.waitpid(rp, 0)
        try:
            r = json.load(open(out_path + f".reuse{i}"))
        except (OSError, ValueError):
            r = {"error": "no reuse report"}
        zres.append({"zpid": zpid, "state": state, "peer_pid": p["pid"], "peer_is_zombie_pid": p["pid"] == zpid,
                     "peer_pidfd_is_zombie": p["pidfd_ino"] == z_ino, "reuse": r})
        os.waitpid(zpid, 0)                            # now reaped
        os.close(zfd)
    srv.close()
    os.unlink(sock_path)
    json.dump({"child_pid": cpid, "conns": conns, "zombies": zres}, open(out_path, "w"))
    return 0


def _connect_send(sock_path: str, label: bytes) -> None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
    s.connect(sock_path)
    s.sendall(label + b"\n")
    s.close()


def child(sock_path: str, n: int, m: int) -> int:
    for _ in range(n):
        _connect_send(sock_path, b"child")
    for _ in range(m):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)   # no CLOEXEC needed: fork without exec
        s.connect(sock_path)
        g = os.fork()
        if g == 0:
            try:
                s.sendall(b"grand\n")
            finally:
                os._exit(0)
        s.close()
        os.waitpid(g, 0)
    return 0


def stranger(sock_path: str, n: int) -> int:
    for _ in range(n):
        _connect_send(sock_path, b"stranger")
    return 0


class CloneArgs(ctypes.Structure):
    _fields_ = [(f, ctypes.c_uint64) for f in ("flags", "pidfd", "child_tid", "parent_tid", "exit_signal", "stack",
                                               "stack_size", "tls", "set_tid", "set_tid_size", "cgroup")]


def reuse(sock_path: str, target: int, out_path: str, forks: int = 200) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    tid = (ctypes.c_int * 1)(target)
    args = CloneArgs(exit_signal=17, set_tid=ctypes.addressof(tid), set_tid_size=1)
    r = libc.syscall(SYS_CLONE3, ctypes.byref(args), ctypes.sizeof(args))
    if r == 0:
        os._exit(0)                                    # we are a child that got the PID: leave at once
    clone_errno = ctypes.get_errno() if r < 0 else 0
    got = []
    for _ in range(forks):
        p = os.fork()
        if p == 0:
            os._exit(0)
        got.append(p)
        os.waitpid(p, 0)
    _connect_send(sock_path, b"reuse")
    json.dump({"clone3_rc": r, "clone3_errno": clone_errno, "clone3_got_target": r == target,
               "forks": forks, "fork_got_target": target in got}, open(out_path, "w"))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "server":
        sys.exit(server(a[1], a[2], int(a[3]), int(a[4]), int(a[5]), int(a[6]), a[7]))
    if a[0] == "child":
        sys.exit(child(a[1], int(a[2]), int(a[3])))
    if a[0] == "stranger":
        sys.exit(stranger(a[1], int(a[2])))
    if a[0] == "reuse":
        sys.exit(reuse(a[1], int(a[2]), a[3]))
    if a[0] == "exit":
        sys.exit(0)
